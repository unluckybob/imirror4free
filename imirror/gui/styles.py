"""
Apple-Premium Dark Theme Styles.

Clean, minimal dark theme with crimson accent — inspired by Apple's
design language. Applied to the entire application via Qt StyleSheet.
"""

# ── Color Palette ──────────────────────────────────────────────────
BG_PRIMARY = "#000000"
BG_SECONDARY = "#1C1C1E"
BG_TERTIARY = "#2C2C2E"
BG_QUATERNARY = "#3A3A3C"

ACCENT = "#B5342B"
ACCENT_HOVER = "#CF3F35"
ACCENT_PRESSED = "#8E2A23"

TEXT_PRIMARY = "#FFFFFF"
TEXT_SECONDARY = "#8E8E93"
TEXT_TERTIARY = "#636366"

SEPARATOR = "#38383A"

SUCCESS = "#30D158"
WARNING = "#FF9F0A"
DANGER = "#FF453A"

FONT_STACK = '"SF Pro Display", "Segoe UI", -apple-system, sans-serif'
FONT_MONO = '"SF Mono", "Cascadia Code", "Consolas", monospace'

# ── Main Application Theme ─────────────────────────────────────────
DARK_THEME = f"""
/* ── Base ─────────────────────────────────────────── */
QMainWindow {{
    background-color: {BG_PRIMARY};
}}

QWidget {{
    background-color: {BG_PRIMARY};
    color: {TEXT_PRIMARY};
    font-family: {FONT_STACK};
    font-size: 13px;
}}

/* ── Labels ───────────────────────────────────────── */
QLabel {{
    color: {TEXT_PRIMARY};
    background: transparent;
}}

QLabel#titleLabel {{
    font-size: 20px;
    font-weight: 300;
    color: {TEXT_PRIMARY};
}}

QLabel#subtitleLabel {{
    font-size: 12px;
    color: {TEXT_SECONDARY};
}}

QLabel#statusLabel {{
    font-size: 11px;
    color: {TEXT_SECONDARY};
    padding: 6px 12px;
    background-color: {BG_SECONDARY};
    border-radius: 8px;
}}

QLabel#fpsLabel {{
    font-size: 12px;
    font-family: {FONT_MONO};
    color: {SUCCESS};
    background-color: rgba(0, 0, 0, 200);
    padding: 6px 10px;
    border-radius: 8px;
}}

/* ── Buttons ──────────────────────────────────────── */
QPushButton {{
    background-color: {BG_TERTIARY};
    color: {TEXT_PRIMARY};
    border: none;
    border-radius: 8px;
    padding: 10px 20px;
    font-size: 13px;
    font-weight: 400;
    min-width: 80px;
}}

QPushButton:hover {{
    background-color: {BG_QUATERNARY};
}}

QPushButton:pressed {{
    background-color: {BG_SECONDARY};
}}

QPushButton:disabled {{
    background-color: {BG_SECONDARY};
    color: {TEXT_TERTIARY};
}}

QPushButton#primaryButton {{
    background-color: {ACCENT};
    color: {TEXT_PRIMARY};
    border: none;
    font-weight: 600;
}}

QPushButton#primaryButton:hover {{
    background-color: {ACCENT_HOVER};
}}

QPushButton#primaryButton:pressed {{
    background-color: {ACCENT_PRESSED};
}}

QPushButton#dangerButton {{
    background-color: {DANGER};
    color: {TEXT_PRIMARY};
    border: none;
    font-weight: 600;
}}

QPushButton#dangerButton:hover {{
    background-color: #FF6961;
}}

QPushButton#dangerButton:pressed {{
    background-color: #CC362E;
}}

/* ── Status Bar ───────────────────────────────────── */
QStatusBar {{
    background-color: {BG_PRIMARY};
    color: {TEXT_SECONDARY};
    font-size: 11px;
    border-top: 1px solid {SEPARATOR};
    padding: 2px 8px;
}}

QStatusBar QLabel {{
    color: {TEXT_SECONDARY};
    padding: 2px 4px;
}}

/* ── Menu Bar ─────────────────────────────────────── */
QMenuBar {{
    background-color: {BG_PRIMARY};
    color: {TEXT_PRIMARY};
    border: none;
    padding: 4px 2px;
    font-size: 13px;
}}

QMenuBar::item {{
    padding: 6px 12px;
    border-radius: 6px;
    background: transparent;
}}

QMenuBar::item:selected {{
    background-color: {BG_TERTIARY};
}}

QMenuBar::item:pressed {{
    background-color: {BG_QUATERNARY};
}}

/* ── Menus ────────────────────────────────────────── */
QMenu {{
    background-color: {BG_SECONDARY};
    color: {TEXT_PRIMARY};
    border: 1px solid {SEPARATOR};
    border-radius: 12px;
    padding: 6px;
}}

QMenu::item {{
    padding: 8px 28px 8px 16px;
    border-radius: 6px;
}}

QMenu::item:selected {{
    background-color: {BG_TERTIARY};
}}

QMenu::item:disabled {{
    color: {TEXT_TERTIARY};
}}

QMenu::separator {{
    height: 1px;
    background-color: {SEPARATOR};
    margin: 6px 12px;
}}

QMenu::indicator {{
    width: 16px;
    height: 16px;
    margin-left: 8px;
}}

/* ── Tooltips ─────────────────────────────────────── */
QToolTip {{
    background-color: {BG_TERTIARY};
    color: {TEXT_PRIMARY};
    border: 1px solid {SEPARATOR};
    border-radius: 8px;
    padding: 6px 10px;
    font-size: 12px;
}}

/* ── Group Boxes (Apple Cards) ────────────────────── */
QGroupBox {{
    font-weight: 600;
    font-size: 13px;
    color: {TEXT_SECONDARY};
    background-color: {BG_SECONDARY};
    border: none;
    border-radius: 12px;
    margin-top: 16px;
    padding: 24px 16px 16px 16px;
}}

QGroupBox::title {{
    subcontrol-origin: margin;
    left: 16px;
    padding: 0 8px;
    color: {TEXT_SECONDARY};
    font-size: 12px;
    font-weight: 600;
}}

/* ── ComboBox ─────────────────────────────────────── */
QComboBox {{
    background-color: {BG_TERTIARY};
    color: {TEXT_PRIMARY};
    border: none;
    border-radius: 8px;
    padding: 8px 12px;
    min-height: 24px;
    font-size: 13px;
}}

QComboBox:hover {{
    background-color: {BG_QUATERNARY};
}}

QComboBox::drop-down {{
    border: none;
    width: 28px;
}}

QComboBox::down-arrow {{
    image: none;
    border: none;
}}

QComboBox QAbstractItemView {{
    background-color: {BG_SECONDARY};
    color: {TEXT_PRIMARY};
    border: 1px solid {SEPARATOR};
    border-radius: 8px;
    padding: 4px;
    selection-background-color: {BG_TERTIARY};
    selection-color: {TEXT_PRIMARY};
    outline: none;
}}

/* ── SpinBox ──────────────────────────────────────── */
QSpinBox {{
    background-color: {BG_TERTIARY};
    color: {TEXT_PRIMARY};
    border: none;
    border-radius: 8px;
    padding: 8px 12px;
    font-size: 13px;
}}

QSpinBox:hover {{
    background-color: {BG_QUATERNARY};
}}

QSpinBox::up-button, QSpinBox::down-button {{
    background-color: transparent;
    border: none;
    width: 20px;
}}

/* ── CheckBox ─────────────────────────────────────── */
QCheckBox {{
    color: {TEXT_PRIMARY};
    spacing: 10px;
    font-size: 13px;
}}

QCheckBox::indicator {{
    width: 18px;
    height: 18px;
    border-radius: 4px;
    border: 1px solid {BG_QUATERNARY};
    background-color: {BG_TERTIARY};
}}

QCheckBox::indicator:hover {{
    border-color: {TEXT_TERTIARY};
}}

QCheckBox::indicator:checked {{
    background-color: {ACCENT};
    border-color: {ACCENT};
}}

/* ── Sliders ──────────────────────────────────────── */
QSlider::groove:horizontal {{
    height: 4px;
    background: {BG_TERTIARY};
    border-radius: 2px;
}}

QSlider::handle:horizontal {{
    background: {TEXT_PRIMARY};
    width: 16px;
    height: 16px;
    margin: -6px 0;
    border-radius: 8px;
}}

QSlider::handle:horizontal:hover {{
    background: {TEXT_PRIMARY};
    width: 18px;
    height: 18px;
    margin: -7px 0;
    border-radius: 9px;
}}

QSlider::sub-page:horizontal {{
    background: {ACCENT};
    border-radius: 2px;
}}

/* ── Scroll Bars ──────────────────────────────────── */
QScrollBar:vertical {{
    background: transparent;
    width: 8px;
    margin: 0;
}}

QScrollBar::handle:vertical {{
    background: {BG_QUATERNARY};
    border-radius: 4px;
    min-height: 24px;
}}

QScrollBar::handle:vertical:hover {{
    background: {TEXT_TERTIARY};
}}

QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0px;
}}

QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{
    background: transparent;
}}

QScrollBar:horizontal {{
    background: transparent;
    height: 8px;
    margin: 0;
}}

QScrollBar::handle:horizontal {{
    background: {BG_QUATERNARY};
    border-radius: 4px;
    min-width: 24px;
}}

QScrollBar::handle:horizontal:hover {{
    background: {TEXT_TERTIARY};
}}

QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {{
    width: 0px;
}}

QScrollBar::add-page:horizontal, QScrollBar::sub-page:horizontal {{
    background: transparent;
}}

/* ── Dialog ───────────────────────────────────────── */
QDialog {{
    background-color: {BG_PRIMARY};
}}

QMessageBox {{
    background-color: {BG_SECONDARY};
}}

QMessageBox QLabel {{
    color: {TEXT_PRIMARY};
    font-size: 13px;
}}

QMessageBox QPushButton {{
    min-width: 72px;
    padding: 8px 20px;
}}

/* ── Form Labels ──────────────────────────────────── */
QFormLayout QLabel {{
    color: {TEXT_SECONDARY};
    font-size: 12px;
}}

/* ── Tab Widget ───────────────────────────────────── */
QTabWidget::pane {{
    border: none;
    background-color: {BG_PRIMARY};
}}

QTabBar::tab {{
    background-color: transparent;
    color: {TEXT_SECONDARY};
    padding: 8px 16px;
    border: none;
    border-bottom: 2px solid transparent;
    font-size: 13px;
}}

QTabBar::tab:selected {{
    color: {TEXT_PRIMARY};
    border-bottom: 2px solid {ACCENT};
}}

QTabBar::tab:hover {{
    color: {TEXT_PRIMARY};
}}
"""

# ── Waiting / Connection Screen ────────────────────────────────────
WAITING_SCREEN_STYLE = f"""
QWidget#waitingScreen {{
    background-color: {BG_PRIMARY};
}}

QLabel#waitingIcon {{
    background: transparent;
}}

QLabel#waitingTitle {{
    font-size: 28px;
    font-weight: 300;
    color: {TEXT_PRIMARY};
    background: transparent;
}}

QLabel#waitingSubtitle {{
    font-size: 14px;
    color: {TEXT_SECONDARY};
    background: transparent;
}}

QLabel#waitingDot {{
    font-size: 32px;
    color: {ACCENT};
    background: transparent;
}}
"""

# ── Toolbar ────────────────────────────────────────────────────────
TOOLBAR_STYLE = f"""
QToolBar {{
    background-color: {BG_PRIMARY};
    border-bottom: 1px solid {SEPARATOR};
    padding: 4px 8px;
    spacing: 4px;
}}

QToolButton {{
    background-color: transparent;
    border: none;
    border-radius: 6px;
    padding: 8px 14px;
    color: {TEXT_PRIMARY};
    font-size: 12px;
}}

QToolButton:hover {{
    background-color: {BG_TERTIARY};
}}

QToolButton:pressed {{
    background-color: {BG_SECONDARY};
}}

QToolButton:disabled {{
    color: {TEXT_TERTIARY};
}}
"""

# ── Settings Dialog ────────────────────────────────────────────────
SETTINGS_DIALOG_STYLE = f"""
QDialog {{
    background-color: {BG_PRIMARY};
}}

QGroupBox {{
    font-weight: 600;
    font-size: 13px;
    color: {TEXT_SECONDARY};
    background-color: {BG_SECONDARY};
    border: none;
    border-radius: 12px;
    margin-top: 16px;
    padding: 24px 16px 16px 16px;
}}

QGroupBox::title {{
    subcontrol-origin: margin;
    left: 16px;
    padding: 0 8px;
    color: {TEXT_SECONDARY};
    font-size: 12px;
    font-weight: 600;
}}

QLabel {{
    color: {TEXT_SECONDARY};
    font-size: 13px;
    background: transparent;
}}

QComboBox {{
    background-color: {BG_TERTIARY};
    color: {TEXT_PRIMARY};
    border: none;
    border-radius: 8px;
    padding: 8px 12px;
    min-height: 24px;
}}

QComboBox:hover {{
    background-color: {BG_QUATERNARY};
}}

QComboBox::drop-down {{
    border: none;
    width: 28px;
}}

QComboBox QAbstractItemView {{
    background-color: {BG_SECONDARY};
    color: {TEXT_PRIMARY};
    border: 1px solid {SEPARATOR};
    border-radius: 8px;
    padding: 4px;
    selection-background-color: {BG_TERTIARY};
    outline: none;
}}

QSpinBox {{
    background-color: {BG_TERTIARY};
    color: {TEXT_PRIMARY};
    border: none;
    border-radius: 8px;
    padding: 8px 12px;
}}

QSpinBox:hover {{
    background-color: {BG_QUATERNARY};
}}

QCheckBox {{
    color: {TEXT_PRIMARY};
    spacing: 10px;
}}

QCheckBox::indicator {{
    width: 18px;
    height: 18px;
    border-radius: 4px;
    border: 1px solid {BG_QUATERNARY};
    background-color: {BG_TERTIARY};
}}

QCheckBox::indicator:checked {{
    background-color: {ACCENT};
    border-color: {ACCENT};
}}

QPushButton {{
    background-color: {BG_TERTIARY};
    color: {TEXT_PRIMARY};
    border: none;
    border-radius: 8px;
    padding: 10px 24px;
    font-size: 13px;
    min-width: 80px;
}}

QPushButton:hover {{
    background-color: {BG_QUATERNARY};
}}

QPushButton#primaryButton {{
    background-color: {ACCENT};
    color: {TEXT_PRIMARY};
    border: none;
    font-weight: 600;
}}

QPushButton#primaryButton:hover {{
    background-color: {ACCENT_HOVER};
}}

QPushButton#primaryButton:pressed {{
    background-color: {ACCENT_PRESSED};
}}
"""
