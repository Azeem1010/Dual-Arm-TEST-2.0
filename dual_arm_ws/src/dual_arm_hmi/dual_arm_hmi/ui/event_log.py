"""Time-ordered events with faults kept at the top."""
from PyQt5.QtCore import QRect, QSize, Qt, pyqtSignal
from PyQt5.QtWidgets import QListWidget, QListWidgetItem, QPushButton, QStyledItemDelegate, QVBoxLayout

from ..model.state import Level
from . import theme
from .widgets import HeaderBar, Panel

_ROW_HEIGHT = 26
_LEVEL_TEXT = {Level.DANGER: '故障', Level.WARN: '警告', Level.OK: '正常', Level.BUSY: '進行', Level.NEUTRAL: '資訊', Level.INFO: '資訊'}
_STRIP = {Level.DANGER: theme.DANGER, Level.WARN: theme.WARN, Level.OK: theme.OK, Level.BUSY: theme.BUSY,
          Level.NEUTRAL: theme.LINE, Level.INFO: theme.LINE}


class _Delegate(QStyledItemDelegate):
    def paint(self, painter, option, index):
        event = index.data(Qt.UserRole)
        rect = option.rect
        painter.save()
        painter.fillRect(QRect(rect.x(), rect.y() + 1, 6, rect.height() - 2), theme.color(_STRIP[event.level]))
        painter.setPen(theme.color(theme.TEXT_MUTED))
        painter.setFont(theme.mono(theme.SIZE_SMALL))
        painter.drawText(rect.adjusted(14, 0, 0, 0), Qt.AlignLeft | Qt.AlignVCenter, event.time_text)
        painter.setFont(theme.sans(theme.SIZE_SMALL, bold=True))
        painter.drawText(rect.adjusted(84, 0, 0, 0), Qt.AlignLeft | Qt.AlignVCenter, _LEVEL_TEXT[event.level])
        painter.setPen(theme.color(theme.TEXT))
        painter.setFont(theme.sans(theme.SIZE_BODY))
        message = painter.fontMetrics().elidedText(event.message, Qt.ElideRight, rect.width() - 128)
        painter.drawText(rect.adjusted(122, 0, 0, 0), Qt.AlignLeft | Qt.AlignVCenter, message)
        painter.restore()

    def sizeHint(self, _option, _index):
        return QSize(100, _ROW_HEIGHT)


def ordered(events):
    """Faults first, otherwise the order given (newest first)."""
    return sorted(events, key=lambda event: event.level is not Level.DANGER)


class EventLog(Panel):
    expand_toggled = pyqtSignal(bool)

    def __init__(self, parent=None):
        super().__init__(parent)
        self.expanded = False
        self._shown = None
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.header = HeaderBar('事件紀錄', theme.NAVY, self)
        self.expand = QPushButton('展開', self.header)
        self.expand.setProperty('headerButton', True)
        self.expand.setFixedSize(44, 22)
        self.expand.clicked.connect(self._toggle)
        self.header.add_right(self.expand)
        layout.addWidget(self.header)
        self.list = QListWidget(self)
        self.list.setItemDelegate(_Delegate(self.list))
        self.list.setFocusPolicy(Qt.NoFocus)
        self.list.setSelectionMode(QListWidget.NoSelection)
        layout.addWidget(self.list, 1)

    def _toggle(self):
        self.expanded = not self.expanded
        self.expand.setText('收合' if self.expanded else '展開')
        self.expand_toggled.emit(self.expanded)

    def set_collapsible(self, collapsible):
        self.expand.setVisible(collapsible)
        if not collapsible and self.expanded:
            self._toggle()

    def collapsed_height(self):
        return theme.HEADER_HEIGHT + _ROW_HEIGHT

    def set_events(self, events):
        if events == self._shown:
            return
        self._shown = events
        self.list.clear()
        for event in ordered(events):
            item = QListWidgetItem()
            item.setData(Qt.UserRole, event)
            self.list.addItem(item)
