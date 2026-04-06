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

        Returns True if the Valeria AV interface (SubClass 0x2A) is accessible.

        On Windows/WinUSB, iterating all USB configurations often fails because
        WinUSB only exposes the active configuration.  We therefore check the
        active configuration first via get_active_configuration(), which issues
        a real GET_CONFIGURATION control request and is reliable on all platforms.
        """
        if not self._dev:
            return False

        # Method 1 — check the active configuration (reliable on Windows/WinUSB)
        try:
            cfg = self._dev.get_active_configuration()
            for intf in cfg:
                if intf.bInterfaceSubClass == QT_SUBCLASS:
                    logger.debug(
                        "QT AV interface found in active config %d, Interface %d",
                        cfg.bConfigurationValue, intf.bInterfaceNumber,
                    )
                    return True
        except Exception as e:
            logger.debug("get_active_configuration: %s", e)

        # Method 2 — iterate all configurations (Linux/macOS fallback)
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
            logger.debug("Cannot enumerate all configs: %s", e)

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

    def wait_for_reenumeration(self, timeout: float = 30.0) -> bool:
        """Wait for the iPhone to re-enumerate with QT AV config.

        After enable_qt_config(), the iPhone disconnects and reconnects
        with Configuration 5 active. This method polls until the new
        device appears with the AV interface.

        On Windows, the re-enumeration is a two-stage process:
          1. iPhone disconnects and reconnects on the USB bus (~1–2 s)
          2. WinUSB installs/binds the driver for the new configuration
             (~3–5 s) before the interface is accessible via libusb

        Calling set_configuration() more than once during this window
        causes the iPhone to reset again (another disconnect/reconnect),
        resetting the countdown. We therefore call set_configuration()
        exactly ONCE per device appearance and then wait 3 s for WinUSB
        to complete driver binding before checking has_qt_config().

        Args:
            timeout: Maximum seconds to wait (default raised to 30 s to
                     accommodate Windows WinUSB two-stage binding).

        Returns:
            True if the device was found with QT config active.
        """
        import usb.core

        logger.info("Waiting up to %.0fs for iPhone to re-enumerate...", timeout)

        # Brief pause for the iPhone to begin re-enumeration.
        # USB trace shows re-enumeration completes in ~1-2s on most devices.
        time.sleep(0.5)

        start = time.monotonic()
        attempt = 0

        # Track whether set_configuration() has been called for the current
        # device appearance, so we never call it twice on the same handle.
        set_config_attempted = False

        # Initialize backend ONCE before the loop.  Re-initializing on every
        # iteration (previous behaviour) can interfere with WinUSB driver
        # binding on Windows; we only re-init when the device disappears.
        self._init_backend()

        while time.monotonic() - start < timeout:
            attempt += 1
            time.sleep(0.5)

            kwargs = {"idVendor": APPLE_VENDOR_ID, "find_all": True}
            if self._backend:
                kwargs["backend"] = self._backend

            try:
                devices = list(usb.core.find(**kwargs))
            except Exception:
                logger.debug("Re-enum attempt %d: usb.core.find error", attempt)
                # Re-init backend on find error (stale device list)
                self._init_backend()
                continue

            if not devices:
                logger.debug("Re-enum attempt %d: device not yet back", attempt)
                # Device has gone away again — reset state and refresh backend
                set_config_attempted = False
                self._init_backend()
                continue

            self._dev = devices[0]

            # ── Check if QT config is ALREADY active ────────────────
            # After re-enumeration the iPhone typically comes back with
            # Configuration 5 already selected by the time WinUSB finishes
            # driver binding.  If has_qt_config() returns True we're done.
            if self.has_qt_config():
                logger.info(
                    "Re-enumeration complete (attempt %d, %.1fs) "
                    "— QT AV config active",
                    attempt, time.monotonic() - start,
                )
                return True

            # ── Config not yet active — call set_configuration() ONCE ──
            # We call it once and then give WinUSB 3 seconds to finish
            # binding the interface.  Calling it again immediately (old
            # behaviour) would reset the iPhone and restart the whole
            # re-enumeration cycle, which is why the 15 s timeout was
            # always hit even when the iPhone came back in ~1 second.
            if not set_config_attempted:
                try:
                    self._dev.set_configuration(QT_CONFIG_VALUE)
                    logger.debug(
                        "Re-enum attempt %d: set_configuration(%d) sent — "
                        "waiting 3 s for WinUSB driver binding",
                        attempt, QT_CONFIG_VALUE,
                    )
                except Exception as set_cfg_err:
                    logger.debug(
                        "Re-enum attempt %d: set_configuration(%d): %s",
                        attempt, QT_CONFIG_VALUE, set_cfg_err,
                    )
                set_config_attempted = True
                # Sleep here (inside the loop) — the main loop sleep of 0.5 s
                # is not enough; WinUSB binding typically takes 2–4 s.
                time.sleep(3.0)
                continue  # Re-check has_qt_config on the next iteration

            logger.debug(
                "Re-enum attempt %d: device present, QT config not yet detected "
                "(WinUSB still binding — will retry)",
                attempt,
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

        # ── Step 1: Activate QT AV configuration (only if not already active) ──
        # On Windows/WinUSB, calling set_configuration() when QT config is
        # already active causes WinUSB to re-initialize the driver binding for
        # the interface. This breaks any existing WinUSB binding and causes
        # claim_interface() to fail with [Errno 2] Entity not found, because
        # the re-binding has not completed by the time we try to claim.
        # It also resets the iPhone's internal Valeria state machine — after
        # the config reset the iPhone no longer sends PING, so the protocol
        # loop waits forever and eventually gets a pipe error.
        if not self.has_qt_config():
            try:
                self._dev.set_configuration(QT_CONFIG_VALUE)
                logger.debug("Set USB configuration %d (QT AV mode)", QT_CONFIG_VALUE)
            except Exception as e:
                logger.debug(
                    "set_configuration(%d): %s (may already be set)", QT_CONFIG_VALUE, e
                )
        else:
            logger.debug(
                "QT AV configuration already active — skipping set_configuration() "
                "to preserve iPhone Valeria state and WinUSB driver binding"
            )

        # ── Step 2: Find the AV interface ───────────────────────────────
        # Use get_active_configuration() first — on Windows/WinUSB,
        # iterating all configurations often fails.
        try:
            cfg = self._dev.get_active_configuration()
            for intf in cfg:
                if intf.bInterfaceSubClass == QT_SUBCLASS:
                    self._interface = intf
                    break
        except Exception:
            pass

        if not self._interface:
            try:
                for cfg in self._dev:
                    for intf in cfg:
                        if intf.bInterfaceSubClass == QT_SUBCLASS:
                            self._interface = intf
                            break
                    if self._interface:
                        break
            except Exception:
                pass

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

        # Claim the interface — retry up to 3 times for transient failures.
        # On Windows, the WinUSB driver binding may not be complete
        # immediately after set_configuration() or device re-enumeration.
        claimed = False
        for claim_attempt in range(3):
            try:
                usb.util.claim_interface(self._dev, intf_num)
                logger.info("Claimed interface %d", intf_num)
                claimed = True
                break
            except Exception as e:
                if claim_attempt < 2:
                    logger.debug(
                        "Claim attempt %d/3 for interface %d failed: %s — retrying",
                        claim_attempt + 1, intf_num, e,
                    )
                    time.sleep(0.5)
                else:
                    logger.error("Failed to claim interface %d: %s", intf_num, e)

        if not claimed:
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
