from setuptools import setup, find_packages

setup(
    name="imirror4free",
    version="0.1.0",
    description="The definitive free iPhone USB screen mirroring tool for Windows",
    author="unluckybob",
    url="https://github.com/unluckybob/IMIRROR4FREE",
    packages=find_packages(),
    python_requires=">=3.10",
    entry_points={
        "console_scripts": [
            "imirror=imirror.main:main",
        ],
    },
)
