"""
Abstract base class for capture backends.

All capture backends inherit from this class and implement the same 
interface so the GUI layer can swap backends transparently.
"""

import abc
import logging
import time
from dataclasses import dataclass
from typing import Callable, Optional

import numpy as np

logger = logging.getLogger(__name__)


@dataclass
class CapturedFrame:
    """A single captured frame from the iPhone."""
    pixels: np.ndarray      # Shape: (H, W, 3), dtype: uint8, RGB
    width: int
    height: int
    timestamp: float        # time.monotonic() of capture
    frame_number: int


class CaptureBackend(abc.ABC):
    """Abstract base class for capture backends."""

    def __init__(self):
        self._running: bool = False
        self._on_frame: Optional[Callable[[CapturedFrame], None]] = None
        self._on_capture_stopped: Optional[Callable[[str], None]] = None
        self.frame_count: int = 0
        self.fps: float = 0.0

    @property
    @abc.abstractmethod
    def name(self) -> str:
        """Human-readable backend name."""
        ...

    @property
    @abc.abstractmethod
    def max_fps(self) -> int:
        """Theoretical maximum FPS for this backend."""
        ...

    @abc.abstractmethod
    def is_available(self) -> bool:
        """Check if this backend can run on the current system."""
        ...

    @abc.abstractmethod
    def start(self, device_udid: str) -> bool:
        """Start capturing from the given device. Returns success."""
        ...

    @abc.abstractmethod
    def stop(self) -> None:
        """Stop capturing."""
        ...

    def on_frame(self, callback: Callable[[CapturedFrame], None]) -> None:
        """Register a callback for new frames."""
        self._on_frame = callback

    def on_capture_stopped(self, callback: Callable[[str], None]) -> None:
        """Register a callback for when capture stops unexpectedly."""
        self._on_capture_stopped = callback

    def _emit_frame(self, frame: CapturedFrame) -> None:
        """Send a frame to the registered callback."""
        self.frame_count += 1
        if self._on_frame:
            self._on_frame(frame)

    def _emit_capture_stopped(self, reason: str) -> None:
        """Notify that capture stopped unexpectedly."""
        if self._on_capture_stopped:
            self._on_capture_stopped(reason)
