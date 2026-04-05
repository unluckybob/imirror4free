"""
Build script — packages IMIRROR4FREE into a standalone Windows application.
Uses PyInstaller with --onedir for reliable USB driver access and fast startup.

Output: dist/IMIRROR4FREE/ folder containing IMIRROR4FREE.exe + all dependencies.
Distribute by zipping the folder.
"""

import subprocess
import sys
from pathlib import Path

# Project root is one level up from build/
PROJECT_ROOT = Path(__file__).resolve().parent.parent
MAIN_SCRIPT = PROJECT_ROOT / "imirror" / "main.py"
ICON_FILE = PROJECT_ROOT / "assets" / "icon.ico"

cmd = [
    sys.executable, "-m", "PyInstaller",
    # --onedir: keeps DLLs alongside the exe for reliable USB/driver access.
    # This avoids the temp-folder extraction issues of --onefile that break
    # libusb, pymobiledevice3 resources, and native driver loading.
    "--onedir",
    "--windowed",
    "--name", "IMIRROR4FREE",
    f"--icon={ICON_FILE}",
    f"--add-data={PROJECT_ROOT / 'assets'};assets",
    # Hidden imports — ensure PyInstaller bundles all needed modules
    # Core
    "--hidden-import", "pymobiledevice3",
    "--hidden-import", "pymobiledevice3.usbmux",
    "--hidden-import", "pymobiledevice3.lockdown",
    "--hidden-import", "pymobiledevice3.services.screenshot",
    # GUI
    "--hidden-import", "PyQt6",
    "--hidden-import", "PyQt6.QtOpenGLWidgets",
    "--hidden-import", "OpenGL",
    "--hidden-import", "OpenGL.GL",
    # Video
    "--hidden-import", "av",
    "--hidden-import", "numpy",
    "--hidden-import", "PIL",
    # Network (required by pymobiledevice3)
    "--hidden-import", "zeroconf",
    "--hidden-import", "ifaddr",
    # USB
    "--hidden-import", "usb",
    "--hidden-import", "usb.core",
    "--hidden-import", "usb.util",
    "--hidden-import", "usb.backend.libusb1",
    "--hidden-import", "libusb_package",
    # Audio
    "--hidden-import", "sounddevice",
    # Our own sub-packages (ensure Python finds them in the frozen app)
    "--hidden-import", "imirror",
    "--hidden-import", "imirror.capture",
    "--hidden-import", "imirror.capture.screenshot",
    "--hidden-import", "imirror.capture.stream",
    "--hidden-import", "imirror.capture.base",
    "--hidden-import", "imirror.decode",
    "--hidden-import", "imirror.decode.video",
    "--hidden-import", "imirror.decode.audio",
    "--hidden-import", "imirror.gui",
    "--hidden-import", "imirror.gui.main_window",
    "--hidden-import", "imirror.gui.overlay",
    "--hidden-import", "imirror.gui.styles",
    "--hidden-import", "imirror.render",
    "--hidden-import", "imirror.render.gl_renderer",
    "--hidden-import", "imirror.render.shaders",
    "--hidden-import", "imirror.usb",
    "--hidden-import", "imirror.usb.device_manager",
    "--hidden-import", "imirror.usb.endpoint",
    "--hidden-import", "imirror.usb.packets",
    "--hidden-import", "imirror.usb.valeria",
    "--hidden-import", "imirror.usb.driver_check",
    "--hidden-import", "imirror.config",
    # Collect all pymobiledevice3 resources, data files, and binaries
    "--collect-all", "pymobiledevice3",
    # Collect libusb binaries so USB device access works
    "--collect-binaries", "libusb_package",
    "--collect-binaries", "usb",
    # Collect av (FFmpeg) binaries for video decoding
    "--collect-binaries", "av",
    # Collect sounddevice for audio playback
    "--collect-binaries", "sounddevice",
    str(MAIN_SCRIPT),
]

print(f"[BUILD] Building IMIRROR4FREE v0.3.0 (onedir)...")
print(f"  Project root: {PROJECT_ROOT}")
print(f"  Icon: {ICON_FILE}")
print(f"  Main script: {MAIN_SCRIPT}")
print(f"  Output: dist/IMIRROR4FREE/")
result = subprocess.run(cmd, cwd=str(PROJECT_ROOT))
sys.exit(result.returncode)
