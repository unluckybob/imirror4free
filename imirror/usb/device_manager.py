"""
Device Manager — Detects and manages connected iPhones via pymobiledevice3.

Uses Apple's usbmuxd protocol (through pymobiledevice3) to:
- Detect connected iOS devices over USB
- Read device info (name, model, resolution, iOS version)
- Establish lockdown connections for DVT services
- Monitor for connect/disconnect events

IMPORTANT: pymobiledevice3's usbmux API is fully async.
We run an asyncio event loop in a background thread to handle this.
"""

import asyncio
import logging
import os
import platform
import shutil
import subprocess
import threading
import time
from dataclasses import dataclass, field
from typing import Optional, Callable

from pymobiledevice3.usbmux import list_devices as async_list_devices
from pymobiledevice3.lockdown import create_using_usbmux as async_create_using_usbmux, LockdownClient

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
            return f"{self.display_width}x{self.display_height}"
        return "unknown"


# Known iPhone display resolutions (points x scale = pixels)
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


def run_startup_diagnostics() -> dict:
    """Check system prerequisites for iPhone USB detection.

    Returns a dict with diagnostic results that can be logged
    or displayed to the user for troubleshooting.
    """
    results = {
        "platform": platform.system(),
        "platform_version": platform.version(),
        "itunes_installed": False,
        "apple_mobile_device_service": False,
        "usbmuxd_reachable": False,
        "pymobiledevice3_version": "unknown",
        "issues": [],
    }

    # Check pymobiledevice3 version
    try:
        import pymobiledevice3
        results["pymobiledevice3_version"] = getattr(pymobiledevice3, "__version__", "installed (version unknown)")
    except ImportError:
        results["issues"].append("pymobiledevice3 is not installed")
        return results

    # Windows-specific checks
    if platform.system() == "Windows":
        # Check if iTunes or Apple Mobile Device Support is installed
        itunes_paths = [
            os.path.join(os.environ.get("ProgramFiles", ""), "iTunes"),
            os.path.join(os.environ.get("ProgramFiles(x86)", ""), "iTunes"),
            os.path.join(os.environ.get("ProgramFiles", ""), "Common Files", "Apple", "Mobile Device Support"),
            os.path.join(os.environ.get("ProgramFiles(x86)", ""), "Common Files", "Apple", "Mobile Device Support"),
        ]
        for path in itunes_paths:
            if os.path.exists(path):
                results["itunes_installed"] = True
                break

        if not results["itunes_installed"]:
            # Also check for Apple Devices app (Windows Store version)
            apple_devices_path = shutil.which("AppleMobileDeviceService.exe")
            if apple_devices_path:
                results["itunes_installed"] = True

        if not results["itunes_installed"]:
            results["issues"].append(
                "iTunes or Apple Mobile Device Support not found. "
                "Install iTunes from apple.com or the Microsoft Store "
                "to enable iPhone USB communication."
            )

        # Check if Apple Mobile Device Service is running
        try:
            output = subprocess.check_output(
                ["sc", "query", "Apple Mobile Device Service"],
                stderr=subprocess.DEVNULL,
                text=True,
            )
            if "RUNNING" in output:
                results["apple_mobile_device_service"] = True
            else:
                results["issues"].append(
                    "Apple Mobile Device Service is installed but not running. "
                    "Try restarting it: open Services (services.msc), find "
                    "'Apple Mobile Device Service', and click Start."
                )
        except (subprocess.CalledProcessError, FileNotFoundError):
            if results["itunes_installed"]:
                results["issues"].append(
                    "Could not check Apple Mobile Device Service status."
                )

    # Test usbmuxd connection
    try:
        devices = _run_async(async_list_devices())
        results["usbmuxd_reachable"] = True
        logger.info("usbmuxd reachable, found %d device(s) at startup", len(devices))
    except Exception as e:
        results["usbmuxd_reachable"] = False
        results["issues"].append(f"Cannot reach usbmuxd: {e}")

    return results


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
        self._diagnostics: Optional[dict] = None

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

    @property
    def diagnostics(self) -> Optional[dict]:
        """Startup diagnostic results, or None if not yet run."""
        return self._diagnostics

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

        # Run startup diagnostics
        logger.info("Running startup diagnostics...")
        self._diagnostics = run_startup_diagnostics()

        logger.info("  Platform: %s %s", self._diagnostics["platform"], self._diagnostics["platform_version"])
        logger.info("  pymobiledevice3: %s", self._diagnostics["pymobiledevice3_version"])
        logger.info("  iTunes/Apple Mobile Device: %s", "OK" if self._diagnostics["itunes_installed"] else "NOT FOUND")
        logger.info("  Apple Mobile Device Service: %s", "RUNNING" if self._diagnostics["apple_mobile_device_service"] else "NOT RUNNING")
        logger.info("  usbmuxd reachable: %s", "YES" if self._diagnostics["usbmuxd_reachable"] else "NO")

        if self._diagnostics["issues"]:
            for issue in self._diagnostics["issues"]:
                logger.warning("  [!] %s", issue)

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
                logger.error("Error polling devices: %s", e, exc_info=True)
            time.sleep(self._poll_interval)

    def _check_devices(self) -> None:
        """Check for connected/disconnected devices."""
        try:
            # pymobiledevice3's list_devices is async — run it synchronously
            usb_devices = _run_async(async_list_devices())
            logger.debug("Found %d USB device(s)", len(usb_devices))
        except Exception as e:
            logger.debug("Failed to list USB devices: %s", e)
            return

        current_udids = set()
        for dev in usb_devices:
            # Only care about USB connections (not network)
            if hasattr(dev, 'is_usb') and not dev.is_usb:
                continue

            udid = dev.serial
            current_udids.add(udid)

            with self._lock:
                if udid not in self._devices:
                    # New device connected
                    device = self._create_device(udid)
                    if device:
                        self._devices[udid] = device
                        logger.info("Device connected: %s", device.display_name)
                        logger.info("  Resolution: %s", device.resolution_str)
                        if self._on_device_connected:
                            self._on_device_connected(device)

        # Check for disconnected devices
        with self._lock:
            disconnected = set(self._devices.keys()) - current_udids
            for udid in disconnected:
                device = self._devices.pop(udid)
                logger.info("Device disconnected: %s", device.display_name)
                if self._on_device_disconnected:
                    self._on_device_disconnected(udid)

    def _create_device(self, udid: str) -> Optional[iPhoneDevice]:
        """Create an iPhoneDevice with full info from lockdown."""
        try:
            # pymobiledevice3's create_using_usbmux is async
            lockdown = _run_async(async_create_using_usbmux(serial=udid))

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
            logger.warning("Failed to create device for UDID %s: %s", udid[:8], e, exc_info=True)
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
