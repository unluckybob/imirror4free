"""
Screenshot Capture Backend — Fallback for when Valeria streaming is unavailable.

Captures the iPhone screen via pymobiledevice3's ScreenshotService, which uses
Apple's native lockdown protocol over usbmuxd. This works when Apple's USB
driver is loaded (before WinUSB mirror driver installation).

Limitations vs Valeria:
  - ~5-15 FPS (individual JPEG screenshots, not a stream)
  - No audio
  - Higher latency (~100-200ms per frame)
  - Requires Apple Mobile Device Service running
  - Does NOT work when WinUSB mirror driver is active

This backend exists so the app can show *something* before the user
installs the mirror driver, and as a diagnostic fallback.
"""

import io
import logging
import threading
import time
from typing import Optional

import numpy as np

from imirror.capture.base import CaptureBackend, CapturedFrame
from imirror.config import config

logger = logging.getLogger(__name__)


class ScreenshotCapture(CaptureBackend):
    """Fallback capture backend using pymobiledevice3 screenshots."""

    def __init__(self):
        super().__init__()
        self._thread: Optional[threading.Thread] = None
        self._lockdown = None

    @property
    def name(self) -> str:
        return "Screenshot (Fallback)"

    @property
    def max_fps(self) -> int:
        return 15

    def is_available(self) -> bool:
        """Check if pymobiledevice3 screenshot service is reachable."""
        try:
            from pymobiledevice3.usbmux import list_devices
            import asyncio
            loop = asyncio.new_event_loop()
            try:
                devices = loop.run_until_complete(list_devices())
            finally:
                loop.close()
            return len(devices) > 0
        except Exception:
            return False

    def start(self, device_udid: str) -> bool:
        """Start screenshot capture loop."""
        if self._running:
            return True

        try:
            from pymobiledevice3.lockdown import create_using_usbmux
            import asyncio
            loop = asyncio.new_event_loop()
            try:
                self._lockdown = loop.run_until_complete(
                    create_using_usbmux(serial=device_udid)
                )
            finally:
                loop.close()
        except ImportError:
            logger.error(
                "Screenshot backend requires pymobiledevice3. "
                "Install it with: pip install pymobiledevice3"
            )
            return False
        except Exception as e:
            logger.error(
                "Screenshot backend cannot connect to iPhone: %s. "
                "This usually means the WinUSB mirror driver is active — "
                "use the Valeria backend instead, or restore the original "
                "Apple driver via Tools → Restore Original Driver.",
                e,
            )
            return False

        self._running = True
        self._thread = threading.Thread(
            target=self._capture_loop,
            name="screenshot-capture",
            daemon=True,
        )
        self._thread.start()
        return True

    def stop(self) -> None:
        """Stop screenshot capture."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=5.0)
            self._thread = None
        self._lockdown = None

    def _capture_loop(self) -> None:
        """Main capture loop — takes screenshots at target FPS."""
        try:
            from pymobiledevice3.services.screenshot import ScreenshotService
            from PIL import Image

            target_interval = 1.0 / config.screenshot_target_fps

            with ScreenshotService(lockdown=self._lockdown) as svc:
                logger.info("Screenshot capture started")

                while self._running:
                    loop_start = time.monotonic()

                    try:
                        png_data = svc.take_screenshot()
                        img = Image.open(io.BytesIO(png_data))
                        rgb = img.convert("RGB")
                        pixels = np.array(rgb, dtype=np.uint8)

                        h, w = pixels.shape[:2]
                        frame = CapturedFrame(
                            pixels=pixels,
                            width=w,
                            height=h,
                            timestamp=time.monotonic(),
                            frame_number=self.frame_count,
                        )
                        self._emit_frame(frame)

                    except Exception as e:
                        logger.debug("Screenshot error: %s", e)

                    # Pace to target FPS
                    elapsed = time.monotonic() - loop_start
                    sleep_time = target_interval - elapsed
                    if sleep_time > 0:
                        time.sleep(sleep_time)

        except Exception as e:
            logger.error("Screenshot capture loop failed: %s", e)
            self._emit_capture_stopped(f"Screenshot error: {e}")
        finally:
            self._running = False
