"""What the operator sees and may do. Free of ROS and Qt so the rules can be unit tested."""
from dataclasses import dataclass, field, replace
from enum import Enum
import re
from typing import Dict, FrozenSet, List, Optional, Tuple

from .joints import JointSample

CAMERA_STALE_S = 1.0
JOINT_STALE_S = 1.0
HARDWARE_MOTION_BLOCKED = '實機自動搬運尚未開放'

_NEEDS_RECOVERY = ('FAULT', 'FULL')
_CAN_START = ('IDLE', 'SUCCEEDED')

# Reasons as published by safety_monitor.py.
_SAFETY_REASON_TEXT = {
    'Emergency stop is asserted': '急停已觸發',
    'Emergency-stop heartbeat has not been received': '尚未收到急停心跳',
    'Emergency-stop heartbeat is stale': '急停心跳逾時',
    'Coordinator stopped responding': '任務節點沒有回應',
    'Operator software stop': '操作員按下強制停止',
}


GAZEBO_VIEWS = (('view_isometric', '等角'), ('view_top', '俯視'), ('view_front', '正面'), ('view_side', '側面'))


class Mode(Enum):
    UNKNOWN = '未知'
    MOCK = 'Mock'
    SIMULATION = '模擬'
    MOCK_SERIAL = 'Mock Serial'
    HARDWARE_READ_ONLY = '實機唯讀'
    HARDWARE_MOTION = '實機動作'

    @property
    def is_hardware(self):
        return self in (Mode.HARDWARE_READ_ONLY, Mode.HARDWARE_MOTION)

    @property
    def has_torque_step(self):
        return self in (Mode.MOCK_SERIAL, Mode.HARDWARE_READ_ONLY, Mode.HARDWARE_MOTION)


class Phase(Enum):
    STOPPED = '未啟動'
    STOPPING = '關閉中'
    STARTING = '啟動中'
    READ_ONLY = '唯讀就緒'
    TORQUE_ON = '已上扭力'
    READY = '就緒'


class Level(Enum):
    NEUTRAL = 'neutral'
    STRUCTURE = 'structure'
    OK = 'ok'
    BUSY = 'busy'
    WARN = 'warn'
    DANGER = 'danger'
    HARDWARE = 'hardware'
    INFO = 'info'


class Action(Enum):
    STOP = '強制停止'
    START_SYSTEM = '啟動系統'
    SHUTDOWN = '關閉系統'
    TORQUE_ON = '上扭力'
    SAFETY_RESET = '解除鎖定'
    RESET_SIMULATION = '重置模擬'
    START_TASK = '開始工作'
    CANCEL_TASK = '取消任務'
    GO_HOME = '回 HOME'
    RECOVER = '復歸'
    SUCTION_OK = '吸取成功'
    SUCTION_FAILED = '吸取失敗'


@dataclass(frozen=True)
class ActionState:
    enabled: bool
    reason: str = ''
    visible: bool = True


@dataclass(frozen=True)
class TaskStatus:
    """Mirrors the JSON on /dual_arm/status."""
    state: str = 'IDLE'
    active_arm: str = ''
    holding: Tuple[Tuple[str, str], ...] = (('arm1', 'empty'), ('arm2', 'empty'))
    b_owner: str = ''
    occupied: Tuple[bool, ...] = (False,) * 8
    slot: int = 0
    completed: int = 0
    message: str = ''
    busy: bool = False
    recovery_token: str = ''
    suction_step: str = ''
    suction_token: str = ''
    # (arm, True/False/None); None when the coordinator has no fresh joint state.
    at_home: Tuple[Tuple[str, Optional[bool]], ...] = ()

    @property
    def both_at_home(self):
        homes = dict(self.at_home)
        return all(homes.get(arm) is True for arm in ('arm1', 'arm2'))

    def held_by(self, arm):
        return dict(self.holding).get(arm, 'empty')


@dataclass(frozen=True)
class SafetyStatus:
    """Mirrors /safety/status, plus what still stops a reset from succeeding."""
    latched: bool = False
    reason: str = ''
    controllers_stopped: bool = False
    blocking_problem: str = ''


@dataclass(frozen=True)
class CameraStatus:
    fps: float = 0.0
    age_s: Optional[float] = None
    calibration: str = 'NOT_RUN'
    has_annotation: bool = True
    stale_after_s: float = CAMERA_STALE_S
    # Arm cameras take turns (USB bandwidth): '' = not rotated, else on / off / switching / error.
    rotation: str = ''

    @property
    def has_signal(self):
        return self.age_s is not None and self.age_s <= self.stale_after_s


@dataclass(frozen=True)
class ZoneView:
    a_has_object: bool = False
    b_has_object: bool = False
    b_arm_clear: bool = True
    c_count: int = 0


@dataclass(frozen=True)
class InterlockCell:
    state: str
    level: Level
    may_enter: bool = False
    owned: bool = False
    gate_unknown: bool = False


@dataclass(frozen=True)
class InterlockView:
    center: str
    center_level: Level
    arm1: InterlockCell
    arm2: InterlockCell
    owner: str = ''


@dataclass(frozen=True)
class EventRecord:
    time_text: str
    level: Level
    message: str
    # Wall-clock seconds, so events from the interface and from ROS can be merged in order.
    stamp: float = 0.0


@dataclass(frozen=True)
class CommandFeedback:
    action: Action
    phase: str
    message: str = ''


@dataclass(frozen=True)
class Snapshot:
    mode: Mode = Mode.SIMULATION
    phase: Phase = Phase.STOPPED
    ros_connected: bool = False
    is_fake: bool = False
    monitor_only: bool = False
    # None means every action is carried out; otherwise only these are.
    wired_actions: Optional[FrozenSet['Action']] = None
    launch_managed: bool = True
    launch_problem: str = ''
    launch_warning: str = ''
    cycles: int = 1
    task: Optional[TaskStatus] = None
    safety: Optional[SafetyStatus] = None
    controllers_active: bool = False
    decision_source: str = ''
    joints: Tuple[JointSample, ...] = ()
    joint_age_s: Optional[float] = None
    cameras: Dict[str, CameraStatus] = field(default_factory=dict)
    zones: Optional[ZoneView] = None
    # False when the task decides zones from another source than the one displayed.
    zones_authoritative: bool = True
    wrong_slots: Tuple[int, ...] = ()
    gazebo_views: Dict[str, CameraStatus] = field(default_factory=dict)
    calibration_pass: bool = False
    # Fail closed: a data source must clear this explicitly for automatic transfer on hardware.
    hardware_blocked_reason: str = HARDWARE_MOTION_BLOCKED
    arms_at_home: bool = True
    residual_processes: bool = False
    events: Tuple[EventRecord, ...] = ()
    feedback: Optional[CommandFeedback] = None

    @property
    def joints_stale(self):
        return self.joint_age_s is None or self.joint_age_s > JOINT_STALE_S

    @property
    def latched(self):
        return self.safety is not None and self.safety.latched

    @property
    def busy(self):
        return self.task is not None and self.task.busy


@dataclass(frozen=True)
class StatusCell:
    title: str
    value: str
    level: Level


@dataclass(frozen=True)
class Banner:
    level: Level
    title: str
    detail: str
    next_step: str


def safety_reason_text(reason):
    return _SAFETY_REASON_TEXT.get(reason, reason)


def _arm_entry(arm, zones):
    """Whether this arm's next step in B is allowed, from the conditions in arm1/arm2_workflow.py."""
    if arm == 'arm1':
        return InterlockCell('等待取走', Level.NEUTRAL) if zones.b_has_object else InterlockCell('可進入', Level.OK, may_enter=True)
    return InterlockCell('可進入', Level.OK, may_enter=True) if zones.b_has_object else InterlockCell('等待物件', Level.NEUTRAL)


def b_interlock(s):
    """Who may enter zone B, following ZoneManager: one owner, clear to acquire, faulted until recovery."""
    unknown = InterlockCell('—', Level.NEUTRAL)
    if s.task is None:
        return InterlockView('—', Level.NEUTRAL, unknown, unknown)
    owner, faulted = s.task.b_owner, s.task.state == 'FAULT'
    if owner:
        cells = {arm: InterlockCell('佔用中', Level.DANGER if faulted else Level.STRUCTURE, may_enter=not faulted, owned=not faulted)
                 if arm == owner else InterlockCell('禁止進入', Level.NEUTRAL) for arm in ('arm1', 'arm2')}
        if faulted:
            return InterlockView('故障鎖定', Level.DANGER, cells['arm1'], cells['arm2'])
        return InterlockView(f'{owner.capitalize()} 佔用', Level.STRUCTURE, cells['arm1'], cells['arm2'], owner=owner)
    closed = InterlockCell('禁止進入', Level.NEUTRAL)
    if s.latched or faulted:
        return InterlockView('暫停', Level.NEUTRAL, closed, closed)
    if not s.zones_authoritative:
        # The task decides from another source, so the displayed zones must not grant entry here.
        undecided = InterlockCell('真值判定', Level.NEUTRAL, gate_unknown=True)
        return InterlockView('未佔用', Level.NEUTRAL, undecided, undecided)
    if s.zones is None:
        return InterlockView('無觀測', Level.NEUTRAL, closed, closed)
    if not s.zones.b_arm_clear:
        return InterlockView('手臂未離開', Level.WARN, closed, closed)
    return InterlockView('可預約', Level.OK, _arm_entry('arm1', s.zones), _arm_entry('arm2', s.zones))


def camera_placeholder(s, name):
    """Text and level for a camera without a current image. Only a lost camera is a warning."""
    if s.phase is Phase.STOPPED:
        return '未啟動', Level.NEUTRAL
    if s.phase is Phase.STARTING:
        return '等待影像', Level.NEUTRAL
    if name not in s.cameras:
        return '此模式沒有相機', Level.NEUTRAL
    rotation = s.cameras[name].rotation
    if rotation == 'off':
        return '輪流中，鏡頭關閉', Level.NEUTRAL
    if rotation == 'switching':
        return '切換中', Level.NEUTRAL
    if rotation == 'error':
        return '鏡頭切換失敗', Level.WARN
    return '無訊號', Level.WARN


def calibration_label(status):
    """Chip text: rotated arm cameras only monitor and are never calibrated."""
    if status is not None and status.rotation:
        return '僅監控'
    return f'校正 {"NOT_RUN" if status is None else status.calibration}'


def next_slot(task):
    """The slot the current or next transfer goes to, or 0 when C is full."""
    if task.slot:
        return task.slot
    return next((index + 1 for index, filled in enumerate(task.occupied) if not filled), 0)


def _refuse(reason, visible=True):
    return ActionState(False, reason, visible)


def _start_task_state(s):
    if s.mode.is_hardware and s.hardware_blocked_reason:
        return _refuse(s.hardware_blocked_reason)
    if s.task is None:
        return _refuse('任務節點未啟動')
    if s.phase is not Phase.READY:
        return _refuse('系統尚未就緒')
    if s.latched:
        return _refuse('安全鎖定中')
    if s.task.busy:
        return _refuse('任務執行中')
    if s.task.state == 'FAULT':
        return _refuse('請先完成復歸')
    if s.task.state == 'FULL':
        return _refuse('C 區已滿，請先復歸')
    if s.task.state not in _CAN_START:
        return _refuse(f'任務狀態為 {s.task.state}')
    if not s.controllers_active:
        return _refuse('控制器未啟用')
    return ActionState(True)


def _shutdown_state(s):
    if s.phase is Phase.STOPPED:
        return _refuse('系統未啟動')
    if s.phase is Phase.STOPPING:
        return _refuse('正在關閉')
    if not s.launch_managed:
        return _refuse('系統不是由介面啟動，請在原終端機關閉')
    if s.busy:
        return _refuse('任務執行中，請先停止')
    return ActionState(True)


def _torque_state(s):
    visible = s.mode.has_torque_step
    if s.mode is Mode.HARDWARE_READ_ONLY:
        return _refuse('唯讀模式不能上扭力', visible)
    if s.phase is not Phase.READ_ONLY:
        return _refuse('需在唯讀就緒時操作', visible)
    if not s.calibration_pass:
        return _refuse('馬達校正尚未通過', visible)
    return ActionState(True, visible=visible)


def _safety_reset_state(s):
    if s.phase is Phase.STOPPED:
        return _refuse('系統未啟動')
    if s.safety is None:
        return _refuse('此模式沒有安全監控')
    if not s.safety.latched:
        return _refuse('目前沒有鎖定')
    if s.safety.blocking_problem:
        return _refuse('原因尚未排除')
    return ActionState(True)


def _reset_simulation_state(s):
    visible = s.mode is Mode.SIMULATION
    if s.phase in (Phase.STOPPED, Phase.STOPPING):
        return _refuse('系統未啟動', visible)
    if not s.launch_managed:
        return _refuse('系統不是由介面啟動', visible)
    if s.busy:
        return _refuse('任務執行中，請先停止', visible)
    return ActionState(True, visible=visible)


def _go_home_state(s, tools_cleared):
    if s.mode.is_hardware:
        return _refuse('實機需等 H5 通過')
    if s.task is None:
        return _refuse('任務節點未啟動')
    if s.task.busy:
        return _refuse('任務執行中')
    if s.latched:
        return _refuse('請先解除鎖定')
    if s.arms_at_home:
        return _refuse('兩臂已在 HOME')
    if not tools_cleared:
        return _refuse('請先勾選已清空')
    return ActionState(True)


def _recover_state(s, tools_cleared):
    if s.task is None:
        return _refuse('任務節點未啟動')
    if s.task.state not in _NEEDS_RECOVERY:
        return _refuse('目前不需要復歸')
    if s.task.busy:
        return _refuse('任務執行中')
    if s.latched:
        return _refuse('請先解除鎖定')
    if not s.arms_at_home:
        return _refuse('兩臂需先回 HOME')
    if not tools_cleared:
        return _refuse('請先勾選已清空')
    return ActionState(True)


def is_wired(s, action):
    """Whether the data source actually carries out this action."""
    if s.monitor_only:
        return False
    return s.wired_actions is None or action in s.wired_actions


def _start_system_state(s):
    if s.phase is Phase.STOPPING:
        return _refuse('系統正在關閉')
    if s.phase is not Phase.STOPPED:
        return _refuse('系統已啟動')
    if s.residual_processes:
        return _refuse('有殘留的 Gazebo 程序')
    return ActionState(True)


def evaluate_actions(s, tools_cleared=False):
    """Every action with whether it may be pressed now and, if not, why."""
    has_token = s.task is not None and bool(s.task.suction_token)
    suction_visible = has_token or s.mode.is_hardware
    suction = ActionState(True) if has_token else _refuse('沒有等待確認的步驟', suction_visible)
    states = {
        Action.STOP: ActionState(True),
        Action.START_SYSTEM: _start_system_state(s),
        Action.SHUTDOWN: _shutdown_state(s),
        Action.TORQUE_ON: _torque_state(s),
        Action.SAFETY_RESET: _safety_reset_state(s),
        Action.RESET_SIMULATION: _reset_simulation_state(s),
        Action.START_TASK: _start_task_state(s),
        Action.CANCEL_TASK: ActionState(True) if s.busy else _refuse('沒有執行中的任務'),
        Action.GO_HOME: _go_home_state(s, tools_cleared),
        Action.RECOVER: _recover_state(s, tools_cleared),
        Action.SUCTION_OK: suction,
        Action.SUCTION_FAILED: suction,
    }
    # A control that looks usable but does nothing would be worse than none, the stop button above all.
    reason = '唯讀監看，尚未接通' if s.monitor_only else '尚未接通'
    return {action: state if is_wired(s, action) else _refuse(reason, state.visible) for action, state in states.items()}


def _expect_no_contact(s):
    """Phases in which missing ROS data is normal rather than a failure."""
    return s.phase in (Phase.STOPPED, Phase.STARTING, Phase.STOPPING)


def _ros_cell(s):
    if s.ros_connected:
        return StatusCell('ROS', '正常', Level.OK)
    if _expect_no_contact(s):
        return StatusCell('ROS', '未連線', Level.NEUTRAL)
    return StatusCell('ROS', '中斷', Level.DANGER)


def _system_cell(s):
    if s.launch_problem:
        return StatusCell('系統', '啟動失敗', Level.DANGER)
    if not _expect_no_contact(s) and not s.ros_connected:
        # The last known phase must not stay green after contact is lost.
        return StatusCell('系統', '狀態未知', Level.WARN)
    levels = {Phase.STOPPED: Level.NEUTRAL, Phase.STARTING: Level.BUSY, Phase.STOPPING: Level.BUSY,
              Phase.READ_ONLY: Level.OK, Phase.TORQUE_ON: Level.WARN, Phase.READY: Level.OK}
    return StatusCell('系統', s.phase.value, levels[s.phase])


def _safety_cell(s):
    if s.safety is None:
        if _expect_no_contact(s) or not s.ros_connected:
            return StatusCell('安全', '—', Level.NEUTRAL)
        return StatusCell('安全', '無監控', Level.WARN)
    return StatusCell('安全', '鎖定', Level.DANGER) if s.safety.latched else StatusCell('安全', '正常', Level.OK)


def _task_cell(s):
    if s.task is None:
        return StatusCell('任務', '—', Level.NEUTRAL)
    if s.task.suction_token:
        return StatusCell('任務', '等待確認', Level.WARN)
    if s.task.busy:
        return StatusCell('任務', '工作中', Level.BUSY)
    known = {'IDLE': ('待命', Level.OK), 'SUCCEEDED': ('完成', Level.OK),
             'FAULT': ('故障', Level.DANGER), 'FULL': ('C 區已滿', Level.WARN)}
    value, level = known.get(s.task.state, (s.task.state, Level.NEUTRAL))
    return StatusCell('任務', value, level)


def status_cells(s):
    mode_title = '模式（假資料）' if s.is_fake else '模式（唯讀監看）' if s.monitor_only else '模式'
    source = {'truth': 'Gazebo 真值', 'vision_pick': '視覺取料'}.get(s.decision_source, '—')
    return [StatusCell(mode_title, s.mode.value, Level.HARDWARE if s.mode.is_hardware else Level.STRUCTURE),
            _ros_cell(s), _system_cell(s), _safety_cell(s), _task_cell(s),
            StatusCell('決策來源', source, Level.STRUCTURE)]


def _idle_banner(s):
    if s.phase is Phase.STOPPED:
        return Banner(Level.INFO, '系統未啟動', '', '選擇模式後按「啟動系統」')
    if s.phase is Phase.STARTING:
        return Banner(Level.INFO, '系統啟動中', '', '等待控制器與相機就緒')
    if s.phase is Phase.STOPPING:
        return Banner(Level.INFO, '系統關閉中', '', '等待所有程序結束')
    if s.phase is Phase.READ_ONLY:
        return Banner(Level.INFO, '唯讀就緒', '馬達未出力', '確認實體急停可用後才上扭力')
    if s.busy:
        return Banner(Level.INFO, '任務執行中', '', '需要停止時按「強制停止」')
    return Banner(Level.INFO, '就緒', '', '可以按「開始工作」')


def _attention_banner(s):
    if s.latched:
        problem = s.safety.blocking_problem
        next_step = f'先排除：{safety_reason_text(problem)}' if problem else '確認現場安全後按「解除鎖定」'
        return Banner(Level.DANGER, '安全鎖定', safety_reason_text(s.safety.reason), next_step)
    if s.launch_problem:
        return Banner(Level.DANGER, '系統啟動失敗', s.launch_problem, '查看紀錄檔後重新按「啟動系統」')
    if not _expect_no_contact(s) and not s.ros_connected:
        return Banner(Level.DANGER, 'ROS 連線中斷', '', '畫面資料已失效，請檢查系統')
    if s.launch_warning:
        return Banner(Level.WARN, '啟動時間過長', s.launch_warning, '查看紀錄檔，必要時關閉後重新啟動')
    if s.task is not None and s.task.state == 'FAULT':
        next_step = '清空吸盤與 B 區，勾選後按「回 HOME」' if not s.arms_at_home else '清空吸盤與 B 區，勾選後按「復歸」'
        if s.mode is Mode.SIMULATION and any(value != 'empty' for _, value in s.task.holding):
            # Nobody can take an object off a simulated suction cup; the coordinator refuses HOME then.
            next_step = '模擬中無法取下吸盤上的物件，請按「重置模擬」'
        return Banner(Level.DANGER, '任務故障', s.task.message, next_step)
    if s.task is not None and s.task.suction_token:
        return Banner(Level.WARN, '等待吸盤確認', s.task.suction_step, '確認實際結果後按成功或失敗')
    if s.task is not None and s.task.state == 'FULL':
        return Banner(Level.WARN, 'C 區已滿', '', '取走 C 區物件後勾選並按「復歸」')
    if _expect_no_contact(s):
        return None
    if s.joints_stale:
        return Banner(Level.WARN, '馬達資料過期', '數值不是即時資料', '檢查 /joint_states 與控制器')
    lost = [name for name, camera in s.cameras.items()
            if not camera.has_signal and camera.rotation not in ('off', 'switching')]
    if lost:
        return Banner(Level.WARN, '相機無訊號', '、'.join(lost), '檢查相機連線')
    if s.mode.is_hardware and s.phase is Phase.READY and s.hardware_blocked_reason:
        return Banner(Level.WARN, '實機 BLOCKED', s.hardware_blocked_reason, '需先完成 H6 前置條件')
    return None


_BUTTON_NAME = re.compile('「(.+?)」')
_ACTION_BY_LABEL = {action.value: action for action in Action}


def _without_unwired_buttons(s, result):
    """Never tell the operator to press a button that does nothing."""
    names = _BUTTON_NAME.findall(result.next_step)
    if any(name in _ACTION_BY_LABEL and not is_wired(s, _ACTION_BY_LABEL[name]) for name in names):
        return replace(result, next_step='這個操作尚未接通，請用終端機處理')
    return result


def banner(s):
    """The single most important thing the operator should know, and what to do next."""
    attention = _attention_banner(s)
    result = attention or _idle_banner(s)
    if attention is None and not is_wired(s, Action.STOP) and s.phase in (Phase.READY, Phase.READ_ONLY, Phase.TORQUE_ON):
        detail = '唯讀監看' if s.monitor_only else '強制停止尚未接通'
        result = (Banner(Level.INFO, '任務執行中', detail, '需要停止時請按實體急停或用終端機') if s.busy
                  else Banner(Level.INFO, '監看中', detail, '任務操作請用終端機'))
    return _without_unwired_buttons(s, result)
