"""
Windows USB Driver Diagnostic Utility.

Provides comprehensive diagnostics for the USB driver situation:
- pyusb/libusb-win32 (libusb0) availability
- Apple device detection
- libusb-win32 driver status
- QT configuration state
- Actionable guidance (integrated with the automated driver installer)

On Windows, the iPhone must be bound to libusb0.sys (libusb-win32),
visible in Device Manager under "LIBUSB-WIN32 DEVICES" with service "libusb0".
This is installed automatically by AnyMiro or the MIRROR4FREE driver installer.

Usage:
    python -m imirror.usb.driver_check
"""

import logging
import platform
import sys

logger = logging.getLogger(__name__)


class DriverCheckResult:
    """Result of a USB driver diagnostic check."""

    def __init__(self):
        self.platform = platform.system()
        self.pyusb_available = False
        self.libusb_backend = False
        self.apple_device_found = False
        self.device_accessible = False
        self.qt_config_active = False
        self.av_endpoints_found = False
        self.libusb0_driver_installed = False
        self.winusb_driver_installed = False  # kept for backward compat
        self.errors: list[str] = []
        self.warnings: list[str] = []
        self.device_info: str = ""
        self.device_pid: int = 0

    @property
    def valeria_ready(self) -> bool:
        """Whether the system is ready for Valeria streaming."""
        return (
            self.pyusb_available
            and self.libusb_backend
            and self.apple_device_found
            and self.device_accessible
        )

    @property
    def needs_driver_install(self) -> bool:
        """Whether the libusb-win32 mirror driver needs to be installed."""
        return (
            self.platform == "Windows"
            and self.apple_device_found
            and not self.device_accessible
            and not self.libusb0_driver_installed
            and not self.winusb_driver_installed
        )

    @property
    def needs_replug(self) -> bool:
        """Whether the user needs to unplug/replug their iPhone."""
        driver_ok = self.libusb0_driver_installed or self.winusb_driver_installed
        return (
            driver_ok
            and self.apple_device_found
            and not self.device_accessible
        )

    def summary(self) -> str:
        """Human-readable summary of the check results."""
        lines = []
        lines.append("=" * 60)
        lines.append("MIRROR4FREE — USB Driver Diagnostic")
        lines.append("=" * 60)
        lines.append(f"Platform: {self.platform}")
        lines.append(f"pyusb installed: {'[OK]' if self.pyusb_available else '[FAIL]'}")
        lines.append(f"libusb backend: {'[OK]' if self.libusb_backend else '[FAIL]'}")
        lines.append(f"Apple device found: {'[OK]' if self.apple_device_found else '[FAIL]'}")
        lines.append(f"Device accessible: {'[OK]' if self.device_accessible else '[FAIL]'}")
        lines.append(f"QT AV config active: {'[OK]' if self.qt_config_active else '[-] (will be enabled)'}")

        if self.platform == "Windows":
            drv_ok = self.libusb0_driver_installed or self.winusb_driver_installed
            lines.append(f"libusb-win32 driver: {'[OK] Installed' if drv_ok else '[FAIL] Not installed'}")

        if self.device_info:
            lines.append(f"Device: {self.device_info}")

        lines.append("")

        if self.valeria_ready:
            lines.append("[SUCCESS] RESULT: System is ready for Valeria streaming!")
            if not self.qt_config_active:
                lines.append("   QT config will be activated automatically when streaming starts.")

        elif self.needs_replug:
            lines.append("[WARN] RESULT: Driver installed — unplug and replug your iPhone")
            lines.append("   The mirror driver is installed but your iPhone needs to be")
            lines.append("   reconnected for Windows to load the new driver.")

        elif self.needs_driver_install:
            lines.append("[WARN] RESULT: Mirror driver installation needed")
            lines.append("")
            lines.append("You have two options:")
            lines.append("")
            lines.append("  Option A — Automatic (recommended):")
            lines.append("    Run: python -m imirror.usb.driver_installer --install")
            lines.append("    Or click 'Install Mirror Driver' in the app.")
            lines.append("")
            lines.append("  Option B — Manual (via Zadig, select libusb-win32):")
            lines.append("    1. Download Zadig from https://zadig.akeo.ie/")
            lines.append("    2. Connect your iPhone via USB")
            lines.append("    3. In Zadig: Options → List All Devices")
            lines.append("    4. Select your iPhone (Apple Mobile Device USB Device)")
            lines.append("    5. Set target driver to libusb-win32 → Click 'Replace Driver'")
            lines.append("")
            lines.append("  Note: This replaces Apple's iPhone USB driver with libusb-win32.")
            lines.append("  iTunes/Apple Music won't detect the iPhone while libusb-win32 is active.")
            lines.append("  You can restore the original driver through the app or Device Manager.")

        elif not self.pyusb_available:
            lines.append("[FAIL] RESULT: pyusb not installed")
            lines.append("   Run: pip install pyusb")
        elif not self.libusb_backend:
            lines.append("[FAIL] RESULT: No libusb backend available")
            lines.append("   Install libusb-win32 via AnyMiro or MIRROR4FREE driver installer.")
        elif not self.apple_device_found:
            lines.append("[FAIL] RESULT: No iPhone found on USB")
            lines.append("   Make sure your iPhone is connected via USB cable.")
            lines.append("   On the iPhone, tap 'Trust' if prompted.")
        else:
            lines.append("[FAIL] RESULT: Unknown issue")

        for err in self.errors:
            lines.append(f"   ERROR: {err}")
        for warn in self.warnings:
            lines.append(f"   WARNING: {warn}")

        lines.append("=" * 60)
        return "\n".join(lines)


def check_usb_drivers() -> DriverCheckResult:
    """Run a comprehensive USB driver diagnostic check.

    Returns a DriverCheckResult with detailed information about
    the USB setup and what needs to be done.
    """
    result = DriverCheckResult()

    # Step 1: Check if pyusb is installed
    try:
        import usb.core
        import usb.util
        result.pyusb_available = True
    except ImportError:
        result.errors.append("pyusb not installed — run: pip install pyusb")
        return result

    # Step 2: Check for libusb backend
    # On Windows, prefer libusb-win32 (libusb0) — same as AnyMiro
    backend = None
    try:
        if platform.system() == "Windows":
            from imirror.usb.endpoint import _find_libusb0_dll
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
        else:
            import usb.backend.libusb1
            backend = usb.backend.libusb1.get_backend()

        if backend:
            result.libusb_backend = True
        else:
            result.errors.append(
                "No libusb backend found. "
                "Install libusb-win32 (via AnyMiro or MIRROR4FREE driver installer) "
                "or run: pip install libusb-package"
            )
            return result

    except Exception as e:
        result.errors.append(f"libusb init failed: {e}")
        return result

    # Step 3: Search for Apple devices
    try:
        kwargs = {"idVendor": 0x05AC, "find_all": True}
        if backend:
            kwargs["backend"] = backend

        devices = list(usb.core.find(**kwargs))

        if not devices:
            # On Windows, also try WMI detection (works without libusb-win32)
            if platform.system() == "Windows":
                try:
                    from imirror.usb.driver_installer import detect_iphone_pid
                    pid = detect_iphone_pid()
                    if pid:
                        result.apple_device_found = True
                        result.device_pid = pid
                        result.device_info = f"Apple Device (PID=0x{pid:04X}, detected via WMI)"
                        # Device found via WMI but not pyusb → needs libusb-win32
                        result.warnings.append(
                            "iPhone found via Windows but not accessible to libusb — "
                            "libusb-win32 mirror driver installation needed"
                        )
                        return result
                except ImportError:
                    pass

            result.warnings.append("No Apple USB device found — is iPhone connected?")
            return result

        result.apple_device_found = True
        dev = devices[0]
        result.device_pid = dev.idProduct

        try:
            product = dev.product or "Apple Device"
            result.device_info = f"{product} (VID=0x{dev.idVendor:04X} PID=0x{dev.idProduct:04X})"
        except (usb.core.USBError, ValueError):
            result.device_info = f"Apple Device (PID=0x{dev.idProduct:04X})"

    except Exception as e:
        result.errors.append(f"USB device search error: {e}")
        return result

    # Step 4: Check if we can access the device (read config descriptors)
    try:
        for cfg in dev:
            for intf in cfg:
                _ = intf.bInterfaceSubClass  # Try reading a descriptor
        result.device_accessible = True
    except usb.core.USBError as e:
        result.warnings.append(f"Cannot read device descriptors: {e}")
        result.warnings.append("This usually means libusb-win32 (libusb0) driver is needed")

        # Check if libusb-win32 is installed but device needs replug
        try:
            from imirror.usb.driver_installer import check_driver_status
            driver_status = check_driver_status()
            result.libusb0_driver_installed = driver_status.installed
            result.winusb_driver_installed = driver_status.installed  # compat
        except ImportError:
            pass

        return result

    # Step 5: Check for QT AV configuration
    try:
        for cfg in dev:
            for intf in cfg:
                if intf.bInterfaceSubClass == 0x2A:
                    result.qt_config_active = True

                    # Check for AV endpoints
                    bulk_in = usb.util.find_descriptor(
                        intf,
                        custom_match=lambda e: (
                            usb.util.endpoint_direction(e.bEndpointAddress) == usb.util.ENDPOINT_IN
                            and usb.util.endpoint_type(e.bmAttributes) == usb.util.ENDPOINT_TYPE_BULK
                        )
                    )
                    bulk_out = usb.util.find_descriptor(
                        intf,
                        custom_match=lambda e: (
                            usb.util.endpoint_direction(e.bEndpointAddress) == usb.util.ENDPOINT_OUT
                            and usb.util.endpoint_type(e.bmAttributes) == usb.util.ENDPOINT_TYPE_BULK
                        )
                    )

                    if bulk_in and bulk_out:
                        result.av_endpoints_found = True

                    break
    except Exception as e:
        result.warnings.append(f"Error checking QT config: {e}")

    # Mark driver as installed if we got this far with device access
    if result.device_accessible:
        result.libusb0_driver_installed = True
        result.winusb_driver_installed = True  # compat

    return result


def run_diagnostic():
    """Run the diagnostic and print results to stdout."""
    result = check_usb_drivers()
    print(result.summary())
    return 0 if result.valeria_ready else 1


if __name__ == "__main__":
    sys.exit(run_diagnostic())
