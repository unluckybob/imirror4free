from setuptools import setup, find_packages

setup(
    name="imirror4free",
    version="0.1.0",
    description="The definitive free iPhone USB screen mirroring tool for Windows",
    author="unluckybob",
    url="https://github.com/unluckybob/IMIRROR4FREE",
    packages=find_packages(),
    python_requires=">=3.10",
    install_requires=[
        "pymobiledevice3>=4.0.0",
        "PyQt6>=6.5.0",
        "PyQt6-WebEngine>=6.5.0",
        "PyOpenGL>=3.1.7",
        "numpy>=1.24.0",
        "Pillow>=10.0.0",
        "pyusb>=1.2.1",
        "av>=12.0.0",
        "sounddevice>=0.4.6",
    ],
    entry_points={
        "console_scripts": [
            "imirror=imirror.main:main",
        ],
    },
)
