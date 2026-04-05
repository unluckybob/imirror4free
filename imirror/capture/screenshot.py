"""
Screenshot Capture Backend (Phase 1).

Uses pymobiledevice3's DVT ScreenshotService to capture individual
PNG screenshots in a tight loop. This works immediately on all
platforms but is limited to ~10-15 FPS due to the overhead of
taking full-resolution PNG screenshots.

This is the "it just works" backend — reliable, full native
resolution, no special driver setup required.
"""

import asyncio
import io
import logging
import threading
import time
from typing import Optional

import numpy as np
from PIL import Image

from pymobiledevice3.lockdown import LockdownClient, create_using_usbmux as async_create_using_usbmux
from pymobiledevice3.services.screenshot import ScreenshotService

from imirror.capture.base import CaptureBackend, CapturedFrame
from imirror.config import config

logger = logging.getLogger(__name__)


def _run_async(coro):
    """Run an async coroutine synchronously from a regular thread.

    Creates a new event loop for each call to avoid conflicts
    with Qt's event loop.
    """
    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(coro)
    finally:
        loop.close()


class ScreenshotCapture(CaptureBackend):
    """
    Capture backend using DVT screenshot service.

    Takes rapid screenshots via pymobiledevice3 and converts them
    to numpy arrays for the OpenGL renderer. Simple and reliable.
    """

    def __init__(self):
        super().__init__()
        self._thread: Optional[threading.Thread] = None
        self._lockdown: Optional[LockdownClient] = None
        self._fps_counter = _FPSCounter()

    @property
    def name(self) -> str:
        return "Screenshot (DVT)"

    @property
    def max_fps(self) -> int:
        return 15

    def is_available(self) -> bool:
        """Always available if pymobiledevice3 is installed."""
        try:
            import pymobiledevice3
            return True
        except ImportError:
            return False

    def start(self, device_udid: str) -> bool:
        """Start the screenshot capture loop."""
        if self._running:
            return True

        try:
            # pymobiledevice3's create_using_usbmux is async — run it properly
            self._lockdown = _run_async(async_create_using_usbmux(serial=device_udid))
            logger.info("Screenshot backend: Connected to %s", device_udid[:8])
        except Exception as e:
            logger.error("Failed to connect to device %s: %s", device_udid[:8], e, exc_info=True)
            return False

        self._running = True
        self._thread = threading.Thread(
            target=self._capture_loop,
            name="ScreenshotCapture",
            daemon=True,
        )
        self._thread.start()
        logger.info("Screenshot capture started (target: %d FPS)", config.screenshot_target_fps)
        return True

    def stop(self) -> None:
        """Stop the capture loop."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=3.0)
            self._thread = None
        logger.info("Screenshot capture stopped (%d frames captured)", self.frame_count)

    def _capture_loop(self) -> None:
        """Main capture loop — takes screenshots as fast as possible."""
        target_interval = 1.0 / config.screenshot_target_fps
        consecutive_errors = 0
        max_errors = 10

        while self._running:
            loop_start = time.monotonic()

            try:
                frame = self._take_screenshot()
                if frame is not None:
                    self._emit_frame(frame)
                    self._fps_counter.tick()
                    self.fps = self._fps_counter.fps
                    consecutive_errors = 0

            except Exception as e:
                consecutive_errors += 1
                logger.warning("Screenshot error (%d/%d): %s",
                             consecutive_errors, max_errors, e)
                if consecutive_errors >= max_errors:
                    logger.error("Too many consecutive errors, stopping capture")
                    self._running = False
                    break
                time.sleep(0.5)
                continue

            # Sleep to maintain target FPS
            elapsed = time.monotonic() - loop_start
            sleep_time = target_interval - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)

    def _take_screenshot(self) -> Optional[CapturedFrame]:
        """Take a single screenshot and convert to CapturedFrame."""
        if not self._lockdown:
            return None

        try:
            # Take screenshot via DVT service
            screenshot_service = ScreenshotService(lockdown=self._lockdown)
            png_data = screenshot_service.take_screenshot()

            # Decode PNG to numpy array
            image = Image.open(io.BytesIO(png_data))

            # Convert to RGB if needed (screenshots may be RGBA)
            if image.mode == "RGBA":
                image = image.convert("RGB")
            elif image.mode != "RGB":
                image = image.convert("RGB")

            # Convert to numpy array (H, W, 3) uint8
            pixels = np.array(image, dtype=np.uint8)

            frame = CapturedFrame(
                pixels=pixels,
                width=image.width,
                height=image.height,
                timestamp_ns=time.monotonic_ns(),
                frame_number=self.frame_count,
            )

            if self.frame_count == 0:
                logger.info("First frame captured: %dx%d", image.width, image.height)

            return frame

        except Exception as e:
            raise RuntimeError(f"Screenshot failed: {e}") from e


class _FPSCounter:
    """Simple rolling FPS counter."""

    def __init__(self, window: float = 1.0):
        self._window = window
        self._times: list[float] = []
        self.fps: float = 0.0

    def tick(self) -> None:
        now = time.monotonic()
        self._times.append(now)
        # Remove old entries
        cutoff = now - self._window
        while self._times and self._times[0] < cutoff:
            self._times.pop(0)
        # Calculate FPS
        if len(self._times) >= 2:
            elapsed = self._times[-1] - self._times[0]
            if elapsed > 0:
                self.fps = (len(self._times) - 1) / elapsed
