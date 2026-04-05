"""
PyInstaller Build Script — Package IMIRROR4FREE as a standalone .exe

Usage:
    python build/build_exe.py

Output:
    dist/IMIRROR4FREE.exe
"""

import PyInstaller.__main__
import os

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
IMIRROR_SRC = os.path.join(ROOT, "imirror")

PyInstaller.__main__.run([
    os.path.join(ROOT, "imirror", "main.py"),
    "--name=IMIRROR4FREE",
    "--onefile",
    "--windowed",
    # "--icon=assets/icon.ico",    # Uncomment when icon is ready
    f"--add-data={IMIRROR_SRC};imirror",
    "--hidden-import=pymobiledevice3",
    "--hidden-import=pymobiledevice3.services",
    "--hidden-import=pymobiledevice3.services.dvt",
    "--hidden-import=pymobiledevice3.lockdown",
    "--hidden-import=PyQt6",
    "--hidden-import=PyQt6.QtWidgets",
    "--hidden-import=PyQt6.QtCore",
    "--hidden-import=PyQt6.QtGui",
    "--hidden-import=PyQt6.QtOpenGLWidgets",
    "--hidden-import=OpenGL",
    "--hidden-import=OpenGL.GL",
    "--hidden-import=av",
    "--hidden-import=numpy",
    "--hidden-import=PIL",
    "--hidden-import=sounddevice",
    f"--distpath={os.path.join(ROOT, 'dist')}",
    f"--workpath={os.path.join(ROOT, 'build', 'temp')}",
    f"--specpath={os.path.join(ROOT, 'build')}",
    "--clean",
])
