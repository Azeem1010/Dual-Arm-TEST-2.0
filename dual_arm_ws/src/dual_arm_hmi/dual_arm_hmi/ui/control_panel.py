"""Operator actions. The stop button never scrolls away and every disabled button says why."""
from PyQt5.QtCore import Qt, pyqtSignal
from PyQt5.QtWidgets import (QCheckBox, QComboBox, QHBoxLayout, QLabel, QPushButton, QScrollArea, QVBoxLayout, QWidget)

from ..model.state import Action, Mode, Phase
from . import theme
from .widgets import Panel

_BUTTON_WIDTH = 112
_STOP_NOTE = '軟體停止（F12），不會切斷馬達電源。危險時請按實體急停。'
_STOP_NOTE_MONITOR = '唯讀監看：這個按鈕尚未接通，按了也不會停止。需要停止時請按實體急停。'


class ActionRow(QWidget):
    triggered = pyqtSignal(object)

    def __init__(self, action, kind='', parent=None, takes_focus=True):
        super().__init__(parent)
        self.action = action
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        self.button = QPushButton(action.value, self)
        self.button.setFixedSize(_BUTTON_WIDTH, theme.BUTTON_HEIGHT)
        self.button.setAutoDefault(False)
        if kind:
            self.button.setProperty('kind', kind)
        if not takes_focus:
            self.button.setFocusPolicy(Qt.NoFocus)
        self.reason = QLabel('', self)
        self.reason.setProperty('muted', True)
        self.reason.setWordWrap(True)
        layout.addWidget(self.button)
        layout.addWidget(self.reason, 1)
        self.button.clicked.connect(lambda: self.triggered.emit(self.action))

    def apply(self, state):
        self.setVisible(state.visible)
        self.button.setEnabled(state.enabled)
        self.reason.setText('' if state.enabled else state.reason)

    def set_button_height(self, height):
        self.button.setFixedHeight(height)


class ControlPanel(Panel):
    action_requested = pyqtSignal(object)
    mode_selected = pyqtSignal(object)
    scenario_selected = pyqtSignal(str)
    gazebo_toggled = pyqtSignal()

    def __init__(self, scenarios=(), parent=None):
        super().__init__(parent)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(8, 8, 8, 8)
        outer.setSpacing(6)

        self.stop = QPushButton(Action.STOP.value, self)
        self.stop.setObjectName('stop')
        self.stop.setFixedHeight(theme.STOP_HEIGHT)
        self.stop.setAutoDefault(False)
        self.stop.clicked.connect(lambda: self.action_requested.emit(Action.STOP))
        outer.addWidget(self.stop)
        self.stop_note = QLabel(_STOP_NOTE, self)
        self.stop_note.setProperty('muted', True)
        self.stop_note.setWordWrap(True)
        outer.addWidget(self.stop_note)
        self.feedback = QLabel('最後操作：無', self)
        self.feedback.setWordWrap(True)
        self.feedback.setStyleSheet(f'border-top: 1px solid {theme.LINE}; border-bottom: 1px solid {theme.LINE}; padding: 3px 0;')
        outer.addWidget(self.feedback)

        scroll = QScrollArea(self)
        scroll.setWidgetResizable(True)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarAlwaysOff)
        scroll.setFocusPolicy(Qt.NoFocus)
        self.scroll = scroll
        outer.addWidget(scroll, 1)
        content = Panel()
        scroll.setWidget(content)
        self.body = QVBoxLayout(content)
        self.body.setContentsMargins(0, 0, 4, 0)
        self.body.setSpacing(6)

        self.rows = {}
        self._build_system(content)
        self._build_task(content)
        self._build_suction(content)
        self._build_display(content)
        self._build_scenarios(content, scenarios)
        self.body.addStretch(1)

    def _section(self, text, parent):
        label = QLabel(text, parent)
        label.setProperty('section', True)
        self.body.addWidget(label)

    def _add_row(self, action, kind, parent, takes_focus=True):
        row = ActionRow(action, kind, parent, takes_focus)
        row.triggered.connect(self.action_requested)
        self.body.addWidget(row)
        self.rows[action] = row

    def _build_system(self, parent):
        self._section('系統', parent)
        self.mode = QComboBox(parent)
        for mode in Mode:
            if mode is not Mode.UNKNOWN:
                self.mode.addItem(mode.value, mode)
        self.mode.currentIndexChanged.connect(lambda: self.mode_selected.emit(self.mode.currentData()))
        self.body.addWidget(self.mode)
        self._add_row(Action.START_SYSTEM, 'primary', parent)
        self._add_row(Action.SHUTDOWN, '', parent)
        self._add_row(Action.TORQUE_ON, 'danger', parent)
        self._add_row(Action.SAFETY_RESET, 'primary', parent)
        self._add_row(Action.RESET_SIMULATION, '', parent)

    def _build_task(self, parent):
        self._section('任務', parent)
        # No focus: Enter or Space must never start motion.
        self._add_row(Action.START_TASK, 'start', parent, takes_focus=False)
        self._add_row(Action.CANCEL_TASK, 'cancel', parent)
        self.tools_cleared = QCheckBox('我已確認吸盤與 B 區都已清空', parent)
        self.body.addWidget(self.tools_cleared)
        self._add_row(Action.GO_HOME, 'primary', parent)
        self._add_row(Action.RECOVER, 'primary', parent)

    def _build_suction(self, parent):
        self.suction_section = QLabel('吸盤確認', parent)
        self.suction_section.setProperty('section', True)
        self.body.addWidget(self.suction_section)
        self.suction_text = QLabel('', parent)
        self.suction_text.setWordWrap(True)
        self.body.addWidget(self.suction_text)
        self._add_row(Action.SUCTION_OK, 'start', parent, takes_focus=False)
        self._add_row(Action.SUCTION_FAILED, 'danger', parent, takes_focus=False)

    def _build_display(self, parent):
        self._section('顯示', parent)
        row = QWidget(parent)
        layout = QHBoxLayout(row)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(8)
        self.gazebo = QPushButton('Gazebo 視角', row)
        self.gazebo.setFixedSize(_BUTTON_WIDTH, theme.BUTTON_HEIGHT)
        self.gazebo.setAutoDefault(False)
        self.gazebo.clicked.connect(self.gazebo_toggled)
        self.gazebo_reason = QLabel('', row)
        self.gazebo_reason.setProperty('muted', True)
        self.gazebo_reason.setWordWrap(True)
        layout.addWidget(self.gazebo)
        layout.addWidget(self.gazebo_reason, 1)
        self.body.addWidget(row)

    def set_gazebo_state(self, available, showing):
        self.gazebo.setEnabled(available or showing)
        self.gazebo.setText('返回相機' if showing else 'Gazebo 視角')
        self.gazebo_reason.setText('' if available or showing else '此模式沒有 Gazebo 影像')

    def _build_scenarios(self, parent, scenarios):
        if not scenarios:
            self.scenario = None
            return
        self._section('假資料情境（開發用）', parent)
        self.scenario = QComboBox(parent)
        for key, label in scenarios:
            self.scenario.addItem(label, key)
        self.scenario.activated.connect(lambda: self.scenario_selected.emit(self.scenario.currentData()))
        self.body.addWidget(self.scenario)

    def set_compact_height(self, compact):
        for row in self.rows.values():
            row.set_button_height(32 if compact else theme.BUTTON_HEIGHT)
        self.stop.setFixedHeight(56 if compact else theme.STOP_HEIGHT)

    def update_from(self, snapshot, actions, scenario_key=''):
        for action, row in self.rows.items():
            row.apply(actions[action])
        self._update_stop(snapshot, actions[Action.STOP])
        suction_visible = actions[Action.SUCTION_OK].visible
        self.suction_section.setVisible(suction_visible)
        self.suction_text.setVisible(suction_visible)
        waiting = snapshot.task.suction_step if snapshot.task and snapshot.task.suction_token else ''
        self.suction_text.setText(f'目前步驟：{waiting}' if waiting else '')
        self._sync_mode(snapshot)
        if self.scenario is not None and self.scenario.currentData() != scenario_key:
            self.scenario.setCurrentIndex(self.scenario.findData(scenario_key))
        if snapshot.feedback is None:
            self.feedback.setText('最後操作：無')
        else:
            detail = f'｜{snapshot.feedback.message}' if snapshot.feedback.message else ''
            self.feedback.setText(f'最後操作：{snapshot.feedback.action.value}｜{snapshot.feedback.phase}{detail}')

    def _update_stop(self, snapshot, state):
        self.stop.setEnabled(state.enabled)
        self.stop.setText('尚未接通' if snapshot.monitor_only else Action.STOP.value)
        self.stop_note.setText(_STOP_NOTE_MONITOR if snapshot.monitor_only else _STOP_NOTE)

    def _sync_mode(self, snapshot):
        self.mode.setEnabled(snapshot.phase is Phase.STOPPED and not snapshot.monitor_only)
        if self.mode.currentData() is not snapshot.mode:
            self.mode.blockSignals(True)
            self.mode.setCurrentIndex(self.mode.findData(snapshot.mode))
            self.mode.blockSignals(False)
