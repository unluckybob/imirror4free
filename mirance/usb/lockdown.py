"""
Apple Lockdown Protocol Implementation.

This module implements the Apple Lockdown service protocol for iOS device
authentication, pairing, and service activation - used by AnyMiro and similar
tools for iPhone screen mirroring.

References:
  - libimobiledevice lockdown protocol
  - AnyMiro's Core.MirroringConnection.dll implementation
"""

import logging
import plistlib
import struct
import socket
import uuid
import threading
import time
from typing import Optional, Dict, Any
from dataclasses import dataclass
from enum import IntEnum

logger = logging.getLogger(__name__)

# Lockdown protocol constants
LOCKDOWN_PORT = 0xf27e
LOCKDOWN_LABEL = "Mirance"


class LockdownMessageType(IntEnum):
    PING = 0
    GET_SERVICE_LIST = 1
    START_SERVICE = 2
    STOP_SERVICE = 3
    GET_VALUE = 4
    SET_VALUE = 5


class LockdownService:
    AFC = "com.apple.afc"
    LOCKDOWN = "com.apple.lockdown"
    NOTIFICATION_PROXY = "com.apple.notificationproxy"


@dataclass
class LockdownDeviceInfo:
    udid: str
    device_name: str = ""
    product_type: str = ""
    product_version: str = ""
    is_paired: bool = False


class LockdownProtocol:
    """Apple Lockdown protocol client for iOS device pairing and service activation."""

    def __init__(self, usbmux_socket: Optional[socket.socket] = None):
        self._sock = usbmux_socket
        self._session_id: Optional[str] = None
        self._is_paired = False
        self._is_connected = False
        self._lock = threading.Lock()

    def connect(self, device_id: int, timeout: float = 10.0) -> bool:
        if not self._sock:
            logger.warning("Lockdown: no usbmux socket")
            return False
        try:
            self._session_id = str(uuid.uuid4()).upper()
            self._is_connected = True
            logger.info(f"Lockdown: connected to device {device_id}")
            return True
        except Exception as e:
            logger.error(f"Lockdown: connection failed: {e}")
            self._is_connected = False
            return False

    def disconnect(self) -> None:
        if self._sock:
            try:
                self._sock.close()
            except Exception:
                pass
        self._is_connected = False

    def is_connected(self) -> bool:
        return self._is_connected

    def pair(self, label: str = LOCKDOWN_LABEL) -> bool:
        if not self._is_connected:
            return False
        try:
            pair_request = {
                "Label": label,
                "MessageType": "Pair",
                "ProtocolVersion": "2",
            }
            response = self._send_plist(pair_request)
            if response and response.get("Result") == 0:
                self._is_paired = True
                return True
            return False
        except Exception as e:
            logger.error(f"Lockdown: pair error: {e}")
            return False

    def start_service(self, service_name: str) -> Optional[Dict[str, Any]]:
        if not self._is_connected:
            return None
        try:
            start_request = {
                "MessageType": "StartService",
                "Service": service_name,
            }
            response = self._send_plist(start_request)
            if response and response.get("Result") == 0:
                return {
                    "port": response.get("Port", 0),
                    "service": response.get("Service", service_name),
                }
            return None
        except Exception as e:
            logger.error(f"Lockdown: start service error: {e}")
            return None

    def get_value(self, key: str) -> Optional[Any]:
        if not self._is_connected:
            return None
        try:
            request = {"MessageType": "GetValue", "Key": key}
            response = self._send_plist(request)
            if response and response.get("Result") == 0:
                return response.get("Value")
            return None
        except Exception as e:
            logger.debug(f"Lockdown: get value error: {e}")
            return None

    def get_device_info(self) -> Optional[LockdownDeviceInfo]:
        if not self._is_connected:
            return None
        info = LockdownDeviceInfo(udid="")
        info.device_name = self.get_value("DeviceName") or ""
        info.product_type = self.get_value("ProductType") or ""
        info.product_version = self.get_value("ProductVersion") or ""
        info.udid = self.get_value("UniqueDeviceID") or ""
        return info

    def _send_plist(self, request: Dict[str, Any]) -> Optional[Dict[str, Any]]:
        if not self._sock:
            return None
        with self._lock:
            try:
                request_data = plistlib.dumps(request, fmt=plistlib.FMT_XML)
                header = struct.pack("<I", len(request_data))
                self._sock.sendall(header + request_data)
                
                resp_header = self._recv_exact(4)
                if not resp_header:
                    return None
                resp_length = struct.unpack("<I", resp_header)[0]
                resp_data = self._recv_exact(resp_length)
                if not resp_data:
                    return None
                return plistlib.loads(resp_data)
            except Exception as e:
                logger.debug(f"Lockdown: plist exchange error: {e}")
                return None

    def _recv_exact(self, num_bytes: int) -> Optional[bytes]:
        if not self._sock:
            return None
        try:
            data = b""
            while len(data) < num_bytes:
                chunk = self._sock.recv(num_bytes - len(data))
                if not chunk:
                    return None
                data += chunk
            return data
        except Exception:
            return None
