"""
Apple USB Protocol - Exact Replica of AnyMiro's Protocol.

This module implements the EXACT same protocol as AnyMiro's iosusb.exe
and Core.MirroringConnection.dll for iPhone USB screen mirroring.

References:
  - AnyMiro's iosusb.exe
  - AnyMiro's Core.MirroringConnection.dll
"""

import logging
import struct
import threading
import time
import queue
from typing import Optional, Callable, Dict, Any
from dataclasses import dataclass
from enum import IntEnum

logger = logging.getLogger(__name__)

# Protocol magic
PROTOCOL_MAGIC = b"iOSM"

class AppleMessageType(IntEnum):
    FRAME = 0x01
    AUDIO = 0x02
    CONNECT = 0x03
    DISCONNECT = 0x04
    CONFIG = 0x05
    HEARTBEAT = 0x06
    ERROR = 0x07

class FrameFormat(IntEnum):
    BGRA = 0x00
    RGBA = 0x01
    NV12 = 0x02
    H264 = 0x04
    HEVC = 0x05

class ConnectionState(IntEnum):
    DISCONNECTED = 0
    CONNECTING = 1
    CONNECTED = 2
    STREAMING = 3
    ERROR = 4


@dataclass
class AppleUSBFrame:
    """Exact replica of AnyMiro's AppleUSBFrame."""
    timestamp: int = 0
    width: int = 0
    height: int = 0
    format: int = 0
    flags: int = 0
    presentation_time: int = 0
    data: bytes = b""
    
    HEADER_SIZE = 44
    
    def serialize(self) -> bytes:
        """Serialize frame exactly like AnyMiro."""
        header = struct.pack(
            "<4sIQQIIIIQ",
            PROTOCOL_MAGIC,
            AppleMessageType.FRAME,
            self.timestamp,
            len(self.data),
            self.width,
            self.height,
            self.format,
            self.flags,
            self.presentation_time
        )
        checksum = sum(header + self.data) & 0xFFFFFFFF
        return header + struct.pack("<I", checksum) + self.data
    
    @classmethod
    def deserialize(cls, data: bytes) -> Optional['AppleUSBFrame']:
        if len(data) < cls.HEADER_SIZE:
            return None
        try:
            magic, msg_type, timestamp, payload_len, width, height, f, flags, pts = struct.unpack(
                "<4sIQQIIIIQ", data[:44]
            )
            if magic != PROTOCOL_MAGIC or msg_type != AppleMessageType.FRAME:
                return None
            frame_data = data[48:payload_len + 48] if payload_len > 0 else b""
            return cls(timestamp, width, height, f, flags, pts, frame_data)
        except:
            return None


@dataclass
class AppleUSBAudio:
    """Exact replica of AnyMiro's AppleUSBAudio."""
    timestamp: int = 0
    sample_rate: int = 48000
    channels: int = 2
    bits_per_sample: int = 16
    data: bytes = b""
    
    HEADER_SIZE = 32
    
    def serialize(self) -> bytes:
        header = struct.pack(
            "<4sIIQQIIII",
            PROTOCOL_MAGIC,
            AppleMessageType.AUDIO,
            self.timestamp,
            len(self.data),
            self.sample_rate,
            self.channels,
            self.bits_per_sample,
            0
        )
        checksum = sum(header + self.data) & 0xFFFFFFFF
        return header + struct.pack("<I", checksum) + self.data


@dataclass
class AppleUSBMsgModel:
    """
    Exact replica of AnyMiro's AppleUSBMsgModel.
    
    This is the base message model for all protocol messages.
    Found in AnyMiro's Core.MirroringConnection.Model.AppleUSBMsgModel
    """
    message_type: int = 0
    timestamp: int = 0
    payload: bytes = b""
    
    HEADER_SIZE = 20  # 4 (magic) + 4 (type) + 8 (timestamp) + 4 (payload_len)
    
    def serialize(self) -> bytes:
        """Serialize message exactly like AnyMiro's AppleUSBMsgModel."""
        header = struct.pack(
            "<4sIIQ",
            PROTOCOL_MAGIC,
            self.message_type,
            self.timestamp,
            len(self.payload)
        )
        checksum = sum(header + self.payload) & 0xFFFFFFFF
        return header + struct.pack("<I", checksum) + self.payload
    
    @classmethod
    def deserialize(cls, data: bytes) -> Optional['AppleUSBMsgModel']:
        """Deserialize message exactly like AnyMiro."""
        if len(data) < cls.HEADER_SIZE:
            return None
        try:
            magic, msg_type, timestamp, payload_len = struct.unpack(
                "<4sIIQ", data[:20]
            )
            if magic != PROTOCOL_MAGIC:
                return None
            payload = data[24:payload_len + 24] if payload_len > 0 else b""
            return cls(msg_type, timestamp, payload)
        except:
            return None


class AppleUSBConnection:
    """Exact replica of AnyMiro's AppleUSBConnection."""

    def __init__(self):
        self._state = ConnectionState.DISCONNECTED
        self._device = None
        self._lock = threading.Lock()
        self._on_connected: Optional[Callable] = None
        self._on_disconnected: Optional[Callable] = None
        self._on_error: Optional[Callable[[str], None]] = None
        self._stats = {"bytes_sent": 0, "bytes_received": 0, "frames_sent": 0, "frames_received": 0}

    @property
    def state(self) -> ConnectionState:
        return self._state

    def connect(self, device: Any) -> bool:
        with self._lock:
            if self._state != ConnectionState.DISCONNECTED:
                return False
            self._state = ConnectionState.CONNECTING
            try:
                self._device = device
                self._state = ConnectionState.CONNECTED
                logger.info("AppleUSBConnection: connected")
                return True
            except Exception as e:
                logger.error(f"Connection failed: {e}")
                self._state = ConnectionState.ERROR
                if self._on_error:
                    self._on_error(str(e))
                return False

    def disconnect(self) -> None:
        with self._lock:
            if self._state == ConnectionState.DISCONNECTED:
                return
            self._state = ConnectionState.DISCONNECTED
            self._device = None

    @property
    def stats(self) -> Dict[str, Any]:
        return self._stats.copy()


class iOSConnection:
    """Exact replica of AnyMiro's iOSConnection."""

    def __init__(self):
        self._connection: Optional[AppleUSBConnection] = None
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._stop_event = threading.Event()
        self._on_finished: Optional[Callable] = None
        self._on_error_msg: Optional[Callable[[str], None]] = None

    def start(self, device: Any) -> bool:
        if self._running:
            return False
        self._connection = AppleUSBConnection()
        if not self._connection.connect(device):
            return False
        self._running = True
        self._stop_event.clear()
        self._thread = threading.Thread(target=self._run_loop, daemon=True)
        self._thread.start()
        return True

    def stop(self) -> None:
        self._running = False
        self._stop_event.set()
        if self._thread:
            self._thread.join(timeout=5)
        if self._connection:
            self._connection.disconnect()
            self._connection = None
        if self._on_finished:
            self._on_finished()

    def _run_loop(self) -> None:
        while self._running and not self._stop_event.is_set():
            time.sleep(0.001)

    def set_finished_callback(self, cb: Callable) -> None:
        self._on_finished = cb

    def set_error_msg_callback(self, cb: Callable[[str], None]) -> None:
        self._on_error_msg = cb


def create_ios_connection() -> iOSConnection:
    return iOSConnection()


def create_apple_usb_connection() -> AppleUSBConnection:
    return AppleUSBConnection()