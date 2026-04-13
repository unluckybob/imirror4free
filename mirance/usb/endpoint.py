"""
USB Endpoint Manager — Low-level USB communication for Valeria streaming.

Handles:
- Finding Apple iPhone devices on the USB bus via pyusb/libusb
- Enabling QT AV configuration (USB control transfer to switch modes)
- Claiming the AV bulk interface (Configuration 5, Interface 2, SubClass 0x2A)
- Reading and writing raw bytes over bulk endpoints
- Waiting for device re-enumeration after configuration changes

This is the layer between the OS-level USB driver (libusb-win32 / libusb0)
and the Valeria protocol layer in valeria.py.

On Windows, we use libusb-win32 (libusb0) — the same driver backend that
MIRANCE uses. The device must have libusb0.sys bound (shown in Device Manager
as "LIBUSB-WIN32 DEVICES" → service: libusb0). This is installed automatically
by MIRANCE or via the MIRANCE driver installer.
"""

import logging
import os
import platform
import struct
import time
from typing import Optional

logger = logging.getLogger(__name__)

# Apple USB vendor ID
APPLE_VENDOR_ID = 0x05AC


def _find_libusb0_dll() -> Optional[str]:
    """Find libusb0.dll (libusb-win32) on Windows.

    Checks MIRANCE's installation directory first (it bundles the DLL),
    then common system paths where libusb-win32 installs itself.

    Returns:
        Absolute path to libusb0.dll, or None to let PyUSB search PATH.
    """
    if platform.system() != "Windows":
        return None

    candidates = [
        # MIRANCE bundles libusb0.dll in its usbmuxd subfolder
        os.path.join(os.environ.get("ProgramFiles(x86)", ""), "MIRANCE", "usbmuxd", "libusb0.dll"),
        os.path.join(os.environ.get("ProgramFiles", ""), "MIRANCE", "usbmuxd", "libusb0.dll"),
        # System paths (libusb-win32 installs here)
        os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", "libusb0.dll"),
        os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "SysWOW64", "libusb0.dll"),
        # libusb-win32 default install
        os.path.join(os.environ.get("ProgramFiles(x86)", ""), "LibUSB-Win32", "bin", "x64", "libusb0.dll"),
        os.path.join(os.environ.get("ProgramFiles(x86)", ""), "LibUSB-Win32", "bin", "x86", "libusb0.dll"),
    ]

    for path in candidates:
        if path and os.path.exists(path):
            logger.debug("Found libusb0.dll at: %s", path)
            return path

    # Not found in known locations — let PyUSB search PATH automatically
    return None

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
        """Initialize the libusb backend.

        On Windows, prefers libusb-win32 (libusb0) which is what MIRANCE
        installs. This backend communicates with devices whose service is
        set to 'libusb0' (visible in Device Manager under LIBUSB-WIN32 DEVICES).

        Falls back to libusb1 on non-Windows platforms (Linux/macOS).
        """
        try:
            if platform.system() == "Windows":
                # Primary: libusb-win32 (libusb0) — matches MIRANCE's driver
                dll_path = _find_libusb0_dll()
                try:
                    import usb.backend.libusb0 as _lb0
                    find_lib = (lambda x: dll_path) if dll_path else None
                    self._backend = _lb0.get_backend(find_library=find_lib)
                    if self._backend:
                        logger.debug("Using libusb-win32 (libusb0) backend%s",
                                     f" [{dll_path}]" if dll_path else "")
                        return
                    else:
                        logger.debug("libusb0 backend returned None — libusb0.dll not found?")
                except Exception as e:
                    logger.debug("libusb0 backend init failed: %s", e)

                # Fallback: libusb1 — for non-Windows platforms or edge cases
                try:
                    import usb.backend.libusb1 as _lb1
                    self._backend = _lb1.get_backend()
                    if self._backend:
                        logger.debug("Using libusb1 backend as fallback (non-Windows / edge case)")
                        return
                except Exception as e:
                    logger.debug("libusb1 fallback init failed: %s", e)

                logger.warning(
                    "No libusb backend found on Windows. "
                    "Ensure libusb-win32 is installed (MIRANCE installs it automatically). "
                    "Run the MIRANCE driver installer to set it up."
                )
                return

            # Non-Windows: use libusb1 (standard backend for Linux/macOS)
            import usb.backend.libusb1
            self._backend = usb.backend.libusb1.get_backend()
            if self._backend:
                logger.debug("Using system libusb1 backend (non-Windows)")
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

        Returns True if the Valeria AV interface (SubClass 0x2A) is present
        in the CURRENTLY ACTIVE USB configuration.

        On Windows/libusb-win32, iterating all USB configurations often fails because
        libusb-win32 only exposes the active configuration.  We therefore check the
        active configuration first via get_active_configuration(), which issues
        a real GET_CONFIGURATION control request and is reliable on all platforms.

        IMPORTANT: We deliberately do NOT fall back to scanning all configurations.
        Scanning all configs produces false positives on Windows — Config 5's
        SubClass 0x2A interface appears in descriptors even when Config 1 is the
        active configuration, causing claim_interface() to fail with [Errno 2]
        because the interface doesn't exist in the active config.
        """
        if not self._dev:
            return False

        # Method 1 — check the active configuration (reliable on Windows/libusb-win32)
        try:
            cfg = self._dev.get_active_configuration()
            for intf in cfg:
                if intf.bInterfaceSubClass == QT_SUBCLASS:
                    logger.debug(
                        "QT AV interface found in active config %d, Interface %d",
                        cfg.bConfigurationValue, intf.bInterfaceNumber,
                    )
                    return True
            # Active config found and fully iterated — no QT interface present.
            # Return False definitively; do NOT fall back to all-configs scan.
            return False
        except Exception as e:
            logger.debug("get_active_configuration: %s", e)

        # Method 2 — iterate all configurations (Linux/macOS only, last resort).
        # On Windows/libusb-win32 this is skipped to avoid false positives where
        # Config 5 descriptors are readable but Config 1 is actually active.
        if platform.system() != "Windows":
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
                    "Access denied — the libusb-win32 driver may not be installed. "
                    "Install the mirror driver through the MIRANCE app. "
                    "The device must appear under 'LIBUSB-WIN32 DEVICES' in Device Manager "
                    "with service 'libusb0'."
                )
            elif "Entity not found" in str(e) or "No such device" in str(e):
                logger.error(
                    "Device not found — iPhone may have disconnected. "
                    "Reconnect the USB cable and try again."
                )

            return False

    def wait_for_reenumeration(self, timeout: float = 30.0) -> bool:
        """Wait for the iPhone to re-enumerate with QT AV config.

        After enable_qt_config(), the iPhone disconnects and reconnects.
        On Windows/libusb-win32, two re-enumeration patterns are observed:

        Pattern A — iPhone auto-selects Config 5:
          The iPhone itself comes back with Config 5 active. libusb-win32 binds
          to interface 2 automatically (~2–5 s).

        Pattern B — iPhone comes back in Config 1, needs set_configuration(5):
          The host must call set_configuration(5) after the iPhone reconnects.
          On some Windows setups this causes a second brief disconnect.

        In both patterns, after the device reappears we:
          1. Re-initialize the libusb backend (clears stale descriptor cache)
          2. Re-find the device with the fresh backend
          3. Wait 3 s for libusb-win32 driver binding to complete
          4. Check has_qt_config() — returns True if Config 5 is active
          5. If has_qt_config() is still False, call set_configuration(5) once
          6. If device has been back for >8 s total, proceed optimistically —
             let claim_av_endpoints() make the final determination

        Args:
            timeout: Maximum seconds to wait (default 30 s).

        Returns:
            True if the device was found or appears to be ready for claiming.
        """
        import usb.core

        logger.info("Waiting up to %.0fs for iPhone to re-enumerate...", timeout)

        # Brief pause for the iPhone to begin disconnect
        time.sleep(0.5)

        start = time.monotonic()
        attempt = 0
        device_was_absent = False
        device_reappeared = False
        reappear_time = None
        set_config_attempted = False

        while time.monotonic() - start < timeout:
            attempt += 1
            time.sleep(0.5)

            kwargs = {"idVendor": APPLE_VENDOR_ID, "find_all": True}
            if self._backend:
                kwargs["backend"] = self._backend

            try:
                devices = list(usb.core.find(**kwargs))
            except Exception:
                logger.debug("Re-enum attempt %d: usb.core.find error — refreshing backend", attempt)
                self._init_backend()
                continue

            if not devices:
                logger.debug("Re-enum attempt %d: device not yet back", attempt)
                device_was_absent = True
                device_reappeared = False
                reappear_time = None
                set_config_attempted = False
                self._init_backend()
                continue

            # ── Device is present ──────────────────────────────────────
            if not device_reappeared:
                # First time we see the device back after being absent.
                # Re-initialize the libusb backend to flush descriptor cache —
                # the old device handle has stale descriptors from before QT enable.
                logger.debug(
                    "Re-enum attempt %d: device reappeared — reinitializing backend "
                    "for fresh descriptors",
                    attempt,
                )
                self._init_backend()
                kwargs_fresh = {"idVendor": APPLE_VENDOR_ID, "find_all": True}
                if self._backend:
                    kwargs_fresh["backend"] = self._backend
                try:
                    fresh_devices = list(usb.core.find(**kwargs_fresh))
                    if fresh_devices:
                        self._dev = fresh_devices[0]
                    else:
                        self._dev = devices[0]
                except Exception:
                    self._dev = devices[0]

                device_reappeared = True
                reappear_time = time.monotonic()

                # Give libusb-win32 time to bind the driver for the new device instance.
                # USB trace analysis shows binding typically takes 2–4 s.
                logger.debug("Re-enum: waiting 3s for libusb-win32 driver binding...")
                time.sleep(3.0)
                continue
            else:
                self._dev = devices[0]

            # ── Check if QT config is active ───────────────────────────
            if self.has_qt_config():
                elapsed = time.monotonic() - start
                elapsed_reappear = time.monotonic() - reappear_time
                logger.info(
                    "Re-enumeration complete (attempt %d, %.1fs total, %.1fs after reappear)"
                    " — QT AV config active",
                    attempt, elapsed, elapsed_reappear,
                )
                return True

            elapsed_reappear = time.monotonic() - reappear_time

            # ── Try set_configuration(5) once ─────────────────────────
            # If the iPhone came back in Config 1, we need to switch manually.
            # Call it once; if it causes another disconnect, device_was_absent
            # will reset set_config_attempted so we can try again after reconnect.
            if not set_config_attempted:
                try:
                    self._dev.set_configuration(QT_CONFIG_VALUE)
                    logger.debug(
                        "Re-enum attempt %d: set_configuration(%d) called — "
                        "waiting 5s for libusb-win32 binding",
                        attempt, QT_CONFIG_VALUE,
                    )
                except Exception as set_cfg_err:
                    logger.debug(
                        "Re-enum attempt %d: set_configuration(%d): %s",
                        attempt, QT_CONFIG_VALUE, set_cfg_err,
                    )
                set_config_attempted = True
                # Increased from 3s to 5s: first-ever Config 5 binding takes
                # longer than subsequent ones because libusb-win32 must install the
                # driver INF for the new interface configuration.
                time.sleep(5.0)
                # Flush descriptor cache after set_configuration() — same as
                # we do on first device reappear — so has_qt_config() sees the
                # newly active configuration rather than a stale cached view.
                self._init_backend()
                kwargs_after_sc = {"idVendor": APPLE_VENDOR_ID, "find_all": True}
                if self._backend:
                    kwargs_after_sc["backend"] = self._backend
                try:
                    import usb.core as _usb_sc
                    sc_devs = list(_usb_sc.find(**kwargs_after_sc))
                    if sc_devs:
                        self._dev = sc_devs[0]
                except Exception:
                    pass
                continue

            # ── Optimistic fallthrough after sufficient wait ───────────
            # has_qt_config() uses get_active_configuration() which may fail on
            # some Windows/libusb-win32 setups even when Config 5 is genuinely active.
            # Threshold raised to 15 s (was 8 s): on first-ever connection libusb-win32
            # needs 10-15 s to bind Config 5's interface for the first time.
            # Keeping the threshold low caused the first attempt to always fail
            # because we bailed out before libusb-win32 finished its driver INF install.
            if elapsed_reappear >= 15.0:
                logger.warning(
                    "Re-enum: has_qt_config() still False after %.1fs since reappear "
                    "— proceeding optimistically (libusb-win32 may have bound Config 5)",
                    elapsed_reappear,
                )
                return True

            logger.debug(
                "Re-enum attempt %d: device present %.1fs after reappear, "
                "QT config not yet detected (will retry)",
                attempt, elapsed_reappear,
            )

        # ── Timeout reached ────────────────────────────────────────────
        # If the device reappeared at any point, proceed optimistically —
        # claim_av_endpoints() will give a clearer error if Config 5 isn't ready.
        if device_reappeared:
            logger.warning(
                "Re-enum: timed out but device DID reappear — "
                "proceeding to claim attempt (libusb-win32 may be ready)"
            )
            return True

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

        # ── Step 1: Activate QT AV configuration ──────────────────────
        # Check if Config 5 is active. If not, activate it.
        # On Windows/libusb-win32, calling set_configuration() when QT config is
        # already active causes libusb-win32 to re-initialize driver binding,
        # which breaks claim_interface(). Only call it when needed.
        if not self.has_qt_config():
            try:
                self._dev.set_configuration(QT_CONFIG_VALUE)
                logger.debug("Set USB configuration %d (QT AV mode)", QT_CONFIG_VALUE)
                # Wait for libusb-win32 to bind to the new configuration
                time.sleep(3.0)
                # Re-init backend to flush descriptor cache after config change
                self._init_backend()
                kwargs = {"idVendor": APPLE_VENDOR_ID, "find_all": True}
                if self._backend:
                    kwargs["backend"] = self._backend
                try:
                    import usb.core as _usb_core
                    devs = list(_usb_core.find(**kwargs))
                    if devs:
                        self._dev = devs[0]
                except Exception:
                    pass
            except Exception as e:
                logger.debug(
                    "set_configuration(%d): %s (may already be set)", QT_CONFIG_VALUE, e
                )
        else:
            logger.debug(
                "QT AV configuration already active — skipping set_configuration() "
                "to preserve iPhone Valeria state and libusb-win32 driver binding"
            )

        # ── Step 2: Find the AV interface ─────────────────────────────
        # Use get_active_configuration() first — on Windows/libusb-win32,
        # iterating all configurations often fails.
        self._interface = self._find_av_interface()

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

        # ── Step 3: Claim the interface ───────────────────────────────
        # Retry with increasing patience. On Windows, libusb-win32 driver binding
        # may not be complete immediately after set_configuration() or
        # device re-enumeration, causing [Errno 2] Entity not found.
        # Strategy:
        #   Attempt 1  — immediate try
        #   Attempt 2  — after set_configuration(5) + 3s wait (in case Config
        #                wasn't switched yet despite has_qt_config() returning True)
        #   Attempts 3-5 — after 2s each (libusb-win32 still binding)
        claimed = False
        for claim_attempt in range(5):
            try:
                usb.util.claim_interface(self._dev, intf_num)
                logger.info("Claimed interface %d (attempt %d)", intf_num, claim_attempt + 1)
                claimed = True
                break
            except Exception as e:
                if claim_attempt == 0:
                    # First failure — try explicit set_configuration(5) +
                    # backend refresh + longer wait before retrying.
                    # This handles the case where has_qt_config() returned True
                    # via a descriptor scan but Config 5 isn't fully bound yet.
                    logger.debug(
                        "Claim attempt 1 failed (%s) — calling set_configuration(%d) "
                        "+ backend refresh + 3s wait",
                        e, QT_CONFIG_VALUE,
                    )
                    try:
                        self._dev.set_configuration(QT_CONFIG_VALUE)
                    except Exception as sc_err:
                        logger.debug("set_configuration: %s (non-fatal)", sc_err)
                    time.sleep(3.0)
                    # Re-init backend and re-find device + interface
                    self._init_backend()
                    kwargs = {"idVendor": APPLE_VENDOR_ID, "find_all": True}
                    if self._backend:
                        kwargs["backend"] = self._backend
                    try:
                        import usb.core as _usb_core2
                        devs = list(_usb_core2.find(**kwargs))
                        if devs:
                            self._dev = devs[0]
                    except Exception:
                        pass
                    # Re-find interface with fresh descriptors
                    fresh_intf = self._find_av_interface()
                    if fresh_intf:
                        self._interface = fresh_intf
                        intf_num = self._interface.bInterfaceNumber
                elif claim_attempt < 4:
                    logger.debug(
                        "Claim attempt %d/5 for interface %d failed: %s — retrying in 2s",
                        claim_attempt + 1, intf_num, e,
                    )
                    time.sleep(2.0)
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

        # Clear any halt/stall on both IN and OUT endpoints.
        # After a [Errno 32] Pipe error the OUT endpoint can remain STALLed,
        # causing subsequent fallback PING writes to time out with [Errno 10060]
        # even though the interface claim succeeded.  Clearing both ensures a
        # clean state for every new connection attempt.
        for _ep_obj, _ep_label in (
            (self._ep_in, "IN"),
            (self._ep_out, "OUT"),
        ):
            try:
                import usb.control as _usb_ctrl
                _usb_ctrl.clear_stall(self._dev, _ep_obj)
                logger.debug(
                    "Cleared stall on %s endpoint 0x%02X",
                    _ep_label, _ep_obj.bEndpointAddress,
                )
            except Exception as _cs_err:
                logger.debug(
                    "clear_stall %s endpoint (non-fatal): %s",
                    _ep_label, _cs_err,
                )

        self._is_connected = True
        return True

    def _find_av_interface(self):
        """Find the AV interface (SubClass 0x2A) in the active configuration.

        Returns the interface object, or None if not found.
        Uses get_active_configuration() only (no all-configs fallback) to
        avoid false positives on Windows where Config 5 descriptors are
        readable even when Config 1 is active.
        """
        if not self._dev:
            return None

        # Method 1: active configuration (correct and reliable)
        try:
            cfg = self._dev.get_active_configuration()
            for intf in cfg:
                if intf.bInterfaceSubClass == QT_SUBCLASS:
                    return intf
        except Exception as e:
            logger.debug("_find_av_interface get_active_configuration: %s", e)

        # Method 2: all configurations (Linux/macOS only — avoids libusb-win32 false positives)
        if platform.system() != "Windows":
            try:
                for cfg in self._dev:
                    for intf in cfg:
                        if intf.bInterfaceSubClass == QT_SUBCLASS:
                            return intf
            except Exception as e:
                logger.debug("_find_av_interface enumerate all configs: %s", e)

        return None

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
