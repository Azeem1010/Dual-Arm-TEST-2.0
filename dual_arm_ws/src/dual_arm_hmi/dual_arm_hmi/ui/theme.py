"""The visual specification from docs/UI_PLAN.md section 3. All colours and sizes live here."""
from PyQt5.QtGui import QColor, QFont, QFontDatabase

from ..model.state import Level

NAVY = '#17375E'
PAGE = '#EAF1F8'
PANEL = '#FFFFFF'
TEXT = '#111827'
TEXT_MUTED = '#4B5563'
LINE = '#C9CED6'
DISABLED_BG = '#E5E7EB'
TRACK = '#DCE5EE'

ARM1 = '#00838F'
ARM2 = '#6A3FA0'
ARM_COLORS = {'arm1': ARM1, 'arm2': ARM2}
ZONE_COLORS = {'A': '#0080FF', 'B': '#00C800', 'C': '#FFDC00'}

OK = '#0B7A3B'
BUSY = '#0B5FD9'
WARN = '#FFC400'
DANGER = '#C8102E'

# Level -> (background, text).
LEVEL_COLORS = {
    Level.NEUTRAL: (DISABLED_BG, TEXT),
    Level.STRUCTURE: (NAVY, '#FFFFFF'),
    Level.OK: (OK, '#FFFFFF'),
    Level.BUSY: (BUSY, '#FFFFFF'),
    Level.WARN: (WARN, '#000000'),
    Level.DANGER: (DANGER, '#FFFFFF'),
    Level.HARDWARE: ('#000000', WARN),
    Level.INFO: (PANEL, NAVY),
}

SIZE_SMALL = 12
SIZE_BODY = 14
SIZE_TITLE = 16
SIZE_STATUS = 20
SIZE_BANNER = 24

HEADER_HEIGHT = 30
STATUS_BAR_HEIGHT = 56
BANNER_HEIGHT = 48
GAP = 8
RAIL_WIDTH = 320
RAIL_WIDTH_COMPACT = 280
BUTTON_HEIGHT = 40
STOP_HEIGHT = 72
MIN_WIDTH = 1280
MIN_HEIGHT = 720

_SANS_FAMILY = 'Noto Sans CJK TC'
_MONO_FAMILY = 'Noto Sans Mono CJK TC'


def font_available():
    return _SANS_FAMILY in QFontDatabase().families()


def sans(size=SIZE_BODY, bold=False):
    font = QFont(_SANS_FAMILY)
    font.setPixelSize(size)
    font.setBold(bold)
    return font


def mono(size=SIZE_BODY, bold=False):
    font = QFont(_MONO_FAMILY)
    font.setPixelSize(size)
    font.setBold(bold)
    return font


def color(value):
    return QColor(value)


def style_sheet():
    return f"""
    QMainWindow, QWidget#page {{ background: {PAGE}; }}
    QWidget {{ color: {TEXT}; font-family: "{_SANS_FAMILY}"; font-size: {SIZE_BODY}px; }}
    QWidget[panel="true"] {{ background: {PANEL}; }}
    QLabel {{ background: transparent; }}
    QLabel[muted="true"] {{ color: {TEXT_MUTED}; font-size: {SIZE_SMALL}px; }}
    QLabel[caption="true"] {{ color: {NAVY}; font-weight: bold; }}
    QLabel[section="true"] {{ color: {NAVY}; font-size: {SIZE_TITLE}px; font-weight: bold;
                              border-bottom: 1px solid {LINE}; padding: 2px 0; }}

    QPushButton {{ border: 1px solid {NAVY}; border-radius: 0; background: {PANEL}; color: {NAVY};
                   font-weight: bold; padding: 0 6px; }}
    QPushButton:hover {{ background: {PAGE}; }}
    QPushButton:focus {{ border: 2px solid {TEXT}; }}
    QPushButton[kind="primary"] {{ background: {NAVY}; color: #FFFFFF; }}
    QPushButton[kind="primary"]:hover {{ background: #0F2745; }}
    QPushButton[kind="start"] {{ background: {OK}; color: #FFFFFF; border-color: {OK}; }}
    QPushButton[kind="start"]:hover {{ background: #086330; }}
    QPushButton[kind="cancel"] {{ background: {WARN}; color: #000000; border-color: {WARN}; }}
    QPushButton[kind="cancel"]:hover {{ background: #E6B000; }}
    QPushButton[kind="danger"] {{ background: {DANGER}; color: #FFFFFF; border-color: {DANGER}; }}
    QPushButton[kind="danger"]:hover {{ background: #A50D26; }}
    QPushButton#stop {{ background: {DANGER}; color: #FFFFFF; border: 2px solid {DANGER};
                        font-size: {SIZE_BANNER + 4}px; font-weight: bold; }}
    QPushButton#stop:hover {{ background: #A50D26; }}
    QPushButton#stop:focus {{ border: 2px solid {TEXT}; }}
    QPushButton:disabled {{ background: {DISABLED_BG}; color: {TEXT_MUTED}; border: 1px solid {DISABLED_BG}; }}
    QPushButton[headerButton="true"] {{ background: {PANEL}; color: {NAVY}; border: none; font-size: {SIZE_SMALL}px;
                                        padding: 0 6px; }}

    QComboBox {{ border: 1px solid {LINE}; border-radius: 0; background: {PANEL}; padding: 0 6px; min-height: 30px; }}
    QComboBox:disabled {{ background: {DISABLED_BG}; color: {TEXT_MUTED}; }}
    QComboBox::drop-down {{ border: none; width: 22px; }}
    QComboBox QAbstractItemView {{ background: {PANEL}; border: 1px solid {LINE}; selection-background-color: {NAVY};
                                   selection-color: #FFFFFF; }}

    QCheckBox {{ spacing: 6px; }}
    QCheckBox::indicator {{ width: 18px; height: 18px; border: 1px solid {NAVY}; background: {PANEL}; }}
    QCheckBox::indicator:checked {{ background: {NAVY}; }}

    QScrollArea {{ border: none; background: transparent; }}
    QScrollBar:vertical {{ background: {PAGE}; width: 10px; border: none; }}
    QScrollBar::handle:vertical {{ background: {LINE}; min-height: 24px; }}
    QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{ height: 0; }}
    QScrollBar::add-page:vertical, QScrollBar::sub-page:vertical {{ background: none; }}

    QListWidget {{ border: none; background: {PANEL}; outline: none; }}
    QMessageBox {{ background: {PANEL}; }}
    """
