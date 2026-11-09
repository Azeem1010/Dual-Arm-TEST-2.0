"""Small flat building blocks shared by the panels."""
from PyQt5.QtCore import Qt
from PyQt5.QtGui import QPainter
from PyQt5.QtWidgets import QHBoxLayout, QLabel, QWidget

from . import theme


class Panel(QWidget):
    """A plain white area. Separation comes from the page colour, not borders or shadows."""

    def paintEvent(self, _event):
        QPainter(self).fillRect(self.rect(), theme.color(theme.PANEL))


class HeaderBar(QWidget):
    """A solid title strip; extra widgets are placed on its right."""

    def __init__(self, title, background=theme.NAVY, parent=None):
        super().__init__(parent)
        self._background = background
        self.setFixedHeight(theme.HEADER_HEIGHT)
        self.layout_ = QHBoxLayout(self)
        self.layout_.setContentsMargins(8, 0, 6, 0)
        self.layout_.setSpacing(8)
        self.title = QLabel(title, self)
        self.title.setStyleSheet(f'color: #FFFFFF; font-size: {theme.SIZE_TITLE}px; font-weight: bold;')
        self.layout_.addWidget(self.title)
        self.layout_.addStretch(1)

    def add_right(self, widget):
        self.layout_.addWidget(widget)

    def paintEvent(self, _event):
        QPainter(self).fillRect(self.rect(), theme.color(self._background))


class Chip(QLabel):
    """Solid status text. Styling is only touched when the content changes."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.setAlignment(Qt.AlignCenter)
        self._current = None

    def set_chip(self, text, background, foreground):
        current = (text, background, foreground)
        if current == self._current:
            return
        self._current = current
        self.setText(text)
        self.setStyleSheet(f'background: {background}; color: {foreground}; font-size: {theme.SIZE_SMALL}px;'
                           ' font-weight: bold; padding: 1px 6px;')


class WhiteLabel(QLabel):
    def __init__(self, text='', parent=None):
        super().__init__(text, parent)
        self.setFont(theme.mono(theme.SIZE_SMALL))
        self.setStyleSheet('color: #FFFFFF;')
