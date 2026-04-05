"""
Device Manager — Detects and manages connected iPhones via pymobiledevice3.

Uses Apple's usbmuxd protocol (through pymobiledevice3) to:
- Detect connected iOS devices over USB
- Read device info (name, model, resolution, iOS version)
- Establish lockdown connections for DVT services
- Monitor for connect/disconnect events
"""

import logging
import threading
import time
from dataclasses import dataclass, field
from typing import Optional, Callable

from pymobiledevice3.usbmux import list_devices
from pymobiledevice3.lockdown import create_using_usbmux, LockdownClient

logger = logging.getLogger(__name__)


@dataclass
class iPhoneDevice:
    """Represents a connected iPhone."""
    udid: str
    name: str = ""
    model: str = ""
    product_type: str = ""
    ios_version: str = ""
    display_width: int = 0
    display_height: int = 0
    serial: str = ""
    lockdown: Optional[LockdownClient] = field(default=None, repr=False)

    @property
    def display_name(self) -> str:
        """Human-readable device description."""
        if self.name and self.model:
            return f"{self.name} ({self.model}, iOS {self.ios_version})"
        return f"iPhone [{self.udid[:8]}...]"

    @property
    def resolution_str(self) -> str:
        if self.display_width and self.display_height:
            return f"{self.display_width}×{self.display_height}"
        return "unknown"


# Known iPhone display resolutions (points × scale = pixels)
IPHONE_RESOLUTIONS = {
    "iPhone14,2": (1170, 2532),     # iPhone 13 Pro
    "iPhone14,3": (1284, 2778),     # iPhone 13 Pro Max
    "iPhone15,2": (1179, 2556),     # iPhone 14 Pro
    "iPhone15,3": (1290, 2796),     # iPhone 14 Pro Max
    "iPhone16,1": (1179, 2556),     # iPhone 15 Pro
    "iPhone16,2": (1320, 2868),     # iPhone 15 Pro Max
    "iPhone17,1": (1206, 2622),     # iPhone 16 Pro
    "iPhone17,2": (1320, 2868),     # iPhone 16 Pro Max
}


class DeviceManager:
    """
    Manages iPhone USB connections.

    Polls for connected devices and notifies callbacks when devices
    connect or disconnect. Handles lockdown client creation for
    accessing device services.
    """

    def __init__(self, poll_interval: float = 1.0):
        self._poll_interval = poll_interval
        self._devices: dict[str, iPhoneDevice] = {}
        self._running = False
        self._thread: Optional[threading.Thread] = None
        self._lock = threading.Lock()

        # Callbacks
        self._on_device_connected: Optional[Callable[[iPhoneDevice], None]] = None
        self._on_device_disconnected: Optional[Callable[[str], None]] = None

    @property
    def devices(self) -> dict[str, iPhoneDevice]:
        """Currently connected devices by UDID."""
        with self._lock:
            return dict(self._devices)

    @property
    def first_device(self) -> Optional[iPhoneDevice]:
        """First connected device, or None."""
        with self._lock:
            if self._devices:
                return next(iter(self._devices.values()))
            return None

    def on_device_connected(self, callback: Callable[[iPhoneDevice], None]) -> None:
        """Register callback for device connection events."""
        self._on_device_connected = callback

    def on_device_disconnected(self, callback: Callable[[str], None]) -> None:
        """Register callback for device disconnection events."""
        self._on_device_disconnected = callback

    def start(self) -> None:
        """Start the device polling thread."""
        if self._running:
            return
        self._running = True
        self._thread = threading.Thread(
            target=self._poll_loop,
            name="DeviceManager-Poll",
            daemon=True,
        )
        self._thread.start()
        logger.info("Device manager started (polling every %.1fs)", self._poll_interval)

    def stop(self) -> None:
        """Stop the device polling thread."""
        self._running = False
        if self._thread:
            self._thread.join(timeout=3.0)
            self._thread = None
        logger.info("Device manager stopped")

    def _poll_loop(self) -> None:
        """Background thread that polls for device changes."""
        while self._running:
            try:
                self._check_devices()
            except Exception as e:
                logger.error("Error polling devices: %s", e)
            time.sleep(self._poll_interval)

    def _check_devices(self) -> None:
        """Check for connected/disconnected devices."""
        try:
            usb_devices = list_devices()
        except Exception as e:
            logger.debug("Failed to list USB devices: %s", e)
            return

        current_udids = set()
        for dev in usb_devices:
            udid = dev.serial
            current_udids.add(udid)

            with self._lock:
                if udid not in self._devices:
                    # New device connected
                    device = self._create_device(udid)
                    if device:
                        self._devices[udid] = device
                        logger.info("📱 Device connected: %s", device.display_name)
                        logger.info("   Resolution: %s", device.resolution_str)
                        if self._on_device_connected:
                            self._on_device_connected(device)

        # Check for disconnected devices
        with self._lock:
            disconnected = set(self._devices.keys()) - current_udids
            for udid in disconnected:
                device = self._devices.pop(udid)
                logger.info("📱 Device disconnected: %s", device.display_name)
                if self._on_device_disconnected:
                    self._on_device_disconnected(udid)

    def _create_device(self, udid: str) -> Optional[iPhoneDevice]:
        """Create an iPhoneDevice with full info from lockdown."""
        try:
            lockdown = create_using_usbmux(serial=udid)

            # Extract device info from lockdown values
            all_values = lockdown.all_values
            product_type = all_values.get("ProductType", "")
            resolution = IPHONE_RESOLUTIONS.get(product_type, (0, 0))

            device = iPhoneDevice(
                udid=udid,
                name=all_values.get("DeviceName", "iPhone"),
                model=all_values.get("MarketingName",
                       all_values.get("ProductType", "Unknown")),
                product_type=product_type,
                ios_version=all_values.get("ProductVersion", ""),
                display_width=resolution[0],
                display_height=resolution[1],
                serial=all_values.get("SerialNumber", ""),
                lockdown=lockdown,
            )
            return device

        except Exception as e:
            logger.warning("Failed to create device for UDID %s: %s", udid[:8], e)
            return None

    def get_lockdown(self, udid: Optional[str] = None) -> Optional[LockdownClient]:
        """Get a lockdown client for the specified device (or first device)."""
        with self._lock:
            if udid:
                device = self._devices.get(udid)
            else:
                device = self.first_device

            if device and device.lockdown:
                return device.lockdown
            return None
