"""Where the transfer is: progress, what each arm holds, zone states and the C grid."""
from PyQt5.QtCore import QRect, QRectF, Qt
from PyQt5.QtGui import QPainter, QPen
from PyQt5.QtWidgets import QGridLayout, QHBoxLayout, QLabel, QSizePolicy, QVBoxLayout, QWidget

from ..model.state import b_interlock, next_slot
from ..model.steps import SEGMENTS, ProgressTracker, SegmentState
from . import theme
from .widgets import HeaderBar, Panel

_SEGMENT_COLORS = {SegmentState.PENDING: (theme.DISABLED_BG, theme.TEXT_MUTED), SegmentState.CURRENT: (theme.BUSY, '#FFFFFF'),
                   SegmentState.DONE: (theme.OK, '#FFFFFF'), SegmentState.FAILED: (theme.DANGER, '#FFFFFF')}
_EMPTY = '—'
_SLOT_COLUMNS, _SLOT_ROWS = 2, 4
_STRIP_HEIGHT, _STRIP_HEIGHT_COMPACT = 62, 54


class ProgressStrip(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.states = (SegmentState.PENDING,) * len(SEGMENTS)
        self.setFixedHeight(_STRIP_HEIGHT)

    def set_states(self, states):
        if states != self.states:
            self.states = states
            self.update()

    def paintEvent(self, _event):
        painter = QPainter(self)
        gap, count = 2, len(SEGMENTS)
        width = (self.width() - gap * (count - 1)) / count
        for index, (name, state) in enumerate(zip(SEGMENTS, self.states)):
            rect = QRectF(index * (width + gap), 0, width, self.height()).toRect()
            background, foreground = _SEGMENT_COLORS[state]
            painter.fillRect(rect, theme.color(background))
            painter.setPen(theme.color(foreground))
            painter.setFont(theme.sans(theme.SIZE_SMALL, bold=state is not SegmentState.PENDING))
            painter.drawText(rect.adjusted(2, 2, -2, -18), Qt.AlignCenter, name)
            painter.drawText(rect.adjusted(2, 0, -2, -2), Qt.AlignHCenter | Qt.AlignBottom, state.value)


class InterlockStrip(QWidget):
    """Arm 1, zone B and Arm 2 side by side. A black bar is a closed gate; a gap means entry is allowed."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.view = None
        self.side_width, self.state_size = 54, theme.SIZE_SMALL
        self.setFixedHeight(46)
        self.setMinimumWidth(190)

    def set_large(self, large):
        self.side_width, self.state_size = (82, theme.SIZE_BODY + 1) if large else (54, theme.SIZE_SMALL)
        self.setFixedHeight(68 if large else 46)
        self.setMinimumWidth(290 if large else 190)
        self.update()

    def set_view(self, view):
        if view != self.view:
            self.view = view
            self.update()

    @staticmethod
    def _colors(level, arm=''):
        if arm:
            return theme.ARM_COLORS[arm], '#FFFFFF'
        return theme.LEVEL_COLORS[level]

    def _draw_cell(self, painter, rect, name, state, colors):
        painter.fillRect(rect, theme.color(colors[0]))
        painter.setPen(theme.color(colors[1]))
        painter.setFont(theme.sans(theme.SIZE_SMALL))
        painter.drawText(rect.adjusted(2, 3, -2, 0), Qt.AlignHCenter | Qt.AlignTop, name)
        painter.setFont(theme.sans(self.state_size, bold=True))
        painter.drawText(rect.adjusted(2, 0, -2, -3), Qt.AlignHCenter | Qt.AlignBottom, state)

    def paintEvent(self, _event):
        if self.view is None:
            return
        painter = QPainter(self)
        gate = 8
        width = self.side_width
        height = self.height()
        left = QRect(0, 0, width, height)
        center = QRect(width + gate, 0, self.width() - 2 * (width + gate), height)
        right = QRect(self.width() - width, 0, width, height)
        view = self.view
        self._draw_cell(painter, left, 'Arm1', view.arm1.state,
                        self._colors(view.arm1.level, 'arm1' if view.arm1.owned else ''))
        self._draw_cell(painter, center, 'B 區', view.center, self._colors(view.center_level, view.owner))
        self._draw_cell(painter, right, 'Arm2', view.arm2.state,
                        self._colors(view.arm2.level, 'arm2' if view.arm2.owned else ''))
        for cell, x in ((view.arm1, width), (view.arm2, self.width() - width - gate)):
            if cell.gate_unknown:
                painter.fillRect(QRect(x + 2, 0, gate - 4, height), theme.color(theme.LINE))
            elif not cell.may_enter:
                painter.fillRect(QRect(x + 2, 0, gate - 4, height), theme.color(theme.TEXT))


class SlotGrid(QWidget):
    """C slots in the operator's view (arms at the top): slots 1 and 2 are the top row,
    nearest the arms, odd slots on the left next to B. This is the real board's
    numbering, measured 2026-11-11 (docs/COORDINATE_FRAMES.md)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self.occupied, self.target, self.wrong = (False,) * 8, 0, ()
        self.setMinimumSize(130, 100)
        self.setSizePolicy(QSizePolicy.Expanding, QSizePolicy.Expanding)

    def set_state(self, occupied, target, wrong):
        current = (tuple(occupied), target, tuple(wrong))
        if current != (self.occupied, self.target, self.wrong):
            self.occupied, self.target, self.wrong = current
            self.update()

    def _cell_style(self, slot):
        if slot in self.wrong:
            return theme.DANGER, '#FFFFFF', '錯誤'
        if self.occupied[slot - 1]:
            return theme.OK, '#FFFFFF', '已放置'
        return theme.PANEL, theme.TEXT, '下一個' if slot == self.target else '空'

    def paintEvent(self, _event):
        painter = QPainter(self)
        gap = 3
        width = (self.width() - gap) // _SLOT_COLUMNS
        height = (self.height() - gap * (_SLOT_ROWS - 1)) // _SLOT_ROWS
        for slot in range(1, 9):
            row, column = (slot - 1) // _SLOT_COLUMNS, (slot - 1) % _SLOT_COLUMNS
            rect = QRect(column * (width + gap), row * (height + gap), width, height)
            background, foreground, text = self._cell_style(slot)
            painter.fillRect(rect, theme.color(background))
            is_target = slot == self.target and not self.occupied[slot - 1] and slot not in self.wrong
            painter.setPen(QPen(theme.color(theme.BUSY if is_target else theme.LINE), 3 if is_target else 1))
            painter.drawRect(rect.adjusted(1, 1, -2, -2) if is_target else rect.adjusted(0, 0, -1, -1))
            painter.setPen(theme.color(foreground))
            painter.setFont(theme.mono(theme.SIZE_BODY, bold=True))
            painter.drawText(rect.adjusted(8, 0, 0, 0), Qt.AlignLeft | Qt.AlignVCenter, str(slot))
            painter.setFont(theme.sans(theme.SIZE_SMALL))
            painter.drawText(rect.adjusted(0, 0, -8, 0), Qt.AlignRight | Qt.AlignVCenter, text)


class TaskPanel(Panel):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.tracker = ProgressTracker()
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        layout.addWidget(HeaderBar('工作狀態', theme.NAVY, self))

        body = QVBoxLayout()
        body.setContentsMargins(8, 8, 8, 8)
        body.setSpacing(6)
        self.body = body
        layout.addLayout(body, 1)
        self.strip = ProgressStrip(self)
        body.addWidget(self.strip)
        self.step = QLabel(_EMPTY, self)
        self.step.setFont(theme.sans(theme.SIZE_STATUS, bold=True))
        body.addWidget(self.step)
        details = QHBoxLayout()
        details.setSpacing(12)
        body.addLayout(details, 1)

        self.info = QGridLayout()
        self.info.setHorizontalSpacing(10)
        self.info.setVerticalSpacing(1)
        self.values = {}
        for row, (key, text) in enumerate((('active', '目前手臂'), ('arm1', 'Arm1 持物'), ('arm2', 'Arm2 持物'), ('b_owner', 'B 區擁有者'),
                                           ('completed', '完成數'), ('target', '目標格位'))):
            self._add_value(key, text, row)
        self.info.setRowStretch(6, 1)
        details.addLayout(self.info)

        self.zones = QGridLayout()
        self.zones.setHorizontalSpacing(8)
        self.zones.setVerticalSpacing(3)
        self.zone_labels = {}
        for row, zone in enumerate('ABC'):
            self._add_zone(zone, row)
        zone_column = QVBoxLayout()
        zone_column.setSpacing(3)
        self.zone_caption = QLabel('區域狀態', self)
        self.zone_caption.setProperty('caption', True)
        zone_column.addWidget(self.zone_caption)
        zone_column.addLayout(self.zones)
        self.interlock_caption = QLabel('B 區互鎖', self)
        self.interlock_caption.setProperty('caption', True)
        zone_column.addWidget(self.interlock_caption)
        self.interlock = InterlockStrip(self)
        zone_column.addWidget(self.interlock)
        zone_column.addStretch(1)
        details.addLayout(zone_column)

        grid_column = QVBoxLayout()
        grid_column.setSpacing(2)
        caption = QLabel('C 區格位', self)
        caption.setProperty('caption', True)
        grid_column.addWidget(caption)
        self.slots = SlotGrid(self)
        grid_column.addWidget(self.slots, 1)
        details.addLayout(grid_column, 1)

    def _add_value(self, key, text, row):
        name = QLabel(text, self)
        name.setProperty('muted', True)
        value = QLabel(_EMPTY, self)
        self.info.addWidget(name, row, 0)
        self.info.addWidget(value, row, 1)
        self.values[key] = value

    def _add_zone(self, zone, row):
        tag = QLabel(f'{zone} 區', self)
        tag.setAlignment(Qt.AlignCenter)
        tag.setStyleSheet(f'background: {theme.ZONE_COLORS[zone]}; color: #000000; font-weight: bold; padding: 0 4px;')
        value = QLabel(_EMPTY, self)
        self.zones.addWidget(tag, row, 0)
        self.zones.addWidget(value, row, 1)
        self.zone_labels[zone] = value

    def set_compact(self, compact, wide):
        self.interlock.set_large(wide and not compact)
        # The strip names zone B itself; on short windows the row is needed for the zone rows.
        self.interlock_caption.setVisible(not compact)
        self.strip.setFixedHeight(_STRIP_HEIGHT_COMPACT if compact else _STRIP_HEIGHT)
        margin = 4 if compact else 8
        self.body.setContentsMargins(8, margin, 8, margin)
        self.body.setSpacing(3 if compact else 6)

    @staticmethod
    def _holding_text(value):
        return {'empty': '空', 'held': '持物中'}.get(value, value)

    def _set_holding(self, key, value, arm):
        label = self.values[key]
        held = value != 'empty'
        label.setText(self._holding_text(value))
        label.setStyleSheet(f'color: {theme.ARM_COLORS[arm]}; font-weight: bold;' if held else '')

    def update_from(self, snapshot):
        task = snapshot.task
        if task is None:
            self.strip.set_states(self.tracker.update('IDLE').segments)
            self.step.setText(_EMPTY)
            for label in self.values.values():
                label.setText(_EMPTY)
                label.setStyleSheet('')
            self.slots.set_state((False,) * 8, 0, ())
        else:
            progress = self.tracker.update(task.state)
            self.strip.set_states(progress.segments)
            self.step.setText(progress.text)
            self.values['active'].setText(task.active_arm or _EMPTY)
            self._set_holding('arm1', task.held_by('arm1'), 'arm1')
            self._set_holding('arm2', task.held_by('arm2'), 'arm2')
            self.values['b_owner'].setText(task.b_owner or '無')
            self.values['completed'].setText(str(task.completed))
            target = next_slot(task)
            self.values['target'].setText(str(target) if target else '無')
            self.slots.set_state(task.occupied, target, snapshot.wrong_slots)
        self._update_zones(snapshot.zones)
        self.zone_caption.setText('區域狀態' if snapshot.zones_authoritative else '區域狀態（視覺參考）')
        self.interlock.set_view(b_interlock(snapshot))

    def _update_zones(self, zones):
        if zones is None:
            for label in self.zone_labels.values():
                label.setText(_EMPTY)
            return
        self.zone_labels['A'].setText('有物件' if zones.a_has_object else '無物件')
        self.zone_labels['B'].setText(('有物件' if zones.b_has_object else '無物件') + '／' + ('手臂離開' if zones.b_arm_clear else '手臂在內'))
        self.zone_labels['C'].setText(f'{zones.c_count} 個')
