"""
Windows USB Driver Diagnostic Utility.

Checks the USB driver situation for IMIRROR4FREE and provides
actionable guidance if WinUSB is needed for Valeria streaming.

This utility helps diagnose common USB issues:
- No Apple device found
- Apple device found but no libusb access
- QT configuration already active
- WinUSB driver needed

The Valeria protocol requires raw USB access via libusb, which on
Windows means the AV interface needs WinUSB (installable via Zadig).
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
        self.errors: list[str] = []
        self.warnings: list[str] = []
        self.device_info: str = ""

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
    def needs_winusb(self) -> bool:
        """Whether WinUSB driver installation is likely needed."""
        return (
            self.platform == "Windows"
            and self.apple_device_found
            and not self.device_accessible
        )

    def summary(self) -> str:
        """Human-readable summary of the check results."""
        lines = []
        lines.append("=" * 60)
        lines.append("IMIRROR4FREE — USB Driver Diagnostic")
        lines.append("=" * 60)
        lines.append(f"Platform: {self.platform}")
        lines.append(f"pyusb installed: {'✅' if self.pyusb_available else '❌'}")
        lines.append(f"libusb backend: {'✅' if self.libusb_backend else '❌'}")
        lines.append(f"Apple device found: {'✅' if self.apple_device_found else '❌'}")
        lines.append(f"Device accessible: {'✅' if self.device_accessible else '❌'}")
        lines.append(f"QT AV config active: {'✅' if self.qt_config_active else '➖ (will be enabled)'}")

        if self.device_info:
            lines.append(f"Device: {self.device_info}")

        lines.append("")

        if self.valeria_ready:
            lines.append("🎉 RESULT: System is ready for Valeria streaming!")
            if not self.qt_config_active:
                lines.append("   QT config will be activated automatically when streaming starts.")
        elif self.needs_winusb:
            lines.append("⚠️ RESULT: WinUSB driver needed for USB raw access")
            lines.append("")
            lines.append("To fix this, install WinUSB via Zadig:")
            lines.append("  1. Download Zadig from https://zadig.akeo.ie/")
            lines.append("  2. Connect your iPhone via USB")
            lines.append("  3. In Zadig: Options → List All Devices")
            lines.append("  4. Select your iPhone (Apple Mobile Device USB Device)")
            lines.append("  5. Set the target driver to WinUSB")
            lines.append("  6. Click 'Replace Driver' or 'Install Driver'")
            lines.append("")
            lines.append("Note: This replaces only the iPhone's USB driver.")
            lines.append("iTunes/Apple Music may not work while WinUSB is active.")
            lines.append("You can restore the original driver through Device Manager.")
        elif not self.pyusb_available:
            lines.append("❌ RESULT: pyusb not installed")
            lines.append("   Run: pip install pyusb")
        elif not self.libusb_backend:
            lines.append("❌ RESULT: No libusb backend available")
            lines.append("   Run: pip install libusb-package")
        elif not self.apple_device_found:
            lines.append("❌ RESULT: No iPhone found on USB")
            lines.append("   Make sure your iPhone is connected via USB cable.")
            lines.append("   On the iPhone, tap 'Trust' if prompted.")
        else:
            lines.append("❌ RESULT: Unknown issue")

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
    backend = None
    try:
        import usb.backend.libusb1

        # Try libusb-package first (Windows)
        if platform.system() == "Windows":
            try:
                import libusb_package
                backend = libusb_package.get_libusb1_backend()
            except ImportError:
                pass

        if not backend:
            backend = usb.backend.libusb1.get_backend()

        if backend:
            result.libusb_backend = True
        else:
            result.errors.append("No libusb backend — run: pip install libusb-package")
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
            result.warnings.append("No Apple USB device found — is iPhone connected?")
            return result

        result.apple_device_found = True
        dev = devices[0]

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
        result.warnings.append("This usually means WinUSB driver is needed")
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

    return result


def run_diagnostic():
    """Run the diagnostic and print results to stdout."""
    result = check_usb_drivers()
    print(result.summary())
    return 0 if result.valeria_ready else 1


if __name__ == "__main__":
    sys.exit(run_diagnostic())
