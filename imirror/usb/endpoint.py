"""
USB Endpoint Manager — Raw USB communication with iPhone AV endpoints.

Handles the low-level USB operations required for Valeria protocol:
1. Finding the iPhone on the USB bus
2. Sending the QT configuration control request
3. Waiting for device re-enumeration with AV endpoints
4. Claiming the AV bulk endpoints
5. Reading/writing data to/from the iPhone

Windows notes:
- Uses pyusb with libusb backend (bundled via libusb-package)
- Requires WinUSB driver for the AV interface (install via Zadig)
- The QT config adds SubClass 0x2A interfaces with bulk endpoints
- Apple Mobile Device driver stays on the main iPhone interface

Reference: https://github.com/danielpaulus/quicktime_video_hack
"""

import logging
import platform
import struct
import time
from typing import Optional

logger = logging.getLogger(__name__)

APPLE_VENDOR_ID = 0x05AC
QT_CONFIG_REQUEST = 0x52
QT_SUBCLASS = 0x2A
USBMUX_SUBCLASS = 0xFE

# Read size for bulk transfers — 64KB is efficient for USB 2.0 High Speed
DEFAULT_READ_SIZE = 65536
DEFAULT_TIMEOUT_MS = 100


class USBEndpointError(Exception):
    """Raised when USB endpoint operations fail."""
    pass


class USBEndpoint:
    """
    Manages raw USB communication with the iPhone's Valeria AV endpoints.

    This class handles the entire USB lifecycle for Valeria streaming:

    Lifecycle:
        1. find_iphone()          — Locate an Apple device on the USB bus
        2. enable_qt_config()     — Activate the hidden QT AV configuration
        3. wait_for_reenumeration() — Wait for device to reconnect with AV endpoints
        4. claim_av_endpoints()   — Claim the AV bulk IN/OUT endpoints
        5. read() / write()       — Transfer data
        6. close()                — Release interfaces and clean up

    The QT configuration is Apple's mechanism for exposing H.264 video and
    PCM audio over USB bulk endpoints. Normally hidden, it's activated by
    a vendor-specific control request (bRequest=0x52).
    """

    def __init__(self):
        self._device = None
        self._av_interface = None
        self._bulk_in = None       # Endpoint: iPhone → PC (video/audio data)
        self._bulk_out = None      # Endpoint: PC → iPhone (protocol responses)
        self._backend = None
        self._claimed = False
        self._av_interface_number = -1

        # Initialize the libusb backend
        self._init_backend()

    def _init_backend(self):
        """Initialize the libusb backend for pyusb."""
        try:
            import usb.backend.libusb1

            # On Windows, try the bundled libusb from libusb-package first
            if platform.system() == "Windows":
                try:
                    import libusb_package
                    self._backend = libusb_package.get_libusb1_backend()
                    if self._backend:
                        logger.info("USB: Using libusb-package backend (bundled)")
                        return
                except ImportError:
                    logger.debug("libusb-package not installed, trying system libusb")

            # Fall back to system-installed libusb
            self._backend = usb.backend.libusb1.get_backend()
            if self._backend:
                logger.info("USB: Using system libusb1 backend")
            else:
                logger.warning("USB: No libusb backend available")

        except Exception as e:
            logger.warning("USB: Failed to initialize libusb backend: %s", e)

    def _find_kwargs(self, **extra):
        """Build keyword arguments for usb.core.find() with backend if available."""
        kwargs = dict(extra)
        if self._backend:
            kwargs["backend"] = self._backend
        return kwargs

    # ─── Device discovery ───────────────────────────────────────────

    def find_iphone(self) -> bool:
        """Find an Apple device on the USB bus.

        Searches for any device with Apple's Vendor ID (0x05AC).
        iPhones, iPads, and iPods all use this VID.

        Returns:
            True if an Apple device was found.
        """
        try:
            import usb.core

            devices = list(usb.core.find(
                find_all=True,
                **self._find_kwargs(idVendor=APPLE_VENDOR_ID)
            ))

            if not devices:
                logger.info("USB: No Apple devices found on bus")
                return False

            # Pick the first accessible Apple device
            for dev in devices:
                try:
                    product = dev.product or "(unknown)"
                except (usb.core.USBError, ValueError):
                    product = "(inaccessible)"

                logger.info(
                    "USB: Found Apple device — VID=0x%04X PID=0x%04X [%s]",
                    dev.idVendor, dev.idProduct, product
                )
                self._device = dev
                return True

            return False

        except Exception as e:
            if "NoBackendError" in type(e).__name__:
                logger.error("USB: No backend — install libusb or libusb-package")
            else:
                logger.error("USB: Device search failed — %s", e)
            return False

    def has_qt_config(self) -> bool:
        """Check if the QT AV configuration is already active on the device.

        When active, the device has a USB interface with SubClass 0x2A
        containing bulk endpoints for H.264 video and PCM audio.

        Returns:
            True if QT AV interface is present.
        """
        if not self._device:
            return False

        try:
            for cfg in self._device:
                for intf in cfg:
                    if intf.bInterfaceSubClass == QT_SUBCLASS:
                        logger.debug("USB: QT AV interface found (#%d)", intf.bInterfaceNumber)
                        return True
        except Exception:
            pass

        return False

    # ─── QT configuration activation ───────────────────────────────

    def enable_qt_config(self) -> bool:
        """Send the vendor control request to activate the hidden QT AV configuration.

        After this request, the iPhone will:
        1. Disconnect from the USB bus
        2. Re-enumerate with additional bulk endpoints for AV streaming

        The re-enumeration takes 2-5 seconds. Call wait_for_reenumeration()
        after this method returns True.

        Returns:
            True if the request was sent (or QT config is already active).
        """
        if not self._device:
            raise USBEndpointError("No device found — call find_iphone() first")

        # Skip if already active
        if self.has_qt_config():
            logger.info("USB: QT AV configuration already active — skipping enable")
            return True

        try:
            import usb.core

            # On non-Windows, detach kernel drivers first
            if platform.system() != "Windows":
                self._detach_kernel_drivers()

            # Send vendor control request: bmRequestType=0x40 (Vendor, Host→Device)
            # bRequest=0x52, wValue=1 (enable), wIndex=0
            self._device.ctrl_transfer(
                bmRequestType=0x40,
                bRequest=QT_CONFIG_REQUEST,
                wValue=1,
                wIndex=0,
                data_or_wLength=None,
                timeout=5000
            )

            logger.info("🎬 USB: QT config request sent — device will re-enumerate")
            return True

        except Exception as e:
            logger.error("USB: Failed to send QT config request — %s", e)
            logger.error(
                "USB: This usually means a driver issue. On Windows, install "
                "WinUSB driver for the iPhone via Zadig (https://zadig.akeo.ie/)"
            )
            return False

    def wait_for_reenumeration(self, timeout: float = 15.0) -> bool:
        """Wait for the device to reconnect with AV endpoints after QT config enable.

        The iPhone disconnects and reconnects within 2-5 seconds.
        This method polls the USB bus until the device reappears with
        the QT SubClass 0x2A interface.

        Args:
            timeout: Maximum seconds to wait for re-enumeration.

        Returns:
            True if device reconnected with AV endpoints.
        """
        import usb.core

        # If QT config is already active, we're done
        if self.has_qt_config():
            logger.info("USB: QT config already active — no re-enumeration needed")
            return True

        logger.info("USB: Waiting for device re-enumeration (up to %.0fs)...", timeout)
        start = time.monotonic()

        # Phase 1: Wait for device to disappear (up to 1/3 of timeout)
        phase1_deadline = start + timeout / 3
        disappeared = False

        while time.monotonic() < phase1_deadline:
            try:
                dev = usb.core.find(**self._find_kwargs(idVendor=APPLE_VENDOR_ID))
                if dev is None:
                    disappeared = True
                    logger.info("USB: Device disconnected — waiting for reconnect...")
                    break
            except Exception:
                disappeared = True
                break
            time.sleep(0.2)

        if not disappeared:
            logger.warning("USB: Device didn't disconnect — checking for AV endpoints anyway")

        # Phase 2: Wait for device to reappear WITH QT config
        while time.monotonic() - start < timeout:
            try:
                dev = usb.core.find(**self._find_kwargs(idVendor=APPLE_VENDOR_ID))
                if dev is not None:
                    self._device = dev

                    if self.has_qt_config():
                        elapsed = time.monotonic() - start
                        logger.info(
                            "✅ USB: Device reconnected with QT AV config (%.1fs)",
                            elapsed
                        )
                        return True

            except Exception:
                pass

            time.sleep(0.5)

        logger.error("USB: Timeout — device didn't reconnect with QT AV configuration")
        return False

    # ─── Endpoint claiming ──────────────────────────────────────────

    def claim_av_endpoints(self) -> bool:
        """Find and claim the AV bulk IN/OUT endpoints.

        The QT configuration adds USB interfaces with SubClass 0x2A.
        These contain bulk endpoints for AV data transfer:
        - Bulk IN:  iPhone → PC (video frames, audio samples)
        - Bulk OUT: PC → iPhone (protocol responses, NEED requests)

        Returns:
            True if both endpoints were claimed successfully.
        """
        import usb.core
        import usb.util

        if not self._device:
            raise USBEndpointError("No device — call find_iphone() first")

        try:
            # Find the AV interface (SubClass 0x2A)
            av_intf = None
            for cfg in self._device:
                for intf in cfg:
                    if intf.bInterfaceSubClass == QT_SUBCLASS:
                        av_intf = intf
                        break
                if av_intf:
                    break

            if av_intf is None:
                logger.error("USB: No AV interface (SubClass 0x2A) found")
                logger.error("USB: The QT configuration may not be active")
                return False

            logger.info(
                "USB: Found AV interface #%d (SubClass=0x%02X, Endpoints=%d)",
                av_intf.bInterfaceNumber,
                av_intf.bInterfaceSubClass,
                av_intf.bNumEndpoints
            )

            self._av_interface_number = av_intf.bInterfaceNumber

            # Detach kernel driver if needed (Linux/macOS)
            if platform.system() != "Windows":
                try:
                    if self._device.is_kernel_driver_active(av_intf.bInterfaceNumber):
                        self._device.detach_kernel_driver(av_intf.bInterfaceNumber)
                        logger.info("USB: Detached kernel driver from AV interface")
                except (usb.core.USBError, NotImplementedError):
                    pass

            # Set USB configuration (may fail if already set — that's fine)
            try:
                self._device.set_configuration()
            except usb.core.USBError:
                pass

            # Claim the interface
            try:
                usb.util.claim_interface(self._device, av_intf.bInterfaceNumber)
                self._claimed = True
                logger.info("USB: Claimed AV interface #%d", av_intf.bInterfaceNumber)
            except usb.core.USBError as e:
                logger.error("USB: Failed to claim AV interface — %s", e)
                logger.error(
                    "USB: Another program may be using it, or WinUSB driver "
                    "is not installed for this interface."
                )
                return False

            # Find bulk IN endpoint (iPhone → PC)
            self._bulk_in = usb.util.find_descriptor(
                av_intf,
                custom_match=lambda e: (
                    usb.util.endpoint_direction(e.bEndpointAddress) == usb.util.ENDPOINT_IN
                    and usb.util.endpoint_type(e.bmAttributes) == usb.util.ENDPOINT_TYPE_BULK
                )
            )

            # Find bulk OUT endpoint (PC → iPhone)
            self._bulk_out = usb.util.find_descriptor(
                av_intf,
                custom_match=lambda e: (
                    usb.util.endpoint_direction(e.bEndpointAddress) == usb.util.ENDPOINT_OUT
                    and usb.util.endpoint_type(e.bmAttributes) == usb.util.ENDPOINT_TYPE_BULK
                )
            )

            if self._bulk_in is None:
                logger.error("USB: No bulk IN endpoint on AV interface")
                return False

            if self._bulk_out is None:
                logger.error("USB: No bulk OUT endpoint on AV interface")
                return False

            logger.info(
                "📡 USB: AV endpoints ready — IN=0x%02X (max %d) OUT=0x%02X (max %d)",
                self._bulk_in.bEndpointAddress,
                self._bulk_in.wMaxPacketSize,
                self._bulk_out.bEndpointAddress,
                self._bulk_out.wMaxPacketSize,
            )

            self._av_interface = av_intf
            return True

        except usb.core.USBError as e:
            logger.error("USB: Failed to set up AV endpoints — %s", e)
            return False

    # ─── Data transfer ──────────────────────────────────────────────

    def read(self, size: int = DEFAULT_READ_SIZE, timeout: int = DEFAULT_TIMEOUT_MS) -> bytes:
        """Read data from the bulk IN endpoint (iPhone → PC).

        Data arrives as Valeria protocol packets (length-prefixed).
        Multiple packets or partial packets may arrive in a single read.

        Args:
            size: Maximum bytes to read (default 64KB).
            timeout: Timeout in milliseconds.

        Returns:
            Bytes read from the endpoint.

        Raises:
            USBEndpointError: If endpoints aren't claimed.
            usb.core.USBTimeoutError: If no data within timeout.
            usb.core.USBError: On USB communication failure.
        """
        if self._bulk_in is None:
            raise USBEndpointError("Endpoints not claimed — call claim_av_endpoints() first")

        data = self._device.read(self._bulk_in.bEndpointAddress, size, timeout=timeout)
        return bytes(data)

    def write(self, data: bytes, timeout: int = 1000) -> int:
        """Write data to the bulk OUT endpoint (PC → iPhone).

        Used to send protocol responses (RPLY), start/stop streaming
        commands (HPD1/HPA1), and NEED requests.

        Args:
            data: Complete packet bytes to send.
            timeout: Timeout in milliseconds.

        Returns:
            Number of bytes actually written.

        Raises:
            USBEndpointError: If endpoints aren't claimed.
            usb.core.USBError: On USB communication failure.
        """
        if self._bulk_out is None:
            raise USBEndpointError("Endpoints not claimed — call claim_av_endpoints() first")

        return self._device.write(self._bulk_out.bEndpointAddress, data, timeout=timeout)

    # ─── Cleanup ────────────────────────────────────────────────────

    def close(self):
        """Release the AV interface and clean up.

        Attempts to:
        1. Release the claimed USB interface
        2. Send QT config disable request (wValue=0) for polite cleanup
        """
        import usb.util

        if self._device and self._claimed and self._av_interface_number >= 0:
            try:
                usb.util.release_interface(self._device, self._av_interface_number)
                logger.info("USB: Released AV interface #%d", self._av_interface_number)
            except Exception:
                pass

        # Try to disable QT config (polite — doesn't matter if it fails)
        if self._device:
            try:
                self._device.ctrl_transfer(
                    bmRequestType=0x40,
                    bRequest=QT_CONFIG_REQUEST,
                    wValue=0,  # Disable
                    wIndex=0,
                    data_or_wLength=None,
                    timeout=1000
                )
                logger.debug("USB: Sent QT config disable request")
            except Exception:
                pass

        self._device = None
        self._av_interface = None
        self._bulk_in = None
        self._bulk_out = None
        self._claimed = False
        self._av_interface_number = -1

    # ─── Helpers ────────────────────────────────────────────────────

    def _detach_kernel_drivers(self):
        """Detach kernel drivers from all interfaces (Linux/macOS only)."""
        if not self._device:
            return
        try:
            for cfg in self._device:
                for intf in cfg:
                    try:
                        if self._device.is_kernel_driver_active(intf.bInterfaceNumber):
                            self._device.detach_kernel_driver(intf.bInterfaceNumber)
                    except Exception:
                        pass
        except Exception:
            pass

    @property
    def is_connected(self) -> bool:
        """Whether both AV endpoints are claimed and ready for I/O."""
        return self._bulk_in is not None and self._bulk_out is not None

    @property
    def device_info(self) -> str:
        """Human-readable device identification string."""
        if not self._device:
            return "No device"
        try:
            product = self._device.product or "Apple Device"
            return f"{product} (VID=0x{self._device.idVendor:04X} PID=0x{self._device.idProduct:04X})"
        except Exception:
            return f"Apple Device (PID=0x{self._device.idProduct:04X})"
