"""
libusb-win32 (libusb0) Driver Auto-Installer for iPhone AV Interface.

Installs the libusb-win32 driver for the iPhone so PyUSB can access it
for Valeria protocol communication — exactly what AnyMiro does.

This installs a libusb-win32 "mirror driver" on first run.
After installation, IMIRROR4FREE can send the USB control transfer to enable
QT Configuration 5 (Valeria AV streaming) and communicate with the
H.264 video + PCM audio endpoints.

Architecture:
    1. Detect iPhone PID on USB bus (pyusb or Windows WMI fallback)
    2. Generate a libusb-win32 INF file targeting the specific iPhone
    3. Create self-signed certificate for driver signing
    4. Install via pnputil (with UAC elevation if needed)
    5. User unplugs and replugs iPhone → libusb0 loads
    6. PyUSB (libusb0 backend) can now access the device → Valeria streaming works

The device will appear in Device Manager under "LIBUSB-WIN32 DEVICES"
with service property "libusb0" — identical to what AnyMiro sets up.

Trade-off:
    While our libusb-win32 driver is installed, Apple's original driver is replaced.
    iTunes/Apple Music won't detect the iPhone. We provide an uninstall method
    to restore the original Apple driver when the user wants.

Requirements:
    - Windows 10 or later
    - Administrator privileges (UAC prompt shown automatically)
    - iPhone connected via USB
    - libusb0.inf in the Windows INF directory (installed by AnyMiro or libusb-win32)
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

    def __init__(self, success: bool, message: str, needs_replug: bool = False, needs_restart: bool = False):
        self.success = success
        self.message = message
        self.needs_replug = needs_replug
        self.needs_restart = needs_restart

    def __repr__(self):
        status = "[OK]" if self.success else "[FAIL]"
        return f"{status} {self.message}"


class DriverStatus:
    """Current status of the libusb-win32 mirror driver."""

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
        # Show "Driver installed: [OK]" if libusb is accessible, regardless of
        # whether we have the OEM INF name saved.  The old logic showed [FAIL]
        # when the user installed libusb-win32 via Zadig (no saved OEM name) or when
        # _is_libusb0_active_for_iphone() returned False due to PowerShell
        # service name differences — confusing because streaming was fine.
        driver_ok = self.installed or self.libusb_accessible
        lines = [
            f"  iPhone detected:   {'[OK]' if self.iphone_detected else '[FAIL]'}",
            f"  Driver installed:  {'[OK]' if driver_ok else '[FAIL]'}",
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
    1. pyusb with libusb0 (best, but may fail without libusb-win32)
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
    """Detect iPhone PID via pyusb (uses libusb-win32 backend on Windows)."""
    try:
        import usb.core
        from imirror.usb.endpoint import _find_libusb0_dll

        backend = None
        if is_windows():
            # Try libusb-win32 (libusb0) first — this is what AnyMiro uses
            dll_path = _find_libusb0_dll()
            try:
                import usb.backend.libusb0 as _lb0
                find_lib = (lambda x: dll_path) if dll_path else None
                backend = _lb0.get_backend(find_library=find_lib)
            except Exception:
                pass

            # Fallback to libusb1 (non-Windows / last resort)
            if not backend:
                try:
                    import usb.backend.libusb1
                    backend = usb.backend.libusb1.get_backend()
                except Exception:
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
    """Detect iPhone PID via Windows WMI (works without libusb/libusb-win32)."""
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


def generate_libusb0_inf(
    pid: int,
    output_dir: Optional[str] = None,
) -> str:
    """Generate a libusb-win32 (libusb0) INF file for the iPhone.

    Creates a self-contained INF (identical in format to what AnyMiro
    installs) that tells Windows to use the libusb-win32 driver for the
    specific iPhone model.  This replaces Apple's composite driver and
    gives PyUSB (libusb0 backend) access for Valeria / QuickTime AV
    protocol communication.

    The generated INF does NOT use Include/Needs — it defines every
    required section inline, so it works whether or not AnyMiro is
    installed.  When AnyMiro IS installed the libusb0.sys / libusb0.dll
    files are already in System32; the CopyFiles sections reference the
    existing DriverStore copies via SourceDisksFiles so pnputil can stage
    them correctly.

    Confirmed against:
        iphone_(composite_parent).inf_amd64_367fccc3b4693915
        libusb-win32 v1.4.0.0  (02/22/2024)
        VID_05AC & PID_12A8

    ClassGuid  : {EB781AAF-9C70-4523-A5DF-642A87ECA567}  (libusb-win32 devices)
    DeviceGUID : {CB090FED-2DFC-4040-9237-9F2F69751D8D}

    Args:
        pid: iPhone USB Product ID (e.g., 0x12A8).
        output_dir: Directory for output files (uses driver dir if None).

    Returns:
        Path to the generated INF file.
    """
    if output_dir is None:
        output_dir = get_driver_dir()

    os.makedirs(output_dir, exist_ok=True)

    # Primary hardware ID — matches the specific iPhone model
    hw_id = f"USB\\VID_{APPLE_VID:04X}&PID_{pid:04X}"

    inf_content = f"""; iMirror4Free - libusb-win32 driver for iPhone AV Interface
; Copyright (c) 2010 libusb-win32 (GNU LGPL)
[Strings]
DeviceName  = "iPhone (Composite Parent)"
VendorName  = "Apple, Inc."
SourceName  = "iPhone (Composite Parent) Install Disk"
DeviceID    = "VID_{APPLE_VID:04X}&PID_{pid:04X}"
DeviceGUID  = "{{CB090FED-2DFC-4040-9237-9F2F69751D8D}}"

[Version]
Signature      = "$Windows NT$"
Class          = "libusb-win32 devices"
ClassGuid      = {{EB781AAF-9C70-4523-A5DF-642A87ECA567}}
Provider       = "libusb-win32"
CatalogFile    = imirror_mirror.cat
DriverVer      = 02/22/2024, 1.4.0.0

[ClassInstall32]
Addreg = libusb_class_install_add_reg

[libusb_class_install_add_reg]
HKR,,,0,"libusb-win32 devices"
HKR,,Icon,,-20

[Manufacturer]
%VendorName% = Devices, NT, NTAMD64, NTARM64

;---------------------------------------------------------------------------
; libusb-win32 files
;---------------------------------------------------------------------------

[SourceDisksNames]
1 = %SourceName%

[SourceDisksFiles.x86]
libusb0.sys      = 1,x86
libusb0_x86.dll  = 1,x86
libusbk_x86.dll  = 1,x86

[SourceDisksFiles.amd64]
libusb0.sys      = 1,amd64
libusb0.dll      = 1,amd64
libusbk.dll      = 1,amd64
libusb0_x86.dll  = 1,x86

[SourceDisksFiles.arm64]
libusb0.sys      = 1,arm64
libusb0.dll      = 1,arm64

[DestinationDirs]
libusb_files_sys        = 10,system32\\drivers
libusb_files_dll        = 10,system32
libusb_files_dll_wow64  = 10,syswow64
libusb_files_dll_x86    = 10,system32

[libusb_files_sys]
libusb0.sys

[libusb_files_dll]
libusb0.dll
libusbk.dll

[libusb_files_dll_x86]
libusb0.dll, libusb0_x86.dll , libusbk.dll , libusbk_x86.dll

[libusb_files_dll_wow64]
libusb0.dll, libusb0_x86.dll , libusbk.dll , libusbk_x86.dll

;---------------------------------------------------------------------------
; libusb-win32 device driver
;---------------------------------------------------------------------------

[LIBUSB_WIN32_DEV.NT]
CopyFiles = libusb_files_sys, libusb_files_dll_x86

[LIBUSB_WIN32_DEV.NTAMD64]
CopyFiles = libusb_files_sys, libusb_files_dll, libusb_files_dll_wow64

[LIBUSB_WIN32_DEV.NTARM64]
CopyFiles = libusb_files_sys, libusb_files_dll

[LIBUSB_WIN32_DEV.NT.HW]
DelReg = libusb_del_reg_hw
AddReg = libusb_add_reg_hw

[LIBUSB_WIN32_DEV.NTAMD64.HW]
DelReg = libusb_del_reg_hw
AddReg = libusb_add_reg_hw

[LIBUSB_WIN32_DEV.NTARM64.HW]
DelReg = libusb_del_reg_hw
AddReg = libusb_add_reg_hw

[LIBUSB_WIN32_DEV.NT.Services]
AddService = libusb0, 0x00000002, libusb_add_service

[LIBUSB_WIN32_DEV.NTAMD64.Services]
AddService = libusb0, 0x00000002, libusb_add_service

[LIBUSB_WIN32_DEV.NTARM64.Services]
AddService = libusb0, 0x00000002, libusb_add_service

; Older versions of this .inf file installed filter drivers. They are not
; needed any more and must be removed
[libusb_del_reg_hw]
HKR,,LowerFilters
HKR,,UpperFilters

; libusb-win32 device properties
[libusb_add_reg_hw]
HKR,,SurpriseRemovalOK,0x00010001,1
HKR,,DeviceInterfaceGUIDs,0x00010000,%DeviceGUID%

;---------------------------------------------------------------------------
; libusb-win32 service
;---------------------------------------------------------------------------

[libusb_add_service]
DisplayName    = "libusb-win32 - Kernel Driver 02/22/2024 1.4.0.0"
ServiceType    = 1
StartType      = 3
ErrorControl   = 0
ServiceBinary  = %12%\\libusb0.sys

;---------------------------------------------------------------------------
; libusb-win32 devices
;---------------------------------------------------------------------------

; Hardware Ids in a 'Devices' section can be installed by libusb-win32
; using usb_install_driver_np(), usb_install_driver_np_rundll(), or the
; inf-wizard utility.
;
[Devices]
%DeviceName% = LIBUSB_WIN32_DEV, USB\\%DeviceID%

[Devices.NT]
%DeviceName% = LIBUSB_WIN32_DEV.NT, USB\\%DeviceID%

[Devices.NTAMD64]
%DeviceName% = LIBUSB_WIN32_DEV.NTAMD64, USB\\%DeviceID%

[Devices.NTARM64]
%DeviceName% = LIBUSB_WIN32_DEV.NTARM64, USB\\%DeviceID%
"""

    inf_path = os.path.join(output_dir, "imirror_mirror.inf")
    with open(inf_path, "w", encoding="utf-8") as f:
        f.write(inf_content)

    logger.info("Generated libusb-win32 INF at: %s", inf_path)
    logger.info("  Hardware ID: %s", hw_id)

    return inf_path


# Keep old name as alias for backward compatibility
generate_winusb_inf = generate_libusb0_inf


# ─── Certificate & signing ──────────────────────────────────────────


def create_certificate_and_sign(inf_path: str) -> bool:
    """Create a self-signed certificate and sign the driver catalog.

    Windows 10/11 x64 requires signed drivers. We create a self-signed
    certificate, add it to the Trusted Root and Trusted Publishers stores,
    then sign the catalog file.

    This is the same approach Zadig uses when installing libusb-win32.

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
    """Install the libusb-win32 mirror driver.

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
            inf_path = generate_libusb0_inf(pid)
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

        # Check for success indicators.
        # Exit code 3010 = success but Windows requires a restart to activate
        # the new driver (the old Apple driver service is still loaded).
        # This mirrors AnyMiro's behavior: it prompts "restart required" on
        # first driver installation because Apple's driver is currently in use.
        needs_restart = (result.returncode == 3010)
        success = (
            result.returncode == 0
            or needs_restart
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
            if needs_restart:
                return DriverInstallResult(
                    True,
                    "Mirror driver installed! Windows needs to restart to activate "
                    "the new driver (the Apple USB service is currently in use). "
                    "Please save your work and restart your PC, then reopen iMirror4Free.",
                    needs_replug=False,
                    needs_restart=True,
                )
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
                    "use Zadig (https://zadig.akeo.ie/) selecting 'libusb-win32' as a fallback."
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
        # Check if libusb0 (libusb-win32) is the current driver for the iPhone
        status.installed = _is_libusb0_active_for_iphone()

    # Check libusb accessibility (using libusb0 backend on Windows)
    try:
        import usb.core
        from imirror.usb.endpoint import _find_libusb0_dll

        backend = None
        if is_windows():
            dll_path = _find_libusb0_dll()
            try:
                import usb.backend.libusb0 as _lb0
                find_lib = (lambda x: dll_path) if dll_path else None
                backend = _lb0.get_backend(find_library=find_lib)
            except Exception:
                pass

            if not backend:
                try:
                    import usb.backend.libusb1
                    backend = usb.backend.libusb1.get_backend()
                except Exception:
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


def _is_libusb0_active_for_iphone() -> bool:
    """Check if libusb-win32 (libusb0) is the active driver for the iPhone.

    Looks for Apple USB devices in Device Manager and checks if their
    service is 'libusb0' — which is what AnyMiro installs.
    """
    if not is_windows():
        return False

    try:
        result = subprocess.run(
            [
                "powershell", "-NoProfile", "-Command",
                "Get-PnpDevice -Status OK | "
                "Where-Object { $_.InstanceId -like '*VID_05AC*' } | "
                "Get-PnpDeviceProperty -KeyName DEVPKEY_Device_Service | "
                "Select-Object -ExpandProperty Data"
            ],
            capture_output=True, text=True, timeout=15,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )

        for line in result.stdout.strip().split("\n"):
            svc = line.strip().lower()
            # Accept libusb0 (libusb-win32) or winusb (WinUSB) as valid
            if svc in ("libusb0", "winusb") or svc.startswith("libusb"):
                logger.debug("Active driver service for iPhone: %s", line.strip())
                return True

    except Exception:
        pass

    return False


# Keep old name as alias for backward compatibility
_is_winusb_active_for_iphone = _is_libusb0_active_for_iphone


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
