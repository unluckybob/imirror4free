"""
Main Application Window — Phase 2.

The central hub that connects device detection, capture backends,
driver installation, and the OpenGL renderer into a cohesive user experience.

Features:
- Auto-detect iPhone on USB (via usbmuxd or pyusb)
- Show waiting screen with connection instructions
- "Install Mirror Driver" button for first-time setup (Phase 2)
- Driver status indicator
- Switch to mirror view when device connects
- FPS overlay (F3)
- Fullscreen mode (F11)
- Clean status bar with device info
- Automatic error recovery with user feedback
"""

import logging
import platform
import threading
from typing import Optional

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QLabel, QStackedWidget, QStatusBar, QApplication,
    QMessageBox, QPushButton,
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, pyqtSlot
from PyQt6.QtGui import QKeyEvent, QAction

from imirror import __version__, __app_name__
from imirror.config import config, CaptureBackend
from imirror.usb.device_manager import DeviceManager, iPhoneDevice
from imirror.capture.base import CapturedFrame, CaptureBackend as CaptureBackendBase
from imirror.capture.screenshot import ScreenshotCapture
from imirror.capture.stream import ValeriaStreamCapture, StreamError
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
    _driver_install_result_signal = pyqtSignal(bool, str)

    def __init__(self):
        super().__init__()

        # State
        self._current_device: Optional[iPhoneDevice] = None
        self._capture: Optional[CaptureBackendBase] = None
        self._is_mirroring = False
        self._show_fps_overlay = config.show_fps_overlay

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
        self.resize(config.default_window_width, config.default_window_height)
        self.setMinimumSize(320, 480)

        if config.always_on_top:
            self.setWindowFlags(
                self.windowFlags() | Qt.WindowType.WindowStaysOnTopHint
            )

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
        from imirror.render.gl_renderer import GLRenderer

        self._mirror_container = QWidget()
        mirror_layout = QVBoxLayout(self._mirror_container)
        mirror_layout.setContentsMargins(0, 0, 0, 0)

        self._renderer = GLRenderer(self._mirror_container)
        mirror_layout.addWidget(self._renderer)

        # FPS overlay (floating on top of renderer)
        self._fps_overlay = FPSOverlay(self._renderer)
        self._fps_overlay.setVisible(self._show_fps_overlay)

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
        """Create the 'waiting for device' screen with driver install button."""
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

        # Subtitle — updated to show errors and status
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

        # ─── Driver install button (Phase 2) ────────────────────────
        # Only shown on Windows and when driver installation is needed.
        self._driver_button_container = QWidget()
        driver_layout = QVBoxLayout(self._driver_button_container)
        driver_layout.setSpacing(8)
        driver_layout.setContentsMargins(40, 16, 40, 0)

        self._driver_install_btn = QPushButton("🔧 Install Mirror Driver")
        self._driver_install_btn.setStyleSheet("""
            QPushButton {
                background-color: #0078D4;
                color: white;
                border: none;
                border-radius: 6px;
                padding: 12px 24px;
                font-size: 14px;
                font-weight: bold;
            }
            QPushButton:hover {
                background-color: #1084D8;
            }
            QPushButton:pressed {
                background-color: #005A9E;
            }
            QPushButton:disabled {
                background-color: #444444;
                color: #888888;
            }
        """)
        self._driver_install_btn.clicked.connect(self._on_install_driver_clicked)
        self._driver_install_btn.setVisible(False)  # Hidden by default
        driver_layout.addWidget(self._driver_install_btn)

        # Driver status label
        self._driver_status_label = QLabel("")
        self._driver_status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._driver_status_label.setStyleSheet("""
            font-size: 11px;
            color: #888888;
            background: transparent;
        """)
        self._driver_status_label.setVisible(False)
        driver_layout.addWidget(self._driver_status_label)

        # Restore driver button (smaller, below install)
        self._driver_restore_btn = QPushButton("Restore Original Apple Driver")
        self._driver_restore_btn.setStyleSheet("""
            QPushButton {
                background-color: transparent;
                color: #888888;
                border: 1px solid #555555;
                border-radius: 4px;
                padding: 6px 16px;
                font-size: 11px;
            }
            QPushButton:hover {
                color: #FFFFFF;
                border-color: #888888;
            }
        """)
        self._driver_restore_btn.clicked.connect(self._on_restore_driver_clicked)
        self._driver_restore_btn.setVisible(False)
        driver_layout.addWidget(self._driver_restore_btn)

        layout.addWidget(self._driver_button_container)

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

        # Show driver button on Windows
        if platform.system() == "Windows":
            self._check_and_show_driver_button()

        return widget

    def _check_and_show_driver_button(self) -> None:
        """Check driver status and show/hide the install button."""
        try:
            from imirror.usb.driver_installer import check_driver_status
            status = check_driver_status()

            if status.ready_to_stream:
                # Driver is ready — hide button, show status
                self._driver_install_btn.setVisible(False)
                self._driver_status_label.setText("✅ Mirror driver ready")
                self._driver_status_label.setVisible(True)
                self._driver_restore_btn.setVisible(True)
            elif status.installed and not status.libusb_accessible:
                # Installed but needs replug
                self._driver_install_btn.setVisible(False)
                self._driver_status_label.setText(
                    "⚡ Driver installed — unplug & replug your iPhone"
                )
                self._driver_status_label.setStyleSheet("""
                    font-size: 11px;
                    color: #FFB900;
                    background: transparent;
                """)
                self._driver_status_label.setVisible(True)
                self._driver_restore_btn.setVisible(True)
            else:
                # Show install button
                self._driver_install_btn.setVisible(True)
                self._driver_status_label.setVisible(False)
                self._driver_restore_btn.setVisible(False)

        except ImportError:
            # driver_installer not available — show the button anyway
            self._driver_install_btn.setVisible(True)

    def _setup_signals(self) -> None:
        """Connect thread-safe signals."""
        self._device_connected_signal.connect(self._handle_device_connected)
        self._device_disconnected_signal.connect(self._handle_device_disconnected)
        self._frame_ready_signal.connect(self._handle_frame_ready)
        self._capture_stopped_signal.connect(self._handle_capture_stopped)
        self._driver_install_result_signal.connect(self._handle_driver_install_result)

    def _apply_theme(self) -> None:
        """Apply the dark theme stylesheet."""
        self.setStyleSheet(DARK_THEME)

    # ─── Driver installation (Phase 2) ──────────────────────────────

    def _on_install_driver_clicked(self) -> None:
        """Handle 'Install Mirror Driver' button click."""
        self._driver_install_btn.setEnabled(False)
        self._driver_install_btn.setText("⏳ Installing...")
        self._driver_status_label.setText("Requesting administrator privileges...")
        self._driver_status_label.setVisible(True)

        # Run installation in background thread to not block UI
        thread = threading.Thread(
            target=self._do_install_driver,
            name="driver-install",
            daemon=True,
        )
        thread.start()

    def _do_install_driver(self) -> None:
        """Install the mirror driver (runs on background thread)."""
        try:
            from imirror.usb.driver_installer import full_driver_setup
            result = full_driver_setup()
            self._driver_install_result_signal.emit(result.success, result.message)
        except Exception as e:
            self._driver_install_result_signal.emit(False, f"Installation error: {e}")

    @pyqtSlot(bool, str)
    def _handle_driver_install_result(self, success: bool, message: str) -> None:
        """Handle driver installation result on the UI thread."""
        self._driver_install_btn.setEnabled(True)

        if success:
            self._driver_install_btn.setText("✅ Driver Installed")
            self._driver_install_btn.setEnabled(False)
            self._driver_status_label.setText(
                "⚡ " + message
            )
            self._driver_status_label.setStyleSheet("""
                font-size: 11px;
                color: #4CAF50;
                background: transparent;
            """)
            self._driver_restore_btn.setVisible(True)
        else:
            self._driver_install_btn.setText("🔧 Install Mirror Driver")
            self._driver_status_label.setText(f"❌ {message}")
            self._driver_status_label.setStyleSheet("""
                font-size: 11px;
                color: #FF6B6B;
                background: transparent;
            """)

    def _on_restore_driver_clicked(self) -> None:
        """Handle 'Restore Original Driver' button click."""
        reply = QMessageBox.question(
            self,
            "Restore Apple Driver",
            "This will remove the IMIRROR4FREE mirror driver and restore "
            "Apple's original iPhone USB driver.\n\n"
            "iTunes/Apple Music will work again, but you'll need to "
            "reinstall the mirror driver to use screen mirroring.\n\n"
            "Continue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
            QMessageBox.StandardButton.No,
        )

        if reply == QMessageBox.StandardButton.Yes:
            try:
                from imirror.usb.driver_installer import uninstall_driver
                result = uninstall_driver()
                QMessageBox.information(
                    self,
                    "Driver Restored" if result.success else "Error",
                    result.message,
                )
                if result.success:
                    self._driver_install_btn.setVisible(True)
                    self._driver_install_btn.setText("🔧 Install Mirror Driver")
                    self._driver_install_btn.setEnabled(True)
                    self._driver_restore_btn.setVisible(False)
                    self._driver_status_label.setText("Apple driver will be restored on next plug")
            except Exception as e:
                QMessageBox.critical(self, "Error", f"Failed to restore driver: {e}")

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

        # Reset any previous error state
        self._waiting_subtitle.setText("Connect your iPhone via USB cable")
        self._waiting_subtitle.setStyleSheet("""
            font-size: 14px;
            color: #888888;
            background: transparent;
        """)

        # Refresh driver button state
        if platform.system() == "Windows":
            self._check_and_show_driver_button()

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

        # Show driver install button if it's a driver issue
        if hasattr(self._capture, 'error_type'):
            error_type = self._capture.error_type
            if error_type in (StreamError.DRIVER_NEEDED, StreamError.DRIVER_REPLUG):
                self._driver_install_btn.setVisible(True)
                if error_type == StreamError.DRIVER_REPLUG:
                    self._driver_status_label.setText(
                        "⚡ Unplug and replug your iPhone to activate the driver"
                    )
                    self._driver_status_label.setVisible(True)

    # ─── Mirroring control ──────────────────────────────────────────

    def _start_mirroring(self, device: iPhoneDevice) -> None:
        """Start screen mirroring with the best available backend."""
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

            # On failure, show the driver install button if on Windows
            if platform.system() == "Windows":
                self._driver_install_btn.setVisible(True)
            return

        logger.info("Using capture backend: %s", self._capture.name)

        # Register frame callback
        self._capture.on_frame(self._on_frame_captured)

        # Register capture-stopped callback for error recovery
        self._capture.on_capture_stopped(
            lambda reason: self._capture_stopped_signal.emit(reason)
        )

        # Start capture
        success = self._capture.start(device.udid)
        if not success:
            logger.error("Failed to start capture backend")
            self._status_label.setText("❌ Failed to start mirroring")

            # Check error type for actionable message
            error_msg = "⚠️ Failed to connect — try unplugging and replugging"
            if hasattr(self._capture, 'error_type'):
                if self._capture.error_type == StreamError.DRIVER_NEEDED:
                    error_msg = "⚠️ Mirror driver needed — click 'Install Mirror Driver' below"
                    self._driver_install_btn.setVisible(True)
                elif self._capture.error_type == StreamError.DRIVER_REPLUG:
                    error_msg = "⚠️ Please unplug and replug your iPhone"

            self._waiting_subtitle.setText(error_msg)
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
        """Select the best available capture backend based on config."""
        backend_pref = config.capture_backend

        if backend_pref == CaptureBackend.AUTO:
            valeria = ValeriaStreamCapture()
            if valeria.is_available():
                logger.info("Auto-selected: Valeria Stream backend")
                return valeria

            screenshot = ScreenshotCapture()
            if screenshot.is_available():
                logger.info("Auto-selected: Screenshot backend (Valeria unavailable)")
                return screenshot

            return None

        elif backend_pref == CaptureBackend.VALERIA:
            return ValeriaStreamCapture()

        elif backend_pref == CaptureBackend.SCREENSHOT:
            return ScreenshotCapture()

        else:
            logger.warning("Unknown backend preference: %s, using auto", backend_pref)
            return self._select_backend_auto()

    def _select_backend_auto(self) -> Optional[CaptureBackendBase]:
        """Auto-select backend (helper for unknown config values)."""
        valeria = ValeriaStreamCapture()
        if valeria.is_available():
            return valeria
        screenshot = ScreenshotCapture()
        if screenshot.is_available():
            return screenshot
        return None

    def _on_frame_captured(self, frame: CapturedFrame) -> None:
        """Called from capture thread when a new frame is ready."""
        self._frame_ready_signal.emit(frame)

    @pyqtSlot(object)
    def _handle_frame_ready(self, frame: CapturedFrame) -> None:
        """Handle new frame on the UI thread — upload to renderer."""
        self._renderer.set_frame(frame.pixels, frame.width, frame.height)

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
            if self.isFullScreen():
                self.showNormal()
            else:
                self.showFullScreen()

        elif key == Qt.Key.Key_F3:
            self._show_fps_overlay = not self._show_fps_overlay
            self._fps_overlay.setVisible(self._show_fps_overlay)

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
            self._fps_overlay.resize(self._renderer.width(), self._renderer.height())
