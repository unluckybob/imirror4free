"""
Main Application Window.

The main GUI window for IMIRROR4FREE. Handles:
- Device detection and connection
- Frame rendering via OpenGL
- Recording controls (start/stop recording, screenshot)
- Settings dialog
- Keyboard shortcuts
- Driver installation UI
- Status bar with connection info
"""

import logging
import os
import sys
import time
import threading
from typing import Optional

import numpy as np

from PyQt6.QtWidgets import (
    QMainWindow, QWidget, QVBoxLayout, QHBoxLayout, QLabel,
    QPushButton, QStackedWidget, QStatusBar, QToolBar,
    QMessageBox, QFileDialog, QSlider, QDialog, QFormLayout,
    QComboBox, QCheckBox, QGroupBox, QSpinBox, QApplication,
    QSizePolicy, QMenu,
)
from PyQt6.QtCore import Qt, QTimer, pyqtSignal, QSize
from PyQt6.QtGui import QAction, QKeySequence, QIcon, QImage, QPixmap

from imirror import __version__, __app_name__
from imirror.config import config, CaptureBackendType, DecoderType, RecordingFormat
from imirror.gui.styles import DARK_THEME, WAITING_SCREEN_STYLE, TOOLBAR_STYLE, SETTINGS_DIALOG_STYLE
from imirror.gui.overlay import FPSOverlay

try:
    from imirror.render.gl_renderer import GLRenderer, OPENGL_AVAILABLE
except ImportError:
    OPENGL_AVAILABLE = False

logger = logging.getLogger(__name__)


class MainWindow(QMainWindow):
    """Main application window."""

    # Signals for cross-thread UI updates
    frame_ready = pyqtSignal(np.ndarray)
    status_update = pyqtSignal(str)
    error_signal = pyqtSignal(str, str)  # title, message
    recording_state_changed = pyqtSignal(bool)  # is_recording
    disconnected_signal = pyqtSignal()  # stream ended / device unplugged

    def __init__(self):
        super().__init__()
        self.setWindowTitle(f"{config.window_title} v{__version__}")
        self.resize(config.default_window_width, config.default_window_height)
        self.setMinimumSize(320, 480)

        # Set window icon
        icon_path = self._resource_path(os.path.join("assets", "icon.ico"))
        if os.path.exists(icon_path):
            self.setWindowIcon(QIcon(icon_path))

        # Apply dark theme
        self.setStyleSheet(DARK_THEME)

        # State
        self._capture_backend = None
        self._device_manager = None
        self._recorder = None
        self._audio_player = None
        self._current_frame: Optional[np.ndarray] = None
        self._is_connected = False
        self._is_recording = False
        self._consecutive_failures = 0
        self._last_capture_failure = 0.0

        # Build UI
        self._build_menu_bar()
        self._build_toolbar()
        self._build_central_widget()
        self._build_status_bar()
        self._setup_shortcuts()

        # Connect signals
        self.frame_ready.connect(self._on_frame_ready)
        self.status_update.connect(self._on_status_update)
        self.error_signal.connect(self._on_error)
        self.recording_state_changed.connect(self._on_recording_state_changed)
        self.disconnected_signal.connect(self._on_disconnected)

        # Timers
        self._stats_timer = QTimer(self)
        self._stats_timer.timeout.connect(self._update_stats)
        self._stats_timer.start(250)

        self._device_timer = QTimer(self)
        self._device_timer.timeout.connect(self._check_device)
        self._device_timer.start(2000)

        # Window flags
        if config.always_on_top:
            self.setWindowFlags(self.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)

        # FPS overlay
        self._fps_overlay = None
        if config.show_fps_overlay:
            self._toggle_fps_overlay()

        logger.info("Main window initialized")

    @staticmethod
    def _resource_path(relative_path: str) -> str:
        """Get path to resource, works for dev and PyInstaller."""
        if getattr(sys, 'frozen', False):
            base = os.path.dirname(sys.executable)
        else:
            base = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        return os.path.join(base, relative_path)

    # ─── UI Construction ────────────────────────────────────────────

    def _build_menu_bar(self) -> None:
        """Build the application menu bar."""
        menubar = self.menuBar()

        # File menu
        file_menu = menubar.addMenu("&File")

        self._action_screenshot = QAction("📸 Screenshot", self)
        self._action_screenshot.setShortcut(QKeySequence("Ctrl+S"))
        self._action_screenshot.triggered.connect(self._take_screenshot)
        self._action_screenshot.setEnabled(False)
        file_menu.addAction(self._action_screenshot)

        self._action_record = QAction("⏺ Start Recording", self)
        self._action_record.setShortcut(QKeySequence("Ctrl+R"))
        self._action_record.triggered.connect(self._toggle_recording)
        self._action_record.setEnabled(False)
        file_menu.addAction(self._action_record)

        file_menu.addSeparator()

        action_open_recordings = QAction("📂 Open Recordings Folder", self)
        action_open_recordings.triggered.connect(self._open_recordings_folder)
        file_menu.addAction(action_open_recordings)

        action_open_screenshots = QAction("📂 Open Screenshots Folder", self)
        action_open_screenshots.triggered.connect(self._open_screenshots_folder)
        file_menu.addAction(action_open_screenshots)

        file_menu.addSeparator()

        action_quit = QAction("Quit", self)
        action_quit.setShortcut(QKeySequence("Ctrl+Q"))
        action_quit.triggered.connect(self.close)
        file_menu.addAction(action_quit)

        # View menu
        view_menu = menubar.addMenu("&View")

        self._action_fullscreen = QAction("Fullscreen", self)
        self._action_fullscreen.setShortcut(QKeySequence("F11"))
        self._action_fullscreen.setCheckable(True)
        self._action_fullscreen.triggered.connect(self._toggle_fullscreen)
        view_menu.addAction(self._action_fullscreen)

        self._action_fps = QAction("FPS Overlay", self)
        self._action_fps.setShortcut(QKeySequence("F3"))
        self._action_fps.setCheckable(True)
        self._action_fps.setChecked(config.show_fps_overlay)
        self._action_fps.triggered.connect(self._toggle_fps_overlay)
        view_menu.addAction(self._action_fps)

        self._action_on_top = QAction("Always on Top", self)
        self._action_on_top.setCheckable(True)
        self._action_on_top.setChecked(config.always_on_top)
        self._action_on_top.triggered.connect(self._toggle_always_on_top)
        view_menu.addAction(self._action_on_top)

        # Tools menu
        tools_menu = menubar.addMenu("&Tools")

        action_install_driver = QAction("🔧 Install Mirror Driver", self)
        action_install_driver.triggered.connect(self._install_driver)
        tools_menu.addAction(action_install_driver)

        action_restore_driver = QAction("↩ Restore Original Driver", self)
        action_restore_driver.triggered.connect(self._restore_driver)
        tools_menu.addAction(action_restore_driver)

        tools_menu.addSeparator()

        action_check_driver = QAction("🔍 Check Driver Status", self)
        action_check_driver.triggered.connect(self._check_driver_status)
        tools_menu.addAction(action_check_driver)

        action_diag = QAction("🩺 Run USB Diagnostic", self)
        action_diag.triggered.connect(self._run_diagnostic)
        tools_menu.addAction(action_diag)

        tools_menu.addSeparator()

        action_settings = QAction("⚙ Settings", self)
        action_settings.setShortcut(QKeySequence("Ctrl+,"))
        action_settings.triggered.connect(self._open_settings)
        tools_menu.addAction(action_settings)

        # Help menu
        help_menu = menubar.addMenu("&Help")

        action_about = QAction("About", self)
        action_about.triggered.connect(self._show_about)
        help_menu.addAction(action_about)

        action_github = QAction("GitHub Repository", self)
        action_github.triggered.connect(
            lambda: __import__("webbrowser").open("https://github.com/unluckybob/imirror4free"))
        help_menu.addAction(action_github)

    def _build_toolbar(self) -> None:
        """Build the toolbar with recording controls."""
        self._toolbar = QToolBar("Controls")
        self._toolbar.setMovable(False)
        self._toolbar.setIconSize(QSize(20, 20))
        self._toolbar.setStyleSheet(TOOLBAR_STYLE)

        self._btn_screenshot = QAction("📸 Screenshot", self)
        self._btn_screenshot.triggered.connect(self._take_screenshot)
        self._btn_screenshot.setEnabled(False)
        self._toolbar.addAction(self._btn_screenshot)

        self._btn_record = QAction("⏺ Record", self)
        self._btn_record.triggered.connect(self._toggle_recording)
        self._btn_record.setEnabled(False)
        self._toolbar.addAction(self._btn_record)

        self._toolbar.addSeparator()

        # Volume slider
        self._volume_slider = QSlider(Qt.Orientation.Horizontal)
        self._volume_slider.setRange(0, 100)
        self._volume_slider.setValue(int(config.audio_volume * 100))
        self._volume_slider.setMaximumWidth(100)
        self._volume_slider.setStyleSheet("""
            QSlider::groove:horizontal {
                height: 4px;
                background: #2C2C2E;
                border-radius: 2px;
            }
            QSlider::handle:horizontal {
                background: #FFFFFF;
                width: 14px;
                margin: -5px 0;
                border-radius: 7px;
            }
            QSlider::sub-page:horizontal {
                background: #B5342B;
                border-radius: 2px;
            }
        """)
        self._volume_slider.valueChanged.connect(self._on_volume_changed)

        vol_label = QLabel("♪")
        vol_label.setStyleSheet("color: #8E8E93; padding: 0 6px; font-size: 14px;")
        self._toolbar.addWidget(vol_label)
        self._toolbar.addWidget(self._volume_slider)

        self.addToolBar(self._toolbar)

    def _build_central_widget(self) -> None:
        """Build the central stacked widget (waiting screen ↔ mirror view)."""
        self._stack = QStackedWidget()
        self.setCentralWidget(self._stack)

        # Page 0: Waiting screen
        self._waiting_page = self._build_waiting_page()
        self._stack.addWidget(self._waiting_page)

        # Page 1: Mirror view (frame display)
        self._mirror_page = QWidget()
        mirror_layout = QVBoxLayout(self._mirror_page)
        mirror_layout.setContentsMargins(0, 0, 0, 0)

        # Use GPU-accelerated GLRenderer when available, fall back to QLabel
        self._gl_renderer = None
        self._frame_label = None

        if OPENGL_AVAILABLE:
            self._gl_renderer = GLRenderer()
            self._gl_renderer.setSizePolicy(
                QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
            mirror_layout.addWidget(self._gl_renderer)
            logger.info("Using OpenGL GPU renderer")
        else:
            self._frame_label = QLabel()
            self._frame_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
            self._frame_label.setStyleSheet("background: #000;")
            self._frame_label.setSizePolicy(
                QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
            mirror_layout.addWidget(self._frame_label)
            logger.info("OpenGL not available — using QLabel fallback renderer")

        self._stack.addWidget(self._mirror_page)

        # Start on waiting page
        self._stack.setCurrentIndex(0)

    def _build_waiting_page(self) -> QWidget:
        """Build the waiting/connection screen."""
        page = QWidget()
        page.setObjectName("waitingScreen")
        page.setStyleSheet(WAITING_SCREEN_STYLE)

        layout = QVBoxLayout(page)
        layout.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.setSpacing(16)

        # Icon — load the actual app icon
        icon_label = QLabel()
        icon_label.setObjectName("waitingIcon")
        icon_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        _icon_path = self._resource_path(os.path.join("assets", "icon.ico"))
        if os.path.exists(_icon_path):
            _pixmap = QPixmap(_icon_path).scaled(
                96, 96,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            icon_label.setPixmap(_pixmap)
        else:
            icon_label.setText("⬡")
            icon_label.setStyleSheet("font-size: 64px; color: #B5342B;")
        layout.addWidget(icon_label)

        # Title
        title_label = QLabel(f"{__app_name__}")
        title_label.setObjectName("waitingTitle")
        title_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title_label.setStyleSheet("font-size: 28px; font-weight: 300; color: #FFFFFF;")
        layout.addWidget(title_label)

        # Version
        version_label = QLabel(f"v{__version__}")
        version_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        version_label.setStyleSheet("font-size: 12px; color: #636366;")
        layout.addWidget(version_label)

        layout.addSpacing(16)

        # Status
        self._waiting_status = QLabel("Waiting for iPhone...")
        self._waiting_status.setObjectName("waitingSubtitle")
        self._waiting_status.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._waiting_status.setStyleSheet("font-size: 14px; color: #8E8E93;")
        layout.addWidget(self._waiting_status)

        layout.addSpacing(8)

        # Instructions
        instructions = QLabel(
            "1.  Connect your iPhone via USB cable\n"
            "2.  Tap 'Trust' on your iPhone if prompted\n"
            "3.  Make sure iTunes is installed"
        )
        instructions.setAlignment(Qt.AlignmentFlag.AlignCenter)
        instructions.setStyleSheet("font-size: 12px; color: #636366;")
        layout.addWidget(instructions)

        layout.addSpacing(16)

        # Driver install button (shown when needed)
        self._btn_install_driver = QPushButton("🔧 Install Mirror Driver")
        self._btn_install_driver.setObjectName("primaryButton")
        self._btn_install_driver.setStyleSheet("""
            QPushButton {
                background-color: #B5342B;
                color: #FFFFFF;
                border: none;
                border-radius: 8px;
                padding: 12px 28px;
                font-size: 14px;
                font-weight: 600;
            }
            QPushButton:hover { background-color: #CF3F35; }
            QPushButton:pressed { background-color: #8E2A23; }
        """)
        self._btn_install_driver.clicked.connect(self._install_driver)
        self._btn_install_driver.setVisible(False)
        layout.addWidget(self._btn_install_driver, alignment=Qt.AlignmentFlag.AlignCenter)

        # Driver status label
        self._driver_status_label = QLabel("")
        self._driver_status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self._driver_status_label.setStyleSheet("font-size: 11px; color: #636366;")
        layout.addWidget(self._driver_status_label)

        return page

    def _build_status_bar(self) -> None:
        """Build the status bar."""
        self._statusbar = QStatusBar()
        self.setStatusBar(self._statusbar)

        self._status_label = QLabel("Ready")
        self._statusbar.addWidget(self._status_label, stretch=1)

        self._recording_label = QLabel("")
        self._recording_label.setStyleSheet("color: #B5342B; font-weight: bold;")
        self._statusbar.addPermanentWidget(self._recording_label)

        self._fps_status_label = QLabel("")
        self._statusbar.addPermanentWidget(self._fps_status_label)

    def _setup_shortcuts(self) -> None:
        """Set up keyboard shortcuts."""
        # Escape: exit fullscreen or quit
        pass  # Handled by menu actions

    # ─── Device Detection ───────────────────────────────────────────

    def _check_device(self) -> None:
        """Periodic device check — detect iPhone connection/disconnection."""
        if self._is_connected:
            return

        # Exponential backoff after consecutive capture failures.
        # Prevents the 2-second retry storm seen when the interface
        # is stuck in an unclaimable state after a pipe error.
        if self._consecutive_failures > 0:
            cooldown = min(self._consecutive_failures * 5, 30)
            if time.time() - self._last_capture_failure < cooldown:
                return

        try:
            from imirror.usb.device_manager import DeviceManager
            if self._device_manager is None:
                self._device_manager = DeviceManager()
                self._device_manager.start()

            device = self._device_manager.first_device
            if device:
                self._waiting_status.setText(f"iPhone detected: {device.display_name}")
                self._start_capture(device)
        except Exception as e:
            logger.debug("Device check: %s", e)

    def _start_capture(self, device) -> None:
        """Start capturing from the detected device."""
        try:
            self._is_connected = True
            self._stack.setCurrentIndex(1)  # Switch to mirror view

            # Enable recording controls
            self._btn_screenshot.setEnabled(True)
            self._btn_record.setEnabled(True)
            self._action_screenshot.setEnabled(True)
            self._action_record.setEnabled(True)

            # Start capture in background thread
            udid = device.udid
            backend = config.capture_backend

            thread = threading.Thread(
                target=self._capture_thread,
                args=(udid, backend),
                daemon=True,
                name="CaptureThread",
            )
            thread.start()

            self.status_update.emit(f"Connected to {device.display_name}")

        except Exception as e:
            logger.error("Failed to start capture: %s", e)
            self.error_signal.emit("Connection Error", str(e))
            self._is_connected = False

    def _capture_thread(self, udid: str, backend: CaptureBackendType) -> None:
        """Background capture thread."""
        try:
            if backend in (CaptureBackendType.AUTO, CaptureBackendType.VALERIA):
                self._start_valeria_capture(udid)
            elif backend == CaptureBackendType.SCREENSHOT:
                self._start_screenshot_capture(udid)
        except Exception as e:
            logger.error("Capture thread error: %s", e)
            self.error_signal.emit("Capture Error", str(e))

    def _start_valeria_capture(self, udid: str) -> None:
        """Start Valeria stream capture."""
        try:
            from imirror.capture.stream import ValeriaStreamCapture

            capture = ValeriaStreamCapture()
            self._capture_backend = capture

            def on_frame(frame):
                if frame.pixels is not None:
                    # Wire audio player for volume control on first frame
                    if self._audio_player is None and capture.audio_player:
                        self._audio_player = capture.audio_player
                    self._current_frame = frame.pixels
                    self.frame_ready.emit(frame.pixels)

            capture.on_frame(on_frame)
            capture.on_raw_h264(self._feed_raw_h264_to_recorder)
            capture.on_raw_audio(self._feed_audio_to_recorder)
            capture.on_stream_stopped(self._on_stream_ended)

            if not capture.start(udid):
                raise RuntimeError(capture._init_error or "Valeria stream failed to start")

            self._consecutive_failures = 0  # Reset on successful stream start
            self.status_update.emit("Valeria stream active — receiving from iPhone")

        except Exception as e:
            logger.warning("Valeria capture failed: %s — falling back to screenshot", e)
            if config.capture_backend == CaptureBackendType.AUTO:
                self._start_screenshot_capture(udid)
            else:
                raise

    def _start_screenshot_capture(self, udid: str) -> None:
        """Start screenshot capture (fallback)."""
        try:
            from imirror.capture.screenshot import ScreenshotCapture

            capture = ScreenshotCapture()
            self._capture_backend = capture

            def on_frame(frame):
                if frame.pixels is not None:
                    self._current_frame = frame.pixels
                    self.frame_ready.emit(frame.pixels)

            capture.on_frame(on_frame)
            capture.start(udid)

            self.status_update.emit("Screenshot capture active")

        except Exception as e:
            logger.error("Screenshot capture failed: %s", e)
            raise

    def _on_stream_ended(self) -> None:
        """Called from valeria stream thread when stream stops — emit signal for UI thread."""
        self._is_connected = False
        self._capture_backend = None
        self._consecutive_failures += 1
        self._last_capture_failure = time.time()
        self.disconnected_signal.emit()

    def _on_disconnected(self) -> None:
        """Reset UI after device disconnects or stream ends (runs on UI thread via signal)."""
        logger.info("Device disconnected — resetting UI")
        self._stack.setCurrentIndex(0)  # Back to waiting page
        self._btn_screenshot.setEnabled(False)
        self._btn_record.setEnabled(False)
        self._action_screenshot.setEnabled(False)
        self._action_record.setEnabled(False)
        self._fps_status_label.setText("")
        if self._consecutive_failures >= 3:
            self._waiting_status.setText(
                "Multiple connection failures — try unplugging and replugging your iPhone"
            )
        else:
            self._waiting_status.setText("Disconnected — reconnect your iPhone")
        if self._is_recording:
            self._stop_recording()
        self._audio_player = None
        self.status_update.emit("Disconnected — plug in your iPhone")

    def _feed_raw_h264_to_recorder(self, h264_data: bytes, is_keyframe: bool,
                                    timestamp_ns: int = 0) -> None:
        """Feed raw H.264 data to the recorder (zero re-encode recording)."""
        if not (self._recorder and self._recorder.is_recording):
            return
        # Set video format params from capture backend on first keyframe
        if is_keyframe and self._capture_backend and not getattr(self, '_recording_fmt_set', False):
            fmt = getattr(self._capture_backend, 'video_format', {})
            w, h = fmt.get('width', 0), fmt.get('height', 0)
            extradata = getattr(getattr(self._capture_backend, '_session', None),
                                'get_decoder_extradata', lambda: None)()
            if w and h:
                self._recorder.set_video_format(w, h, extradata)
            self._recording_fmt_set = True
        self._recorder.feed_video(h264_data, is_keyframe, timestamp_ns)

    def _feed_audio_to_recorder(self, pcm_data: bytes) -> None:
        """Feed PCM audio data to the recorder."""
        if self._recorder and self._recorder.is_recording:
            self._recorder.feed_audio(pcm_data)

    # ─── Frame Rendering ────────────────────────────────────────────

    def _on_frame_ready(self, frame: np.ndarray) -> None:
        """Handle a new frame (called on UI thread via signal)."""
        try:
            h, w, ch = frame.shape

            if self._gl_renderer:
                # GPU path: zero-copy texture upload, VSync, proper aspect ratio
                self._gl_renderer.set_frame(frame, w, h)
            elif self._frame_label:
                # CPU fallback: QImage → QPixmap → scaled
                bytes_per_line = ch * w
                image = QImage(frame.data, w, h, bytes_per_line, QImage.Format.Format_RGB888)
                pixmap = QPixmap.fromImage(image)
                scaled = pixmap.scaled(
                    self._frame_label.size(),
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
                self._frame_label.setPixmap(scaled)

        except Exception as e:
            logger.debug("Frame render error: %s", e)

    # ─── Recording ──────────────────────────────────────────────────

    def _toggle_recording(self) -> None:
        """Start or stop recording."""
        if self._is_recording:
            self._stop_recording()
        else:
            self._start_recording()

    def _start_recording(self) -> None:
        """Start recording the mirror stream."""
        try:
            from imirror.capture.recording import ScreenRecorder

            if self._recorder is None:
                self._recorder = ScreenRecorder()

            if self._recorder.start():
                self._is_recording = True
                self._recording_fmt_set = False  # Reset so format is set on next keyframe
                self._btn_record.setText("⏹ Stop")
                self._action_record.setText("⏹ Stop Recording")
                self._recording_label.setText("⏺ REC")
                self.recording_state_changed.emit(True)
                self.status_update.emit(f"Recording to {self._recorder.output_path}")
            else:
                QMessageBox.warning(self, "Recording Error",
                                   "Failed to start recording. Check the log for details.")

        except Exception as e:
            logger.error("Recording error: %s", e)
            QMessageBox.warning(self, "Recording Error", str(e))

    def _stop_recording(self) -> None:
        """Stop recording."""
        if self._recorder:
            path = self._recorder.stop()
            self._is_recording = False
            self._btn_record.setText("⏺ Record")
            self._action_record.setText("⏺ Start Recording")
            self._recording_label.setText("")
            self.recording_state_changed.emit(False)
            if path:
                self.status_update.emit(f"Recording saved: {os.path.basename(path)}")

    def _take_screenshot(self) -> None:
        """Take a screenshot of the current frame."""
        if self._current_frame is None:
            self.status_update.emit("No frame available for screenshot")
            return

        try:
            from imirror.capture.recording import ScreenshotSaver

            path = ScreenshotSaver.save_screenshot(self._current_frame)
            if path:
                self.status_update.emit(f"Screenshot saved: {os.path.basename(path)}")
            else:
                self.status_update.emit("Screenshot failed")

        except Exception as e:
            logger.error("Screenshot error: %s", e)

    def _on_recording_state_changed(self, is_recording: bool) -> None:
        """Update UI when recording state changes."""
        if self._fps_overlay:
            self._fps_overlay.set_recording(is_recording)

    # ─── Driver Management ──────────────────────────────────────────

    def _install_driver(self) -> None:
        """Install the WinUSB mirror driver."""
        reply = QMessageBox.question(
            self, "Install Mirror Driver",
            "This will install the WinUSB mirror driver for iPhone USB streaming.\n\n"
            "• Requires administrator privileges\n"
            "• One-time setup (about 10 seconds)\n"
            "• You may need to replug your iPhone after installation\n\n"
            "Continue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )

        if reply != QMessageBox.StandardButton.Yes:
            return

        try:
            from imirror.usb.driver_installer import full_driver_setup
            result = full_driver_setup()

            if result.success:
                QMessageBox.information(
                    self, "Driver Installed",
                    f"[OK] {result.message}\n\n"
                    "Please unplug and replug your iPhone to activate the new driver."
                )
                self._waiting_status.setText("Driver installed — please replug your iPhone")
                self._btn_install_driver.setVisible(False)
            else:
                QMessageBox.warning(self, "Driver Installation Failed",
                                   f"[FAIL] {result.message}")
        except Exception as e:
            QMessageBox.critical(self, "Error", f"Driver installation error: {e}")

    def _restore_driver(self) -> None:
        """Restore the original Apple driver."""
        reply = QMessageBox.question(
            self, "Restore Original Driver",
            "This will remove the mirror driver and restore Apple's original USB driver.\n\n"
            "You'll need to reinstall the mirror driver to use Valeria streaming again.\n\n"
            "Continue?",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )

        if reply != QMessageBox.StandardButton.Yes:
            return

        try:
            from imirror.usb.driver_installer import uninstall_driver
            result = uninstall_driver()

            if result.success:
                QMessageBox.information(self, "Driver Restored",
                                       f"[OK] {result.message}")
            else:
                QMessageBox.warning(self, "Restore Failed",
                                   f"[FAIL] {result.message}")
        except Exception as e:
            QMessageBox.critical(self, "Error", str(e))

    def _check_driver_status(self) -> None:
        """Check and display driver status."""
        try:
            from imirror.usb.driver_installer import check_driver_status
            status = check_driver_status()

            lines = [
                f"iPhone detected: {'[OK] Yes' if status.iphone_detected else '[FAIL] No'}",
                f"Mirror driver installed: {'[OK] Yes' if status.installed else '[FAIL] No'}",
                f"libusb accessible: {'[OK] Yes' if status.libusb_accessible else '[FAIL] No'}",
                f"Ready to stream: {'[OK] Yes' if status.ready_to_stream else '[FAIL] No'}",
            ]
            if status.device_pid:
                lines.append(f"Device PID: 0x{status.device_pid:04X}")

            QMessageBox.information(self, "Driver Status", "\n".join(lines))

        except Exception as e:
            QMessageBox.warning(self, "Driver Check Failed", str(e))

    def _run_diagnostic(self) -> None:
        """Run USB diagnostic."""
        try:
            from imirror.usb.driver_check import run_diagnostic
            QMessageBox.information(
                self, "USB Diagnostic",
                "Running diagnostic... Check the console/log for detailed output."
            )
            threading.Thread(target=run_diagnostic, daemon=True).start()
        except Exception as e:
            QMessageBox.warning(self, "Diagnostic Failed", str(e))

    # ─── Settings ───────────────────────────────────────────────────

    def _open_settings(self) -> None:
        """Open the settings dialog."""
        dialog = SettingsDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            dialog.apply_settings()
            config.save()
            self.status_update.emit("Settings saved")

    # ─── View Controls ──────────────────────────────────────────────

    def _toggle_fullscreen(self) -> None:
        if self.isFullScreen():
            self.showNormal()
            self._action_fullscreen.setChecked(False)
        else:
            self.showFullScreen()
            self._action_fullscreen.setChecked(True)

    def _toggle_fps_overlay(self) -> None:
        if self._fps_overlay is None:
            self._fps_overlay = FPSOverlay(self._mirror_page)
            self._fps_overlay.show()
            self._action_fps.setChecked(True)
        else:
            self._fps_overlay.close()
            self._fps_overlay = None
            self._action_fps.setChecked(False)

    def _toggle_always_on_top(self) -> None:
        config.always_on_top = not config.always_on_top
        if config.always_on_top:
            self.setWindowFlags(self.windowFlags() | Qt.WindowType.WindowStaysOnTopHint)
        else:
            self.setWindowFlags(self.windowFlags() & ~Qt.WindowType.WindowStaysOnTopHint)
        self.show()  # Required after changing window flags

    def _on_volume_changed(self, value: int) -> None:
        config.audio_volume = value / 100.0
        if self._audio_player:
            self._audio_player.set_volume(config.audio_volume)

    # ─── Status Updates ─────────────────────────────────────────────

    def _update_stats(self) -> None:
        """Periodic stats update."""
        if self._capture_backend and hasattr(self._capture_backend, 'fps'):
            fps = self._capture_backend.fps
            self._fps_status_label.setText(f"{fps:.1f} FPS")

            if self._fps_overlay:
                backend_name = getattr(self._capture_backend, 'name', 'Unknown')
                self._fps_overlay.update_stats(
                    capture_fps=fps,
                    backend=backend_name,
                    frame_count=getattr(self._capture_backend, 'frame_count', 0),
                )

        # Update recording duration
        if self._is_recording and self._recorder:
            duration = self._recorder.duration_seconds
            mins = int(duration // 60)
            secs = int(duration % 60)
            self._recording_label.setText(f"⏺ REC {mins:02d}:{secs:02d}")

    def _on_status_update(self, message: str) -> None:
        self._status_label.setText(message)

    def _on_error(self, title: str, message: str) -> None:
        QMessageBox.warning(self, title, message)

    # ─── Folder Shortcuts ───────────────────────────────────────────

    def _open_recordings_folder(self) -> None:
        os.makedirs(config.recording_output_dir, exist_ok=True)
        os.startfile(config.recording_output_dir) if sys.platform == "win32" else None

    def _open_screenshots_folder(self) -> None:
        os.makedirs(config.screenshot_output_dir, exist_ok=True)
        os.startfile(config.screenshot_output_dir) if sys.platform == "win32" else None

    def _show_about(self) -> None:
        about_box = QMessageBox(self)
        about_box.setWindowTitle(f"About {__app_name__}")
        about_box.setTextFormat(Qt.TextFormat.RichText)
        about_box.setText(
            f"<h2 style='font-weight: 300; color: #FFFFFF;'>{__app_name__}</h2>"
            f"<p style='color: #8E8E93;'>Version {__version__}</p>"
            f"<p style='color: #FFFFFF;'>Free iPhone USB Screen Mirror for Windows</p>"
            f"<p style='color: #8E8E93;'>Full native resolution · Low latency · No watermarks</p>"
            f"<p><a href='https://github.com/unluckybob/imirror4free' "
            f"style='color: #B5342B;'>GitHub Repository</a></p>"
            f"<p style='color: #636366;'>License: GPL-3.0</p>"
        )
        _about_icon_path = self._resource_path(os.path.join("assets", "icon.ico"))
        if os.path.exists(_about_icon_path):
            _about_pixmap = QPixmap(_about_icon_path).scaled(
                64, 64,
                Qt.AspectRatioMode.KeepAspectRatio,
                Qt.TransformationMode.SmoothTransformation,
            )
            about_box.setIconPixmap(_about_pixmap)
        about_box.exec()

    # ─── Lifecycle ──────────────────────────────────────────────────

    def keyPressEvent(self, event) -> None:
        """Handle key presses."""
        key = event.key()
        if key == Qt.Key.Key_Escape:
            if self.isFullScreen():
                self.showNormal()
            else:
                self.close()
        elif key == Qt.Key.Key_F11:
            self._toggle_fullscreen()
        elif key == Qt.Key.Key_F3:
            self._toggle_fps_overlay()
        else:
            super().keyPressEvent(event)

    def resizeEvent(self, event) -> None:
        """Handle window resize — reposition overlay."""
        super().resizeEvent(event)
        if self._fps_overlay:
            self._fps_overlay.resize(self._mirror_page.size())

    def closeEvent(self, event) -> None:
        """Clean shutdown."""
        logger.info("Shutting down...")

        # Stop recording
        if self._is_recording and self._recorder:
            self._recorder.stop()

        # Stop device manager
        if self._device_manager:
            self._device_manager.stop()

        # Stop capture
        if self._capture_backend:
            self._capture_backend.stop()

        # Stop audio
        if self._audio_player:
            self._audio_player.stop()

        # Save settings
        config.save()

        event.accept()


class SettingsDialog(QDialog):
    """Application settings dialog."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setWindowTitle("Settings")
        self.setMinimumSize(400, 500)
        self.setStyleSheet(SETTINGS_DIALOG_STYLE)

        layout = QVBoxLayout(self)
        layout.setSpacing(8)

        # ── Capture ────────────────────────────
        capture_group = QGroupBox("Capture")
        capture_layout = QFormLayout(capture_group)

        self._backend_combo = QComboBox()
        self._backend_combo.addItems(["Auto", "Valeria (USB Stream)", "Screenshot (Fallback)"])
        backend_idx = {"auto": 0, "valeria": 1, "screenshot": 2}
        self._backend_combo.setCurrentIndex(backend_idx.get(config.capture_backend.value, 0))
        capture_layout.addRow("Capture Backend:", self._backend_combo)

        layout.addWidget(capture_group)

        # ── Video ──────────────────────────────
        video_group = QGroupBox("Video Decoder")
        video_layout = QFormLayout(video_group)

        self._decoder_combo = QComboBox()
        self._decoder_combo.addItems(["Auto", "D3D11VA (GPU)", "DXVA2 (GPU)", "Software (CPU)"])
        decoder_idx = {"auto": 0, "d3d11va": 1, "dxva2": 2, "software": 3}
        self._decoder_combo.setCurrentIndex(decoder_idx.get(config.decoder_type.value, 0))
        video_layout.addRow("Decoder:", self._decoder_combo)

        self._low_delay_check = QCheckBox("Low-latency mode")
        self._low_delay_check.setChecked(config.decoder_low_delay)
        video_layout.addRow(self._low_delay_check)

        layout.addWidget(video_group)

        # ── Audio ──────────────────────────────
        audio_group = QGroupBox("Audio")
        audio_layout = QFormLayout(audio_group)

        self._audio_enabled_check = QCheckBox("Enable audio playback")
        self._audio_enabled_check.setChecked(config.audio_enabled)
        audio_layout.addRow(self._audio_enabled_check)

        self._audio_buffer_spin = QSpinBox()
        self._audio_buffer_spin.setRange(20, 500)
        self._audio_buffer_spin.setValue(config.audio_buffer_ms)
        self._audio_buffer_spin.setSuffix(" ms")
        audio_layout.addRow("Buffer size:", self._audio_buffer_spin)

        layout.addWidget(audio_group)

        # ── Recording ──────────────────────────
        recording_group = QGroupBox("Recording")
        recording_layout = QFormLayout(recording_group)

        self._recording_format_combo = QComboBox()
        self._recording_format_combo.addItems(["MP4", "MKV"])
        self._recording_format_combo.setCurrentIndex(
            0 if config.recording_format == RecordingFormat.MP4 else 1
        )
        recording_layout.addRow("Format:", self._recording_format_combo)

        self._screenshot_format_combo = QComboBox()
        self._screenshot_format_combo.addItems(["PNG", "JPEG"])
        self._screenshot_format_combo.setCurrentIndex(
            0 if config.screenshot_format == "png" else 1
        )
        recording_layout.addRow("Screenshot format:", self._screenshot_format_combo)

        layout.addWidget(recording_group)

        # ── GUI ────────────────────────────────
        gui_group = QGroupBox("Window")
        gui_layout = QFormLayout(gui_group)

        self._on_top_check = QCheckBox("Always on top")
        self._on_top_check.setChecked(config.always_on_top)
        gui_layout.addRow(self._on_top_check)

        self._fullscreen_check = QCheckBox("Start in fullscreen")
        self._fullscreen_check.setChecked(config.start_fullscreen)
        gui_layout.addRow(self._fullscreen_check)

        self._fps_overlay_check = QCheckBox("Show FPS overlay on startup")
        self._fps_overlay_check.setChecked(config.show_fps_overlay)
        gui_layout.addRow(self._fps_overlay_check)

        layout.addWidget(gui_group)

        # ── Buttons ────────────────────────────
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()

        btn_cancel = QPushButton("Cancel")
        btn_cancel.clicked.connect(self.reject)
        btn_layout.addWidget(btn_cancel)

        btn_save = QPushButton("Save")
        btn_save.setObjectName("primaryButton")
        btn_save.clicked.connect(self.accept)
        btn_layout.addWidget(btn_save)

        layout.addLayout(btn_layout)

    def apply_settings(self) -> None:
        """Apply the settings from the dialog to config."""
        backend_map = {0: CaptureBackendType.AUTO, 1: CaptureBackendType.VALERIA,
                       2: CaptureBackendType.SCREENSHOT}
        config.capture_backend = backend_map.get(self._backend_combo.currentIndex(),
                                                  CaptureBackendType.AUTO)

        decoder_map = {0: DecoderType.AUTO, 1: DecoderType.HARDWARE_D3D11,
                       2: DecoderType.HARDWARE_DXVA2, 3: DecoderType.SOFTWARE}
        config.decoder_type = decoder_map.get(self._decoder_combo.currentIndex(),
                                               DecoderType.AUTO)

        config.decoder_low_delay = self._low_delay_check.isChecked()
        config.audio_enabled = self._audio_enabled_check.isChecked()
        config.audio_buffer_ms = self._audio_buffer_spin.value()

        config.recording_format = (RecordingFormat.MP4
                                    if self._recording_format_combo.currentIndex() == 0
                                    else RecordingFormat.MKV)
        config.screenshot_format = (
            "png" if self._screenshot_format_combo.currentIndex() == 0 else "jpg"
        )

        config.always_on_top = self._on_top_check.isChecked()
        config.start_fullscreen = self._fullscreen_check.isChecked()
        config.show_fps_overlay = self._fps_overlay_check.isChecked()
