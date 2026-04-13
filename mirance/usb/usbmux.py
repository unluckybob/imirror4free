"""
Minimal USB Multiplexer (usbmuxd) session for Valeria compatibility.

The iPhone's Valeria AV firmware requires an active usbmuxd session on the
USB multiplexer interface BEFORE it will send CWPA after the initial PING.
Without this session, the iPhone echoes PING but stalls the endpoint ~19s
later with [Errno 32] Pipe error — it's waiting for a host usbmuxd connection
that never comes.

This module implements just enough of the usbmux protocol to satisfy the
iPhone's state machine:
  1. Claim Interface 0 (the usbmux bulk interface in QT Config 5)
  2. Send a plist-format "Hello" to establish version negotiation
  3. Drain the IN endpoint in a background thread (keepalive)

References:
  - libimobiledevice usbmuxd protocol (https://github.com/libimobiledevice/usbmuxd)
  - chotgpt/quicktime_video_hack_windows (custom usbmuxd.exe for Windows)
  - Root cause analysis: IMIRROR_POST_PING_DIAGNOSIS.md
"""

import logging
import plistlib
import struct
import threading
import time
from typing import Optional

logger = logging.getLogger(__name__)

# usbmux header format: (length, version, type, tag) all uint32 little-endian
_HEADER_FMT = "<IIII"
_HEADER_SIZE = struct.calcsize(_HEADER_FMT)  # 16 bytes

# Protocol constants
USBMUX_VERSION_PLIST = 1   # plist-based protocol version
USBMUX_TYPE_PLIST    = 8   # message type for plist payloads

# usbmux interface USB class/subclass/protocol identifiers
USBMUX_CLASS    = 0xFF
USBMUX_SUBCLASS = 0xFE
USBMUX_PROTOCOL = 0x02


def _pack_plist_message(tag: int, payload: dict) -> bytes:
    """Pack a usbmux plist message with 16-byte header."""
    plist_data = plistlib.dumps(payload, fmt=plistlib.FMT_XML)
    total_len = _HEADER_SIZE + len(plist_data)
    header = struct.pack(
        _HEADER_FMT,
        total_len,
        USBMUX_VERSION_PLIST,
        USBMUX_TYPE_PLIST,
        tag,
    )
    return header + plist_data


def _hello_packet() -> bytes:
    """Build the usbmux 'Hello' handshake packet."""
    return _pack_plist_message(1, {
        "BundleID": "org.libimobiledevice.usbmuxd",
        "ClientVersionString": "usbmuxd-374.70",
        "MessageType": "Hello",
        "ProgName": "mirance",
        "kLibUSBMuxVersion": 3,
    })


class UsbMuxSession:
    """
    Minimal usbmuxd session on the iPhone's USB multiplexer interface.

    Satisfies the iPhone Valeria firmware's requirement for an active host
    usbmuxd connection during streaming.  Without this, the iPhone echoes
    PING but never sends CWPA — it stalls ~19 s later with Errno 32 Pipe error.

    Protocol flow:
      1. Find usbmux interface in active USB configuration
         (Class=0xFF SubClass=0xFE Proto=0x02, falls back to Interface 0)
      2. Claim the interface
      3. Send plist Hello on bulk OUT
      4. Drain bulk IN in a background keepalive thread

    Usage::

        session = UsbMuxSession(usb_device)
        if session.start():
            session.wait_ready(timeout=3.0)
        # ... run Valeria protocol ...
        session.stop()
    """

    def __init__(self, dev):
        """
        Args:
            dev: usb.core.Device — the same device object used by USBEndpoint.
        """
        self._dev          = dev
        self._intf_num: Optional[int] = None
        self._ep_in        = None
        self._ep_out       = None
        self._stop_event   = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._ready        = threading.Event()

    # ── Public API ─────────────────────────────────────────────────

    def start(self) -> bool:
        """Find and claim the usbmux interface, then start the keepalive thread.

        Returns True if the interface was found and claimed.
        Non-blocking — the keepalive runs in the background.
        """
        if not self._find_and_claim_interface():
            return False

        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._keepalive_loop,
            name="usbmux-keepalive",
            daemon=True,
        )
        self._thread.start()
        return True

    def stop(self) -> None:
        """Signal the keepalive thread to stop and release the interface."""
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=3.0)
            self._thread = None

        if self._intf_num is not None and self._dev:
            try:
                import usb.util
                usb.util.release_interface(self._dev, self._intf_num)
                logger.debug(
                    "UsbMuxSession: released interface %d", self._intf_num
                )
            except Exception:
                pass
        self._intf_num = None
        self._ep_in    = None
        self._ep_out   = None

    def wait_ready(self, timeout: float = 3.0) -> bool:
        """Block until the hello handshake completes (or timeout elapses)."""
        return self._ready.wait(timeout=timeout)

    # ── Private ────────────────────────────────────────────────────

    def _find_and_claim_interface(self) -> bool:
        """Locate the usbmux interface in the active config and claim it."""
        import usb.util

        if not self._dev:
            logger.warning("UsbMuxSession: no USB device provided")
            return False

        # Get active configuration
        try:
            cfg = self._dev.get_active_configuration()
        except Exception as e:
            logger.warning("UsbMuxSession: get_active_configuration: %s", e)
            return False

        # Look for USB mux interface by class/subclass/protocol
        intf = None
        for i in cfg:
            if (i.bInterfaceClass    == USBMUX_CLASS
                    and i.bInterfaceSubClass == USBMUX_SUBCLASS
                    and i.bInterfaceProtocol == USBMUX_PROTOCOL):
                intf = i
                logger.debug(
                    "UsbMuxSession: found usbmux interface %d "
                    "(Class=0x%02X Sub=0x%02X Proto=0x%02X)",
                    i.bInterfaceNumber,
                    i.bInterfaceClass,
                    i.bInterfaceSubClass,
                    i.bInterfaceProtocol,
                )
                break

        # Fallback: interface 0 is always the mux interface in QT Config 5
        if intf is None:
            logger.debug(
                "UsbMuxSession: no exact usbmux interface — trying Interface 0"
            )
            try:
                intf = cfg[(0, 0)]
            except Exception as e:
                logger.warning("UsbMuxSession: Interface 0 not found: %s", e)
                return False

        if intf is None:
            logger.warning("UsbMuxSession: no usable interface found")
            return False

        self._intf_num = intf.bInterfaceNumber

        # Find bulk IN and OUT endpoints
        self._ep_in = usb.util.find_descriptor(
            intf,
            custom_match=lambda e: (
                usb.util.endpoint_direction(e.bEndpointAddress)
                    == usb.util.ENDPOINT_IN
                and usb.util.endpoint_type(e.bmAttributes)
                    == usb.util.ENDPOINT_TYPE_BULK
            ),
        )
        self._ep_out = usb.util.find_descriptor(
            intf,
            custom_match=lambda e: (
                usb.util.endpoint_direction(e.bEndpointAddress)
                    == usb.util.ENDPOINT_OUT
                and usb.util.endpoint_type(e.bmAttributes)
                    == usb.util.ENDPOINT_TYPE_BULK
            ),
        )

        if not self._ep_in or not self._ep_out:
            logger.warning(
                "UsbMuxSession: bulk endpoints not found on interface %d "
                "(IN=%s OUT=%s) — claiming anyway; just holding the interface "
                "may satisfy the iPhone's state machine",
                self._intf_num, self._ep_in, self._ep_out,
            )

        # Detach kernel driver if needed (Linux/macOS)
        try:
            if self._dev.is_kernel_driver_active(self._intf_num):
                self._dev.detach_kernel_driver(self._intf_num)
                logger.debug(
                    "UsbMuxSession: detached kernel driver from interface %d",
                    self._intf_num,
                )
        except (NotImplementedError, Exception):
            pass  # not supported on Windows

        # Claim the interface
        try:
            usb.util.claim_interface(self._dev, self._intf_num)
            logger.info(
                "UsbMuxSession: claimed interface %d", self._intf_num
            )
        except Exception as e:
            logger.warning(
                "UsbMuxSession: claim interface %d failed: %s "
                "(iPhone may still proceed — Valeria sometimes works "
                "without explicit usbmux claim on this platform)",
                self._intf_num, e,
            )
            self._intf_num = None
            return False

        # Clear any stale stalls on both endpoints
        for ep in (self._ep_in, self._ep_out):
            if ep is not None:
                try:
                    import usb.control as _usb_ctrl
                    _usb_ctrl.clear_stall(self._dev, ep)
                except Exception:
                    pass

        return True

    def _keepalive_loop(self) -> None:
        """Background thread: send hello and drain IN endpoint continuously."""

        # ── Send Hello ──────────────────────────────────────────────
        if self._ep_out is not None:
            try:
                hello = _hello_packet()
                self._ep_out.write(hello, timeout=3000)
                logger.info(
                    "UsbMuxSession: sent Hello on interface %d (%d bytes)",
                    self._intf_num, len(hello),
                )
            except Exception as e:
                logger.warning(
                    "UsbMuxSession: Hello send failed: %s "
                    "(interface still claimed — may be enough)",
                    e,
                )
        else:
            logger.debug(
                "UsbMuxSession: no OUT endpoint — skipping Hello send; "
                "interface %d is claimed and held open",
                self._intf_num,
            )

        # ── Read Hello response ─────────────────────────────────────
        if self._ep_in is not None:
            try:
                resp = self._ep_in.read(4096, timeout=3000)
                logger.info(
                    "UsbMuxSession: Hello response received (%d bytes)",
                    len(resp),
                )
            except Exception as e:
                logger.debug("UsbMuxSession: Hello response read: %s", e)

        # Signal that the session handshake is done (success or not)
        self._ready.set()

        # ── Keepalive drain loop ────────────────────────────────────
        # Continuously drain the IN endpoint to keep the interface "active"
        # in the iPhone's state machine while Valeria runs on Interface 2.
        while not self._stop_event.is_set():
            if self._ep_in is not None:
                try:
                    self._ep_in.read(4096, timeout=500)
                except Exception:
                    pass
            else:
                # No endpoint — just keep the interface claimed
                time.sleep(0.5)
