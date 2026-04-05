import re
from setuptools import setup, find_packages

with open("imirror/__init__.py") as f:
    version = re.search(r'__version__\s*=\s*"(.+)"', f.read()).group(1)

setup(
    name="imirror4free",
    version=version,
    description="The definitive free iPhone USB screen mirroring tool for Windows",
    author="unluckybob",
    url="https://github.com/unluckybob/IMIRROR4FREE",
    packages=find_packages(),
    python_requires=">=3.10",
    install_requires=[
        "pyusb>=1.2.0",
        "libusb-package>=1.0.26.0",
        "pymobiledevice3>=2.0.0",
        "av>=12.0.0",
        "PyQt6>=6.6.0",
        "PyOpenGL>=3.1.7",
        "sounddevice>=0.4.6",
        "numpy>=1.24.0",
        "Pillow>=10.0.0",
    ],
    entry_points={
        "console_scripts": [
            "imirror=imirror.main:main",
        ],
    },
)
