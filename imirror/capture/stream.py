"""
Valeria Stream Capture Backend (Phase 2).

Uses the Valeria protocol to receive a true H.264/HEVC video stream
from the iPhone over USB. This is the high-performance backend that
delivers 30-60 FPS at native resolution with minimal latency.

This is the same protocol that QuickTime and AnyMiro use.

Status: In Development
- Protocol packet handling: ✅ Complete
- USB endpoint communication: 🔧 Requires platform-specific driver setup
- H.264 decode pipeline: ✅ Complete (via PyAV)
- Windows driver integration: 🔧 Requires WinUSB/Zadig setup

Prerequisites for Phase 2:
1. Install Zadig (https://zadig.akeo.ie/)
2. Replace iPhone AV interface driver with WinUSB
3. This allows pyusb to access the hidden QT USB endpoints
"""

import logging
import threading
import time
from typing import Optional

import numpy as np

from imirror.capture.base import CaptureBackend, CapturedFrame

logger = logging.getLogger(__name__)


class ValeriaStreamCapture(CaptureBackend):
    """
    High-performance capture backend using the Valeria protocol.

    Receives H.264 video frames directly from the iPhone over USB
    bulk endpoints, decodes them with GPU-accelerated FFmpeg, and
    delivers pixel buffers to the renderer.
    """

    def __init__(self):
        super().__init__()
        self._thread: Optional[threading.Thread] = None

    @property
    def name(self) -> str:
        return "Valeria Stream (H.264)"

    @property
    def max_fps(self) -> int:
        return 60

    def is_available(self) -> bool:
        """Check if raw USB access is available (requires WinUSB driver)."""
        try:
            import usb.core
            # Try to find an Apple device with the QT config
            dev = usb.core.find(idVendor=0x05AC)
            if dev is None:
                logger.debug("Valeria: No Apple USB device found via pyusb")
                return False

            # Check if the device has the hidden QT configuration
            # (SubClass 0x2A on the AV interface)
            for cfg in dev:
                for intf in cfg:
                    if intf.bInterfaceSubClass == 0x2A:
                        logger.info("Valeria: Found active QT USB configuration!")
                        return True

            logger.debug("Valeria: Apple device found but QT config not active")
            return False

        except Exception as e:
            logger.debug("Valeria: Not available — %s", e)
            return False

    def start(self, device_udid: str) -> bool:
        """Start the Valeria stream capture.

        TODO Phase 2:
        1. Enable hidden QT USB configuration via control request
        2. Claim AV bulk endpoints
        3. Perform PING handshake
        4. Handle SYNC exchanges
        5. Start receiving FEED/EAT packets
        """
        logger.warning(
            "⚠️ Valeria Stream backend is in development. "
            "Falling back to Screenshot backend."
        )
        return False

    def stop(self) -> None:
        """Stop the Valeria stream."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=3.0)
            self._thread = None

    def _stream_loop(self) -> None:
        """Main streaming loop — reads from USB bulk endpoints.

        TODO Phase 2: Implement full USB communication:
        1. Read raw bytes from AV bulk IN endpoint
        2. Accumulate into complete packets (length-prefixed)
        3. Parse packets via read_packet()
        4. Route to ValeriaSession.handle_packet()
        5. Send responses to AV bulk OUT endpoint
        6. Decode H.264 FEED data via PyAV
        7. Convert to CapturedFrame and emit
        """
        pass
