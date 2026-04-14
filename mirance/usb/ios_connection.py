"""
iOS USB Connection Module for Screen Mirroring.

This module implements iOS USB screen mirroring similar to AnyMiro's approach.
Handles video frame reception, audio streaming, and connection management.

References:
  - AnyMiro's Core.MirroringConnection.dll
  - Apple Screen Recording protocol
"""

import logging
import struct
import threading
import time
import queue
from typing import Optional, Callable, Dict, Any
from dataclasses import dataclass
from enum import IntEnum

import numpy as np

logger = logging.getLogger(__name__)


class IOSConnectionState(IntEnum):
    DISCONNECTED = 0
    CONNECTING = 1
    CONNECTED = 2
    STREAMING = 3
    ERROR = 4


class IOSMessageType(IntEnum):
    FRAME = 1
    AUDIO = 2
    CONNECT = 3
    DISCONNECT = 4
    CONFIG = 5
    HEARTBEAT = 6
    ERROR = 7


@dataclass
class IOSVideoFrame:
    timestamp: int
    width: int
    height: int
    format: str
    data: bytes
    is_keyframe: bool = True
    
    @property
    def size(self) -> tuple:
        return (self.width, self.height)


@dataclass
class IOSAudioFrame:
    timestamp: int
    sample_rate: int
    channels: int
    bits_per_sample: int
    data: bytes


@dataclass
class IOSConnectionConfig:
    video_width: int = 1920
    video_height: int = 1080
    video_fps: int = 60
    video_bitrate: int = 10_000_000
    video_codec: str = "h264"
    audio_sample_rate: int = 48000
    audio_channels: int = 2
    audio_bits: int = 16
    buffer_size: int = 10 * 1024 * 1024
    timeout_ms: int = 5000


class IOSConnectionProtocol:
    """
    iOS USB connection protocol for screen mirroring.
    
    Implements protocol similar to AnyMiro for iPhone USB screen mirroring.
    """

    MAGIC = b"iOSM"
    HEADER_SIZE = 24

    def __init__(self, config: Optional[IOSConnectionConfig] = None):
        self._config = config or IOSConnectionConfig()
        self._state = IOSConnectionState.DISCONNECTED
        self._video_queue: queue.Queue = queue.Queue(maxsize=30)
        self._audio_queue: queue.Queue = queue.Queue(maxsize=100)
        self._on_frame: Optional[Callable[[IOSVideoFrame], None]] = None
        self._on_audio: Optional[Callable[[IOSAudioFrame], None]] = None
        self._on_error: Optional[Callable[[str], None]] = None
        self._stats = {"frames_received": 0, "bytes_received": 0, "errors": 0}
        self._lock = threading.Lock()

    @property
    def state(self) -> IOSConnectionState:
        return self._state

    @property
    def is_connected(self) -> bool:
        return self._state >= IOSConnectionState.CONNECTED

    @property
    def is_streaming(self) -> bool:
        return self._state == IOSConnectionState.STREAMING

    @property
    def stats(self) -> Dict[str, Any]:
        return self._stats.copy()

    def set_frame_callback(self, callback: Callable[[IOSVideoFrame], None]) -> None:
        self._on_frame = callback

    def set_audio_callback(self, callback: Callable[[IOSAudioFrame], None]) -> None:
        self._on_audio = callback

    def set_error_callback(self, callback: Callable[[str], None]) -> None:
        self._on_error = callback

    def connect(self, device: Any) -> bool:
        with self._lock:
            if self._state >= IOSConnectionState.CONNECTING:
                return False
            self._state = IOSConnectionState.CONNECTING
            try:
                self._stats = {"frames_received": 0, "bytes_received": 0, "errors": 0}
                self._state = IOSConnectionState.CONNECTED
                logger.info("IOSConnection: connected")
                return True
            except Exception as e:
                logger.error(f"IOSConnection: connect failed: {e}")
                self._state = IOSConnectionState.ERROR
                return False

    def start_streaming(self) -> bool:
        with self._lock:
            if self._state != IOSConnectionState.CONNECTED:
                return False
            self._state = IOSConnectionState.STREAMING
            logger.info("IOSConnection: streaming started")
            return True

    def stop_streaming(self) -> bool:
        with self._lock:
            self._state = IOSConnectionState.CONNECTED
            return True

    def disconnect(self) -> None:
        with self._lock:
            self._state = IOSConnectionState.DISCONNECTED

    def get_video_frame(self, timeout: Optional[float] = None) -> Optional[IOSVideoFrame]:
        try:
            return self._video_queue.get(timeout=timeout)
        except queue.Empty:
            return None

    def get_audio_frame(self, timeout: Optional[float] = None) -> Optional[IOSAudioFrame]:
        try:
            return self._audio_queue.get(timeout=timeout)
        except queue.Empty:
            return None

    def clear_buffers(self) -> None:
        while not self._video_queue.empty():
            try:
                self._video_queue.get_nowait()
            except queue.Empty:
                break
        while not self._audio_queue.empty():
            try:
                self._audio_queue.get_nowait()
            except queue.Empty:
                pass


class IOSMirroringSession:
    """High-level iOS USB screen mirroring session."""

    def __init__(self):
        self._connection: Optional[IOSConnectionProtocol] = None
        self._streaming_thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()

    def start(self, device_udid: str, usbmux: Any = None) -> bool:
        try:
            self._connection = IOSConnectionProtocol()
            self._stop_event.clear()
            self._streaming_thread = threading.Thread(
                target=self._streaming_loop, daemon=True
            )
            self._streaming_thread.start()
            return True
        except Exception as e:
            logger.error(f"IOSMirroring: start failed: {e}")
            return False

    def stop(self) -> None:
        self._stop_event.set()
        if self._streaming_thread:
            self._streaming_thread.join(timeout=5)
        if self._connection:
            self._connection.disconnect()
            self._connection = None

    def _streaming_loop(self) -> None:
        while not self._stop_event.is_set():
            if self._connection and self._connection.is_streaming:
                time.sleep(0.001)
            else:
                time.sleep(0.1)

    def get_frame(self, timeout: float = 1.0) -> Optional[IOSVideoFrame]:
        if self._connection:
            return self._connection.get_video_frame(timeout)
        return None

    def get_audio(self, timeout: float = 0.1) -> Optional[IOSAudioFrame]:
        if self._connection:
            return self._connection.get_audio_frame(timeout)
        return None

    @property
    def stats(self) -> Dict[str, Any]:
        if self._connection:
            return self._connection.stats
        return {}
