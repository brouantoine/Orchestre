"""Thème « studio de nuit » : anthracite profond, accent or, vert pour ce qui joue."""

from orchestre_ia.interface.icons import ICON_DIR

BG = "#0e1015"
SIDEBAR = "#12141b"
PANEL = "#171a22"
PANEL_ALT = "#1f2330"
PANEL_HI = "#272c3b"
BORDER = "#262b37"
BORDER_HI = "#353c4d"
TEXT = "#eceef2"
TEXT_DIM = "#8d94a5"
TEXT_FAINT = "#5c6375"
ACCENT = "#f0b046"
ACCENT_HI = "#ffd27a"
ACCENT_LO = "#c7861d"
OK = "#34d399"
WARN = "#fbbf24"
DANGER = "#f87171"
INFO = "#60a5fa"

FONT = '"Segoe UI Variable Text", "Segoe UI", sans-serif'
FONT_DISPLAY = '"Segoe UI Variable Display", "Segoe UI", sans-serif'
_CHEVRON = (ICON_DIR / "chevron-down.svg").as_posix()
_CHECK = (ICON_DIR / "check.svg").as_posix()
_CHEVRON_UP = (ICON_DIR / "chevron-up.svg").as_posix()

STYLESHEET = f"""
QWidget {{ background: {BG}; color: {TEXT}; font-family: {FONT}; font-size: 10pt; }}
QToolTip {{ background: {PANEL_HI}; color: {TEXT}; border: 1px solid {BORDER_HI}; padding: 6px 8px; border-radius: 6px; }}

/* ---------- barre latérale ---------- */
QWidget#Sidebar {{ background: {SIDEBAR}; border-right: 1px solid {BORDER}; }}
QWidget#Sidebar QLabel {{ background: transparent; }}
QLabel#Brand {{ font-family: {FONT_DISPLAY}; font-size: 13pt; font-weight: 700; letter-spacing: 1.5px; color: {TEXT}; }}
QWidget#Sidebar QLabel#BrandTag {{ background: {ACCENT}; color: #16130c; font-size: 8pt; font-weight: 800; padding: 1px 6px; border-radius: 4px; }}
QLabel#NavSection {{ color: {TEXT_FAINT}; font-size: 8pt; font-weight: 700; letter-spacing: 1.5px; padding: 0 22px; }}
QListWidget#Nav {{ background: transparent; border: none; outline: 0; padding: 4px 10px; }}
QListWidget#Nav::item {{ color: {TEXT_DIM}; padding: 10px 12px; margin: 2px 0; border-radius: 8px; }}
QListWidget#Nav::item:hover {{ background: {PANEL}; color: {TEXT}; }}
QListWidget#Nav::item:selected {{ background: {PANEL_ALT}; color: {TEXT}; border-left: 3px solid {ACCENT}; }}
QLabel#SideStatus {{ color: {TEXT_DIM}; font-size: 9pt; }}
QLabel#Version {{ color: {TEXT_FAINT}; font-size: 8pt; }}

/* ---------- titres ---------- */
QLabel#ViewTitle {{ font-family: {FONT_DISPLAY}; font-size: 21pt; font-weight: 700; }}
QLabel#ViewSubtitle {{ color: {TEXT_DIM}; font-size: 10.5pt; }}
QLabel#Dim {{ color: {TEXT_DIM}; background: transparent; }}
QLabel#Faint {{ color: {TEXT_FAINT}; background: transparent; }}
QLabel#Warning {{ color: {WARN}; background: transparent; }}

/* ---------- cartes et tuiles ---------- */
QFrame#Card {{ background: {PANEL}; border: 1px solid {BORDER}; border-radius: 14px; }}
QFrame#Card QLabel, QFrame#Card QCheckBox, QFrame#Card QRadioButton {{ background: transparent; }}
QFrame#Card QWidget#Transparent {{ background: transparent; }}
QFrame#Tile {{ background: {PANEL}; border: 1px solid {BORDER}; border-radius: 14px; }}
QFrame#Tile[accent="true"] {{ background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #2a2416, stop:1 {PANEL}); border: 1px solid #4a3a1c; }}
QFrame#Tile QLabel, QFrame#Tile QWidget {{ background: transparent; }}
QLabel#CardTitle {{ color: {TEXT_DIM}; font-size: 8.5pt; font-weight: 700; letter-spacing: 1.2px; }}
QLabel#TileValue {{ font-family: {FONT_DISPLAY}; font-size: 19pt; font-weight: 700; }}
QLabel#ChordValue {{ font-family: {FONT_DISPLAY}; font-size: 30pt; font-weight: 800; color: {ACCENT_HI}; }}
QLabel#BigValue {{ font-family: "Cascadia Mono", "Consolas", monospace; font-size: 16pt; font-weight: 600; }}

/* ---------- pastilles d'état ---------- */
QLabel#Pill {{ background: {PANEL_ALT}; border: 1px solid {BORDER_HI}; border-radius: 13px; padding: 4px 12px; color: {TEXT_DIM}; font-size: 9pt; font-weight: 600; }}
QLabel#Pill[state="ok"] {{ color: {OK}; border-color: #1f5c47; background: #12241e; }}
QLabel#Pill[state="warn"] {{ color: {WARN}; border-color: #5c4a17; background: #241e10; }}
QLabel#Pill[state="error"] {{ color: {DANGER}; border-color: #6b2b2b; background: #2a1414; }}

/* ---------- boutons ---------- */
QPushButton {{ background: {PANEL_ALT}; border: 1px solid {BORDER_HI}; border-radius: 9px; padding: 8px 16px; color: {TEXT}; font-weight: 600; }}
QPushButton:hover {{ border-color: {ACCENT}; background: {PANEL_HI}; }}
QPushButton:pressed {{ background: {BORDER}; }}
QPushButton:disabled {{ color: {TEXT_FAINT}; border-color: {BORDER}; background: {PANEL}; }}
QPushButton#Primary {{ background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 {ACCENT_HI}, stop:1 {ACCENT_LO}); color: #17130a; border: none; padding: 11px 22px; font-size: 10.5pt; font-weight: 700; }}
QPushButton#Primary:hover {{ background: qlineargradient(x1:0, y1:0, x2:1, y2:1, stop:0 #ffe3a8, stop:1 {ACCENT}); }}
QPushButton#Primary:disabled {{ background: {PANEL_ALT}; color: {TEXT_FAINT}; border: 1px solid {BORDER}; }}
QPushButton#Danger {{ background: #3a1c1f; color: {DANGER}; border: 1px solid #6b2b2b; padding: 11px 18px; }}
QPushButton#Danger:hover {{ background: #4a2226; border-color: {DANGER}; }}
QPushButton#Danger:disabled {{ background: {PANEL}; color: {TEXT_FAINT}; border-color: {BORDER}; }}
QPushButton#Secondary {{ padding: 11px 18px; }}
QPushButton#IconButton {{ padding: 7px; min-width: 22px; }}

/* ---------- champs ---------- */
QComboBox, QSpinBox, QDoubleSpinBox {{ background: {PANEL_ALT}; border: 1px solid {BORDER_HI}; border-radius: 9px; padding: 7px 12px; min-height: 20px; }}
QComboBox:hover, QSpinBox:hover, QDoubleSpinBox:hover {{ border-color: {ACCENT}; }}
QComboBox:disabled {{ color: {TEXT_FAINT}; border-color: {BORDER}; }}
QComboBox::drop-down {{ border: none; width: 28px; }}
QComboBox::down-arrow {{ image: url("{_CHEVRON}"); width: 14px; height: 14px; }}
QComboBox QAbstractItemView {{ background: {PANEL_HI}; border: 1px solid {BORDER_HI}; border-radius: 8px; padding: 4px; selection-background-color: {ACCENT}; selection-color: #17130a; outline: 0; }}
QSpinBox::up-button, QDoubleSpinBox::up-button, QSpinBox::down-button, QDoubleSpinBox::down-button {{ width: 22px; border: none; background: transparent; }}
QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {{ image: url("{_CHEVRON_UP}"); width: 12px; height: 12px; }}
QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {{ image: url("{_CHEVRON}"); width: 12px; height: 12px; }}
QLabel#Progression {{ color: {TEXT_DIM}; font-size: 9.5pt; }}
QLabel#ChordNotes {{ color: {ACCENT}; font-size: 11pt; font-weight: 600; }}

/* ---------- cases ---------- */
QCheckBox, QRadioButton {{ background: transparent; spacing: 9px; }}
QCheckBox::indicator, QRadioButton::indicator {{ width: 16px; height: 16px; border: 2px solid {TEXT_FAINT}; background: {PANEL_ALT}; }}
QCheckBox::indicator {{ border-radius: 5px; }}
QRadioButton::indicator {{ border-radius: 10px; }}
QCheckBox::indicator:hover, QRadioButton::indicator:hover {{ border-color: {ACCENT}; }}
QCheckBox::indicator:checked {{ background: {ACCENT}; border-color: {ACCENT}; image: url("{_CHECK}"); }}
QRadioButton::indicator:checked {{ background: qradialgradient(cx:0.5, cy:0.5, radius:0.5, fx:0.5, fy:0.5, stop:0 #17130a, stop:0.35 #17130a, stop:0.45 {ACCENT}, stop:1 {ACCENT}); border-color: {ACCENT}; }}
QCheckBox:disabled, QRadioButton:disabled {{ color: {TEXT_FAINT}; }}

/* ---------- curseurs ---------- */
QSlider::groove:horizontal {{ height: 6px; background: {PANEL_HI}; border-radius: 3px; }}
QSlider::sub-page:horizontal {{ background: qlineargradient(x1:0, y1:0, x2:1, y2:0, stop:0 {ACCENT_LO}, stop:1 {ACCENT}); border-radius: 3px; }}
QSlider::handle:horizontal {{ background: {TEXT}; border: 3px solid {ACCENT}; width: 12px; height: 12px; margin: -6px 0; border-radius: 9px; }}
QSlider::handle:horizontal:hover {{ background: {ACCENT_HI}; }}

/* ---------- défilement ---------- */
QScrollArea {{ background: {BG}; border: none; }}
QScrollBar:vertical {{ background: transparent; width: 10px; margin: 4px 2px; }}
QScrollBar::handle:vertical {{ background: {BORDER_HI}; border-radius: 3px; min-height: 40px; }}
QScrollBar::handle:vertical:hover {{ background: {TEXT_FAINT}; }}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical, QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ height: 0; background: none; }}
QScrollBar:horizontal {{ height: 0; }}

QStatusBar {{ background: {SIDEBAR}; color: {TEXT_FAINT}; border-top: 1px solid {BORDER}; font-size: 9pt; }}
QStatusBar QLabel {{ background: transparent; }}
"""
