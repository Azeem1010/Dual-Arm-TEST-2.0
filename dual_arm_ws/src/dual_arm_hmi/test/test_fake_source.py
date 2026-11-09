import sys

import pytest

from dual_arm_hmi.model.state import Action, Mode, Phase, evaluate_actions
from dual_arm_hmi.sources.fake_source import CAMERAS, STEP_PERIOD_S, FakeSource


class Clock:
    def __init__(self):
        self.now = 100.0

    def __call__(self):
        return self.now


@pytest.fixture
def clock():
    return Clock()


def settle(source, clock, seconds=3.0):
    for _ in range(int(seconds / 0.1)):
        clock.now += 0.1
        source.snapshot()
    return source.snapshot()


def run(source, clock, action):
    source.invoke(action)
    return settle(source, clock)


EXPECTED = {'未啟動', '啟動中', '就緒', '工作中', '等待吸盤確認', '取消後故障', '安全鎖定', 'C 區已滿', '實機唯讀', '實機 BLOCKED', '相機無訊號', '資料過期'}


def test_all_twelve_planned_scenarios_exist():
    assert {label for _, label in FakeSource().scenarios()} == EXPECTED


def test_every_snapshot_is_marked_fake():
    for key, _ in FakeSource().scenarios():
        assert FakeSource(key).snapshot().is_fake


def test_fake_source_does_not_need_ros():
    assert 'rclpy' not in sys.modules


@pytest.mark.parametrize('annotated', (True, False))
def test_frames_are_bgr_640_by_480(annotated):
    source = FakeSource('ready')
    source.snapshot()
    for camera in CAMERAS:
        assert source.frame(camera, annotated).shape == (480, 640, 3)


def test_annotation_changes_the_picture():
    source = FakeSource('ready')
    source.snapshot()
    assert (source.frame('env', True) != source.frame('env', False)).any()


def test_no_signal_returns_no_image():
    source = FakeSource('no_signal')
    source.snapshot()
    assert source.frame('env', True) is None and source.frame('arm1', True) is None
    assert source.frame('arm2', True) is not None


def test_stopped_has_no_data():
    source = FakeSource('stopped')
    snapshot = source.snapshot()
    assert snapshot.joints == () and snapshot.task is None and source.frame('env', True) is None


def test_stale_scenario_is_stale():
    assert FakeSource('stale').snapshot().joints_stale


def test_working_advances_through_steps(clock):
    source = FakeSource('working', clock=clock)
    first = source.snapshot().task.state
    clock.now += STEP_PERIOD_S * 3
    assert source.snapshot().task.state != first


def test_feedback_goes_sent_accepted_done(clock):
    source = FakeSource('ready', clock=clock)
    source.invoke(Action.START_TASK)
    assert source.snapshot().feedback.phase == '已送出'
    clock.now += 0.31
    assert source.snapshot().feedback.phase == '已接受'
    clock.now += 0.51
    assert source.snapshot().feedback.phase == '完成'


def test_start_and_shutdown_flow(clock):
    source = FakeSource('stopped', clock=clock)
    assert run(source, clock, Action.START_SYSTEM).phase is Phase.READY
    assert run(source, clock, Action.SHUTDOWN).phase is Phase.STOPPED


def test_stop_then_full_recovery_flow(clock):
    source = FakeSource('working', clock=clock)
    assert source.snapshot().busy
    snapshot = run(source, clock, Action.STOP)
    assert snapshot.latched and snapshot.task.state == 'FAULT' and not snapshot.controllers_active
    assert evaluate_actions(snapshot)[Action.SAFETY_RESET].enabled
    snapshot = run(source, clock, Action.SAFETY_RESET)
    assert not snapshot.latched and not snapshot.arms_at_home
    assert evaluate_actions(snapshot, True)[Action.GO_HOME].enabled
    snapshot = run(source, clock, Action.GO_HOME)
    assert evaluate_actions(snapshot, True)[Action.RECOVER].enabled
    snapshot = run(source, clock, Action.RECOVER)
    assert evaluate_actions(snapshot)[Action.START_TASK].enabled


def test_hardware_motion_startup_steps(clock):
    source = FakeSource('stopped', clock=clock)
    source.select_mode(Mode.HARDWARE_MOTION)
    snapshot = run(source, clock, Action.START_SYSTEM)
    assert snapshot.phase is Phase.READ_ONLY and evaluate_actions(snapshot)[Action.TORQUE_ON].enabled
    snapshot = run(source, clock, Action.TORQUE_ON)
    assert snapshot.phase is Phase.TORQUE_ON and snapshot.latched
    snapshot = run(source, clock, Action.SAFETY_RESET)
    assert snapshot.phase is Phase.READY and not evaluate_actions(snapshot)[Action.START_TASK].enabled


def test_suction_confirmation_flow(clock):
    source = FakeSource('suction', clock=clock)
    assert evaluate_actions(source.snapshot())[Action.SUCTION_OK].enabled
    assert run(source, clock, Action.SUCTION_OK).task.suction_token == ''
    source = FakeSource('suction', clock=clock)
    assert run(source, clock, Action.SUCTION_FAILED).task.state == 'FAULT'
