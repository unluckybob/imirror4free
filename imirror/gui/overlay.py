"""
FPS and Status Overlay.

Transparent overlay that shows real-time performance stats
on top of the rendered frame. Toggle with F3.
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
        self._fps_label.setStyleSheet("""
            font-size: 12px;
            font-family: "Cascadia Code", "Consolas", monospace;
            color: #00FF88;
            background-color: rgba(0, 0, 0, 180);
            padding: 6px 10px;
            border-radius: 6px;
        """)
        layout.addWidget(self._fps_label)

        self._info_label = QLabel("")
        self._info_label.setObjectName("infoLabel")
        self._info_label.setStyleSheet("""
            font-size: 10px;
            font-family: "Cascadia Code", "Consolas", monospace;
            color: #AAAAAA;
            background-color: rgba(0, 0, 0, 150);
            padding: 4px 8px;
            border-radius: 4px;
        """)
        layout.addWidget(self._info_label)

        # State
        self._capture_fps: float = 0.0
        self._render_fps: float = 0.0
        self._resolution: str = "—"
        self._backend: str = "—"
        self._frame_count: int = 0

        # Update timer
        self._timer = QTimer(self)
        self._timer.timeout.connect(self._update_display)
        self._timer.start(250)  # 4x per second

    def update_stats(
        self,
        capture_fps: float = 0.0,
        resolution: str = "—",
        backend: str = "—",
        frame_count: int = 0,
    ) -> None:
        """Update the stats displayed in the overlay."""
        self._capture_fps = capture_fps
        self._resolution = resolution
        self._backend = backend
        self._frame_count = frame_count

    def _update_display(self) -> None:
        """Refresh the overlay text."""
        fps = self._capture_fps

        # Color code FPS
        if fps >= 25:
            color = "#00FF88"  # Green — great
        elif fps >= 10:
            color = "#FFAA00"  # Orange — okay
        else:
            color = "#FF4444"  # Red — low

        self._fps_label.setStyleSheet(f"""
            font-size: 12px;
            font-family: "Cascadia Code", "Consolas", monospace;
            color: {color};
            background-color: rgba(0, 0, 0, 180);
            padding: 6px 10px;
            border-radius: 6px;
        """)
        self._fps_label.setText(f"{fps:.1f} FPS")

        info_lines = [
            f"Res: {self._resolution}",
            f"Backend: {self._backend}",
            f"Frames: {self._frame_count}",
        ]
        self._info_label.setText("\n".join(info_lines))
