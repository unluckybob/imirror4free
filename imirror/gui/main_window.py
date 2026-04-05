"""
Main Application Window.

The central hub that connects device detection, capture backends,
and the OpenGL renderer into a cohesive user experience.

Features:
- Auto-detect iPhone on USB
- Show waiting screen with connection instructions
- Switch to mirror view when device connects
- FPS overlay (F3)
- Fullscreen mode (F11)
- Clean status bar with device info
- Automatic error recovery with user feedback
"""

import logging
from typing import Optional

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QStackedWidget, QStatusBar, QApplication,
    QMessageBox,
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QKeyEvent, QAction

from imirror import __version__, __app_name__
from imirror.config import config, CaptureBackend
from imirror.usb.device_manager import DeviceManager, iPhoneDevice
from imirror.capture.base import CapturedFrame, CaptureBackend as CaptureBackendBase
from imirror.capture.screenshot import ScreenshotCapture
from imirror.capture.stream import ValeriaStreamCapture
from imirror.render.gl_renderer import GLRenderer
from imirror.gui.overlay import FPSOverlay
from imirror.gui.styles import DARK_THEME

logger = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    """Main application window for IMIRROR4FREE."""

    # Signals to update UI from background threads
    _device_connected_signal = pyqtSignal(object)
    _device_disconnected_signal = pyqtSignal(str)
    _frame_ready_signal = pyqtSignal(object)
    _capture_stopped_signal = pyqtSignal(str)

    def __init__(self):
        super().__init__()

        # State
        self._current_device: Optional[iPhoneDevice] = None
        self._capture: Optional[CaptureBackendBase] = None
        self._is_mirroring = False

        # Setup UI
        self._setup_window()
        self._setup_widgets()
        self._setup_signals()
        self._apply_theme()

        # Create device manager and start scanning
        self._device_manager = DeviceManager(poll_interval=1.0)
        self._device_manager.on_device_connected(self._on_device_connected)
        self._device_manager.on_device_disconnected(self._on_device_disconnected)
        self._device_manager.start()

        # Status update timer
        self._status_timer = QTimer(self)
        self._status_timer.timeout.connect(self._update_status)
        self._status_timer.start(500)

    # ─── Window setup ───────────────────────────────────────────────

    def _setup_window(self) -> None:
        """Configure the main window."""
        self.setWindowTitle(f"{__app_name__}")
        self.resize(config.default_width, config.default_height)
        self.setMinimumSize(480, 320)

        if config.start_fullscreen:
            self.showFullScreen()

    def _setup_widgets(self) -> None:
        """Create and layout all widgets."""
        central = QWidget()
        self.setCentralWidget(central)

        layout = QVBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # Stacked widget: waiting screen / mirror view
        self._stack = QStackedWidget()
        layout.addWidget(self._stack)

        # Page 0: Waiting for device
        self._waiting_widget = self._create_waiting_screen()
        self._stack.addWidget(self._waiting_widget)

        # Page 1: Mirror view (OpenGL renderer)
        self._mirror_container = QWidget()
        mirror_layout = QVBoxLayout(self._mirror_container)
        mirror_layout.setContentsMargins(0, 0, 0, 0)

        self._renderer = GLRenderer(self._mirror_container)
        mirror_layout.addWidget(self._renderer)

        # FPS overlay (floating on top of renderer)
        self._fps_overlay = FPSOverlay(self._renderer)
        self._fps_overlay.setVisible(config.show_fps_overlay)

        self._stack.addWidget(self._mirror_container)

        # Start on waiting screen
        self._stack.setCurrentIndex(0)

        # Status bar
        self._status_bar = QStatusBar()
        self.setStatusBar(self._status_bar)
        self._status_label = QLabel("Waiting for iPhone...")
        self._status_bar.addWidget(self._status_label)
        self._status_bar.addPermanentWidget(QLabel(f"v{__version__}"))

    def _create_waiting_screen(self) -> QWidget:
        """Create the 'waiting for device' screen."""
        widget = QWidget()
        widget.setObjectName("waitingScreen")

        layout = QVBoxLayout(widget)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(16)

        # Icon
        icon_label = QLabel("📱")
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        icon_label.setStyleSheet("font-size: 64px; background: transparent;")
        layout.addWidget(icon_label)

        # Title
        title = QLabel(__app_name__)
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet("""
            font-size: 28px;
            font-weight: bold;
            color: #FFFFFF;
            background: transparent;
        """)
        layout.addWidget(title)

        # Subtitle — this label is updated to show errors too
        self._waiting_subtitle = QLabel("Connect your iPhone via USB cable")
        self._waiting_subtitle.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._waiting_subtitle.setObjectName("waitingSubtitle")
        self._waiting_subtitle.setStyleSheet("""
            font-size: 14px;
            color: #888888;
            background: transparent;
        """)
        layout.addWidget(self._waiting_subtitle)

        # Instructions
        instructions = QLabel(
            "1. Connect iPhone with a USB cable\n"
            "2. Tap \"Trust\" on your iPhone if prompted\n"
            "3. Mirroring starts automatically"
        )
        instructions.setAlignment(Qt.AlignmentFlag.AlignCenter)
        instructions.setStyleSheet("""
            font-size: 12px;
            color: #666666;
            background: transparent;
            line-height: 1.6;
            margin-top: 16px;
        """)
        layout.addWidget(instructions)

        # Scanning indicator
        self._scanning_label = QLabel("🔍 Scanning for devices...")
        self._scanning_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._scanning_label.setStyleSheet("""
            font-size: 11px;
            color: #0078D4;
            background: transparent;
            margin-top: 24px;
        """)
        layout.addWidget(self._scanning_label)

        return widget

    def _setup_signals(self) -> None:
        """Connect thread-safe signals."""
        self._device_connected_signal.connect(self._handle_device_connected)
        self._device_disconnected_signal.connect(self._handle_device_disconnected)
        self._frame_ready_signal.connect(self._handle_frame_ready)
        self._capture_stopped_signal.connect(self._handle_capture_stopped)

    def _apply_theme(self) -> None:
        """Apply the dark theme stylesheet."""
        self.setStyleSheet(DARK_THEME)

    # ─── Device events (from background thread) ────────────────────

    def _on_device_connected(self, device: iPhoneDevice) -> None:
        """Called from DeviceManager thread when a device connects."""
        self._device_connected_signal.emit(device)

    def _on_device_disconnected(self, udid: str) -> None:
        """Called from DeviceManager thread when a device disconnects."""
        self._device_disconnected_signal.emit(udid)

    @pyqtSlot(object)
    def _handle_device_connected(self, device: iPhoneDevice) -> None:
        """Handle device connection on the UI thread."""
        logger.info("UI: Device connected — %s", device.display_name)
        self._current_device = device

        # Reset any previous error state on the waiting screen
        self._waiting_subtitle.setText("Connect your iPhone via USB cable")
        self._waiting_subtitle.setStyleSheet("""
            font-size: 14px;
            color: #888888;
            background: transparent;
        """)

        self._start_mirroring(device)

    @pyqtSlot(str)
    def _handle_device_disconnected(self, udid: str) -> None:
        """Handle device disconnection on the UI thread."""
        logger.info("UI: Device disconnected")
        self._stop_mirroring()
        self._current_device = None
        self._stack.setCurrentIndex(0)
        self._status_label.setText("Waiting for iPhone...")
        self._waiting_subtitle.setText("Connect your iPhone via USB cable")
        self._waiting_subtitle.setStyleSheet("""
            font-size: 14px;
            color: #888888;
            background: transparent;
        """)

    @pyqtSlot(str)
    def _handle_capture_stopped(self, reason: str) -> None:
        """Handle unexpected capture stop — show error and return to waiting screen."""
        logger.warning("Capture stopped unexpectedly: %s", reason)
        self._stop_mirroring()
        self._stack.setCurrentIndex(0)

        # Show the error on the waiting screen
        self._waiting_subtitle.setText(f"⚠️ {reason}")
        self._waiting_subtitle.setStyleSheet("""
            font-size: 14px;
            color: #FF6B6B;
            background: transparent;
        """)
        self._scanning_label.setText("🔍 Scanning for devices... (will auto-reconnect)")
        self._status_label.setText("⚠️ Capture stopped — waiting for reconnect...")

    # ─── Mirroring control ──────────────────────────────────────────

    def _start_mirroring(self, device: iPhoneDevice) -> None:
        """Start screen mirroring with the best available backend."""
        # Select backend
        self._capture = self._select_backend()

        if self._capture is None:
            logger.error("No capture backend available!")
            self._status_label.setText("❌ No capture backend available")
            self._waiting_subtitle.setText("⚠️ No capture backend available — check installation")
            self._waiting_subtitle.setStyleSheet("""
                font-size: 14px;
                color: #FF6B6B;
                background: transparent;
            """)
            return

        logger.info("Using capture backend: %s", self._capture.name)

        # Register frame callback
        self._capture.on_frame(self._on_frame_captured)

        # Register capture-stopped callback for error recovery
        self._capture._on_capture_stopped = lambda reason: self._capture_stopped_signal.emit(reason)

        # Start capture
        success = self._capture.start(device.udid)
        if not success:
            logger.error("Failed to start capture backend")
            self._status_label.setText("❌ Failed to start mirroring")
            self._waiting_subtitle.setText("⚠️ Failed to connect — try unplugging and replugging")
            self._waiting_subtitle.setStyleSheet("""
                font-size: 14px;
                color: #FF6B6B;
                background: transparent;
            """)
            return

        self._is_mirroring = True
        self._stack.setCurrentIndex(1)
        self._status_label.setText(
            f"📱 {device.display_name} • {self._capture.name}"
        )

    def _stop_mirroring(self) -> None:
        """Stop screen mirroring."""
        if self._capture:
            self._capture.stop()
            self._capture = None
        self._is_mirroring = False

    def _select_backend(self) -> Optional[CaptureBackendBase]:
        """Select the best available capture backend."""
        if config.auto_select_backend:
            # Try Valeria first (best quality)
            valeria = ValeriaStreamCapture()
            if valeria.is_available():
                logger.info("Auto-selected: Valeria Stream backend")
                return valeria

            # Fall back to screenshots
            screenshot = ScreenshotCapture()
            if screenshot.is_available():
                logger.info("Auto-selected: Screenshot backend")
                return screenshot

            return None
        else:
            # Use configured backend
            if config.capture_backend == CaptureBackend.VALERIA_STREAM:
                return ValeriaStreamCapture()
            else:
                return ScreenshotCapture()

    def _on_frame_captured(self, frame: CapturedFrame) -> None:
        """Called from capture thread when a new frame is ready."""
        self._frame_ready_signal.emit(frame)

    @pyqtSlot(object)
    def _handle_frame_ready(self, frame: CapturedFrame) -> None:
        """Handle new frame on the UI thread — upload to renderer."""
        self._renderer.set_frame(frame.pixels, frame.width, frame.height)

        # Update overlay stats
        if self._capture:
            self._fps_overlay.update_stats(
                capture_fps=self._capture.fps,
                resolution=f"{frame.width}×{frame.height}",
                backend=self._capture.name,
                frame_count=self._capture.frame_count,
            )

    # ─── Status updates ─────────────────────────────────────────────

    def _update_status(self) -> None:
        """Periodic status bar update."""
        if self._is_mirroring and self._capture:
            fps = self._capture.fps
            self._status_label.setText(
                f"📱 Mirroring • {fps:.1f} FPS • {self._capture.name}"
            )

    # ─── Keyboard shortcuts ─────────────────────────────────────────

    def keyPressEvent(self, event: QKeyEvent) -> None:
        """Handle keyboard shortcuts."""
        key = event.key()

        if key == Qt.Key.Key_F11:
            # Toggle fullscreen
            if self.isFullScreen():
                self.showNormal()
            else:
                self.showFullScreen()

        elif key == Qt.Key.Key_F3:
            # Toggle FPS overlay
            visible = not self._fps_overlay.isVisible()
            self._fps_overlay.setVisible(visible)
            config.show_fps_overlay = visible

        elif key == Qt.Key.Key_Escape:
            if self.isFullScreen():
                self.showNormal()
            else:
                self.close()

        else:
            super().keyPressEvent(event)

    # ─── Cleanup ────────────────────────────────────────────────────

    def closeEvent(self, event) -> None:
        """Clean up on window close."""
        logger.info("Shutting down...")
        self._stop_mirroring()
        self._device_manager.stop()
        event.accept()

    def resizeEvent(self, event) -> None:
        """Handle window resize — update overlay position."""
        super().resizeEvent(event)
        if hasattr(self, '_fps_overlay') and hasattr(self, '_renderer'):
            # Resize overlay to match the renderer widget, not the whole window
            self._fps_overlay.resize(self._renderer.width(), self._renderer.height())
