"""Demonstration data for building and reviewing the interface without ROS or hardware.

Every value here is invented. Nothing from this module may be used as a measurement.
"""
from dataclasses import replace
import math
import time

import cv2
import numpy as np

from ..model.joints import JOINT_NAMES, RADIANS_PER_COUNT, JointSample
from ..model.state import (GAZEBO_VIEWS, Action, CameraStatus, CommandFeedback, EventRecord, Level, Mode, Phase,
                           SafetyStatus, Snapshot, TaskStatus, ZoneView)
from .base import DataSource

CAMERAS = ('env', 'arm1', 'arm2')
_SUPERVISOR_MISSING_HEARTBEAT = 'Emergency-stop heartbeat has not been received'

WORK_SEQUENCE = (
    'STARTING', 'ARM1:INITIAL_HOME', 'ARM2:INITIAL_HOME', 'ARM1:CHECK_ZONES', 'ARM1:QUERY_TARGET', 'ARM1:PREFLIGHT',
    'ARM1:APPROACH_A', 'ARM1:DESCEND_A', 'ARM1:GRASP_A', 'ARM1:ATTACH', 'ARM1:LIFT_A', 'ARM1:HOME_HOLDING',
    'ARM1:RESERVE_B', 'ARM1:APPROACH_B', 'ARM1:DESCEND_B', 'ARM1:RELEASE_B', 'ARM1:DETACH', 'ARM1:LIFT_B',
    'ARM1:HOME_EMPTY', 'ARM1:VERIFY_B', 'ARM2:CHECK_ZONES', 'ARM2:RESERVE_SLOT', 'ARM2:PREFLIGHT', 'ARM2:RESERVE_B',
    'ARM2:APPROACH_B', 'ARM2:DESCEND_B', 'ARM2:GRASP_B', 'ARM2:ATTACH', 'ARM2:LIFT_B', 'ARM2:HOME_HOLDING',
    'ARM2:VERIFY_B_EMPTY', 'ARM2:APPROACH_C', 'ARM2:DESCEND_C', 'ARM2:RELEASE_C', 'ARM2:DETACH', 'ARM2:LIFT_C',
    'ARM2:HOME_EMPTY', 'ARM2:VERIFY_C',
)
STEP_PERIOD_S = 1.2

_PREFILLED = (True, True) + (False,) * 6
_HOME_POSE = (0.10, -0.60, 0.95, 0.40, -0.10, -0.60, 0.95, 1.44)
# Demonstration counts around the v17 board HOME (arm_config.h home_A / home_C).
_HOME_RAW = (90, 567, 712, 825, 590, 567, 712, 825)
_DEMO_RAW_SPAN = 200
_READY_ZONES = ZoneView(a_has_object=True, b_has_object=False, b_arm_clear=True, c_count=2)
_CAL_PASS = {name: CameraStatus(fps=15.0, age_s=0.04, calibration='PASS') for name in CAMERAS}
_CAL_FAIL = {name: CameraStatus(fps=15.0, age_s=0.04, calibration='FAIL') for name in CAMERAS}


def _event(clock_text, level, message):
    return EventRecord(clock_text, level, message)


_READY = dict(mode=Mode.SIMULATION, phase=Phase.READY, ros_connected=True, task=TaskStatus(occupied=_PREFILLED),
              safety=SafetyStatus(), controllers_active=True, decision_source='truth', cameras=_CAL_PASS,
              zones=_READY_ZONES, joint_age_s=0.02,
              events=(_event('10:21:05', Level.OK, '控制器已全部啟用，系統就緒'),
                      _event('10:21:02', Level.NEUTRAL, '視覺節點已連線')))

_SCENARIOS = {
    'stopped': ('未啟動', dict(phase=Phase.STOPPED, joint_age_s=None, events=())),
    'starting': ('啟動中', dict(phase=Phase.STARTING, ros_connected=True, joint_age_s=None,
                             cameras={name: CameraStatus() for name in CAMERAS},
                             events=(_event('10:20:48', Level.NEUTRAL, '啟動模式：模擬'),))),
    'ready': ('就緒', _READY),
    'working': ('工作中', {**_READY, 'task': TaskStatus(busy=True, occupied=_PREFILLED, state='STARTING'),
                        'events': (_event('10:22:10', Level.BUSY, '任務開始'),) + _READY['events']}),
    'suction': ('等待吸盤確認', {
        **_READY, 'mode': Mode.HARDWARE_MOTION, 'hardware_blocked_reason': '', 'decision_source': 'vision_pick',
        'calibration_pass': True, 'task': TaskStatus(busy=True, state='ARM1:ATTACH', active_arm='arm1', suction_token='demo',
                                                     suction_step='arm1 吸取 A 區瓶蓋', occupied=_PREFILLED),
        'events': (_event('10:24:31', Level.WARN, '等待操作員確認吸盤結果'),) + _READY['events']}),
    'fault': ('取消後故障', {
        **_READY, 'arms_at_home': False,
        'task': TaskStatus(state='FAULT', message='Task canceled', recovery_token='demo', b_owner='arm1', slot=3,
                           holding=(('arm1', 'cap_3'), ('arm2', 'empty')), occupied=_PREFILLED),
        'events': (_event('10:25:12', Level.DANGER, '任務故障：Task canceled'),
                   _event('10:25:11', Level.WARN, '操作員取消任務'),) + _READY['events']}),
    'latched': ('安全鎖定', {
        **_READY, 'controllers_active': False, 'arms_at_home': False,
        'safety': SafetyStatus(latched=True, reason='Operator software stop', controllers_stopped=True),
        'task': TaskStatus(state='FAULT', message='Task canceled', recovery_token='demo', holding=(('arm1', 'cap_3'), ('arm2', 'empty')),
                           occupied=_PREFILLED),
        'events': (_event('10:26:40', Level.DANGER, '強制停止：控制器已確認停用'),
                   _event('10:26:40', Level.DANGER, '操作員按下強制停止'),) + _READY['events']}),
    'full': ('C 區已滿', {
        **_READY, 'zones': ZoneView(a_has_object=False, c_count=8),
        'task': TaskStatus(state='FULL', occupied=(True,) * 8, completed=6, recovery_token='demo'),
        'events': (_event('10:40:02', Level.WARN, 'C 區已滿'),) + _READY['events']}),
    'hw_read_only': ('實機唯讀', dict(
        mode=Mode.HARDWARE_READ_ONLY, phase=Phase.READ_ONLY, ros_connected=True, cameras=_CAL_FAIL, joint_age_s=0.03,
        events=(_event('09:58:13', Level.NEUTRAL, '馬達未出力，唯讀模式'),))),
    'hw_blocked': ('實機 BLOCKED', dict(
        mode=Mode.HARDWARE_MOTION, phase=Phase.READY, ros_connected=True, safety=SafetyStatus(), controllers_active=True,
        cameras=_CAL_FAIL, joint_age_s=0.03, calibration_pass=True,
        events=(_event('10:02:44', Level.WARN, '任務節點拒絕實機模式'),))),
    'no_signal': ('相機無訊號', {
        **_READY, 'cameras': {'env': CameraStatus(fps=0.0, age_s=3.2, calibration='PASS'), 'arm1': CameraStatus(calibration='PASS'),
                              'arm2': _CAL_PASS['arm2']},
        'events': (_event('10:30:51', Level.WARN, '環境相機超過 1 秒沒有更新'),) + _READY['events']}),
    'stale': ('資料過期', {
        **_READY, 'joint_age_s': 4.0,
        'events': (_event('10:33:20', Level.WARN, '/joint_states 超過 1 秒沒有更新'),) + _READY['events']}),
}


class FakeSource(DataSource):
    def __init__(self, scenario='ready', clock=time.monotonic):
        self._clock = clock
        self._selected_mode = Mode.SIMULATION
        self._last = None
        self.set_scenario(scenario)

    # --- scenarios ---

    def scenarios(self):
        return tuple((key, value[0]) for key, value in _SCENARIOS.items())

    def scenario(self):
        return self._scenario

    def set_scenario(self, key):
        self._pending, self._log, self._feedback = [], [], None
        self._enter(key)

    def _enter(self, key, **changes):
        self._scenario = key
        self._state = {**_SCENARIOS[key][1], **changes}
        self._entered_at = self._clock()
        self._selected_mode = self._state.get('mode', self._selected_mode)
        # The real coordinator passes through a step before FAULT; the display remembers that step.
        self._lead_in = 'ARM1:DESCEND_B' if key in ('fault', 'latched') else ''

    # --- commands ---

    def select_mode(self, mode):
        self._selected_mode = mode
        if self._state.get('phase') is Phase.STOPPED:
            self._state = {**self._state, 'mode': mode}

    def invoke(self, action, cleared=False):
        now = self._clock()
        self._feedback = CommandFeedback(action, '已送出')
        self._note(Level.NEUTRAL, f'操作：{action.value}')
        self._pending.append((now + 0.3, lambda: self._accept(action)))

    def _accept(self, action):
        self._feedback = CommandFeedback(action, '已接受', '等待系統回報結果')
        self._apply(action)
        self._pending.append((self._clock() + 0.5, lambda: self._finish(action)))

    def _finish(self, action):
        self._feedback = CommandFeedback(action, '完成')

    def _note(self, level, message):
        self._log.insert(0, _event(time.strftime('%H:%M:%S'), level, message))

    def _apply(self, action):
        state = self._state
        mode = state.get('mode', self._selected_mode)
        if action is Action.STOP:
            self._apply_stop()
        elif action is Action.START_SYSTEM:
            self._enter('starting', mode=self._selected_mode)
            self._pending.append((self._clock() + 1.5, self._finish_starting))
        elif action is Action.SHUTDOWN:
            self._enter('stopped', mode=mode)
        elif action is Action.RESET_SIMULATION:
            self._enter('starting', mode=Mode.SIMULATION)
            self._pending.append((self._clock() + 1.5, self._finish_starting))
        elif action is Action.TORQUE_ON:
            self._state = {**state, 'phase': Phase.TORQUE_ON,
                           'safety': SafetyStatus(latched=True, reason=_SUPERVISOR_MISSING_HEARTBEAT, controllers_stopped=True)}
        elif action is Action.SAFETY_RESET:
            self._apply_safety_reset()
        elif action is Action.START_TASK:
            self._enter('working', mode=mode)
        elif action is Action.CANCEL_TASK or action is Action.SUCTION_FAILED:
            self._enter('fault', mode=mode)
        elif action is Action.SUCTION_OK:
            self._enter('working', mode=mode, hardware_blocked_reason='')
        elif action is Action.GO_HOME:
            self._state = {**state, 'arms_at_home': True}
        elif action is Action.RECOVER:
            self._enter('ready', mode=mode)

    def _apply_stop(self):
        state = self._state
        if state.get('phase', Phase.STOPPED) is Phase.STOPPED:
            return
        task = state.get('task')
        if task is not None and task.busy:
            task = TaskStatus(state='FAULT', message='Task canceled', recovery_token='demo', occupied=task.occupied)
            self._scenario = 'latched'
        self._state = {**state, 'task': task, 'controllers_active': False, 'arms_at_home': task is None,
                       'safety': SafetyStatus(latched=True, reason='Operator software stop', controllers_stopped=True)}
        self._note(Level.DANGER, '強制停止：控制器已確認停用')

    def _apply_safety_reset(self):
        state = self._state
        if state.get('phase') is Phase.TORQUE_ON:
            self._enter('hw_blocked', mode=Mode.HARDWARE_MOTION)
            return
        self._state = {**state, 'safety': SafetyStatus(), 'controllers_active': True}

    def _finish_starting(self):
        mode = self._selected_mode
        if mode is Mode.SIMULATION:
            self._enter('ready')
        elif mode is Mode.MOCK:
            self._enter('ready', mode=mode, task=None, safety=None, decision_source='', zones=None, cameras={})
        else:
            self._enter('hw_read_only', mode=mode, calibration_pass=mode is not Mode.HARDWARE_READ_ONLY)

    def _advance(self):
        now = self._clock()
        due = [item for item in self._pending if item[0] <= now]
        self._pending = [item for item in self._pending if item[0] > now]
        for _, callback in due:
            callback()

    # --- data ---

    def _working_task(self, base):
        index = int((self._clock() - self._entered_at) / STEP_PERIOD_S) % len(WORK_SEQUENCE)
        state = WORK_SEQUENCE[index]
        arm = state.split(':')[0].lower() if ':' in state else ''
        arm1_holding = WORK_SEQUENCE.index('ARM1:ATTACH') <= index < WORK_SEQUENCE.index('ARM1:RELEASE_B')
        arm2_holding = WORK_SEQUENCE.index('ARM2:ATTACH') <= index < WORK_SEQUENCE.index('ARM2:RELEASE_C')
        return TaskStatus(state=state, busy=True, active_arm=arm, occupied=base.occupied, slot=3 if index >= 21 else 0,
                          b_owner=self._working_b_owner(index),
                          holding=(('arm1', 'cap_3' if arm1_holding else 'empty'), ('arm2', 'cap_3' if arm2_holding else 'empty')))

    @staticmethod
    def _working_b_owner(index):
        if WORK_SEQUENCE.index('ARM1:RESERVE_B') <= index <= WORK_SEQUENCE.index('ARM1:HOME_EMPTY'):
            return 'arm1'
        if WORK_SEQUENCE.index('ARM2:RESERVE_B') <= index <= WORK_SEQUENCE.index('ARM2:HOME_HOLDING'):
            return 'arm2'
        return ''

    def _working_zones(self):
        index = int((self._clock() - self._entered_at) / STEP_PERIOD_S) % len(WORK_SEQUENCE)
        has_object = WORK_SEQUENCE.index('ARM1:RELEASE_B') <= index < WORK_SEQUENCE.index('ARM2:ATTACH')
        inside = (WORK_SEQUENCE.index('ARM1:APPROACH_B') <= index <= WORK_SEQUENCE.index('ARM1:LIFT_B')
                  or WORK_SEQUENCE.index('ARM2:APPROACH_B') <= index <= WORK_SEQUENCE.index('ARM2:LIFT_B'))
        return ZoneView(a_has_object=True, b_has_object=has_object, b_arm_clear=not inside, c_count=2)

    def _joints(self, moving, mode):
        if self._state.get('joint_age_s') is None:
            return ()
        phase = self._clock() - self._entered_at
        # Counts only exist where a CM-530 (or its firmware mock) reports them; a target only once AX was acknowledged.
        with_raw = mode is not None and mode.has_torque_step
        with_target = mode in (Mode.HARDWARE_MOTION, Mode.MOCK_SERIAL)
        samples = []
        for index, (name, home, home_raw) in enumerate(zip(JOINT_NAMES, _HOME_POSE, _HOME_RAW)):
            amplitude = 0.0 if not moving or index == 7 else 0.3
            position = home + amplitude * math.sin(phase * 0.8 + index)
            velocity = amplitude * 0.8 * math.cos(phase * 0.8 + index)
            command = position + 0.004 * ((-1) ** index) if moving else position
            raw = home_raw + round((position - home) / RADIANS_PER_COUNT) if with_raw else None
            raw_target = home_raw + round((command - home) / RADIANS_PER_COUNT) if with_target else None
            limits = (max(0, home_raw - _DEMO_RAW_SPAN), min(1023, home_raw + _DEMO_RAW_SPAN)) if with_raw else None
            samples.append(JointSample(name, position, velocity, -1.5, 1.5, command, raw, raw_target, limits))
        return tuple(samples)

    def snapshot(self):
        self._advance()
        state = dict(self._state)
        moving = False
        if self._scenario == 'working':
            state['task'] = self._working_task(state['task'])
            state['zones'] = self._working_zones()
            moving = True
        elif self._lead_in:
            state['task'] = replace(state['task'], state=self._lead_in)
            self._lead_in = ''
        if state.get('mode') is Mode.SIMULATION and state.get('phase') is Phase.READY:
            state['gazebo_views'] = {key: CameraStatus(fps=2.0, age_s=0.2) for key, _ in GAZEBO_VIEWS}
        state['joints'] = self._joints(moving, state.get('mode'))
        state['events'] = tuple(self._log) + tuple(state.get('events', ()))
        state['feedback'] = self._feedback
        self._last = Snapshot(is_fake=True, **state)
        return self._last

    def frame(self, camera, annotated):
        if camera in dict(GAZEBO_VIEWS):
            return _draw_gazebo_view(camera) if self._last is not None and camera in self._last.gazebo_views else None
        status = self._last.cameras.get(camera) if self._last is not None else None
        if status is None or not status.has_signal:
            return None
        return {'env': _draw_env, 'arm1': _draw_arm1, 'arm2': _draw_arm2}[camera](self._last, annotated, self._clock())


# --- pictures in the style of the vision nodes' debug output ---

_W, _H = 640, 480
_CAP = (190, 90, 20)
_GREEN, _RED, _WHITE = (0, 255, 0), (0, 0, 255), (255, 255, 255)
_ZONE_BGR = {'A': (255, 128, 0), 'B': (0, 200, 0), 'C': (0, 220, 255)}
_ZONE_BOXES = {'A': ((36, 110), (220, 370)), 'B': ((250, 160), (392, 320)), 'C': ((424, 96), (612, 384))}
_A_CAPS = ((80, 170), (150, 170), (80, 250), (150, 250), (80, 330), (150, 330))
_C_SLOTS = tuple(((150 + column * 180, 390 - row * 100)) for row in range(4) for column in range(2))


def _text(image, text, origin, color=_WHITE, scale=0.5):
    position = (int(origin[0]), int(origin[1]))
    cv2.putText(image, text, position, cv2.FONT_HERSHEY_SIMPLEX, scale, (0, 0, 0), 3, cv2.LINE_AA)
    cv2.putText(image, text, position, cv2.FONT_HERSHEY_SIMPLEX, scale, color, 1, cv2.LINE_AA)


def _canvas(shade):
    image = np.full((_H, _W, 3), shade, dtype=np.uint8)
    cv2.putText(image, 'FAKE DATA', (_W - 150, _H - 14), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (120, 120, 120), 2, cv2.LINE_AA)
    return image


def _draw_gazebo_view(view):
    image = _canvas((180, 190, 200))
    cv2.rectangle(image, (120, 300), (520, 420), (150, 150, 235), -1)
    cv2.line(image, (240, 300), (300, 170), (70, 70, 70), 14, cv2.LINE_AA)
    cv2.line(image, (400, 300), (340, 170), (70, 70, 70), 14, cv2.LINE_AA)
    _text(image, f'simulated {view}', (20, 40), scale=0.7)
    return image


def _draw_env(snapshot, annotated, now):
    image = _canvas((196, 202, 200))
    zones = snapshot.zones or ZoneView()
    for corner_a, corner_b in _ZONE_BOXES.values():
        cv2.rectangle(image, corner_a, corner_b, (232, 236, 234), -1)
    centers = list(_A_CAPS[:4] if zones.a_has_object else ())
    if zones.b_has_object:
        centers.append((320, 240))
    centers += [(470 + (i % 2) * 96, 340 - (i // 2) * 72) for i in range(zones.c_count)]
    for center in centers:
        cv2.circle(image, center, 15, _CAP, -1, cv2.LINE_AA)
    if not annotated:
        return image
    labels = {'A': 'A: OBJECT' if zones.a_has_object else 'A: empty',
              'B': 'B: ' + ('OBJECT ' if zones.b_has_object else '') + ('clear' if zones.b_arm_clear else 'ARM'),
              'C': f'C: n={zones.c_count}'}
    for center in centers:
        cv2.circle(image, center, 17, (0, 255, 255), 2, cv2.LINE_AA)
    for zone, (corner_a, corner_b) in _ZONE_BOXES.items():
        cv2.rectangle(image, corner_a, corner_b, _ZONE_BGR[zone], 2, cv2.LINE_AA)
        _text(image, labels[zone], (corner_a[0] + 4, corner_a[1] + 18), _ZONE_BGR[zone], 0.55)
    _text(image, f'zones OK  frame_age={0.03 + 0.01 * math.sin(now):.2f}s', (8, 18))
    return image


def _draw_arm1(snapshot, annotated, now):
    image = _canvas((214, 220, 216))
    centers = [(190 + (i % 3) * 130, 150 + (i // 3) * 150) for i in range(6)] if (snapshot.zones or ZoneView()).a_has_object else []
    for center in centers:
        cv2.circle(image, center, 34, _CAP, -1, cv2.LINE_AA)
    if not annotated:
        return image
    cv2.rectangle(image, (110, 74), (530, 410), _ZONE_BGR['A'], 2, cv2.LINE_AA)
    _text(image, 'A ROI', (110, 68), _ZONE_BGR['A'])
    for index, center in enumerate(centers):
        target = index == 0
        color = _RED if target else _GREEN
        cv2.circle(image, center, 36, color, 3 if target else 2, cv2.LINE_AA)
        if target:
            _text(image, 'PICK', (center[0] - 18, center[1] - 44), color, 0.45)
        _text(image, f'{0.142 + index * 0.031:.3f}', (center[0] - 20, center[1] + 50), color, 0.35)
    _text(image, f'caps={len(centers)} rejected=0  coords: x / y = base m', (8, 18))
    return image


def _draw_arm2(snapshot, annotated, now):
    image = _canvas((226, 230, 228))
    occupied = snapshot.task.occupied if snapshot.task else (False,) * 8
    for center, filled in zip(_C_SLOTS, occupied):
        cv2.rectangle(image, (center[0] - 42, center[1] - 42), (center[0] + 42, center[1] + 42), (248, 250, 250), -1)
        if filled:
            cv2.circle(image, center, 32, _CAP, -1, cv2.LINE_AA)
    if not annotated:
        return image
    for slot, (center, filled) in enumerate(zip(_C_SLOTS, occupied), start=1):
        color = _RED if filled else _GREEN
        cv2.rectangle(image, (center[0] - 42, center[1] - 42), (center[0] + 42, center[1] + 42), color, 2, cv2.LINE_AA)
        _text(image, str(slot), (center[0] - 38, center[1] - 26), color, 0.45)
        _text(image, f'{82 if filled else 1}%', (center[0] - 14, center[1] + 37), color, 0.35)
    _text(image, 'slot 1 must be bottom-left in user view', (8, 18), (0, 255, 255))
    return image
