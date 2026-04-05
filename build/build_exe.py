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

PyInstaller.__main__.run([
    os.path.join(ROOT, "imirror", "main.py"),
    "--name=IMIRROR4FREE",
    "--onefile",
    "--windowed",
    # "--icon=assets/icon.ico",    # Uncomment when icon is ready
    "--add-data=imirror;imirror",
    "--hidden-import=pymobiledevice3",
    "--hidden-import=PyQt6",
    "--hidden-import=OpenGL",
    "--hidden-import=av",
    "--hidden-import=numpy",
    "--hidden-import=PIL",
    f"--distpath={os.path.join(ROOT, 'dist')}",
    f"--workpath={os.path.join(ROOT, 'build', 'temp')}",
    f"--specpath={os.path.join(ROOT, 'build')}",
    "--clean",
])
