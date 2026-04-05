"""
Abstract base class for capture backends.

All capture backends must implement this interface. The main app
creates the appropriate backend based on config and swaps between
them transparently.
"""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from typing import Optional, Callable
import numpy as np


@dataclass
class CapturedFrame:
    """A captured frame ready for rendering."""
    pixels: np.ndarray          # RGB pixel data (H, W, 3) uint8
    width: int
    height: int
    timestamp_ns: int           # Capture timestamp
    frame_number: int

    @property
    def aspect_ratio(self) -> float:
        if self.height == 0:
            return 1.0
        return self.width / self.height


class CaptureBackend(ABC):
    """Abstract capture backend interface."""

    def __init__(self):
        self._on_frame: Optional[Callable[[CapturedFrame], None]] = None
        self._running = False
        self.frame_count = 0
        self.fps: float = 0.0

    def on_frame(self, callback: Callable[[CapturedFrame], None]) -> None:
        """Register callback for new frames."""
        self._on_frame = callback

    @abstractmethod
    def start(self, device_udid: str) -> bool:
        """Start capturing from the specified device.

        Returns True if capture started successfully.
        """
        ...

    @abstractmethod
    def stop(self) -> None:
        """Stop capturing."""
        ...

    @abstractmethod
    def is_available(self) -> bool:
        """Check if this backend is available on the current system."""
        ...

    @property
    @abstractmethod
    def name(self) -> str:
        """Human-readable name of this backend."""
        ...

    @property
    @abstractmethod
    def max_fps(self) -> int:
        """Maximum FPS this backend can achieve."""
        ...

    def _emit_frame(self, frame: CapturedFrame) -> None:
        """Emit a captured frame to the registered callback."""
        self.frame_count += 1
        if self._on_frame:
            self._on_frame(frame)
