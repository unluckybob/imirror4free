"""
Premium Dark Theme for MIRROR4FREE.

iOS-inspired premium dark theme with subtle gradients and glass effects.
The accent color is derived from the app icon (deep crimson/rose).
"""

# ── Premium Dark Color Palette ───────────────────────────────────────
BG_DEEP = "#000000"
BG_PRIMARY = "#0D0D0D"
BG_SECONDARY = "#1C1C1E"
BG_TERTIARY = "#2C2C2E"
BG_CARD = "#1E1E22"
BG_OVERLAY = "rgba(30, 30, 34, 0.85)"

# Accent - Derived from app icon (deep crimson/rose)
ACCENT_PRIMARY = "#B5342B"
ACCENT_LIGHT = "#E8453A"
ACCENT_DARK = "#8E2620"
ACCENT_GLOW = "rgba(181, 52, 43, 0.3)"

# Text
TEXT_PRIMARY = "#FFFFFF"
TEXT_SECONDARY = "#8E8E93"
TEXT_TERTIARY = "#636366"
TEXT_LINK = "#0A84FF"

# Status Colors
SUCCESS = "#30D158"
WARNING = "#FF9F0A"
ERROR = "#FF453A"
INFO = "#64D2FF"

# Borders & Separators
BORDER_SUBTLE = "rgba(255, 255, 255, 0.08)"
BORDER_ACTIVE = "rgba(181, 52, 43, 0.4)"
SEPARATOR = "rgba(255, 255, 255, 0.06)"

# Fonts
FONT_DISPLAY = '"SF Pro Display", -apple-system, "Segoe UI", sans-serif'
FONT_BODY = '"SF Pro Text", -apple-system, "Segoe UI", sans-serif'
FONT_MONO = '"SF Mono", "Cascadia Code", "Consolas", monospace'

# ── Premium Glass Effect ────────────────────────────────────────────
GLASS_EFFECT = """
    background: rgba(30, 30, 34, 0.7);
    backdrop-filter: blur(20px);
    border: 1px solid rgba(255, 255, 255, 0.08);
    border-radius: 16px;
"""

# ── Main Dark Theme ─────────────────────────────────────────────────
DARK_THEME = f"""
    /* ── Base ───────────────────────────────────────────────────── */
    QMainWindow {{
        background-color: {BG_DEEP};
        background-image: linear-gradient(180deg, {BG_PRIMARY} 0%, {BG_DEEP} 100%);
    }}

    QWidget {{
        background: transparent;
        color: {TEXT_PRIMARY};
        font-family: {FONT_BODY};
        font-size: 13px;
    }}

    /* ── Central Widget ─────────────────────────────────────────── */
    QStackedWidget {{
        background: {BG_DEEP};
    }}

    /* ── Labels ─────────────────────────────────────────────────── */
    QLabel {{
        background: transparent;
        color: {TEXT_PRIMARY};
    }}

    QLabel#titleLabel {{
        font-family: {FONT_DISPLAY};
        font-size: 24px;
        font-weight: 600;
        letter-spacing: -0.5px;
    }}

    QLabel#subtitleLabel {{
        font-size: 13px;
        color: {TEXT_SECONDARY};
    }}

    QLabel#statusLabel {{
        font-size: 12px;
        color: {TEXT_SECONDARY};
        background: {BG_SECONDARY};
        padding: 8px 16px;
        border-radius: 12px;
    }}

    QLabel#fpsLabel {{
        font-family: {FONT_MONO};
        font-size: 13px;
        color: {SUCCESS};
        background: {BG_OVERLAY};
        padding: 6px 12px;
        border-radius: 8px;
        border: 1px solid rgba(48, 209, 88, 0.2);
    }}

    /* ── Buttons ─────────────────────────────────────────────────── */
    QPushButton {{
        background: {BG_TERTIARY};
        color: {TEXT_PRIMARY};
        border: none;
        border-radius: 12px;
        padding: 12px 24px;
        font-family: {FONT_BODY};
        font-size: 14px;
        font-weight: 500;
        transition: all 0.2s ease;
    }}

    QPushButton:hover {{
        background: {BG_CARD};
        transform: translateY(-1px);
    }}

    QPushButton:pressed {{
        background: {BG_SECONDARY};
        transform: translateY(0);
    }}

    QPushButton:disabled {{
        background: {BG_SECONDARY};
        color: {TEXT_TERTIARY};
        opacity: 0.6;
    }}

    /* Primary Button - Accent */
    QPushButton#primaryButton {{
        background: {ACCENT_PRIMARY};
        color: {TEXT_PRIMARY};
        font-weight: 600;
        box-shadow: 0 4px 12px {ACCENT_GLOW};
    }}

    QPushButton#primaryButton:hover {{
        background: {ACCENT_LIGHT};
        box-shadow: 0 6px 16px {ACCENT_GLOW};
    }}

    QPushButton#primaryButton:pressed {{
        background: {ACCENT_DARK};
    }}

    /* Icon Button (circular) */
    QPushButton#iconButton {{
        background: {BG_TERTIARY};
        border-radius: 50%;
        padding: 12px;
        min-width: 44px;
        min-height: 44px;
    }}

    QPushButton#iconButton:hover {{
        background: {BG_CARD};
    }}

    /* ── Status Bar ─────────────────────────────────────────────── */
    QStatusBar {{
        background: {BG_PRIMARY};
        color: {TEXT_SECONDARY};
        font-size: 12px;
        border-top: 1px solid {SEPARATOR};
        padding: 4px 12px;
    }}

    /* ── Menu Bar ───────────────────────────────────────────────── */
    QMenuBar {{
        background: {BG_PRIMARY};
        color: {TEXT_PRIMARY};
        border: none;
        padding: 6px 8px;
        font-size: 13px;
    }}

    QMenuBar::item {{
        padding: 8px 16px;
        border-radius: 8px;
        background: transparent;
    }}

    QMenuBar::item:selected {{
        background: {BG_TERTIARY};
    }}

    /* ── Menus ─────────────────────────────────────────────────── */
    QMenu {{
        background: {BG_OVERLAY};
        backdrop-filter: blur(20px);
        color: {TEXT_PRIMARY};
        border: 1px solid {BORDER_SUBTLE};
        border-radius: 16px;
        padding: 8px;
    }}

    QMenu::item {{
        padding: 10px 32px 10px 16px;
        border-radius: 8px;
    }}

    QMenu::item:selected {{
        background: {BG_TERTIARY};
    }}

    QMenu::separator {{
        height: 1px;
        background: {SEPARATOR};
        margin: 6px 8px;
    }}

    /* ── Tooltips ───────────────────────────────────────────────── */
    QToolTip {{
        background: {BG_CARD};
        color: {TEXT_PRIMARY};
        border: 1px solid {BORDER_SUBTLE};
        border-radius: 10px;
        padding: 8px 14px;
        font-size: 12px;
    }}

    /* ── Group Boxes ────────────────────────────────────────────── */
    QGroupBox {{
        font-family: {FONT_DISPLAY};
        font-weight: 600;
        font-size: 13px;
        color: {TEXT_SECONDARY};
        background: {BG_SECONDARY};
        border: 1px solid {BORDER_SUBTLE};
        border-radius: 16px;
        margin-top: 20px;
        padding: 20px;
    }}

    QGroupBox::title {{
        subcontrol-origin: margin;
        left: 16px;
        padding: 0 12px;
        color: {TEXT_SECONDARY};
        font-size: 12px;
        font-weight: 600;
    }}

    /* ── ComboBox ───────────────────────────────────────────────── */
    QComboBox {{
        background: {BG_TERTIARY};
        color: {TEXT_PRIMARY};
        border: 1px solid {BORDER_SUBTLE};
        border-radius: 10px;
        padding: 10px 14px;
        font-size: 13px;
        min-height: 20px;
    }}

    QComboBox:hover {{
        border-color: {BORDER_ACTIVE};
    }}

    QComboBox::drop-down {{
        border: none;
        width: 32px;
    }}

    QComboBox QAbstractItemView {{
        background: {BG_OVERLAY};
        backdrop-filter: blur(20px);
        color: {TEXT_PRIMARY};
        border: 1px solid {BORDER_SUBTLE};
        border-radius: 12px;
        padding: 6px;
        selection-background-color: {BG_TERTIARY};
    }}

    /* ── SpinBox ───────────────────────────────────────────────── */
    QSpinBox {{
        background: {BG_TERTIARY};
        color: {TEXT_PRIMARY};
        border: 1px solid {BORDER_SUBTLE};
        border-radius: 10px;
        padding: 10px 14px;
        font-size: 13px;
    }}

    QSpinBox:hover {{
        border-color: {BORDER_ACTIVE};
    }}

    /* ── CheckBox ───────────────────────────────────────────────── */
    QCheckBox {{
        color: {TEXT_PRIMARY};
        spacing: 12px;
        font-size: 14px;
    }}

    QCheckBox::indicator {{
        width: 22px;
        height: 22px;
        border-radius: 6px;
        border: 2px solid {BG_TERTIARY};
        background: {BG_TERTIARY};
    }}

    QCheckBox::indicator:hover {{
        border-color: {TEXT_TERTIARY};
    }}

    QCheckBox::indicator:checked {{
        background: {ACCENT_PRIMARY};
        border-color: {ACCENT_PRIMARY};
    }}

    /* ── Sliders ───────────────────────────────────────────────── */
    QSlider::groove:horizontal {{
        height: 6px;
        background: {BG_TERTIARY};
        border-radius: 3px;
    }}

    QSlider::handle:horizontal {{
        background: {TEXT_PRIMARY};
        width: 20px;
        height: 20px;
        margin: -7px 0;
        border-radius: 10px;
        box-shadow: 0 2px 8px rgba(0, 0, 0, 0.3);
    }}

    QSlider::sub-page:horizontal {{
        background: {ACCENT_PRIMARY};
        border-radius: 3px;
    }}

    /* ── Scroll Bars ─────────────────────────────────────────────── */
    QScrollBar:vertical {{
        background: transparent;
        width: 10px;
        margin: 0;
    }}

    QScrollBar::handle:vertical {{
        background: {BG_TERTIARY};
        border-radius: 5px;
        min-height: 30px;
    }}

    QScrollBar::handle:vertical:hover {{
        background: {BG_CARD};
    }}

    QScrollBar:horizontal {{
        background: transparent;
        height: 10px;
        margin: 0;
    }}

    /* ── Dialog ─────────────────────────────────────────────────── */
    QDialog {{
        background: {BG_PRIMARY};
    }}

    QMessageBox {{
        background: {BG_SECONDARY};
    }}

    QMessageBox QLabel {{
        color: {TEXT_PRIMARY};
        font-size: 14px;
    }}
"""

# ── Waiting / Connection Screen ────────────────────────────────────
WAITING_SCREEN_STYLE = f"""
    QWidget#waitingScreen {{
        background: transparent;
    }}

    QLabel#waitingIcon {{
        background: transparent;
    }}

    QLabel#waitingTitle {{
        font-family: {FONT_DISPLAY};
        font-size: 32px;
        font-weight: 300;
        color: {TEXT_PRIMARY};
        letter-spacing: -0.5px;
        background: transparent;
    }}

    QLabel#waitingSubtitle {{
        font-size: 14px;
        color: {TEXT_SECONDARY};
        background: transparent;
    }}

    QLabel#waitingDot {{
        font-size: 36px;
        color: {ACCENT_PRIMARY};
        background: transparent;
    }}
"""

# ── Toolbar ────────────────────────────────────────────────────────
TOOLBAR_STYLE = f"""
    QToolBar {{
        background: {BG_PRIMARY};
        border-bottom: 1px solid {SEPARATOR};
        padding: 6px 12px;
        spacing: 8px;
    }}

    QToolButton {{
        background: transparent;
        border: none;
        border-radius: 10px;
        padding: 10px 16px;
        color: {TEXT_PRIMARY};
        font-size: 13px;
        font-weight: 500;
    }}

    QToolButton:hover {{
        background: {BG_TERTIARY};
    }}

    QToolButton:pressed {{
        background: {BG_SECONDARY};
    }}

    QToolButton:disabled {{
        color: {TEXT_TERTIARY};
    }}
"""

# ── Settings Dialog ────────────────────────────────────────────────
SETTINGS_DIALOG_STYLE = f"""
    QDialog {{
        background: {BG_PRIMARY};
    }}

    QGroupBox {{
        font-family: {FONT_DISPLAY};
        font-weight: 600;
        font-size: 13px;
        color: {TEXT_SECONDARY};
        background: {BG_SECONDARY};
        border: 1px solid {BORDER_SUBTLE};
        border-radius: 16px;
        margin-top: 20px;
        padding: 20px;
    }}

    QGroupBox::title {{
        subcontrol-origin: margin;
        left: 16px;
        padding: 0 12px;
        font-size: 12px;
    }}

    QLabel {{
        color: {TEXT_SECONDARY};
        font-size: 13px;
        background: transparent;
    }}

    QComboBox {{
        background: {BG_TERTIARY};
        color: {TEXT_PRIMARY};
        border: 1px solid {BORDER_SUBTLE};
        border-radius: 10px;
        padding: 10px 14px;
    }}

    QSpinBox {{
        background: {BG_TERTIARY};
        color: {TEXT_PRIMARY};
        border: 1px solid {BORDER_SUBTLE};
        border-radius: 10px;
        padding: 10px 14px;
    }}

    QCheckBox {{
        color: {TEXT_PRIMARY};
        spacing: 12px;
    }}

    QCheckBox::indicator {{
        width: 22px;
        height: 22px;
        border-radius: 6px;
        border: 2px solid {BG_TERTIARY};
        background: {BG_TERTIARY};
    }}

    QCheckBox::indicator:checked {{
        background: {ACCENT_PRIMARY};
        border-color: {ACCENT_PRIMARY};
    }}

    QPushButton {{
        background: {BG_TERTIARY};
        color: {TEXT_PRIMARY};
        border: none;
        border-radius: 12px;
        padding: 12px 24px;
        font-size: 14px;
    }}

    QPushButton:hover {{
        background: {BG_CARD};
    }}

    QPushButton#primaryButton {{
        background: {ACCENT_PRIMARY};
        color: {TEXT_PRIMARY};
        font-weight: 600;
    }}

    QPushButton#primaryButton:hover {{
        background: {ACCENT_LIGHT};
    }}
"""
