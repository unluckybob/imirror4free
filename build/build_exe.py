"""
PyInstaller Build Script for MIRROR4FREE.

Creates a ONE-DIR Windows executable bundle with all dependencies.
Uses --onedir (not --onefile) because native DLL packages like
av (FFmpeg), PyQt6, sounddevice, and libusb need their DLLs next
to the executable. --onefile extracts to a temp dir and frequently
breaks with these packages.

The entry point is run.py (startup crash handler) which wraps
imirror.main and catches import errors with a user-friendly dialog.

Usage:
    python build/build_exe.py            # Release build (windowed, no console)
    python build/build_exe.py --debug    # Debug build (console visible for errors)

Output:
    dist/MIRROR4FREE/MIRROR4FREE.exe   (main executable)
    dist/MIRROR4FREE/...                (bundled DLLs and data)
"""

import PyInstaller.__main__
import os
import sys

# Force UTF-8 stdout to prevent UnicodeEncodeError on Windows CI runners
if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if sys.stderr and hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

# Project root
PROJECT_ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# Icon path (relative to project root)
ICON_PATH = os.path.join(PROJECT_ROOT, "assets", "icon.ico")

# Debug mode: pass --debug to keep console window open for error output
DEBUG_MODE = "--debug" in sys.argv


def build():
    """Build the MIRROR4FREE executable."""

    args = [
        # Entry point: crash-handler wrapper
        os.path.join(PROJECT_ROOT, "run.py"),

        "--name=MIRROR4FREE",

        # -- ONE-DIR mode (critical for native DLLs) --
        "--onedir",

        # -- Windowed (no console) for release, console for debug --
        *(["--console"] if DEBUG_MODE else ["--windowed"]),

        # -- Icon --
        *([f"--icon={ICON_PATH}"] if os.path.exists(ICON_PATH) else []),

        # -- Hidden imports (modules PyInstaller can't detect) --

        # USB
        "--hidden-import=usb",
        "--hidden-import=usb.core",
        "--hidden-import=usb.util",
        "--hidden-import=usb.backend",
        "--hidden-import=usb.backend.libusb0",
        "--hidden-import=usb.backend.libusb1",
        "--hidden-import=libusb_package",

        # Video decoding
        "--hidden-import=av",

        # iPhone detection
        "--hidden-import=pymobiledevice3",
        "--hidden-import=pymobiledevice3.lockdown",
        "--hidden-import=pymobiledevice3.usbmux",

        # GUI — only the modules we actually use
        "--hidden-import=PyQt6",
        "--hidden-import=PyQt6.QtWidgets",
        "--hidden-import=PyQt6.QtCore",
        "--hidden-import=PyQt6.QtGui",
        "--hidden-import=PyQt6.QtOpenGL",
        "--hidden-import=PyQt6.QtOpenGLWidgets",

        # OpenGL
        "--hidden-import=OpenGL",
        "--hidden-import=OpenGL.GL",
        "--hidden-import=OpenGL.platform",
        "--hidden-import=OpenGL.platform.win32",

        # Audio
        "--hidden-import=sounddevice",
        "--hidden-import=_sounddevice_data",

        # Numerical
        "--hidden-import=numpy",

        # System
        "--hidden-import=ctypes",
        "--hidden-import=ctypes.wintypes",
        "--hidden-import=_cffi_backend",       # Required by pymobiledevice3/cryptography

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
        "--hidden-import=imirror.render.gl_renderer",
        "--hidden-import=imirror.render.shaders",
        "--hidden-import=imirror.usb",
        "--hidden-import=imirror.usb.endpoint",
        "--hidden-import=imirror.usb.device_manager",
        "--hidden-import=imirror.usb.valeria",
        "--hidden-import=imirror.usb.packets",
        "--hidden-import=imirror.usb.driver_check",
        "--hidden-import=imirror.usb.driver_installer",

        # -- Collect packages with native DLLs --
        # CRITICAL: without these, the EXE crashes on import with missing DLL errors.
        "--collect-all=imirror",
        "--collect-all=av",                    # FFmpeg DLLs (avcodec, avformat, etc.)
        "--collect-all=pymobiledevice3",
        "--collect-all=OpenGL",

        # libusb_package bundles libusb-1.0.dll (libusb1 backend).
        # We use usb.backend.libusb0 which requires libusb0.dll (libusb-win32).
        # libusb0.dll is NOT in libusb_package — we collect it separately below.
        # (On the developer machine it is in System32, put there by AnyMiro / libusb-win32 installer.)
        "--collect-binaries=libusb_package",   # still needed: pulls in hidden cffi deps

        # *** FIX: sounddevice bundles portaudio DLL — collect binaries too ***
        "--collect-binaries=sounddevice",
        "--collect-data=sounddevice",

        # TLS certificates for pymobiledevice3
        "--collect-data=certifi",

        # -- PyQt6: collect selectively to avoid bloat --
        # Instead of --collect-all=PyQt6 (which bundles 300+ MB of unused modules
        # like QtWebEngine, Qt3D, QtBluetooth, QtMultimedia, etc.), we collect
        # only the submodules we actually use.
        "--collect-submodules=PyQt6.QtWidgets",
        "--collect-submodules=PyQt6.QtCore",
        "--collect-submodules=PyQt6.QtGui",
        "--collect-submodules=PyQt6.QtOpenGL",
        "--collect-submodules=PyQt6.QtOpenGLWidgets",
        "--collect-binaries=PyQt6.QtWidgets",
        "--collect-binaries=PyQt6.QtCore",
        "--collect-binaries=PyQt6.QtGui",
        "--collect-binaries=PyQt6.QtOpenGL",
        "--collect-binaries=PyQt6.QtOpenGLWidgets",
        # Qt platform plugins (required for window creation on Windows)
        "--collect-data=PyQt6.Qt6",

        # -- Exclude unused Qt modules to slash bundle size --
        "--exclude-module=PyQt6.QtWebEngine",
        "--exclude-module=PyQt6.QtWebEngineCore",
        "--exclude-module=PyQt6.QtWebEngineWidgets",
        "--exclude-module=PyQt6.QtWebChannel",
        "--exclude-module=PyQt6.QtDesigner",
        "--exclude-module=PyQt6.QtDBus",
        "--exclude-module=PyQt6.QtBluetooth",
        "--exclude-module=PyQt6.QtMultimedia",
        "--exclude-module=PyQt6.QtMultimediaWidgets",
        "--exclude-module=PyQt6.QtNetwork",
        "--exclude-module=PyQt6.QtNfc",
        "--exclude-module=PyQt6.QtPositioning",
        "--exclude-module=PyQt6.QtPrintSupport",
        "--exclude-module=PyQt6.QtQml",
        "--exclude-module=PyQt6.QtQuick",
        "--exclude-module=PyQt6.QtQuickWidgets",
        "--exclude-module=PyQt6.QtRemoteObjects",
        "--exclude-module=PyQt6.QtSensors",
        "--exclude-module=PyQt6.QtSerialPort",
        "--exclude-module=PyQt6.QtSql",
        "--exclude-module=PyQt6.QtSvg",
        "--exclude-module=PyQt6.QtSvgWidgets",
        "--exclude-module=PyQt6.QtTest",
        "--exclude-module=PyQt6.QtXml",
        "--exclude-module=PyQt6.Qt3D",

        # -- Exclude test and debug modules --
        "--exclude-module=pytest",
        "--exclude-module=unittest",
        "--exclude-module=tkinter",
        "--exclude-module=_tkinter",

        # NOTE: --strip is intentionally OMITTED.
        # On Windows, strip corrupts PE binaries (it's a Unix ELF tool).
        # PyInstaller docs explicitly warn against --strip on Windows.
        # Use UPX or MSVC release optimisations instead if you need smaller binaries.

        # -- Output paths --
        f"--distpath={os.path.join(PROJECT_ROOT, 'dist')}",
        f"--workpath={os.path.join(PROJECT_ROOT, 'build', 'work')}",
        f"--specpath={os.path.join(PROJECT_ROOT, 'build')}",

        # Clean build
        "--clean",

        # Don't prompt for confirmation
        "--noconfirm",
    ]

    mode_str = "DEBUG (console)" if DEBUG_MODE else "RELEASE (windowed)"

    print("=" * 60)
    from imirror import __version__
    print(f"Building MIRROR4FREE v{__version__}  [{mode_str}]")
    print("=" * 60)
    print(f"  Entry point : run.py")
    print(f"  Mode        : --onedir")
    print(f"  Console     : {'Yes' if DEBUG_MODE else 'No'}")
    print(f"  Icon        : {'Yes' if os.path.exists(ICON_PATH) else 'No (assets/icon.ico not found)'}")
    print(f"  PyQt6       : Selective (trimmed — no WebEngine/3D/Multimedia)")
    print(f"  libusb      : --collect-binaries (DLL bundled)")
    print()

    # ── Bundle libusb0.dll (libusb-win32 user-mode component) ─────────────────
    # usb.backend.libusb0 searches for libusb0.dll by name.  If it is not in
    # the bundle, PyUSB will silently find no backend on machines that don't
    # have AnyMiro (or libusb-win32) installed and will never enumerate the
    # iPhone.  We copy it from System32 (where AnyMiro/libusb-win32 installs
    # it on the DEVELOPER machine) into the bundle root so PyUSB finds it
    # next to the .exe on the END-USER machine too.
    import shutil
    import glob as _glob

    _libusb0_dll = None
    _search_paths = [
        os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "System32", "libusb0.dll"),
        os.path.join(os.environ.get("SystemRoot", r"C:\Windows"), "SysWOW64", "libusb0.dll"),
    ]
    # Also check any libusb-win32 installation directories
    for _pat in [r"C:\Program Files*\libusb-win32\bin\x64\libusb0.dll",
                 r"C:\Program Files*\libusb-win32\bin\libusb0.dll"]:
        _search_paths.extend(_glob.glob(_pat))

    for _p in _search_paths:
        if os.path.exists(_p):
            _libusb0_dll = _p
            break

    if _libusb0_dll:
        print(f"  libusb0.dll : Found at {_libusb0_dll} — will be bundled")
        # Pass it to PyInstaller via --add-binary
        args.append(f"--add-binary={_libusb0_dll}{os.pathsep}.")
    else:
        print("  libusb0.dll : WARNING — NOT FOUND in System32 or SysWOW64.")
        print("    The built app will ONLY work on machines where libusb-win32")
        print("    is already installed (e.g. machines that have AnyMiro).")
        print("    To fix: install libusb-win32 on the BUILD machine first,")
        print("    or place libusb0.dll in C:\\Windows\\System32 manually.")
    # ────────────────────────────────────────────────────────────────────────

    PyInstaller.__main__.run(args)

    exe_path = os.path.join(PROJECT_ROOT, "dist", "MIRROR4FREE", "MIRROR4FREE.exe")
    if os.path.exists(exe_path):
        # Calculate total bundle size (entire dist folder)
        total_size = 0
        dist_dir = os.path.join(PROJECT_ROOT, "dist", "MIRROR4FREE")
        for dirpath, dirnames, filenames in os.walk(dist_dir):
            for f in filenames:
                fp = os.path.join(dirpath, f)
                total_size += os.path.getsize(fp)
        exe_size_mb = os.path.getsize(exe_path) / (1024 * 1024)
        total_size_mb = total_size / (1024 * 1024)

        print()
        print("=" * 60)
        print("[OK] Build complete!")
        print(f"   Executable  : {exe_path}")
        print(f"   EXE size    : {exe_size_mb:.1f} MB")
        print(f"   Bundle total: {total_size_mb:.1f} MB")
        print("=" * 60)

        if DEBUG_MODE:
            print()
            print("  ** DEBUG BUILD — console window will stay open **")
            print("  ** Run MIRROR4FREE.exe from a terminal to see errors **")
    else:
        print()
        print("[FAIL] Build may have failed -- executable not found at expected path")
        print(f"   Expected: {exe_path}")
        sys.exit(1)


if __name__ == "__main__":
    build()
