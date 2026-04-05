"""
PyInstaller Build Script for IMIRROR4FREE.

Creates a single-file Windows executable with all dependencies bundled.
Includes the mirror driver installer for one-click setup.

Usage:
    python build/build_exe.py
"""

import PyInstaller.__main__
import os
import sys

# Project root
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))


def build():
    """Build the IMIRROR4FREE executable."""
    args = [
        os.path.join(PROJECT_ROOT, "imirror", "main.py"),
        "--name=IMIRROR4FREE",
        "--onefile",
        "--windowed",

        # Icon (if we have one)
        # "--icon=assets/icon.ico",

        # Hidden imports that PyInstaller can't detect
        "--hidden-import=usb",
        "--hidden-import=usb.core",
        "--hidden-import=usb.util",
        "--hidden-import=usb.backend",
        "--hidden-import=usb.backend.libusb1",
        "--hidden-import=libusb_package",
        "--hidden-import=av",
        "--hidden-import=pymobiledevice3",
        "--hidden-import=pymobiledevice3.lockdown",
        "--hidden-import=pymobiledevice3.usbmux",
        "--hidden-import=PyQt6",
        "--hidden-import=PyQt6.QtWidgets",
        "--hidden-import=PyQt6.QtCore",
        "--hidden-import=PyQt6.QtGui",
        "--hidden-import=PyQt6.QtOpenGLWidgets",
        "--hidden-import=OpenGL",
        "--hidden-import=OpenGL.GL",
        "--hidden-import=sounddevice",
        "--hidden-import=numpy",

        # Phase 2+3: Include all modules
        "--hidden-import=imirror.usb.driver_installer",
        "--hidden-import=imirror.capture.recording",
        "--hidden-import=ctypes",
        "--hidden-import=ctypes.wintypes",

        # Collect the entire imirror package
        "--collect-submodules=imirror",

        # Output directory
        f"--distpath={os.path.join(PROJECT_ROOT, 'dist')}",
        f"--workpath={os.path.join(PROJECT_ROOT, 'build', 'work')}",
        f"--specpath={os.path.join(PROJECT_ROOT, 'build')}",

        # Clean build
        "--clean",
    ]

    print("=" * 60)
    print("Building IMIRROR4FREE v0.5.0")
    print("=" * 60)

    PyInstaller.__main__.run(args)

    print()
    print("✅ Build complete!")
    print(f"   Executable: {os.path.join(PROJECT_ROOT, 'dist', 'IMIRROR4FREE.exe')}")


if __name__ == "__main__":
    build()
