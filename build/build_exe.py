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
    f"--add-data={PROJECT_ROOT / 'imirror'};imirror",
    f"--add-data={PROJECT_ROOT / 'assets'};assets",
    # Hidden imports — ensure PyInstaller bundles these
    "--hidden-import", "pymobiledevice3",
    "--hidden-import", "pymobiledevice3.usbmux",
    "--hidden-import", "pymobiledevice3.lockdown",
    "--hidden-import", "pymobiledevice3.services.screenshot",
    "--hidden-import", "PyQt6",
    "--hidden-import", "PyQt6.QtOpenGLWidgets",
    "--hidden-import", "OpenGL",
    "--hidden-import", "OpenGL.GL",
    "--hidden-import", "av",
    "--hidden-import", "numpy",
    "--hidden-import", "PIL",
    "--hidden-import", "zeroconf",
    "--hidden-import", "ifaddr",
    # USB and audio support
    "--hidden-import", "usb",
    "--hidden-import", "usb.core",
    "--hidden-import", "usb.util",
    "--hidden-import", "usb.backend.libusb1",
    "--hidden-import", "libusb_package",
    "--hidden-import", "sounddevice",
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

print(f"[BUILD] Building IMIRROR4FREE (onedir)...")
print(f"  Project root: {PROJECT_ROOT}")
print(f"  Icon: {ICON_FILE}")
print(f"  Main script: {MAIN_SCRIPT}")
print(f"  Output: dist/IMIRROR4FREE/")
result = subprocess.run(cmd, cwd=str(PROJECT_ROOT))
sys.exit(result.returncode)
