"""
Build script — packages IMIRROR4FREE into a standalone Windows .exe
Uses PyInstaller with GPU-optimized settings.
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
    "--onefile",
    "--windowed",
    "--name", "IMIRROR4FREE",
    f"--icon={ICON_FILE}",
    f"--add-data={PROJECT_ROOT / 'imirror'};imirror",
    f"--add-data={PROJECT_ROOT / 'assets'};assets",
    "--hidden-import", "pymobiledevice3",
    "--hidden-import", "pymobiledevice3.usbmux",
    "--hidden-import", "pymobiledevice3.lockdown",
    "--hidden-import", "PyQt6",
    "--hidden-import", "PyQt6.QtOpenGLWidgets",
    "--hidden-import", "OpenGL",
    "--hidden-import", "OpenGL.GL",
    "--hidden-import", "av",
    "--hidden-import", "numpy",
    "--hidden-import", "PIL",
    "--collect-all", "pymobiledevice3",
    str(MAIN_SCRIPT),
]

print(f"[BUILD] Building IMIRROR4FREE.exe...")
print(f"   Project root: {PROJECT_ROOT}")
print(f"   Icon: {ICON_FILE}")
print(f"   Main script: {MAIN_SCRIPT}")
result = subprocess.run(cmd, cwd=str(PROJECT_ROOT))
sys.exit(result.returncode)
