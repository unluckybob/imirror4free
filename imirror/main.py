"""
IMIRROR4FREE — Entry Point.

A free, open-source USB screen mirroring tool for iPhone on Windows.
Uses Apple's Valeria protocol for zero-latency H.264 streaming.

Usage:
    python -m imirror                    # Launch GUI
    python -m imirror --backend valeria  # Force Valeria backend
    python -m imirror --install-driver   # Install mirror driver (CLI)
    python -m imirror --check-driver     # Check driver status (CLI)
    python -m imirror --diag             # Run full USB diagnostic
"""

import argparse
import logging
import sys
import os

if sys.stdout and hasattr(sys.stdout, 'reconfigure'):
    sys.stdout.reconfigure(encoding='utf-8', errors='replace')
if sys.stderr and hasattr(sys.stderr, 'reconfigure'):
    sys.stderr.reconfigure(encoding='utf-8', errors='replace')

from imirror import __version__, __app_name__
from imirror.config import config, CaptureBackendType


def setup_logging(verbose: bool = False, log_file: str = None) -> None:
    """Configure logging for the application."""
    level = logging.DEBUG if verbose else logging.INFO

    handlers = [logging.StreamHandler(sys.stdout)]
    if log_file:
        handlers.append(logging.FileHandler(log_file, encoding="utf-8"))

    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
        handlers=handlers,
    )

    # Quiet down noisy libraries
    logging.getLogger("PIL").setLevel(logging.WARNING)
    logging.getLogger("usb").setLevel(logging.WARNING)


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        prog="imirror",
        description=f"{__app_name__} v{__version__} — Free iPhone USB Screen Mirror",
    )

    parser.add_argument(
        "--version", action="version", version=f"{__app_name__} v{__version__}",
    )

    parser.add_argument(
        "--backend",
        choices=["auto", "valeria", "screenshot"],
        default="auto",
        help="Capture backend to use (default: auto)",
    )

    parser.add_argument(
        "--fps", action="store_true",
        help="Show FPS overlay on startup",
    )

    parser.add_argument(
        "--fullscreen", action="store_true",
        help="Start in fullscreen mode",
    )

    parser.add_argument(
        "--always-on-top", action="store_true",
        help="Keep the window above all others",
    )

    parser.add_argument(
        "--verbose", "-v", action="store_true",
        help="Enable debug logging",
    )

    parser.add_argument(
        "--log-file",
        help="Write logs to a file",
    )

    # Phase 2: Driver management commands
    parser.add_argument(
        "--install-driver", action="store_true",
        help="Install the WinUSB mirror driver (requires admin)",
    )

    parser.add_argument(
        "--uninstall-driver", action="store_true",
        help="Remove the mirror driver and restore Apple's driver",
    )

    parser.add_argument(
        "--check-driver", action="store_true",
        help="Check mirror driver status",
    )

    parser.add_argument(
        "--diag", action="store_true",
        help="Run comprehensive USB diagnostic",
    )

    return parser.parse_args()


def cmd_install_driver() -> int:
    """Install the WinUSB mirror driver via CLI."""
    from imirror.usb.driver_installer import full_driver_setup
    print(f"{__app_name__} — Mirror Driver Installer")
    print("=" * 50)
    result = full_driver_setup()
    print()
    print(f"{'[OK]' if result.success else '[FAIL]'} {result.message}")
    return 0 if result.success else 1


def cmd_uninstall_driver() -> int:
    """Uninstall the mirror driver via CLI."""
    from imirror.usb.driver_installer import uninstall_driver
    print(f"{__app_name__} — Restore Original Driver")
    print("=" * 50)
    result = uninstall_driver()
    print()
    print(f"{'[OK]' if result.success else '[FAIL]'} {result.message}")
    return 0 if result.success else 1


def cmd_check_driver() -> int:
    """Check driver status via CLI."""
    from imirror.usb.driver_installer import check_driver_status
    print(f"{__app_name__} — Driver Status")
    print("=" * 50)
    status = check_driver_status()
    print(f"  iPhone detected: {'Yes' if status.iphone_detected else 'No'}")
    print(f"  Driver installed: {'Yes' if status.installed else 'No'}")
    print(f"  libusb accessible: {'Yes' if status.libusb_accessible else 'No'}")
    print(f"  Ready to stream: {'Yes' if status.ready_to_stream else 'No'}")
    if status.device_pid is not None:
        print(f"  Device PID: 0x{status.device_pid:04X}")
    return 0 if status.ready_to_stream else 1


def cmd_diag() -> int:
    """Run comprehensive USB diagnostic via CLI."""
    from imirror.usb.driver_check import run_diagnostic
    return run_diagnostic()


def main() -> int:
    """Application entry point."""
    args = parse_args()
    setup_logging(verbose=args.verbose, log_file=args.log_file)

    logger = logging.getLogger(__name__)
    logger.info("%s v%s starting...", __app_name__, __version__)

    # Handle CLI-only commands
    if args.install_driver:
        return cmd_install_driver()
    if args.uninstall_driver:
        return cmd_uninstall_driver()
    if args.check_driver:
        return cmd_check_driver()
    if args.diag:
        return cmd_diag()

    # Apply config from CLI args
    backend_map = {
        "auto": CaptureBackendType.AUTO,
        "valeria": CaptureBackendType.VALERIA,
        "screenshot": CaptureBackendType.SCREENSHOT,
    }
    config.capture_backend = backend_map.get(args.backend, CaptureBackendType.AUTO)
    config.always_on_top = args.always_on_top or config.always_on_top
    config.show_fps_overlay = args.fps or config.show_fps_overlay
    config.start_fullscreen = args.fullscreen or config.start_fullscreen

    # Launch the Qt GUI
    try:
        from PyQt6.QtWidgets import QApplication
        from imirror.gui.main_window import MainWindow

        app = QApplication(sys.argv)
        app.setApplicationName(__app_name__)
        app.setApplicationVersion(__version__)

        window = MainWindow()
        window.show()

        if config.start_fullscreen:
            window.showFullScreen()

        logger.info("Application ready")
        return app.exec()

    except ImportError as e:
        logger.error("Missing dependency: %s", e)
        logger.error("Run: pip install -r requirements.txt")
        return 1
    except Exception as e:
        logger.exception("Fatal error: %s", e)
        return 1


if __name__ == "__main__":
    sys.exit(main())
