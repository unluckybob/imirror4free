"""
USB Endpoint Manager — Low-level USB communication for Valeria streaming.

Handles:
- Finding Apple iPhone devices on the USB bus via pyusb/libusb
- Enabling QT AV configuration (USB control transfer to switch modes)
- Claiming the AV bulk interface (Configuration 5, Interface 2, SubClass 0x2A)
- Reading and writing raw bytes over bulk endpoints
- Waiting for device re-enumeration after configuration changes

This is the layer between the OS-level USB driver (WinUSB / libusb)
and the Valeria protocol layer in valeria.py.
"""

import logging
import platform
import struct
import time
from typing import Optional

logger = logging.getLogger(__name__)

# Apple USB vendor ID
APPLE_VENDOR_ID = 0x05AC

# QT AV interface identifier (SubClass 0x2A = Valeria video/audio)
QT_SUBCLASS = 0x2A

# Configuration number for the QT AV mode
QT_CONFIG_VALUE = 5

# USB control transfer constants for QT mode switching
QT_SET_CONFIG_BMREQUEST_TYPE = 0x40  # Vendor request, Host→Device
QT_SET_CONFIG_BREQUEST = 0x52       # 'R' — request QT mode
QT_SET_CONFIG_WVALUE = 0x00
QT_SET_CONFIG_WINDEX = 0x02


class USBEndpoint:
    """
    Manages raw USB communication to an iPhone for Valeria streaming.

    Usage:
        ep = USBEndpoint()
        if ep.find_iphone():
            if not ep.has_qt_config():
                ep.enable_qt_config()
                ep.wait_for_reenumeration()
            ep.claim_av_endpoints()
            data = ep.read(65536)
            ep.write(response_bytes)
    """

    def __init__(self):
        self._dev = None           # usb.core.Device
        self._backend = None       # libusb backend
        self._ep_in = None         # Bulk IN endpoint object
        self._ep_out = None        # Bulk OUT endpoint object
        self._interface = None     # The claimed AV interface
        self._is_connected = False
        self._device_info = "No device"

        self._init_backend()

    @property
    def is_connected(self) -> bool:
        return self._is_connected

    @property
    def device_info(self) -> str:
        return self._device_info

    def _init_backend(self) -> None:
        """Initialize the libusb backend."""
        try:
            if platform.system() == "Windows":
                try:
                    import libusb_package
                    self._backend = libusb_package.get_libusb1_backend()
                    if self._backend:
                        logger.debug("Using libusb-package backend")
                        return
                except ImportError:
                    pass

            import usb.backend.libusb1
            self._backend = usb.backend.libusb1.get_backend()
            if self._backend:
                logger.debug("Using system libusb1 backend")
            else:
                logger.warning("No libusb backend found — USB access will fail")

        except Exception as e:
            logger.error("Failed to initialize USB backend: %s", e)

    def find_iphone(self) -> bool:
        """Find an Apple iPhone on the USB bus.

        Returns True if an Apple device is found and accessible.
        """
        import usb.core

        kwargs = {"idVendor": APPLE_VENDOR_ID, "find_all": True}
        if self._backend:
            kwargs["backend"] = self._backend

        devices = list(usb.core.find(**kwargs))

        if not devices:
            logger.debug("No Apple USB devices found")
            return False

        self._dev = devices[0]

        try:
            product = self._dev.product or "Apple Device"
        except Exception:
            product = "Apple Device"

        self._device_info = (
            f"{product} (VID=0x{self._dev.idVendor:04X} "
            f"PID=0x{self._dev.idProduct:04X})"
        )

        logger.info("Found: %s", self._device_info)
        return True

    def has_qt_config(self) -> bool:
        """Check if the iPhone currently has the QT AV configuration active.

        Returns True if Configuration 5 with SubClass 0x2A is present
        and the AV interface is accessible.
        """
        if not self._dev:
            return False

        try:
            for cfg in self._dev:
                for intf in cfg:
                    if intf.bInterfaceSubClass == QT_SUBCLASS:
                        logger.debug(
                            "QT AV interface found: Config %d, Interface %d",
                            cfg.bConfigurationValue, intf.bInterfaceNumber,
                        )
                        return True
        except Exception as e:
            logger.debug("Cannot enumerate configs: %s", e)

        return False

    def enable_qt_config(self) -> bool:
        """Send a USB control transfer to enable QT AV mode.

        This tells the iPhone to expose Configuration 5 with the
        Valeria AV interface. The iPhone will disconnect and
        reconnect with the new configuration — you must call
        wait_for_reenumeration() afterward.

        Returns True if the control transfer was sent successfully.
        """
        if not self._dev:
            logger.error("No device — cannot enable QT config")
            return False

        try:
            logger.info("Sending QT mode enable control transfer...")

            # Vendor-specific control transfer to request QT mode
            self._dev.ctrl_transfer(
                bmRequestType=QT_SET_CONFIG_BMREQUEST_TYPE,
                bRequest=QT_SET_CONFIG_BREQUEST,
                wValue=QT_SET_CONFIG_WVALUE,
                wIndex=QT_SET_CONFIG_WINDEX,
                data_or_wLength=0,
                timeout=5000,
            )

            logger.info("QT mode enable command sent — iPhone will re-enumerate")
            return True

        except Exception as e:
            logger.error("Failed to send QT enable command: %s", e)

            # Provide actionable error message
            if "Access denied" in str(e) or "permission" in str(e).lower():
                logger.error(
                    "Access denied — the WinUSB mirror driver may not be installed. "
                    "Install the mirror driver through the IMIRROR4FREE app, or manually "
                    "via Zadig (https://zadig.akeo.ie/)."
                )
            elif "Entity not found" in str(e) or "No such device" in str(e):
                logger.error(
                    "Device not found — iPhone may have disconnected. "
                    "Reconnect the USB cable and try again."
                )

            return False

    def wait_for_reenumeration(self, timeout: float = 15.0) -> bool:
        """Wait for the iPhone to re-enumerate with QT AV config.

        After enable_qt_config(), the iPhone disconnects and reconnects
        with Configuration 5 active. This method polls until the new
        device appears with the AV interface.

        Args:
            timeout: Maximum seconds to wait.

        Returns:
            True if the device was found with QT config active.
        """
        import usb.core

        logger.info("Waiting up to %.0fs for iPhone to re-enumerate...", timeout)

        # Brief pause for the iPhone to begin re-enumeration.
        # USB trace shows re-enumeration completes in ~2.4s; the device
        # disappears almost immediately, so 0.3s is enough before polling.
        time.sleep(0.3)

        start = time.monotonic()
        attempt = 0

        while time.monotonic() - start < timeout:
            attempt += 1
            time.sleep(0.5)

            kwargs = {"idVendor": APPLE_VENDOR_ID, "find_all": True}
            if self._backend:
                kwargs["backend"] = self._backend

            devices = list(usb.core.find(**kwargs))

            if not devices:
                logger.debug("Re-enum attempt %d: device not yet back", attempt)
                continue

            self._dev = devices[0]

            if self.has_qt_config():
                logger.info(
                    "Re-enumeration complete (attempt %d, %.1fs) — QT AV config active",
                    attempt, time.monotonic() - start,
                )
                return True
            else:
                logger.debug(
                    "Re-enum attempt %d: device found but no QT config yet", attempt
                )

        logger.error("Re-enumeration timed out after %.0fs", timeout)
        return False

    def claim_av_endpoints(self) -> bool:
        """Claim the AV bulk interface and get endpoint references.

        Finds the Valeria AV interface (SubClass 0x2A), detaches
        any kernel driver, claims the interface, and stores references
        to the bulk IN and OUT endpoints for read()/write().

        Returns True if endpoints are ready for communication.
        """
        import usb.core
        import usb.util

        if not self._dev:
            return False

        # Find the AV interface
        for cfg in self._dev:
            for intf in cfg:
                if intf.bInterfaceSubClass == QT_SUBCLASS:
                    self._interface = intf
                    break
            if self._interface:
                break

        if not self._interface:
            logger.error("No AV interface (SubClass 0x2A) found")
            return False

        intf_num = self._interface.bInterfaceNumber
        logger.info(
            "Claiming AV interface %d (SubClass 0x%02X, %d endpoints)",
            intf_num, self._interface.bInterfaceSubClass,
            self._interface.bNumEndpoints,
        )

        # Detach kernel driver if necessary (Linux/macOS)
        try:
            if self._dev.is_kernel_driver_active(intf_num):
                self._dev.detach_kernel_driver(intf_num)
                logger.info("Detached kernel driver from interface %d", intf_num)
        except (NotImplementedError, Exception):
            pass  # Not supported on Windows

        # Set configuration if needed
        try:
            cfg_value = self._interface.device.configurations()[0].bConfigurationValue
            for cfg in self._dev:
                if self._interface in cfg:
                    cfg_value = cfg.bConfigurationValue
                    break
            self._dev.set_configuration(cfg_value)
            logger.debug("Set USB configuration %d", cfg_value)
        except Exception as e:
            logger.debug("set_configuration: %s (may already be set)", e)

        # Claim the interface
        try:
            usb.util.claim_interface(self._dev, intf_num)
            logger.info("Claimed interface %d", intf_num)
        except Exception as e:
            logger.error("Failed to claim interface %d: %s", intf_num, e)
            return False

        # Select alternate setting — USB trace analysis shows 4 ×
        # SELECT_INTERFACE calls.  Explicitly selecting alt setting 0
        # ensures the Valeria bulk endpoints are activated and matches
        # the observed protocol behaviour.
        try:
            alt_setting = self._interface.bAlternateSetting
            self._dev.set_interface_altsetting(
                interface=intf_num,
                alternate_setting=alt_setting,
            )
            logger.debug(
                "Set alternate setting %d on interface %d",
                alt_setting, intf_num,
            )
        except Exception as e:
            logger.debug("set_interface_altsetting: %s (non-fatal)", e)

        # Find bulk IN and OUT endpoints
        self._ep_in = usb.util.find_descriptor(
            self._interface,
            custom_match=lambda e: (
                usb.util.endpoint_direction(e.bEndpointAddress) == usb.util.ENDPOINT_IN
                and usb.util.endpoint_type(e.bmAttributes) == usb.util.ENDPOINT_TYPE_BULK
            ),
        )
        self._ep_out = usb.util.find_descriptor(
            self._interface,
            custom_match=lambda e: (
                usb.util.endpoint_direction(e.bEndpointAddress) == usb.util.ENDPOINT_OUT
                and usb.util.endpoint_type(e.bmAttributes) == usb.util.ENDPOINT_TYPE_BULK
            ),
        )

        if not self._ep_in or not self._ep_out:
            logger.error(
                "AV endpoints not found! IN=%s, OUT=%s",
                self._ep_in, self._ep_out,
            )
            return False

        logger.info(
            "Endpoints ready: IN=0x%02X (%d byte max), OUT=0x%02X (%d byte max)",
            self._ep_in.bEndpointAddress, self._ep_in.wMaxPacketSize,
            self._ep_out.bEndpointAddress, self._ep_out.wMaxPacketSize,
        )

        self._is_connected = True
        return True

    def read(self, size: int = 65536, timeout: int = 1000) -> Optional[bytes]:
        """Read from the AV bulk IN endpoint.

        Args:
            size: Maximum bytes to read.
            timeout: Timeout in milliseconds.

        Returns:
            Bytes read, or None on error.
        """
        if not self._ep_in:
            return None

        try:
            data = self._ep_in.read(size, timeout=timeout)
            if data is not None:
                return bytes(data)
            return None
        except Exception:
            raise  # Let caller handle USBTimeoutError vs USBError

    def write(self, data: bytes, timeout: int = 1000) -> int:
        """Write to the AV bulk OUT endpoint.

        Args:
            data: Bytes to write.
            timeout: Timeout in milliseconds.

        Returns:
            Number of bytes written.
        """
        if not self._ep_out:
            return 0

        return self._ep_out.write(data, timeout=timeout)

    def close(self) -> None:
        """Release the USB interface and clean up."""
        import usb.util

        if self._interface and self._dev:
            try:
                usb.util.release_interface(
                    self._dev, self._interface.bInterfaceNumber
                )
                logger.info("Released USB interface")
            except Exception:
                pass

        self._ep_in = None
        self._ep_out = None
        self._interface = None
        self._is_connected = False
        self._dev = None
