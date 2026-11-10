"""LiveSource joins the launcher with ROS data. Both are replaced by stand-ins here."""
from dataclasses import replace

import pytest

from dual_arm_hmi.launcher.process import LaunchStatus
from dual_arm_hmi.model.state import Action, Mode, Phase, Snapshot, TaskStatus, banner, evaluate_actions
from dual_arm_hmi.sources import live_source
from dual_arm_hmi.sources.live_source import LiveSource

PROFILES = {'simulation': {'prefilled_slots': 2}, 'startup_warning_s': 240}


class Ros:
    def __init__(self):
        self.base = Snapshot(mode=Mode.UNKNOWN, monitor_only=True)
        self.expected = None

    def snapshot(self):
        return self.base

    def expect_disconnect(self, expected):
        self.expected = expected

    def frame(self, camera, annotated):
        return None

    def close(self):
        pass


class Launcher:
    def __init__(self):
        self.status_value, self.started = LaunchStatus(), []

    def status(self):
        return self.status_value

    def start(self, mode, command, environment=None):
        self.started.append((mode, command))
        self.status_value = LaunchStatus('running', mode, started_at=100.0, log_path='/log')
        return ''

    def stop_async(self):
        if self.status_value.state != 'running':
            return False
        self.status_value = replace(self.status_value, state='stopping')
        return True


class Store:
    def __init__(self, data=None):
        self.data = dict(data or {})

    def load(self):
        return dict(self.data)

    def save(self, data):
        self.data = dict(data)


@pytest.fixture
def parts(monkeypatch):
    monkeypatch.setattr(live_source, 'gazebo_processes', lambda partition=None: [])
    ros, launcher, store, clock = Ros(), Launcher(), Store(), [100.0]
    source = LiveSource(ros, launcher, PROFILES, '/ws', store, clock=lambda: clock[0])
    return source, ros, launcher, store, clock


def connected(phase=Phase.READY, **changes):
    values = {'mode': Mode.SIMULATION, 'phase': phase, 'ros_connected': True, 'monitor_only': True, 'joint_age_s': 0.01}
    return Snapshot(**{**values, **changes})


def test_idle_is_stopped_and_only_launch_actions_are_wired(parts):
    source, *_ = parts
    snapshot = source.snapshot()
    assert snapshot.phase is Phase.STOPPED and not snapshot.monitor_only
    actions = evaluate_actions(snapshot)
    assert actions[Action.START_SYSTEM].enabled
    assert not actions[Action.STOP].enabled and actions[Action.STOP].reason == '尚未接通'
    assert '啟動系統' in banner(snapshot).next_step


def test_start_runs_the_selected_mode_and_shows_starting_until_ready(parts):
    source, ros, launcher, store, _ = parts
    source.select_mode(Mode.MOCK)
    source.invoke(Action.START_SYSTEM)
    assert launcher.started[0][0] == 'Mock' and ros.expected is False
    snapshot = source.snapshot()
    assert snapshot.phase is Phase.STARTING and snapshot.mode is Mode.MOCK
    assert banner(snapshot).title == '系統啟動中'
    ros.base = connected(mode=Mode.MOCK)
    snapshot = source.snapshot()
    assert snapshot.phase is Phase.READY and snapshot.feedback.phase == '完成'
    assert store.data['mode'] == 'Mock'


def test_a_refused_plan_is_reported_and_nothing_starts(parts):
    source, _, launcher, *_ = parts
    source.select_mode(Mode.HARDWARE_READ_ONLY)
    source.invoke(Action.START_SYSTEM)
    assert not launcher.started and source.snapshot().feedback.phase == '已拒絕'


def test_shutdown_shows_stopping_and_expects_the_disconnect(parts):
    source, ros, launcher, *_ = parts
    source.invoke(Action.START_SYSTEM)
    ros.base = connected()
    source.invoke(Action.SHUTDOWN)
    assert ros.expected is True
    snapshot = source.snapshot()
    assert snapshot.phase is Phase.STOPPING and not evaluate_actions(snapshot)[Action.START_SYSTEM].enabled
    launcher.status_value = LaunchStatus('idle')
    ros.base = replace(ros.base, ros_connected=False)
    snapshot = source.snapshot()
    assert snapshot.phase is Phase.STOPPED and banner(snapshot).level.value == 'info'


def test_a_system_started_elsewhere_cannot_be_shut_down_here(parts):
    source, ros, *_ = parts
    ros.base = connected()
    actions = evaluate_actions(source.snapshot())
    assert not actions[Action.SHUTDOWN].enabled and '原終端機' in actions[Action.SHUTDOWN].reason
    assert not actions[Action.START_SYSTEM].enabled


def test_shutdown_refused_while_a_task_runs(parts):
    source, ros, *_ = parts
    source.invoke(Action.START_SYSTEM)
    ros.base = connected(task=TaskStatus(busy=True))
    assert not evaluate_actions(source.snapshot())[Action.SHUTDOWN].enabled


def test_failure_is_shown_with_the_log(parts):
    source, _, launcher, *_ = parts
    launcher.status_value = LaunchStatus('failed', '模擬', log_path='/log/x.log', message='系統意外結束（代碼 1）')
    snapshot = source.snapshot()
    assert banner(snapshot).title == '系統啟動失敗' and '/log/x.log' in banner(snapshot).detail
    assert evaluate_actions(snapshot)[Action.START_SYSTEM].enabled


def test_slow_start_warns(parts):
    source, _, launcher, _, clock = parts
    source.invoke(Action.START_SYSTEM)
    clock[0] += 241
    assert banner(source.snapshot()).title == '啟動時間過長'


def test_reset_simulation_rotates_the_journal_and_restarts(parts):
    source, ros, launcher, store, _ = parts
    source.invoke(Action.START_SYSTEM)
    first_journal = [word for word in launcher.started[0][1] if word.startswith('journal_path:=')][0]
    ros.base = connected()
    source.invoke(Action.RESET_SIMULATION)
    launcher.status_value = LaunchStatus('idle')
    ros.base = replace(ros.base, ros_connected=False)
    source.snapshot()
    assert len(launcher.started) == 2
    second_journal = [word for word in launcher.started[1][1] if word.startswith('journal_path:=')][0]
    assert second_journal != first_journal and store.data['journal_path'] in second_journal


def test_actions_not_yet_wired_are_refused_with_feedback(parts):
    source, _, launcher, *_ = parts
    source.invoke(Action.STOP)
    assert not launcher.started and source.snapshot().feedback.phase == '已拒絕'


def test_cycles_are_remembered_and_passed(parts):
    source, _, launcher, store, _ = parts
    source.set_cycles(4)
    source.invoke(Action.START_SYSTEM)
    assert 'cycles:=4' in launcher.started[0][1] and store.data['cycles'] == 4
    assert source.snapshot().cycles == 4


def test_residual_gazebo_blocks_start(parts, monkeypatch):
    source, *_ = parts
    monkeypatch.setattr(live_source, 'gazebo_processes', lambda partition=None: [123])
    source._residual_checked = -1e9
    state = evaluate_actions(source.snapshot())[Action.START_SYSTEM]
    assert not state.enabled and 'Gazebo' in state.reason
