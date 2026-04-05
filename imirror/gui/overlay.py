"""
FPS and Status Overlay.

Transparent overlay that shows real-time performance stats
on top of the rendered frame. Toggle with F3.

Shows:
  - FPS (color-coded)
  - Resolution
  - Backend type
  - Decoder info (HW/SW)
  - Frame count
  - Bandwidth
  - Recording indicator
"""

import time
from PyQt6.QtWidgets import QLabel, QWidget, QVBoxLayout
from PyQt6.QtCore import Qt, QTimer


class FPSOverlay(QWidget):
    """Semi-transparent FPS overlay displayed on top of the renderer."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setObjectName("fpsOverlay")

        # Make transparent background
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)
        self.setStyleSheet("background: transparent;")

        layout = QVBoxLayout(self)
        layout.setContentsMargins(12, 12, 12, 12)
        layout.setAlignment(Qt.AlignmentFlag.AlignTop | Qt.AlignmentFlag.AlignLeft)

        self._fps_label = QLabel("-- FPS")
        self._fps_label.setObjectName("fpsLabel")
        self._fps_label.setStyleSheet(self._fps_style("#00FF88"))
        layout.addWidget(self._fps_label)

        self._info_label = QLabel("")
        self._info_label.setObjectName("infoLabel")
        self._info_label.setStyleSheet("""
            font-size: 10px;
            font-family: "Cascadia Code", "Consolas", monospace;
            color: #AAAAAA;
            background-color: rgba(0, 0, 0, 150);
            padding: 6px 10px;
            border-radius: 4px;
        """)
        layout.addWidget(self._info_label)

        self._recording_label = QLabel("")
        self._recording_label.setStyleSheet("""
            font-size: 11px;
            font-family: "Cascadia Code", "Consolas", monospace;
            color: #FF4444;
            background-color: rgba(60, 0, 0, 200);
            padding: 4px 10px;
            border-radius: 4px;
            font-weight: bold;
        """)
        self._recording_label.setVisible(False)
        layout.addWidget(self._recording_label)

        # State
        self._capture_fps: float = 0.0
        self._resolution: str = "—"
        self._backend: str = "—"
        self._decoder: str = "—"
        self._frame_count: int = 0
        self._bandwidth_mbps: float = 0.0
        self._decode_time_ms: float = 0.0
        self._is_recording: bool = False

        # Update timer
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._update_display)
        self._timer.start(250)  # 4x per second

    @staticmethod
    def _fps_style(color: str) -> str:
        return f"""
            font-size: 13px;
            font-family: "Cascadia Code", "Consolas", monospace;
            color: {color};
            background-color: rgba(0, 0, 0, 200);
            padding: 6px 10px;
            border-radius: 6px;
            font-weight: bold;
        """

    def update_stats(
        self,
        capture_fps: float = 0.0,
        resolution: str = "—",
        backend: str = "—",
        decoder: str = "—",
        frame_count: int = 0,
        bandwidth_mbps: float = 0.0,
        decode_time_ms: float = 0.0,
    ) -> None:
        """Update the stats displayed in the overlay."""
        self._capture_fps = capture_fps
        self._resolution = resolution
        self._backend = backend
        self._decoder = decoder
        self._frame_count = frame_count
        self._bandwidth_mbps = bandwidth_mbps
        self._decode_time_ms = decode_time_ms

    def set_recording(self, is_recording: bool) -> None:
        """Show/hide the recording indicator."""
        self._is_recording = is_recording
        self._recording_label.setVisible(is_recording)
        if is_recording:
            self._recording_label.setText("⏺ RECORDING")

    def _update_display(self) -> None:
        """Refresh the overlay text."""
        fps = self._capture_fps

        # Color code FPS
        if fps >= 25:
            color = "#00FF88"   # Green — great
        elif fps >= 10:
            color = "#FFAA00"   # Orange — okay
        else:
            color = "#FF4444"   # Red — low

        self._fps_label.setStyleSheet(self._fps_style(color))
        self._fps_label.setText(f"{fps:.1f} FPS")

        info_lines = [
            f"Res: {self._resolution}",
            f"Backend: {self._backend}",
            f"Decoder: {self._decoder}",
            f"Frames: {self._frame_count:,}",
        ]
        if self._bandwidth_mbps > 0:
            info_lines.append(f"Bandwidth: {self._bandwidth_mbps:.1f} Mbps")
        if self._decode_time_ms > 0:
            info_lines.append(f"Decode: {self._decode_time_ms:.1f} ms")

        self._info_label.setText("\n".join(info_lines))
