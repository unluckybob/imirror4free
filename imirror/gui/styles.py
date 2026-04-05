"""
Windows 11 Dark Theme Styles.

Clean, modern dark theme that matches Windows 11 aesthetics.
Applied to the entire application via Qt StyleSheet.
"""

DARK_THEME = """
QMainWindow {
    background-color: #0D0D0D;
}

QWidget {
    background-color: #0D0D0D;
    color: #E0E0E0;
    font-family: "Segoe UI", sans-serif;
    font-size: 13px;
}

QLabel {
    color: #E0E0E0;
    background: transparent;
}

QLabel#titleLabel {
    font-size: 18px;
    font-weight: bold;
    color: #FFFFFF;
}

QLabel#subtitleLabel {
    font-size: 12px;
    color: #888888;
}

QLabel#statusLabel {
    font-size: 11px;
    color: #AAAAAA;
    padding: 4px 8px;
    background-color: #1A1A1A;
    border-radius: 4px;
}

QLabel#fpsLabel {
    font-size: 11px;
    font-family: "Cascadia Code", "Consolas", monospace;
    color: #00FF88;
    background-color: rgba(0, 0, 0, 180);
    padding: 4px 8px;
    border-radius: 4px;
}

QPushButton {
    background-color: #2D2D2D;
    color: #E0E0E0;
    border: 1px solid #404040;
    border-radius: 6px;
    padding: 8px 16px;
    font-size: 13px;
    min-width: 80px;
}

QPushButton:hover {
    background-color: #383838;
    border-color: #505050;
}

QPushButton:pressed {
    background-color: #1A1A1A;
}

QPushButton:disabled {
    background-color: #1A1A1A;
    color: #555555;
    border-color: #2D2D2D;
}

QPushButton#primaryButton {
    background-color: #0078D4;
    color: #FFFFFF;
    border: none;
    font-weight: 600;
}

QPushButton#primaryButton:hover {
    background-color: #1A8AE8;
}

QPushButton#primaryButton:pressed {
    background-color: #006ABE;
}

QPushButton#dangerButton {
    background-color: #C42B1C;
    color: #FFFFFF;
    border: none;
}

QPushButton#dangerButton:hover {
    background-color: #D83B2B;
}

QStatusBar {
    background-color: #1A1A1A;
    color: #888888;
    font-size: 11px;
    border-top: 1px solid #2D2D2D;
}

QMenuBar {
    background-color: #1A1A1A;
    color: #E0E0E0;
    border-bottom: 1px solid #2D2D2D;
    padding: 2px;
}

QMenuBar::item {
    padding: 4px 10px;
    border-radius: 4px;
}

QMenuBar::item:selected {
    background-color: #2D2D2D;
}

QMenu {
    background-color: #1A1A1A;
    color: #E0E0E0;
    border: 1px solid #2D2D2D;
    border-radius: 8px;
    padding: 4px;
}

QMenu::item {
    padding: 6px 24px 6px 16px;
    border-radius: 4px;
}

QMenu::item:selected {
    background-color: #2D2D2D;
}

QMenu::separator {
    height: 1px;
    background-color: #2D2D2D;
    margin: 4px 8px;
}

QToolTip {
    background-color: #2D2D2D;
    color: #E0E0E0;
    border: 1px solid #404040;
    border-radius: 4px;
    padding: 4px;
}

QGroupBox {
    font-weight: 600;
    border: 1px solid #2D2D2D;
    border-radius: 8px;
    margin-top: 12px;
    padding-top: 16px;
}

QGroupBox::title {
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 6px;
    color: #AAAAAA;
}

QComboBox {
    background-color: #2D2D2D;
    color: #E0E0E0;
    border: 1px solid #404040;
    border-radius: 4px;
    padding: 4px 8px;
    min-height: 24px;
}

QComboBox:hover {
    border-color: #505050;
}

QComboBox::drop-down {
    border: none;
    width: 24px;
}

QComboBox QAbstractItemView {
    background-color: #1A1A1A;
    color: #E0E0E0;
    border: 1px solid #2D2D2D;
    selection-background-color: #2D2D2D;
}

QSpinBox {
    background-color: #2D2D2D;
    color: #E0E0E0;
    border: 1px solid #404040;
    border-radius: 4px;
    padding: 4px 8px;
}

QCheckBox {
    color: #E0E0E0;
    spacing: 8px;
}

QCheckBox::indicator {
    width: 16px;
    height: 16px;
    border-radius: 3px;
    border: 1px solid #555;
    background-color: #2D2D2D;
}

QCheckBox::indicator:checked {
    background-color: #0078D4;
    border-color: #0078D4;
}

QSlider::groove:horizontal {
    height: 4px;
    background: #2D2D2D;
    border-radius: 2px;
}

QSlider::handle:horizontal {
    background: #0078D4;
    width: 14px;
    height: 14px;
    margin: -5px 0;
    border-radius: 7px;
}

QSlider::sub-page:horizontal {
    background: #0078D4;
    border-radius: 2px;
}

QDialog {
    background-color: #0D0D0D;
}

QMessageBox {
    background-color: #0D0D0D;
}

QMessageBox QLabel {
    color: #E0E0E0;
}
"""

# Waiting/connection screen styles
WAITING_SCREEN_STYLE = """
QWidget#waitingScreen {
    background-color: #0D0D0D;
}

QLabel#waitingIcon {
    font-size: 64px;
    color: #404040;
}

QLabel#waitingTitle {
    font-size: 24px;
    font-weight: 600;
    color: #FFFFFF;
}

QLabel#waitingSubtitle {
    font-size: 14px;
    color: #888888;
    line-height: 1.6;
}

QLabel#waitingDot {
    font-size: 32px;
    color: #0078D4;
}
"""
