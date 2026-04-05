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

QPushButton#primaryButton {
    background-color: #0078D4;
    color: #FFFFFF;
    border: none;
}

QPushButton#primaryButton:hover {
    background-color: #1A8AE8;
}

QPushButton#primaryButton:pressed {
    background-color: #006ABE;
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

QMenu::item:selected {
    background-color: #2D2D2D;
    border-radius: 4px;
}

QToolTip {
    background-color: #2D2D2D;
    color: #E0E0E0;
    border: 1px solid #404040;
    border-radius: 4px;
    padding: 4px;
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
    font-size: 22px;
    font-weight: 600;
    color: #FFFFFF;
}

QLabel#waitingSubtitle {
    font-size: 13px;
    color: #888888;
    line-height: 1.6;
}

QLabel#waitingDot {
    font-size: 32px;
    color: #0078D4;
}
"""
