"""
IMIRROR4FREE — Main entry point.

Usage:
    python -m imirror
"""

import sys
import signal
import logging
import argparse

from PyQt6.QtWidgets import QApplication
from PyQt6.QtCore import Qt

from imirror import __version__, __app_name__
from imirror.config import config, CaptureBackend, DecoderType
from imirror.gui.main_window import MainWindow

logger = logging.getLogger(__name__)


def setup_logging(verbose: bool = False) -> None:
    """Configure logging for the application."""
    level = logging.DEBUG if verbose else logging.INFO
    logging.basicConfig(
        level=level,
        format="%(asctime)s [%(levelname)-7s] %(name)-25s │ %(message)s",
        datefmt="%H:%M:%S",
    )


def parse_args() -> argparse.Namespace:
    """Parse command-line arguments."""
    parser = argparse.ArgumentParser(
        prog="imirror",
        description=f"{__app_name__} v{__version__} — iPhone USB Screen Mirroring",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable verbose debug logging",
    )
    parser.add_argument(
        "--backend",
        choices=["auto", "screenshot", "valeria"],
        default="auto",
        help="Capture backend (default: auto)",
    )
    parser.add_argument(
        "--decoder",
        choices=["auto", "software", "dxva2", "d3d11va"],
        default="auto",
        help="Video decoder (default: auto = hardware with software fallback)",
    )
    parser.add_argument(
        "--fps",
        action="store_true",
        help="Show FPS overlay on startup",
    )
    parser.add_argument(
        "--fullscreen",
        action="store_true",
        help="Start in fullscreen mode",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"{__app_name__} v{__version__}",
    )
    return parser.parse_args()


def apply_args_to_config(args: argparse.Namespace) -> None:
    """Apply CLI arguments to the global config."""
    if args.backend == "screenshot":
        config.capture_backend = CaptureBackend.SCREENSHOT
    elif args.backend == "valeria":
        config.capture_backend = CaptureBackend.VALERIA

    if args.decoder == "software":
        config.decoder_type = DecoderType.SOFTWARE
    elif args.decoder == "dxva2":
        config.decoder_type = DecoderType.HARDWARE_DXVA2
    elif args.decoder == "d3d11va":
        config.decoder_type = DecoderType.HARDWARE_D3D11

    if args.fps:
        config.show_fps_overlay = True

    if args.fullscreen:
        config.start_fullscreen = True


def main() -> int:
    """Application entry point."""
    args = parse_args()
    setup_logging(verbose=args.verbose)

    logger.info("=" * 60)
    logger.info(f"  {__app_name__} v{__version__}")
    logger.info(f"  The definitive iPhone USB screen mirror")
    logger.info("=" * 60)

    apply_args_to_config(args)

    # Allow Ctrl+C to kill the app
    signal.signal(signal.SIGINT, signal.SIG_DFL)

    # Create Qt application
    app = QApplication(sys.argv)
    app.setApplicationName(__app_name__)
    app.setApplicationVersion(__version__)

    # High-DPI support
    app.setHighDpiScaleFactorRoundingPolicy(
        Qt.HighDpiScaleFactorRoundingPolicy.PassThrough
    )

    # Create and show main window
    window = MainWindow()
    if config.start_fullscreen:
        window.showFullScreen()
    else:
        window.show()

    logger.info("Application started. Waiting for iPhone connection...")

    return app.exec()


if __name__ == "__main__":
    sys.exit(main())
