"""Eight joints in one table: angles from ROS, AX-12A counts exactly as the CM-530 reported them."""
from PyQt5.QtCore import Qt
from PyQt5.QtWidgets import QGridLayout, QLabel, QVBoxLayout, QWidget

from ..model.joints import ARMS, EMPTY, JOINT_LABELS, JOINT_NAMES, joint_row
from ..model.state import Mode
from . import theme
from .widgets import Chip, HeaderBar, Panel

# (field, header, tooltip); the joint name is column 0 and the limit margin chip comes last.
_COLUMNS = (
    ('motor_id', 'ID', 'AX-12A 馬達 ID'),
    ('degrees', '實際°', '/joint_states 的關節角度'),
    ('target_degrees', '目標°', '控制器目前的目標角度'),
    ('error_degrees', '差°', '目標減實際'),
    ('raw', '實際計數', 'CM-530 READ 回傳的 Present Position（0–1023）'),
    ('raw_target', '目標計數', 'CM-530 已回 OK,AX 的目標位置（0–1023）'),
)
_HEADERS = ('關節',) + tuple(header for _, header, _ in _COLUMNS) + ('距限位°',)
_ID_COLUMN = 1
_MARGIN_COLUMN = len(_HEADERS) - 1
_EMPHASIS = {'degrees', 'raw'}
_NO_COUNTS = {
    'simulation': ('計數：模擬無', '模擬沒有 AX-12A，計數欄留空'),
    'waiting': ('計數：未收到', '還沒收到 CM-530 回報的計數，或資料已過期'),
    'live': ('計數：韌體回報', '實際計數來自 READ，目標計數來自已回 OK,AX 的命令'),
}


class MotorPanel(Panel):
    def __init__(self, parent=None):
        super().__init__(parent)
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)
        self.header = HeaderBar('馬達', theme.NAVY, self)
        self.counts_source = Chip(self.header)
        self.freshness = Chip(self.header)
        self.header.add_right(self.counts_source)
        self.header.add_right(self.freshness)
        layout.addWidget(self.header)

        self.table = QWidget(self)
        self.grid = QGridLayout(self.table)
        self.grid.setContentsMargins(8, 2, 8, 2)
        self.grid.setHorizontalSpacing(12)
        self.grid.setVerticalSpacing(0)
        layout.addWidget(self.table, 1)
        self.rows = {}
        self._column_widgets = {_ID_COLUMN: []}
        self._build_table()

    def _build_table(self):
        tips = ('',) + tuple(tip for _, _, tip in _COLUMNS) + ('離 URDF 關節限位的最小角度',)
        for column, (text, tip) in enumerate(zip(_HEADERS, tips)):
            label = QLabel(text, self.table)
            label.setProperty('muted', True)
            label.setToolTip(tip)
            self.grid.addWidget(label, 0, column, Qt.AlignVCenter | (Qt.AlignLeft if column == 0 else Qt.AlignRight))
            if column in self._column_widgets:
                self._column_widgets[column].append(label)
        row = 1
        for arm_index, arm in enumerate(ARMS):
            title = QLabel(f'Arm {arm_index + 1}', self.table)
            title.setStyleSheet(f'background: {theme.ARM_COLORS[arm]}; color: #FFFFFF; font-weight: bold; padding: 0 8px;')
            title.setFixedHeight(22)
            self.grid.addWidget(title, row, 0, 1, len(_HEADERS))
            row += 1
            for joint_index, label in enumerate(JOINT_LABELS):
                self._add_joint(JOINT_NAMES[arm_index * 4 + joint_index], label, row)
                row += 1
        self.grid.setColumnStretch(0, 1)
        for index in range(row):
            self.grid.setRowMinimumHeight(index, 24)

    def _add_joint(self, name, text, row):
        name_label = QLabel(text, self.table)
        self.grid.addWidget(name_label, row, 0)
        cells = {}
        for column, (field, _, _) in enumerate(_COLUMNS, start=1):
            cell = QLabel(EMPTY, self.table)
            cell.setFont(theme.mono(theme.SIZE_TITLE if field in _EMPHASIS else theme.SIZE_BODY, bold=field in _EMPHASIS))
            cell.setAlignment(Qt.AlignRight | Qt.AlignVCenter)
            cell.setProperty('base', '')
            self.grid.addWidget(cell, row, column)
            cells[field] = cell
            if column in self._column_widgets:
                self._column_widgets[column].append(cell)
        margin = Chip(self.table)
        margin.setFont(theme.mono(theme.SIZE_SMALL))
        margin.setMinimumWidth(52)
        self.grid.addWidget(margin, row, _MARGIN_COLUMN, Qt.AlignRight | Qt.AlignVCenter)
        self.rows[name] = (name_label, cells, margin)

    def set_compact(self, compact):
        for widget in self._column_widgets[_ID_COLUMN]:
            widget.setVisible(not compact)

    @staticmethod
    def _paint(cell, text, alert=None):
        """alert is None, 'warn' or 'danger'; the style is only rewritten when it changes."""
        cell.setText(text)
        style = {'warn': f'background: {theme.WARN}; color: #000000;',
                 'danger': f'background: {theme.DANGER}; color: #FFFFFF;'}.get(alert, '')
        if cell.property('base') != style:
            cell.setProperty('base', style)
            cell.setStyleSheet(style)

    def _update_counts_source(self, snapshot, samples):
        if snapshot.mode is Mode.SIMULATION:
            key = 'simulation'
        elif any(sample.raw is not None for sample in samples.values()):
            key = 'live'
        else:
            key = 'waiting'
        text, tip = _NO_COUNTS[key]
        colors = {'live': (theme.OK, '#FFFFFF'), 'waiting': (theme.WARN, '#000000')}.get(key, (theme.DISABLED_BG, theme.TEXT))
        self.counts_source.set_chip(text, *colors)
        self.counts_source.setToolTip(tip)

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
        self._update_counts_source(snapshot, samples)
        for name, (name_label, cells, margin) in self.rows.items():
            sample = samples.get(name)
            if sample is None:
                for cell in cells.values():
                    self._paint(cell, EMPTY)
                margin.set_chip(EMPTY, theme.PANEL, theme.TEXT_MUTED)
                name_label.setToolTip('')
                continue
            row = joint_row(sample)
            # Stale data is greyed out by the disabled table and never coloured as if it were current.
            live = not stale
            alerts = {'error_degrees': 'warn' if live and row.large_error else None,
                      'raw': 'danger' if live and row.raw_outside else None,
                      'raw_target': 'danger' if live and row.raw_target_outside else None}
            for field, cell in cells.items():
                self._paint(cell, getattr(row, field), alerts.get(field))
            name_label.setToolTip(row.detail)
            if row.near_limit and live:
                margin.set_chip(row.margin, theme.WARN, '#000000')
            else:
                margin.set_chip(row.margin, theme.PANEL, theme.TEXT_MUTED if stale or row.margin == EMPTY else theme.TEXT)
