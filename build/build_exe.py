"""
PyInstaller Build Script for MIRANCE.

Creates a ONE-DIR Windows executable bundle with all dependencies.
Uses --onedir (not --onefile) because native DLL packages like
av (FFmpeg), PyQt6, sounddevice, and libusb need their DLLs next
to the executable. --onefile extracts to a temp dir and frequently
breaks with these packages.

The entry point is run.py (startup crash handler) which wraps
mirance.main and catches import errors with a user-friendly dialog.

Usage:
    python build/build_exe.py            # Release build (windowed, no console)
    python build/build_exe.py --debug    # Debug build (console visible for errors)

Output:
    dist/MIRANCE/MIRANCE.exe   (main executable)
    dist/MIRANCE/...                (bundled DLLs and data)
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
    """Build the MIRANCE executable."""

    args = [
        # Entry point: crash-handler wrapper
        os.path.join(PROJECT_ROOT, "run.py"),

        "--name=MIRANCE",

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
        "--hidden-import=usb.backend.winusb",
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

        # Driver + recording + all mirance submodules
        "--hidden-import=mirance",
        "--hidden-import=mirance.main",
        "--hidden-import=mirance.config",
        "--hidden-import=mirance.capture",
        "--hidden-import=mirance.capture.base",
        "--hidden-import=mirance.capture.stream",
        "--hidden-import=mirance.capture.recording",
        "--hidden-import=mirance.decode",
        "--hidden-import=mirance.decode.video",
        "--hidden-import=mirance.decode.audio",
        "--hidden-import=mirance.gui",
        "--hidden-import=mirance.gui.main_window",
        "--hidden-import=mirance.gui.overlay",
        "--hidden-import=mirance.gui.styles",
        "--hidden-import=mirance.render",
        "--hidden-import=mirance.render.gl_renderer",
        "--hidden-import=mirance.render.shaders",
        "--hidden-import=mirance.usb",
        "--hidden-import=mirance.usb.endpoint",
        "--hidden-import=mirance.usb.device_manager",
        "--hidden-import=mirance.usb.valeria",
        "--hidden-import=mirance.usb.packets",
        "--hidden-import=mirance.usb.driver_check",
        "--hidden-import=mirance.usb.driver_installer",

        # -- Collect packages with native DLLs --
        # CRITICAL: without these, the EXE crashes on import with missing DLL errors.
        "--collect-all=mirance",
        "--collect-all=av",                    # FFmpeg DLLs (avcodec, avformat, etc.)
        "--collect-all=pymobiledevice3",
        "--collect-all=OpenGL",

        # libusb_package bundles libusb-1.0.dll (libusb1 backend).
        # We use usb.backend.libusb0 which requires libusb0.dll (libusb-win32).
        # libusb0.dll is NOT in libusb_package — we collect it separately below.
        # (On the developer machine it is in System32, put there by MIRANCE / libusb-win32 installer.)
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
    from mirance import __version__
    print(f"Building MIRANCE v{__version__}  [{mode_str}]")
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
    # have MIRANCE (or libusb-win32) installed and will never enumerate the
    # iPhone.  We copy it from System32 (where MIRANCE/libusb-win32 installs
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
        print("    is already installed (e.g. machines that have MIRANCE).")
        print("    To fix: install libusb-win32 on the BUILD machine first,")
        print("    or place libusb0.dll in C:\\Windows\\System32 manually.")
    # ────────────────────────────────────────────────────────────────────────

    # ── Bundle FFmpeg DLLs (exact match to AnyMiro) ────────────────────────
    # AnyMiro includes: avcodec-60.dll, avformat-60.dll, avutil-58.dll,
    # swresample-4.dll, swscale-7.dll
    # We bundle these for fallback if PyAV's bundled FFmpeg has issues
    _ffmpeg_dlls = [
        "avcodec-60.dll",
        "avformat-60.dll", 
        "avutil-58.dll",
        "swresample-4.dll",
        "swscale-7.dll",
    ]
    _ffmpeg_path = os.path.join(PROJECT_ROOT, "assets", "ffmpeg")
    _bundled_ffmpeg = 0
    for _dll in _ffmpeg_dlls:
        _src = os.path.join(_ffmpeg_path, _dll)
        if os.path.exists(_src):
            args.append(f"--add-binary={_src}{os.pathsep}.")
            _bundled_ffmpeg += 1
    if _bundled_ffmpeg > 0:
        print(f"  FFmpeg      : {_bundled_ffmpeg} DLLs bundled (like AnyMiro)")
    else:
        print("  FFmpeg      : Using PyAV bundled FFmpeg (no external DLLs)")
    # ────────────────────────────────────────────────────────────────────────

    # ── Bundle libusb DLLs (from usbmuxd folder - exact AnyMiro) ───────────
    # AnyMiro includes libusb0.dll and libusb-1.0.dll in usbmuxd folder
    # These are critical for USB device communication
    _libusb_dlls = [
        ("libusb0.dll", "libusb0.dll"),
        ("libusb-1.0.dll", "libusb-1.0.dll"),
    ]
    _bundled_libusb = 0
    for _src_name, _dst_name in _libusb_dlls:
        _src = os.path.join(PROJECT_ROOT, "assets", _src_name)
        if os.path.exists(_src):
            args.append(f"--add-binary={_src}{os.pathsep}.")
            _bundled_libusb += 1
            print(f"  libusb     : {_src_name} bundled (like AnyMiro)")
    # ────────────────────────────────────────────────────────────────────────

    # ── Bundle usbmuxd.exe (exact copy from AnyMiro) ────────────────────────
    # usbmuxd.exe is the USB multiplexing daemon - critical for iPhone USB
    _usbmuxd = os.path.join(PROJECT_ROOT, "assets", "usbmuxd.exe")
    if os.path.exists(_usbmuxd):
        args.append(f"--add-binary={_usbmuxd}{os.pathsep}.")
        print(f"  usbmuxd.exe : Bundled (like AnyMiro)")
    else:
        print(f"  usbmuxd.exe : NOT FOUND - will use Python usbmux implementation")
    # ────────────────────────────────────────────────────────────────────────

    # ── Bundle iosusb.exe (exact copy from AnyMiro) ────────────────────────
    # iosusb.exe is the iOS USB mirroring executable
    _iosusb = os.path.join(PROJECT_ROOT, "assets", "iosusb.exe")
    if os.path.exists(_iosusb):
        args.append(f"--add-binary={_iosusb}{os.pathsep}.")
        print(f"  iosusb.exe  : Bundled (like AnyMiro)")
    # ────────────────────────────────────────────────────────────────────────

    # ── Bundle driver.exe (exact copy from AnyMiro) ────────────────────────
    # driver.exe is the driver installer
    _driver = os.path.join(PROJECT_ROOT, "assets", "driver.exe")
    if os.path.exists(_driver):
        args.append(f"--add-binary={_driver}{os.pathsep}.")
        print(f"  driver.exe  : Bundled (like AnyMiro)")
    # ────────────────────────────────────────────────────────────────────────

    PyInstaller.__main__.run(args)

    exe_path = os.path.join(PROJECT_ROOT, "dist", "MIRANCE", "MIRANCE.exe")
    if os.path.exists(exe_path):
        # Calculate total bundle size (entire dist folder)
        total_size = 0
        dist_dir = os.path.join(PROJECT_ROOT, "dist", "MIRANCE")
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
            print("  ** Run MIRANCE.exe from a terminal to see errors **")
    else:
        print()
        print("[FAIL] Build may have failed -- executable not found at expected path")
        print(f"   Expected: {exe_path}")
        sys.exit(1)


if __name__ == "__main__":
    build()
