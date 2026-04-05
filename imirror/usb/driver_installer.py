"""
WinUSB Driver Auto-Installer for iPhone AV Interface.

Automates what Zadig does manually — installs the WinUSB driver for the
iPhone so libusb can access it for Valeria protocol communication.

This is the "mirror driver" equivalent of what AnyMiro installs on first run.
After installation, IMIRROR4FREE can send the USB control transfer to enable
QT Configuration 5 (Valeria AV streaming) and communicate with the
H.264 video + PCM audio endpoints.

Architecture:
    1. Detect iPhone PID on USB bus (pyusb or Windows WMI fallback)
    2. Generate a WinUSB INF file targeting the specific iPhone
    3. Create self-signed certificate for driver signing
    4. Install via pnputil (with UAC elevation if needed)
    5. User unplugs and replugs iPhone → WinUSB loads
    6. libusb can now access the device → Valeria streaming works

Trade-off:
    While our WinUSB driver is installed, Apple's original driver is replaced.
    iTunes/Apple Music won't detect the iPhone. We provide an uninstall method
    to restore the original Apple driver when the user wants.

Requirements:
    - Windows 10 or later
    - Administrator privileges (UAC prompt shown automatically)
    - iPhone connected via USB
"""

import ctypes
import logging
import os
import platform
import re
import shutil
import subprocess
import sys
import tempfile
import uuid
from pathlib import Path
from typing import Optional, Tuple

logger = logging.getLogger(__name__)

APPLE_VID = 0x05AC

# Persistent driver directory (survives app restarts)
DRIVER_DIR_NAME = "imirror_driver"


class DriverInstallResult:
    """Result of a driver installation attempt."""

    def __init__(self, success: bool, message: str, needs_replug: bool = False):
        self.success = success
        self.message = message
        self.needs_replug = needs_replug

    def __repr__(self):
        status = "[OK]" if self.success else "[FAIL]"
        return f"{status} {self.message}"


class DriverStatus:
    """Current status of the WinUSB mirror driver."""

    def __init__(self):
        self.installed = False
        self.inf_path: Optional[str] = None
        self.oem_inf_name: Optional[str] = None  # e.g., "oem42.inf"
        self.iphone_detected = False
        self.libusb_accessible = False
        self.qt_config_active = False
        self.device_pid: Optional[int] = None

    @property
    def ready_to_stream(self) -> bool:
        """Whether everything is ready for Valeria streaming."""
        return self.iphone_detected and self.libusb_accessible

    @property
    def needs_driver(self) -> bool:
        """Whether driver installation is needed."""
        return self.iphone_detected and not self.libusb_accessible and not self.installed

    def summary(self) -> str:
        lines = [
            f"  iPhone detected:   {'[OK]' if self.iphone_detected else '[FAIL]'}",
            f"  Driver installed:  {'[OK]' if self.installed else '[FAIL]'}",
            f"  libusb accessible: {'[OK]' if self.libusb_accessible else '[FAIL]'}",
            f"  QT config active:  {'[OK]' if self.qt_config_active else '[-]'}",
        ]
        return "\n".join(lines)


# ─── Utility functions ──────────────────────────────────────────────


def is_windows() -> bool:
    """Check if running on Windows."""
    return platform.system() == "Windows"


def is_admin() -> bool:
    """Check if the current process has administrator privileges."""
    if not is_windows():
        return os.geteuid() == 0
    try:
        return ctypes.windll.shell32.IsUserAnAdmin() != 0
    except Exception:
        return False


def get_driver_dir() -> str:
    """Get the persistent directory for driver files.

    Uses the app's data directory so driver files survive updates.
    Falls back to a temp directory if needed.
    """
    # Try app data directory first
    appdata = os.environ.get("LOCALAPPDATA", "")
    if appdata:
        driver_dir = os.path.join(appdata, "IMIRROR4FREE", DRIVER_DIR_NAME)
    else:
        driver_dir = os.path.join(tempfile.gettempdir(), DRIVER_DIR_NAME)

    os.makedirs(driver_dir, exist_ok=True)
    return driver_dir


# ─── iPhone detection ───────────────────────────────────────────────


def detect_iphone_pid() -> Optional[int]:
    """Detect the connected iPhone's Product ID.

    Tries multiple methods:
    1. pyusb with libusb (best, but may fail without WinUSB)
    2. Windows WMI/PowerShell (works regardless of driver)

    Returns:
        The iPhone's USB Product ID, or None if not found.
    """
    # Method 1: pyusb
    pid = _detect_pid_pyusb()
    if pid:
        return pid

    # Method 2: Windows WMI
    if is_windows():
        pid = _detect_pid_wmi()
        if pid:
            return pid

    return None


def _detect_pid_pyusb() -> Optional[int]:
    """Detect iPhone PID via pyusb (requires libusb backend)."""
    try:
        import usb.core

        backend = None
        if is_windows():
            try:
                import libusb_package
                backend = libusb_package.get_libusb1_backend()
            except ImportError:
                pass

        if not backend:
            try:
                import usb.backend.libusb1
                backend = usb.backend.libusb1.get_backend()
            except Exception:
                pass

        kwargs = {"idVendor": APPLE_VID, "find_all": True}
        if backend:
            kwargs["backend"] = backend

        devices = list(usb.core.find(**kwargs))
        if devices:
            pid = devices[0].idProduct
            logger.info("Detected iPhone PID via pyusb: 0x%04X", pid)
            return pid

    except Exception as e:
        logger.debug("pyusb detection failed: %s", e)

    return None


def _detect_pid_wmi() -> Optional[int]:
    """Detect iPhone PID via Windows WMI (works without libusb/WinUSB)."""
    try:
        result = subprocess.run(
            [
                "powershell", "-NoProfile", "-Command",
                "Get-PnpDevice -Class USB -Status OK | "
                "Where-Object { $_.InstanceId -like '*VID_05AC*' } | "
                "Select-Object -ExpandProperty InstanceId"
            ],
            capture_output=True, text=True, timeout=15,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )

        for line in result.stdout.strip().split("\n"):
            line = line.strip()
            if "VID_05AC" in line:
                match = re.search(r"PID_([0-9A-Fa-f]{4})", line)
                if match:
                    pid = int(match.group(1), 16)
                    logger.info("Detected iPhone PID via WMI: 0x%04X", pid)
                    return pid

    except Exception as e:
        logger.debug("WMI detection failed: %s", e)

    return None


def detect_iphone_hwids() -> list[str]:
    """Detect all Apple USB hardware IDs currently on the system.

    Returns a list of hardware IDs like 'USB\\VID_05AC&PID_12A8'.
    Used to generate INF files that match the specific iPhone model.
    """
    hwids = []

    if not is_windows():
        return hwids

    try:
        result = subprocess.run(
            [
                "powershell", "-NoProfile", "-Command",
                "Get-PnpDevice -Class USB -Status OK | "
                "Where-Object { $_.InstanceId -like '*VID_05AC*' } | "
                "ForEach-Object { Get-PnpDeviceProperty -InstanceId $_.InstanceId "
                "-KeyName DEVPKEY_Device_HardwareIds | "
                "Select-Object -ExpandProperty Data }"
            ],
            capture_output=True, text=True, timeout=15,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )

        for line in result.stdout.strip().split("\n"):
            line = line.strip()
            if line and "VID_05AC" in line:
                hwids.append(line)

    except Exception as e:
        logger.debug("Hardware ID detection failed: %s", e)

    return hwids


# ─── INF generation ─────────────────────────────────────────────────


def generate_winusb_inf(
    pid: int,
    output_dir: Optional[str] = None,
) -> str:
    """Generate a WinUSB INF file for the iPhone.

    Creates an INF that tells Windows to use the WinUSB driver for
    the specific iPhone model. This replaces Apple's driver and gives
    libusb access for Valeria protocol communication.

    Args:
        pid: iPhone USB Product ID (e.g., 0x12A8).
        output_dir: Directory for output files (uses driver dir if None).

    Returns:
        Path to the generated INF file.
    """
    if output_dir is None:
        output_dir = get_driver_dir()

    os.makedirs(output_dir, exist_ok=True)

    device_guid = "{" + str(uuid.uuid4()).upper() + "}"

    # Primary hardware ID — matches the specific iPhone model
    hw_id_specific = f"USB\\VID_{APPLE_VID:04X}&PID_{pid:04X}"

    # Secondary — matches any Apple USB device (broader fallback)
    hw_id_vendor = f"USB\\VID_{APPLE_VID:04X}"

    inf_content = f"""; ═══════════════════════════════════════════════════════════════
; IMIRROR4FREE Mirror Driver — WinUSB for iPhone AV Streaming
; ═══════════════════════════════════════════════════════════════
;
; This driver enables USB screen mirroring from iPhone to PC.
; It replaces Apple's driver with WinUSB so that IMIRROR4FREE
; can send the QuickTime AV configuration request and receive
; H.264 video + PCM audio over USB bulk endpoints.
;
; To restore Apple's original driver:
;   1. Open Device Manager
;   2. Right-click your iPhone → Update Driver
;   3. Browse → Let me pick → Apple Mobile Device USB Driver
;   Or use IMIRROR4FREE's "Restore Original Driver" option.
;
; Auto-generated by IMIRROR4FREE

[Version]
Signature   = "$Windows NT$"
Class       = USBDevice
ClassGUID   = {{88BAE032-5A81-49f0-BC3D-A4FF138216D6}}
Provider    = %ProviderName%
CatalogFile = imirror_mirror.cat
DriverVer   = 04/05/2026,2.0.0.0

; ─── Manufacturer ────────────────────────────────────────────

[Manufacturer]
%MfgName% = DeviceList,NTamd64,NTx86,NTarm64

[DeviceList.NTamd64]
%DeviceName% = USB_Install, {hw_id_specific}
%DeviceNameGeneric% = USB_Install, {hw_id_vendor}

[DeviceList.NTx86]
%DeviceName% = USB_Install, {hw_id_specific}
%DeviceNameGeneric% = USB_Install, {hw_id_vendor}

[DeviceList.NTarm64]
%DeviceName% = USB_Install, {hw_id_specific}
%DeviceNameGeneric% = USB_Install, {hw_id_vendor}

; ─── Installation ────────────────────────────────────────────

[USB_Install]
Include = winusb.inf
Needs   = WINUSB.NT

[USB_Install.Services]
Include = winusb.inf
Needs   = WINUSB.NT.Services

[USB_Install.HW]
AddReg = Dev_AddReg

[Dev_AddReg]
HKR,,DeviceInterfaceGUIDs,0x10000,"{device_guid}"

; ─── Strings ─────────────────────────────────────────────────

[Strings]
ProviderName     = "IMIRROR4FREE"
MfgName          = "Apple Inc."
DeviceName       = "iPhone Mirror Interface (IMIRROR4FREE)"
DeviceNameGeneric = "Apple Device Mirror Interface (IMIRROR4FREE)"
"""

    inf_path = os.path.join(output_dir, "imirror_mirror.inf")
    with open(inf_path, "w", encoding="utf-8") as f:
        f.write(inf_content)

    logger.info("Generated WinUSB INF at: %s", inf_path)
    logger.info("  Hardware ID: %s", hw_id_specific)

    return inf_path


# ─── Certificate & signing ──────────────────────────────────────────


def create_certificate_and_sign(inf_path: str) -> bool:
    """Create a self-signed certificate and sign the driver catalog.

    Windows 10/11 x64 requires signed drivers. We create a self-signed
    certificate, add it to the Trusted Root and Trusted Publishers stores,
    then sign the catalog file.

    This is the same approach Zadig uses for driver installation.

    Args:
        inf_path: Path to the INF file.

    Returns:
        True if signing succeeded.
    """
    output_dir = os.path.dirname(inf_path)
    cat_path = os.path.join(output_dir, "imirror_mirror.cat")
    cert_name = "IMIRROR4FREE Mirror Driver"

    try:
        # Step 1: Create self-signed code signing certificate
        ps_create_cert = f"""
$ErrorActionPreference = 'Stop'

# Remove any old IMIRROR4FREE certs
Get-ChildItem Cert:\\\\CurrentUser\\\\My | Where-Object {{ $_.Subject -eq 'CN={cert_name}' }} | Remove-Item -Force

# Create new self-signed code signing cert
$cert = New-SelfSignedCertificate `
    -Type CodeSigningCert `
    -Subject "CN={cert_name}" `
    -CertStoreLocation "Cert:\\\\CurrentUser\\\\My" `
    -NotAfter (Get-Date).AddYears(10) `
    -HashAlgorithm SHA256

# Add to Trusted Root CA (so Windows trusts it)
$rootStore = New-Object System.Security.Cryptography.X509Certificates.X509Store("Root", "LocalMachine")
$rootStore.Open("ReadWrite")
$rootStore.Add($cert)
$rootStore.Close()

# Add to Trusted Publishers (so driver signing is trusted)
$pubStore = New-Object System.Security.Cryptography.X509Certificates.X509Store("TrustedPublisher", "LocalMachine")
$pubStore.Open("ReadWrite")
$pubStore.Add($cert)
$pubStore.Close()

# Output the cert thumbprint
$cert.Thumbprint
"""
        result = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
             "-Command", ps_create_cert],
            capture_output=True, text=True, timeout=30,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )

        if result.returncode != 0:
            logger.warning("Certificate creation failed: %s", result.stderr.strip())
            return False

        thumbprint = result.stdout.strip().split("\n")[-1].strip()
        logger.info("Created self-signed certificate: %s", thumbprint)

        # Step 2: Create catalog file using MakeCat or inf2cat
        # If inf2cat is available (from WDK), use it
        inf2cat = shutil.which("inf2cat")
        if inf2cat:
            try:
                subprocess.run(
                    [inf2cat, f"/driver:{output_dir}",
                     "/os:10_X64,10_X86,10_ARM64"],
                    check=True, capture_output=True, text=True, timeout=30,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
                logger.info("Created catalog via inf2cat")
            except Exception as e:
                logger.debug("inf2cat failed (will create minimal cat): %s", e)

        # Create minimal .cat file if inf2cat didn't work
        if not os.path.exists(cat_path):
            # Write an empty catalog — signtool can still sign it
            with open(cat_path, "wb") as f:
                f.write(b"")

        # Step 3: Sign catalog with signtool
        signtool = _find_signtool()
        if signtool:
            try:
                subprocess.run(
                    [signtool, "sign", "/fd", "SHA256",
                     "/sha1", thumbprint,
                     "/tr", "http://timestamp.digicert.com",
                     "/td", "SHA256",
                     cat_path],
                    check=True, capture_output=True, text=True, timeout=30,
                    creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
                )
                logger.info("Catalog signed with signtool")
                return True
            except Exception as e:
                logger.debug("signtool signing failed: %s", e)

        # Step 4: Try PowerShell signing as fallback
        ps_sign = f"""
$cert = Get-ChildItem Cert:\\\\CurrentUser\\\\My | Where-Object {{ $_.Thumbprint -eq '{thumbprint}' }}
Set-AuthenticodeSignature -FilePath '{cat_path}' -Certificate $cert -HashAlgorithm SHA256
"""
        result = subprocess.run(
            ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass",
             "-Command", ps_sign],
            capture_output=True, text=True, timeout=30,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )

        if result.returncode == 0:
            logger.info("Catalog signed with PowerShell")
            return True

        logger.warning("Could not sign catalog — driver may need test signing mode")
        return False

    except Exception as e:
        logger.warning("Certificate/signing failed: %s", e)
        return False


def _find_signtool() -> Optional[str]:
    """Find signtool.exe from Windows SDK."""
    signtool = shutil.which("signtool")
    if signtool:
        return signtool

    # Search common Windows SDK paths
    program_files = os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)")
    sdk_base = os.path.join(program_files, "Windows Kits", "10", "bin")

    if os.path.exists(sdk_base):
        # Find the latest SDK version
        versions = sorted(
            [d for d in os.listdir(sdk_base) if d.startswith("10.")],
            reverse=True
        )
        for ver in versions:
            for arch in ["x64", "x86", "arm64"]:
                path = os.path.join(sdk_base, ver, arch, "signtool.exe")
                if os.path.exists(path):
                    return path

    return None


# ─── Driver installation ────────────────────────────────────────────


def install_driver(inf_path: Optional[str] = None, pid: Optional[int] = None) -> DriverInstallResult:
    """Install the WinUSB mirror driver.

    This is the main installation entry point. It handles:
    1. Auto-detecting the iPhone if PID not provided
    2. Generating the INF if path not provided
    3. Creating and installing the self-signed certificate
    4. Installing the driver via pnputil
    5. Requesting UAC elevation if needed

    Args:
        inf_path: Path to pre-generated INF (auto-generates if None).
        pid: iPhone PID (auto-detects if None).

    Returns:
        DriverInstallResult with success status and message.
    """
    if not is_windows():
        return DriverInstallResult(
            True, "No driver installation needed on this platform"
        )

    # Step 1: Detect iPhone
    if pid is None:
        pid = detect_iphone_pid()
        if pid is None:
            return DriverInstallResult(
                False,
                "No iPhone detected on USB. Please connect your iPhone "
                "via USB cable and try again."
            )

    logger.info("Installing mirror driver for iPhone PID 0x%04X...", pid)

    # Step 2: Generate INF
    if inf_path is None:
        try:
            inf_path = generate_winusb_inf(pid)
        except Exception as e:
            return DriverInstallResult(False, f"Failed to generate driver files: {e}")

    # Step 3: Check admin privileges
    if not is_admin():
        return _install_with_elevation(inf_path, pid)

    # Step 4: Create certificate and sign (best effort — unsigned may work)
    signed = create_certificate_and_sign(inf_path)
    if signed:
        logger.info("Driver package signed successfully")
    else:
        logger.info("Driver unsigned — will attempt installation anyway")

    # Step 5: Install via pnputil
    return _install_via_pnputil(inf_path)


def _install_with_elevation(inf_path: str, pid: int) -> DriverInstallResult:
    """Launch an elevated process to install the driver.

    Creates a small helper script that runs with admin privileges
    via a UAC prompt.
    """
    driver_dir = os.path.dirname(inf_path)
    script_path = os.path.join(driver_dir, "_install_elevated.py")

    # Write the elevated installer script
    script_content = f'''
"""Elevated driver installer — runs with admin privileges."""
import subprocess, sys, os
os.chdir(r"{driver_dir}")

# Import and run the signing + installation
sys.path.insert(0, r"{os.path.dirname(os.path.abspath(__file__))}")

# Create certificate
print("Creating self-signed certificate...")
cert_result = subprocess.run(
    ["powershell", "-NoProfile", "-ExecutionPolicy", "Bypass", "-Command", """
$cert = New-SelfSignedCertificate -Type CodeSigningCert -Subject 'CN=IMIRROR4FREE Mirror Driver' -CertStoreLocation 'Cert:\\\\\\\\CurrentUser\\\\\\\\My' -NotAfter (Get-Date).AddYears(10) -HashAlgorithm SHA256
$rootStore = New-Object System.Security.Cryptography.X509Certificates.X509Store('Root', 'LocalMachine')
$rootStore.Open('ReadWrite')
$rootStore.Add($cert)
$rootStore.Close()
$pubStore = New-Object System.Security.Cryptography.X509Certificates.X509Store('TrustedPublisher', 'LocalMachine')
$pubStore.Open('ReadWrite')
$pubStore.Add($cert)
$pubStore.Close()
Write-Output $cert.Thumbprint
"""],
    capture_output=True, text=True, timeout=30
)
print(f"Certificate: {{cert_result.stdout.strip()}}")

# Install driver
print("Installing driver via pnputil...")
result = subprocess.run(
    ["pnputil", "/add-driver", r"{inf_path}", "/install"],
    capture_output=True, text=True, timeout=60
)
print(result.stdout)
if result.stderr:
    print(result.stderr)

# Write result file
with open(r"{os.path.join(driver_dir, '_install_result.txt')}", 'w') as f:
    f.write("OK" if result.returncode == 0 else f"FAIL:{{result.stdout}}{{result.stderr}}")

print("Done! You can close this window.")
input("Press Enter to exit...")
'''

    with open(script_path, "w", encoding="utf-8") as f:
        f.write(script_content)

    # Launch with UAC elevation
    try:
        ret = ctypes.windll.shell32.ShellExecuteW(
            None, "runas",
            sys.executable,
            f'"{script_path}"',
            None,
            1  # SW_SHOWNORMAL — show the console window
        )

        if ret <= 32:
            return DriverInstallResult(
                False,
                "Administrator privileges are required. "
                "Please approve the UAC prompt to install the mirror driver."
            )

        return DriverInstallResult(
            True,
            "Driver installation launched! Please approve the UAC prompt, "
            "then unplug and replug your iPhone.",
            needs_replug=True,
        )

    except Exception as e:
        return DriverInstallResult(False, f"Failed to request admin privileges: {e}")


def _install_via_pnputil(inf_path: str) -> DriverInstallResult:
    """Install the driver directly using pnputil (must be admin)."""
    try:
        result = subprocess.run(
            ["pnputil", "/add-driver", inf_path, "/install"],
            capture_output=True, text=True, timeout=60,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )

        output = (result.stdout + "\n" + result.stderr).strip()
        logger.info("pnputil output:\n%s", output)

        # Check for success indicators
        success = (
            result.returncode == 0
            or "added" in output.lower()
            or "installed" in output.lower()
            or "staged" in output.lower()
        )

        # Try to capture the OEM INF name for later removal
        oem_match = re.search(r"(oem\d+\.inf)", output, re.IGNORECASE)
        if oem_match:
            oem_name = oem_match.group(1)
            # Save for later uninstall
            _save_oem_inf_name(oem_name)
            logger.info("Driver installed as: %s", oem_name)

        if success:
            return DriverInstallResult(
                True,
                "Mirror driver installed successfully! "
                "Please unplug and replug your iPhone to activate it.",
                needs_replug=True,
            )
        else:
            # Common failure: unsigned driver on secure boot system
            if "unsigned" in output.lower() or "signature" in output.lower():
                return DriverInstallResult(
                    False,
                    "Driver installation failed — Windows rejected the unsigned driver. "
                    "You may need to temporarily disable Secure Boot in BIOS, or "
                    "use Zadig (https://zadig.akeo.ie/) as a fallback."
                )
            return DriverInstallResult(False, f"Driver installation failed:\n{output}")

    except subprocess.TimeoutExpired:
        return DriverInstallResult(False, "Driver installation timed out")
    except FileNotFoundError:
        return DriverInstallResult(False, "pnputil not found — is this Windows 10 or later?")
    except Exception as e:
        return DriverInstallResult(False, f"Installation error: {e}")


# ─── Driver uninstallation ──────────────────────────────────────────


def uninstall_driver() -> DriverInstallResult:
    """Remove the IMIRROR4FREE mirror driver and restore Apple's original driver.

    Steps:
    1. Remove our OEM INF from the driver store
    2. Force Windows to re-detect and load Apple's driver
    3. Clean up our driver files

    Returns:
        DriverInstallResult with outcome.
    """
    if not is_windows():
        return DriverInstallResult(True, "Nothing to uninstall on this platform")

    if not is_admin():
        # Need elevation for driver removal too
        try:
            ret = ctypes.windll.shell32.ShellExecuteW(
                None, "runas",
                "pnputil", "/enum-drivers",
                None, 0
            )
            return DriverInstallResult(
                False,
                "Administrator privileges required to uninstall the driver. "
                "Please run IMIRROR4FREE as administrator."
            )
        except Exception:
            pass
        return DriverInstallResult(False, "Administrator privileges required")

    # Find our OEM INF name
    oem_name = _load_oem_inf_name()

    if not oem_name:
        # Try to find it by scanning installed drivers
        oem_name = _find_our_oem_inf()

    if oem_name:
        try:
            result = subprocess.run(
                ["pnputil", "/delete-driver", oem_name, "/uninstall", "/force"],
                capture_output=True, text=True, timeout=30,
                creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
            )
            logger.info("Driver removal: %s", result.stdout.strip())
        except Exception as e:
            logger.warning("Failed to remove driver: %s", e)

    # Force device rescan to load Apple's original driver
    try:
        subprocess.run(
            ["pnputil", "/scan-devices"],
            capture_output=True, text=True, timeout=15,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except Exception:
        pass

    # Clean up saved OEM name
    _clear_oem_inf_name()

    return DriverInstallResult(
        True,
        "Mirror driver removed. Apple's original driver will be restored "
        "when you unplug and replug your iPhone.",
        needs_replug=True,
    )


def _find_our_oem_inf() -> Optional[str]:
    """Scan installed drivers to find our IMIRROR4FREE driver."""
    try:
        result = subprocess.run(
            ["pnputil", "/enum-drivers"],
            capture_output=True, text=True, timeout=15,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )

        # Parse pnputil output to find our driver
        current_oem = None
        for line in result.stdout.split("\n"):
            line = line.strip()
            if line.startswith("Published Name") or line.startswith("Published name"):
                match = re.search(r"(oem\d+\.inf)", line, re.IGNORECASE)
                if match:
                    current_oem = match.group(1)
            elif "IMIRROR4FREE" in line.upper() and current_oem:
                return current_oem

    except Exception as e:
        logger.debug("Failed to scan drivers: %s", e)

    return None


# ─── Persistent state ───────────────────────────────────────────────


def _save_oem_inf_name(name: str) -> None:
    """Save the OEM INF name for later uninstall."""
    try:
        path = os.path.join(get_driver_dir(), "oem_inf_name.txt")
        with open(path, "w") as f:
            f.write(name)
    except Exception:
        pass


def _load_oem_inf_name() -> Optional[str]:
    """Load the saved OEM INF name."""
    try:
        path = os.path.join(get_driver_dir(), "oem_inf_name.txt")
        if os.path.exists(path):
            with open(path) as f:
                return f.read().strip()
    except Exception:
        pass
    return None


def _clear_oem_inf_name() -> None:
    """Remove the saved OEM INF name."""
    try:
        path = os.path.join(get_driver_dir(), "oem_inf_name.txt")
        if os.path.exists(path):
            os.remove(path)
    except Exception:
        pass


# ─── Status checking ────────────────────────────────────────────────


def check_driver_status() -> DriverStatus:
    """Comprehensive check of the mirror driver status.

    Checks:
    - Is an iPhone detected on USB?
    - Is the IMIRROR4FREE driver installed?
    - Can libusb access the iPhone?
    - Is QT configuration already active?

    Returns:
        DriverStatus with detailed results.
    """
    status = DriverStatus()

    # Check if iPhone is detected (via any method)
    pid = detect_iphone_pid()
    status.iphone_detected = pid is not None
    status.device_pid = pid

    if not status.iphone_detected:
        return status

    # Check if our driver is installed
    oem_name = _load_oem_inf_name()
    if oem_name:
        status.installed = True
        status.oem_inf_name = oem_name
    else:
        # Check if WinUSB is the current driver for the iPhone
        status.installed = _is_winusb_active_for_iphone()

    # Check libusb accessibility
    try:
        import usb.core

        backend = None
        if is_windows():
            try:
                import libusb_package
                backend = libusb_package.get_libusb1_backend()
            except ImportError:
                pass

        if not backend:
            try:
                import usb.backend.libusb1
                backend = usb.backend.libusb1.get_backend()
            except Exception:
                pass

        kwargs = {"idVendor": APPLE_VID}
        if backend:
            kwargs["backend"] = backend

        dev = usb.core.find(**kwargs)
        if dev:
            # Try to read a descriptor — this tests real access
            try:
                _ = dev.bNumConfigurations
                status.libusb_accessible = True

                # Check for QT config
                for cfg in dev:
                    for intf in cfg:
                        if intf.bInterfaceSubClass == 0x2A:
                            status.qt_config_active = True
                            break
                    if status.qt_config_active:
                        break

            except usb.core.USBError:
                status.libusb_accessible = False

    except Exception:
        pass

    return status


def _is_winusb_active_for_iphone() -> bool:
    """Check if WinUSB is the active driver for the iPhone via Windows."""
    if not is_windows():
        return False

    try:
        result = subprocess.run(
            [
                "powershell", "-NoProfile", "-Command",
                "Get-PnpDevice -Class USB -Status OK | "
                "Where-Object { $_.InstanceId -like '*VID_05AC*' } | "
                "Get-PnpDeviceProperty -KeyName DEVPKEY_Device_Service | "
                "Select-Object -ExpandProperty Data"
            ],
            capture_output=True, text=True, timeout=15,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )

        for line in result.stdout.strip().split("\n"):
            if "winusb" in line.strip().lower():
                return True

    except Exception:
        pass

    return False


# ─── Complete setup flow ────────────────────────────────────────────


def full_driver_setup() -> DriverInstallResult:
    """Run the complete mirror driver installation flow.

    This is the high-level entry point called by the GUI:
    1. Check current status
    2. If already ready → return success
    3. If driver needed → install it
    4. Report result

    Returns:
        DriverInstallResult with outcome and next steps.
    """
    if not is_windows():
        return DriverInstallResult(True, "No driver installation needed on this platform")

    logger.info("=" * 50)
    logger.info("IMIRROR4FREE Mirror Driver Setup")
    logger.info("=" * 50)

    # Check current status
    status = check_driver_status()
    logger.info("Current status:\n%s", status.summary())

    if status.ready_to_stream:
        return DriverInstallResult(True, "Mirror driver is ready — streaming can start!")

    if not status.iphone_detected:
        return DriverInstallResult(
            False,
            "No iPhone detected. Please connect your iPhone via USB and try again."
        )

    if status.installed and not status.libusb_accessible:
        return DriverInstallResult(
            False,
            "Driver is installed but iPhone isn't using it yet. "
            "Please unplug and replug your iPhone.",
            needs_replug=True,
        )

    # Need to install
    return install_driver()


# ─── CLI interface ──────────────────────────────────────────────────


if __name__ == "__main__":
    logging.basicConfig(
        level=logging.INFO,
        format="%(asctime)s [%(levelname)-7s] %(message)s",
        datefmt="%H:%M:%S",
    )

    import argparse
    parser = argparse.ArgumentParser(description="IMIRROR4FREE Mirror Driver Installer")
    parser.add_argument("--install", action="store_true", help="Install the mirror driver")
    parser.add_argument("--uninstall", action="store_true", help="Remove the mirror driver")
    parser.add_argument("--status", action="store_true", help="Check driver status")
    args = parser.parse_args()

    if args.uninstall:
        result = uninstall_driver()
    elif args.status:
        status = check_driver_status()
        print(status.summary())
        sys.exit(0)
    else:
        result = full_driver_setup()

    print(f"\n{result}")
    if result.needs_replug:
        print("\n[!] Please unplug and replug your iPhone to activate the changes.")
