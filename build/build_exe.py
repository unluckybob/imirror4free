"""
PyInstaller Build Script for IMIRROR4FREE.

Creates a ONE-DIR Windows executable bundle with all dependencies.
Uses --onedir (not --onefile) because native DLL packages like
av (FFmpeg), PyQt6, sounddevice, and libusb need their DLLs next
to the executable. --onefile extracts to a temp dir and frequently
breaks with these packages.

The entry point is run.py (startup crash handler) which wraps
imirror.main and catches import errors with a user-friendly dialog.

Usage:
    python build/build_exe.py

Output:
    dist/IMIRROR4FREE/IMIRROR4FREE.exe   (main executable)
    dist/IMIRROR4FREE/...                (bundled DLLs and data)
"""

import PyInstaller.__main__
import os
import sys

# Project root
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Icon path (relative to project root)
ICON_PATH = os.path.join(PROJECT_ROOT, "assets", "icon.ico")


def build():
    """Build the IMIRROR4FREE executable."""

    args = [
        # Entry point: crash-handler wrapper
        os.path.join(PROJECT_ROOT, "run.py"),

        "--name=IMIRROR4FREE",

        # ── ONE-DIR mode (critical for native DLLs) ────────────
        "--onedir",

        # ── Windowed (no console) ───────────────────────────────
        "--windowed",

        # ── Icon ────────────────────────────────────────────────
        *(["--icon=" + ICON_PATH] if os.path.exists(ICON_PATH) else []),

        # ── Hidden imports (modules PyInstaller can't detect) ───
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
        "--hidden-import=ctypes",
        "--hidden-import=ctypes.wintypes",

        # Driver + recording + all imirror submodules
        "--hidden-import=imirror",
        "--hidden-import=imirror.main",
        "--hidden-import=imirror.config",
        "--hidden-import=imirror.capture",
        "--hidden-import=imirror.capture.base",
        "--hidden-import=imirror.capture.stream",
        "--hidden-import=imirror.capture.screenshot",
        "--hidden-import=imirror.capture.recording",
        "--hidden-import=imirror.decode",
        "--hidden-import=imirror.decode.video",
        "--hidden-import=imirror.decode.audio",
        "--hidden-import=imirror.gui",
        "--hidden-import=imirror.gui.main_window",
        "--hidden-import=imirror.gui.overlay",
        "--hidden-import=imirror.gui.styles",
        "--hidden-import=imirror.render",
        "--hidden-import=imirror.render.opengl_widget",
        "--hidden-import=imirror.usb",
        "--hidden-import=imirror.usb.endpoint",
        "--hidden-import=imirror.usb.device_manager",
        "--hidden-import=imirror.usb.valeria",
        "--hidden-import=imirror.usb.packets",
        "--hidden-import=imirror.usb.driver_check",
        "--hidden-import=imirror.usb.driver_installer",

        # ── Collect entire packages (bundles native DLLs) ───────
        # These are CRITICAL — without them, the EXE crashes on
        # import with missing DLL errors.
        "--collect-all=imirror",
        "--collect-all=av",
        "--collect-all=pymobiledevice3",
        "--collect-all=PyQt6",
        "--collect-all=OpenGL",
        "--collect-data=libusb_package",
        "--collect-data=sounddevice",
        "--collect-data=certifi",

        # ── Output paths ────────────────────────────────────────
        f"--distpath={os.path.join(PROJECT_ROOT, 'dist')}",
        f"--workpath={os.path.join(PROJECT_ROOT, 'build', 'work')}",
        f"--specpath={os.path.join(PROJECT_ROOT, 'build')}",

        # Clean build
        "--clean",

        # Don't prompt for confirmation
        "--noconfirm",
    ]

    print("=" * 60)
    print("Building IMIRROR4FREE v0.6.0")
    print("=" * 60)
    print(f"  Entry point: run.py")
    print(f"  Mode: --onedir")
    print(f"  Icon: {'Yes' if os.path.exists(ICON_PATH) else 'No (assets/icon.ico not found)'}")
    print()

    PyInstaller.__main__.run(args)

    exe_path = os.path.join(PROJECT_ROOT, "dist", "IMIRROR4FREE", "IMIRROR4FREE.exe")
    if os.path.exists(exe_path):
        size_mb = os.path.getsize(exe_path) / (1024 * 1024)
        print()
        print("[OK] Build complete!")
        print(f"   Executable: {exe_path}")
        print(f"   Size: {size_mb:.1f} MB")
    else:
        print()
        print("[FAIL] Build may have failed — executable not found at expected path")
        print(f"   Expected: {exe_path}")
        sys.exit(1)


if __name__ == "__main__":
    build()
