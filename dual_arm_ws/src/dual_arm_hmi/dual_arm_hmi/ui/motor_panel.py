"""Eight joints in one table, with position drawn against the joint limits."""
from PyQt5.QtCore import QRect, Qt
from PyQt5.QtGui import QPainter
from PyQt5.QtWidgets import QGridLayout, QLabel, QSizePolicy, QVBoxLayout, QWidget

from ..model.joints import ARMS, EMPTY, JOINT_LABELS, JOINT_NAMES, joint_row
from . import theme
from .widgets import Chip, HeaderBar, Panel

_VALUE_COLUMNS = ('degrees', 'radians', 'raw', 'velocity', 'error')
_HEADERS = ('關節', '角度 °', 'rad', 'raw', '速度(估)', '誤差', '限位位置', '距限位 °')
_RAD_COLUMN = 2
_BAR_COLUMN = 6
_MARGIN_COLUMN = 7


class LimitBar(QWidget):
    def __init__(self, arm_color, parent=None):
        super().__init__(parent)
        self._arm_color = arm_color
        self._fraction, self._near = None, False
        self.setMinimumWidth(60)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Preferred)

    def set_value(self, fraction, near):
        self._fraction, self._near = fraction, near
        self.update()

    def paintEvent(self, _event):
        painter = QPainter(self)
        track = QRect(0, self.height() // 2 - 5, self.width(), 10)
        painter.fillRect(track, theme.color(theme.TRACK))
        if self._fraction is None:
            return
        fill = theme.WARN if self._near else self._arm_color
        if not self.isEnabled():
            fill = theme.LINE
        painter.fillRect(QRect(track.x(), track.y(), int(track.width() * self._fraction), track.height()), theme.color(fill))
        marker = int((track.width() - 3) * self._fraction)
        painter.fillRect(QRect(marker, self.height() // 2 - 9, 3, 18), theme.color(theme.TEXT))


class MotorPanel(Panel):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.header = HeaderBar('馬達', theme.NAVY, self)
        self.freshness = Chip(self.header)
        self.header.add_right(self.freshness)
        layout.addWidget(self.header)

        self.table = QWidget(self)
        self.grid = QGridLayout(self.table)
        self.grid.setContentsMargins(8, 2, 8, 2)
        self.grid.setHorizontalSpacing(10)
        self.grid.setVerticalSpacing(0)
        layout.addWidget(self.table, 1)
        self.rows = {}
        self._column_widgets = {_RAD_COLUMN: []}
        self._build_table()

    def _build_table(self):
        for column, text in enumerate(_HEADERS):
            label = QLabel(text, self.table)
            label.setProperty('muted', True)
            align = Qt.AlignVCenter | (Qt.AlignLeft if column in (0, _BAR_COLUMN) else Qt.AlignRight)
            self.grid.addWidget(label, 0, column, align)
            if column in self._column_widgets:
                self._column_widgets[column].append(label)
        row = 1
        for arm_index, arm in enumerate(ARMS):
            color = theme.ARM_COLORS[arm]
            title = QLabel(f'Arm {arm_index + 1}', self.table)
            title.setStyleSheet(f'background: {color}; color: #FFFFFF; font-weight: bold; padding: 0 8px;')
            title.setFixedHeight(22)
            self.grid.addWidget(title, row, 0, 1, len(_HEADERS))
            row += 1
            for joint_index, label in enumerate(JOINT_LABELS):
                self._add_joint(JOINT_NAMES[arm_index * 4 + joint_index], label, color, row)
                row += 1
        self.grid.setColumnStretch(_BAR_COLUMN, 1)
        for index in range(row):
            self.grid.setRowMinimumHeight(index, 22)

    def _add_joint(self, name, text, arm_color, row):
        self.grid.addWidget(QLabel(text, self.table), row, 0)
        cells = {}
        for column, field in enumerate(_VALUE_COLUMNS, start=1):
            cell = QLabel(EMPTY, self.table)
            cell.setFont(theme.mono())
            cell.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            self.grid.addWidget(cell, row, column)
            cells[field] = cell
            if column in self._column_widgets:
                self._column_widgets[column].append(cell)
        bar = LimitBar(arm_color, self.table)
        self.grid.addWidget(bar, row, _BAR_COLUMN)
        margin = Chip(self.table)
        margin.setFont(theme.mono(theme.SIZE_SMALL))
        margin.setMinimumWidth(52)
        self.grid.addWidget(margin, row, _MARGIN_COLUMN, Qt.AlignRight | Qt.AlignVCenter)
        self.rows[name] = (cells, bar, margin)

    def set_compact(self, compact):
        for widget in self._column_widgets[_RAD_COLUMN]:
            widget.setVisible(not compact)

    def update_from(self, snapshot):
        stale = snapshot.joints_stale
        self.table.setEnabled(not stale)
        if snapshot.joint_age_s is None:
            self.freshness.set_chip('無資料', theme.DISABLED_BG, theme.TEXT)
        elif stale:
            self.freshness.set_chip('資料過期', theme.WARN, '#000000')
        else:
            self.freshness.set_chip('即時', theme.OK, '#FFFFFF')
        samples = {sample.name: sample for sample in snapshot.joints}
        for name, (cells, bar, margin) in self.rows.items():
            sample = samples.get(name)
            if sample is None:
                for cell in cells.values():
                    cell.setText(EMPTY)
                bar.set_value(None, False)
                margin.set_chip(EMPTY, theme.PANEL, theme.TEXT_MUTED)
                continue
            row = joint_row(sample)
            for field, cell in cells.items():
                cell.setText(getattr(row, field))
            bar.set_value(row.fraction, row.near_limit)
            if row.fraction is None:
                margin.set_chip(row.margin, theme.PANEL, theme.TEXT_MUTED)
            elif row.near_limit and not stale:
                margin.set_chip(row.margin, theme.WARN, '#000000')
            else:
                margin.set_chip(row.margin, theme.PANEL, theme.TEXT_MUTED if stale else theme.TEXT)
