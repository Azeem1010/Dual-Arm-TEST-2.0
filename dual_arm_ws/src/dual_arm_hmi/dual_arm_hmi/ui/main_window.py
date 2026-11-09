"""Page layout, the refresh loop and action confirmation."""
from PyQt5.QtCore import QRect, Qt, QTimer
from PyQt5.QtGui import QKeySequence, QPainter
from PyQt5.QtWidgets import QHBoxLayout, QMainWindow, QMessageBox, QShortcut, QVBoxLayout, QWidget

from ..model.state import Action, Level, banner, camera_placeholder, evaluate_actions, status_cells
from . import theme
from .camera_panel import CameraPanel, GazeboPanel
from .control_panel import ControlPanel
from .event_log import EventLog
from .motor_panel import MotorPanel
from .task_panel import TaskPanel

REFRESH_MS = 100
WIDE_MIN_WIDTH = 1600
FULL_LOG_MIN_HEIGHT = 801
_LOG_HEIGHT = 136
_GAZEBO = 'gazebo'
# Tall enough for every motor row at full text height.
_TABLES_MIN_HEIGHT = 276

_CAMERAS = (('env', '環境相機', theme.NAVY), ('arm1', '手臂 1 相機', theme.ARM1), ('arm2', '手臂 2 相機', theme.ARM2))
_CONFIRM_TEXT = {
    Action.SHUTDOWN: ('關閉系統', '確定要關閉整個系統嗎？'),
    Action.TORQUE_ON: ('上扭力', '馬達將開始出力。\n請確認實體急停可用、手臂活動範圍內沒有人和物品。'),
    Action.SAFETY_RESET: ('解除鎖定', '解除後控制器會重新啟用。\n請確認鎖定原因已排除、現場安全。'),
    Action.RESET_SIMULATION: ('重置模擬', '將重啟模擬並清除目前任務紀錄。確定要重置嗎？'),
}


class StatusCellWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.cell = None

    def set_cell(self, cell):
        if cell != self.cell:
            self.cell = cell
            self.update()

    def paintEvent(self, _event):
        if self.cell is None:
            return
        painter = QPainter(self)
        background, foreground = theme.LEVEL_COLORS[self.cell.level]
        painter.fillRect(self.rect(), theme.color(background))
        painter.setPen(theme.color(foreground))
        painter.setFont(theme.sans(theme.SIZE_SMALL))
        painter.drawText(self.rect().adjusted(10, 4, -4, 0), Qt.AlignLeft | Qt.AlignTop, self.cell.title)
        painter.setFont(theme.sans(theme.SIZE_STATUS, bold=True))
        painter.drawText(self.rect().adjusted(10, 0, -4, -4), Qt.AlignLeft | Qt.AlignBottom, self.cell.value)


class BannerWidget(QWidget):
    def __init__(self, parent=None):
        super().__init__(parent)
        self.banner = None
        self.setFixedHeight(theme.BANNER_HEIGHT)

    def set_banner(self, value):
        if value != self.banner:
            self.banner = value
            self.setToolTip('' if value is None else f'{value.detail}\n{value.next_step}'.strip())
            self.update()

    def paintEvent(self, _event):
        if self.banner is None:
            return
        painter = QPainter(self)
        background, foreground = theme.LEVEL_COLORS[self.banner.level]
        painter.fillRect(self.rect(), theme.color(background))
        painter.setPen(theme.color(foreground))
        painter.setFont(theme.sans(theme.SIZE_BANNER, bold=True))
        title_width = painter.fontMetrics().horizontalAdvance(self.banner.title)
        painter.drawText(QRect(16, 0, title_width + 2, self.height()), Qt.AlignVCenter, self.banner.title)
        size = theme.SIZE_STATUS if self.width() >= WIDE_MIN_WIDTH else theme.SIZE_BODY + 2
        painter.setFont(theme.sans(size))
        parts = [part for part in (self.banner.detail, f'下一步：{self.banner.next_step}') if part]
        left = 16 + title_width + 24
        text = painter.fontMetrics().elidedText('　｜　'.join(parts), Qt.ElideRight, self.width() - left - 16)
        painter.drawText(QRect(left, 0, self.width() - left - 16, self.height()), Qt.AlignVCenter, text)


class MainWindow(QMainWindow):
    def __init__(self, source):
        super().__init__()
        self.source = source
        self.focused_camera = None
        self.log_expanded = False
        self.setWindowTitle('雙臂系統操作介面')
        self.setMinimumSize(theme.MIN_WIDTH, theme.MIN_HEIGHT)
        self._build()
        QShortcut(QKeySequence(Qt.Key_F12), self, context=Qt.ApplicationShortcut,
                  activated=lambda: self._send(Action.STOP))
        QShortcut(QKeySequence(Qt.Key_Escape), self, activated=self._leave_focus)
        self.timer = QTimer(self)
        self.timer.timeout.connect(self.refresh)
        self.timer.start(REFRESH_MS)
        self.refresh()

    def _build(self):
        page = QWidget(self)
        page.setObjectName('page')
        self.setCentralWidget(page)
        root = QVBoxLayout(page)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        self.status_cells = [StatusCellWidget(page) for _ in range(6)]
        status_bar = QWidget(page)
        status_bar.setFixedHeight(theme.STATUS_BAR_HEIGHT)
        status_layout = QHBoxLayout(status_bar)
        status_layout.setContentsMargins(0, 0, 0, 0)
        status_layout.setSpacing(2)
        for cell in self.status_cells:
            status_layout.addWidget(cell, 1)
        self.status_bar = status_bar
        root.addWidget(status_bar)
        self.banner = BannerWidget(page)
        root.addWidget(self.banner)

        body = QHBoxLayout()
        body.setContentsMargins(theme.GAP, theme.GAP, theme.GAP, theme.GAP)
        body.setSpacing(theme.GAP)
        root.addLayout(body, 1)
        left = QVBoxLayout()
        left.setSpacing(theme.GAP)
        body.addLayout(left, 1)

        self.camera_row = QWidget(page)
        cameras = QHBoxLayout(self.camera_row)
        cameras.setContentsMargins(0, 0, 0, 0)
        cameras.setSpacing(theme.GAP)
        self.cameras = {}
        for key, title, background in _CAMERAS:
            panel = CameraPanel(key, title, background, self.camera_row)
            panel.focus_toggled.connect(self._toggle_camera_focus)
            cameras.addWidget(panel, 1)
            self.cameras[key] = panel
        self.gazebo_panel = GazeboPanel(self.camera_row)
        self.gazebo_panel.close_requested.connect(self._toggle_gazebo)
        self.gazebo_panel.setVisible(False)
        cameras.addWidget(self.gazebo_panel, 1)
        left.addWidget(self.camera_row)

        self.tables = QWidget(page)
        tables = QHBoxLayout(self.tables)
        tables.setContentsMargins(0, 0, 0, 0)
        tables.setSpacing(theme.GAP)
        self.motor_panel = MotorPanel(self.tables)
        self.task_panel = TaskPanel(self.tables)
        tables.addWidget(self.motor_panel, 1)
        tables.addWidget(self.task_panel, 1)
        left.addWidget(self.tables, 1)

        self.event_log = EventLog(page)
        self.event_log.expand_toggled.connect(self._set_log_expanded)
        left.addWidget(self.event_log)

        self.control = ControlPanel(self.source.scenarios(), page)
        self.control.action_requested.connect(self._on_action)
        self.control.mode_selected.connect(self.source.select_mode)
        self.control.scenario_selected.connect(self.source.set_scenario)
        self.control.gazebo_toggled.connect(self._toggle_gazebo)
        body.addWidget(self.control)
        self._apply_layout()

    # --- layout ---

    def resizeEvent(self, event):
        super().resizeEvent(event)
        self._apply_layout()

    def _apply_layout(self):
        wide = self.width() >= WIDE_MIN_WIDTH
        full_log = self.height() >= FULL_LOG_MIN_HEIGHT
        rail = theme.RAIL_WIDTH if wide else theme.RAIL_WIDTH_COMPACT
        self.control.setFixedWidth(rail)
        self.control.set_compact_height(not full_log)
        self.motor_panel.set_compact(not wide)
        self.task_panel.set_compact(not full_log, wide)
        self.event_log.set_collapsible(not full_log)
        available = self.height() - theme.STATUS_BAR_HEIGHT - theme.BANNER_HEIGHT - 2 * theme.GAP

        if self.focused_camera is not None or self.log_expanded:
            self.camera_row.setMinimumHeight(0)
            self.camera_row.setMaximumHeight(16777215)
        else:
            width = (self.width() - rail - 3 * theme.GAP - 2 * theme.GAP) / 3
            wanted = int(width * 3 / 4) + theme.HEADER_HEIGHT
            log_height = _LOG_HEIGHT if full_log else self.event_log.collapsed_height()
            self.camera_row.setFixedHeight(min(wanted, available - log_height - 2 * theme.GAP - _TABLES_MIN_HEIGHT))

        focused = self.focused_camera is not None
        self.tables.setVisible(not focused and not self.log_expanded)
        self.camera_row.setVisible(not self.log_expanded)
        self.event_log.setVisible(not focused)
        for key, panel in self.cameras.items():
            panel.setVisible(not focused or key == self.focused_camera)
        self.gazebo_panel.setVisible(self.focused_camera == _GAZEBO)
        if self.log_expanded:
            self.event_log.setMinimumHeight(0)
            self.event_log.setMaximumHeight(16777215)
        else:
            self.event_log.setFixedHeight(_LOG_HEIGHT if full_log else self.event_log.collapsed_height())

    def _toggle_camera_focus(self, key):
        self.focused_camera = None if self.focused_camera == key else key
        self._apply_layout()

    def _toggle_gazebo(self):
        self._toggle_camera_focus(_GAZEBO)

    def _leave_focus(self):
        if self.focused_camera is not None:
            self.focused_camera = None
            self._apply_layout()

    def _set_log_expanded(self, expanded):
        self.log_expanded = expanded
        self._apply_layout()

    # --- refresh ---

    def refresh(self):
        snapshot = self.source.snapshot()
        actions = evaluate_actions(snapshot, self.control.tools_cleared.isChecked())
        for widget, cell in zip(self.status_cells, status_cells(snapshot)):
            widget.set_cell(cell)
        self.banner.set_banner(banner(snapshot))
        for key, panel in self.cameras.items():
            panel.set_status(snapshot.cameras.get(key))
            panel.set_frame(self.source.frame(key, panel.annotated), camera_placeholder(snapshot, key))
        showing_gazebo = self.focused_camera == _GAZEBO
        if showing_gazebo:
            self.gazebo_panel.set_frame(self.source.frame(self.gazebo_panel.current_view(), False), ('無 Gazebo 影像', Level.WARN))
        self.control.set_gazebo_state(bool(snapshot.gazebo_views), showing_gazebo)
        self.motor_panel.update_from(snapshot)
        self.task_panel.update_from(snapshot)
        self.event_log.set_events(snapshot.events)
        self.control.update_from(snapshot, actions, self.source.scenario())

    def closeEvent(self, event):
        self.timer.stop()
        self.source.close()
        super().closeEvent(event)

    # --- actions ---

    def _send(self, action):
        self.source.invoke(action)
        self.refresh()

    def _on_action(self, action):
        if action in _CONFIRM_TEXT and not self._confirm(action):
            return
        self._send(action)
        if action in (Action.GO_HOME, Action.RECOVER):
            self.control.tools_cleared.setChecked(False)

    def _confirm(self, action):
        title, text = _CONFIRM_TEXT[action]
        box = QMessageBox(QMessageBox.Warning, title, text, QMessageBox.Yes | QMessageBox.No, self)
        box.button(QMessageBox.Yes).setText('確定')
        box.button(QMessageBox.No).setText('取消')
        box.setDefaultButton(QMessageBox.No)
        return box.exec_() == QMessageBox.Yes
