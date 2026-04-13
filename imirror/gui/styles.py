"""
Premium Dark Theme for MIRROR4FREE.

Based on Image 1 (icon) and Image 2 (GUI reference):
- Dark black background with crimson/maroon accents
- Minimalist sidebar-style UI
- Glass effects with subtle gradients
"""

# ── Color Palette (from Image 1 icon analysis) ───────────────────────
# Primary dark - near black
BG_DEEP = "#000000"
BG_PRIMARY = "#0A0A0A"
BG_SECONDARY = "#141414"
BG_TERTIARY = "#1C1C1C"
BG_CARD = "#1A1A1A"
BG_OVERLAY = "rgba(20, 20, 20, 0.92)"

# Crimson/Maroon accent (from icon colors #1a0808 to #260609)
ACCENT_PRIMARY = "#8B0000"       # Dark red from icon
ACCENT_LIGHT = "#B5342B"         # Brighter crimson
ACCENT_MEDIUM = "#6B0000"        # Mid-tone
ACCENT_DARK = "#4A0000"          # Deep crimson
ACCENT_GLOW = "rgba(139, 0, 0, 0.4)"

# Text colors
TEXT_PRIMARY = "#FFFFFF"
TEXT_SECONDARY = "#A0A0A0"
TEXT_TERTIARY = "#606060"
TEXT_LINK = "#4A90D9"

# Status
SUCCESS = "#00C853"
WARNING = "#FFB300"
ERROR = "#FF1744"
INFO = "#2979FF"

# Borders & Separators
BORDER_SUBTLE = "rgba(255, 255, 255, 0.06)"
BORDER_ACTIVE = "rgba(139, 0, 0, 0.5)"
SEPARATOR = "rgba(255, 255, 255, 0.04)"

# Fonts
FONT_DISPLAY = '"Inter", "SF Pro Display", -apple-system, "Segoe UI", sans-serif'
FONT_BODY = '"Inter", "SF Pro Text", -apple-system, "Segoe UI", sans-serif'
FONT_MONO = '"JetBrains Mono", "SF Mono", "Cascadia Code", monospace'

# ── Main Dark Theme ─────────────────────────────────────────────────
DARK_THEME = f"""
    /* ── Base ───────────────────────────────────────────────────── */
    QMainWindow {{
        background-color: {BG_DEEP};
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
        font-size: 22px;
        font-weight: 600;
        letter-spacing: -0.3px;
    }}

    QLabel#subtitleLabel {{
        font-size: 13px;
        color: {TEXT_SECONDARY};
    }}

    QLabel#statusLabel {{
        font-size: 12px;
        color: {TEXT_SECONDARY};
        background: {BG_SECONDARY};
        padding: 8px 14px;
        border-radius: 10px;
    }}

    QLabel#fpsLabel {{
        font-family: {FONT_MONO};
        font-size: 12px;
        color: {SUCCESS};
        background: {BG_TERTIARY};
        padding: 6px 10px;
        border-radius: 6px;
    }}

    /* ── Buttons ─────────────────────────────────────────────────── */
    QPushButton {{
        background: {BG_TERTIARY};
        color: {TEXT_PRIMARY};
        border: none;
        border-radius: 10px;
        padding: 12px 20px;
        font-family: {FONT_BODY};
        font-size: 13px;
        font-weight: 500;
    }}

    QPushButton:hover {{
        background: {BG_CARD};
    }}

    QPushButton:pressed {{
        background: {BG_SECONDARY};
    }}

    QPushButton:disabled {{
        background: {BG_SECONDARY};
        color: {TEXT_TERTIARY};
    }}

    /* Primary Button - Crimson accent */
    QPushButton#primaryButton {{
        background: {ACCENT_PRIMARY};
        color: {TEXT_PRIMARY};
        font-weight: 600;
    }}

    QPushButton#primaryButton:hover {{
        background: {ACCENT_LIGHT};
    }}

    QPushButton#primaryButton:pressed {{
        background: {ACCENT_DARK};
    }}

    /* Icon Button */
    QPushButton#iconButton {{
        background: {BG_TERTIARY};
        border-radius: 50%;
        padding: 10px;
        min-width: 40px;
        min-height: 40px;
    }}

    /* ── Status Bar ─────────────────────────────────────────────── */
    QStatusBar {{
        background: {BG_PRIMARY};
        color: {TEXT_SECONDARY};
        font-size: 11px;
        border-top: 1px solid {SEPARATOR};
        padding: 4px 10px;
    }}

    /* ── Menu Bar ───────────────────────────────────────────────── */
    QMenuBar {{
        background: {BG_PRIMARY};
        color: {TEXT_PRIMARY};
        border: none;
        padding: 4px 8px;
        font-size: 12px;
    }}

    QMenuBar::item {{
        padding: 6px 12px;
        border-radius: 6px;
    }}

    QMenuBar::item:selected {{
        background: {BG_TERTIARY};
    }}

    /* ── Menus ─────────────────────────────────────────────────── */
    QMenu {{
        background: {BG_OVERLAY};
        color: {TEXT_PRIMARY};
        border: 1px solid {BORDER_SUBTLE};
        border-radius: 12px;
        padding: 6px;
    }}

    QMenu::item {{
        padding: 8px 28px 8px 14px;
        border-radius: 6px;
    }}

    QMenu::item:selected {{
        background: {BG_TERTIARY};
    }}

    QMenu::separator {{
        height: 1px;
        background: {SEPARATOR};
        margin: 4px 8px;
    }}

    /* ── Tooltips ───────────────────────────────────────────────── */
    QToolTip {{
        background: {BG_CARD};
        color: {TEXT_PRIMARY};
        border: 1px solid {BORDER_SUBTLE};
        border-radius: 8px;
        padding: 6px 10px;
        font-size: 11px;
    }}

    /* ── Group Boxes ────────────────────────────────────────────── */
    QGroupBox {{
        font-weight: 600;
        font-size: 12px;
        color: {TEXT_SECONDARY};
        background: {BG_SECONDARY};
        border: 1px solid {BORDER_SUBTLE};
        border-radius: 12px;
        margin-top: 16px;
        padding: 16px;
    }}

    QGroupBox::title {{
        subcontrol-origin: margin;
        left: 12px;
        padding: 0 8px;
        color: {TEXT_SECONDARY};
        font-size: 11px;
    }}

    /* ── ComboBox ───────────────────────────────────────────────── */
    QComboBox {{
        background: {BG_TERTIARY};
        color: {TEXT_PRIMARY};
        border: 1px solid {BORDER_SUBTLE};
        border-radius: 8px;
        padding: 8px 12px;
        font-size: 12px;
    }}

    QComboBox:hover {{
        border-color: {BORDER_ACTIVE};
    }}

    QComboBox::drop-down {{
        border: none;
        width: 24px;
    }}

    QComboBox QAbstractItemView {{
        background: {BG_OVERLAY};
        color: {TEXT_PRIMARY};
        border: 1px solid {BORDER_SUBTLE};
        border-radius: 10px;
        padding: 4px;
        selection-background-color: {BG_TERTIARY};
    }}

    /* ── SpinBox ───────────────────────────────────────────────── */
    QSpinBox {{
        background: {BG_TERTIARY};
        color: {TEXT_PRIMARY};
        border: 1px solid {BORDER_SUBTLE};
        border-radius: 8px;
        padding: 8px 12px;
        font-size: 12px;
    }}

    /* ── CheckBox ───────────────────────────────────────────────── */
    QCheckBox {{
        color: {TEXT_PRIMARY};
        spacing: 10px;
        font-size: 13px;
    }}

    QCheckBox::indicator {{
        width: 18px;
        height: 18px;
        border-radius: 5px;
        border: 2px solid {BG_TERTIARY};
        background: {BG_TERTIARY};
    }}

    QCheckBox::indicator:checked {{
        background: {ACCENT_PRIMARY};
        border-color: {ACCENT_PRIMARY};
    }}

    /* ── Sliders ───────────────────────────────────────────────── */
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

    QSlider::sub-page:horizontal {{
        background: {ACCENT_PRIMARY};
        border-radius: 2px;
    }}

    /* ── Scroll Bars ─────────────────────────────────────────────── */
    QScrollBar:vertical {{
        background: transparent;
        width: 8px;
        margin: 0;
    }}

    QScrollBar::handle:vertical {{
        background: {BG_TERTIARY};
        border-radius: 4px;
        min-height: 24px;
    }}

    /* ── Dialog ─────────────────────────────────────────────────── */
    QDialog {{
        background: {BG_PRIMARY};
    }}

    QMessageBox {{
        background: {BG_SECONDARY};
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
        font-size: 28px;
        font-weight: 300;
        color: {TEXT_PRIMARY};
        letter-spacing: -0.5px;
        background: transparent;
    }}

    QLabel#waitingSubtitle {{
        font-size: 13px;
        color: {TEXT_SECONDARY};
        background: transparent;
    }}

    QLabel#waitingDot {{
        font-size: 32px;
        color: {ACCENT_PRIMARY};
        background: transparent;
    }}
"""

# ── Toolbar ────────────────────────────────────────────────────────
TOOLBAR_STYLE = f"""
    QToolBar {{
        background: {BG_PRIMARY};
        border-bottom: 1px solid {SEPARATOR};
        padding: 6px 10px;
        spacing: 6px;
    }}

    QToolButton {{
        background: transparent;
        border: none;
        border-radius: 8px;
        padding: 8px 14px;
        color: {TEXT_PRIMARY};
        font-size: 12px;
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
        font-weight: 600;
        font-size: 12px;
        color: {TEXT_SECONDARY};
        background: {BG_SECONDARY};
        border: 1px solid {BORDER_SUBTLE};
        border-radius: 12px;
        margin-top: 16px;
        padding: 16px;
    }}

    QGroupBox::title {{
        subcontrol-origin: margin;
        left: 12px;
        padding: 0 8px;
        font-size: 11px;
    }}

    QLabel {{
        color: {TEXT_SECONDARY};
        font-size: 12px;
        background: transparent;
    }}

    QComboBox {{
        background: {BG_TERTIARY};
        color: {TEXT_PRIMARY};
        border: 1px solid {BORDER_SUBTLE};
        border-radius: 8px;
        padding: 8px 12px;
    }}

    QSpinBox {{
        background: {BG_TERTIARY};
        color: {TEXT_PRIMARY};
        border: 1px solid {BORDER_SUBTLE};
        border-radius: 8px;
        padding: 8px 12px;
    }}

    QCheckBox {{
        color: {TEXT_PRIMARY};
        spacing: 10px;
    }}

    QCheckBox::indicator {{
        width: 18px;
        height: 18px;
        border-radius: 5px;
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
        border-radius: 10px;
        padding: 10px 20px;
        font-size: 13px;
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
