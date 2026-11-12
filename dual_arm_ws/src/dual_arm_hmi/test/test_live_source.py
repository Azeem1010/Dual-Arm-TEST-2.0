"""LiveSource joins the launcher with ROS data. Both are replaced by stand-ins here."""
from dataclasses import replace

import pytest

from dual_arm_hmi.launcher.process import LaunchStatus
from dual_arm_hmi.model.state import Action, Mode, Phase, SafetyStatus, Snapshot, TaskStatus, banner, evaluate_actions
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
        self.environments = []

    def status(self):
        return self.status_value

    def start(self, mode, command, environment=None):
        self.started.append((mode, command))
        self.environments.append(dict(environment or {}))
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


HARDWARE_PROFILES = {**PROFILES, 'hardware': {'port': '/dev/serial/by-id/x', 'ros_domain_id': '0'}}


class Monitors:
    """Stand-in for RosSource creation: records which domain each new monitor joins."""

    def __init__(self):
        self.domains, self.closed = [], 0

    def __call__(self, domain):
        self.domains.append(domain)
        monitor = Ros()
        original = monitor.close

        def close():
            self.closed += 1
            original()
        monitor.close = close
        return monitor


@pytest.fixture
def hardware_parts(monkeypatch):
    monkeypatch.setattr(live_source, 'gazebo_processes', lambda partition=None: [])
    monkeypatch.setenv('ROS_DOMAIN_ID', '43')
    monitors, launcher = Monitors(), Launcher()
    first = monitors(43)
    source = LiveSource(first, launcher, HARDWARE_PROFILES, '/ws', Store(), clock=lambda: 100.0, reconnect=monitors)
    return source, monitors, launcher


def test_selecting_hardware_moves_the_monitor_to_the_hardware_domain(hardware_parts):
    source, monitors, _ = hardware_parts
    source.select_mode(Mode.HARDWARE_READ_ONLY)
    assert monitors.domains == [43, 0] and monitors.closed == 1
    source.select_mode(Mode.HARDWARE_MOTION)
    assert monitors.domains == [43, 0]
    source.select_mode(Mode.SIMULATION)
    assert monitors.domains == [43, 0, 43] and monitors.closed == 2


def test_hardware_start_runs_on_the_hardware_domain(hardware_parts):
    source, monitors, launcher = hardware_parts
    source.select_mode(Mode.HARDWARE_READ_ONLY)
    source.invoke(Action.START_SYSTEM)
    assert launcher.started and launcher.environments[0] == {'ROS_DOMAIN_ID': '0'}
    assert any('cameras.yaml' in event.message for event in source.snapshot().events)


def test_the_monitor_stays_with_a_running_system(hardware_parts):
    source, monitors, launcher = hardware_parts
    source.select_mode(Mode.HARDWARE_READ_ONLY)
    source.invoke(Action.START_SYSTEM)
    source.select_mode(Mode.SIMULATION)
    assert monitors.domains == [43, 0]


def test_an_adopted_hardware_system_is_watched_on_its_domain(monkeypatch):
    monkeypatch.setattr(live_source, 'gazebo_processes', lambda partition=None: [])
    monkeypatch.setenv('ROS_DOMAIN_ID', '43')
    monitors, launcher = Monitors(), Launcher()
    launcher.status_value = LaunchStatus('running', Mode.HARDWARE_READ_ONLY.value, adopted=True)
    LiveSource(monitors(43), launcher, HARDWARE_PROFILES, '/ws', Store({'mode': Mode.SIMULATION.value}),
               clock=lambda: 100.0, reconnect=monitors)
    assert monitors.domains == [43, 0]


def test_without_reconnect_the_monitor_never_moves(parts):
    source, ros, *_ = parts
    source.select_mode(Mode.HARDWARE_READ_ONLY)
    assert source._ros is ros


ALL_SERVICES = {name for names in live_source.TASK_ACTIONS.values() for name in names}


class Commander:
    """Stand-in for RosCommander: records calls and hands back replies the test chooses."""

    def __init__(self, domain=None, services=None):
        self.domain, self.sent, self.queued, self.closed = domain, [], [], False
        self.services = set(services if services is not None else ALL_SERVICES)

    def available(self, service):
        return service in self.services

    def send(self, batch, calls):
        self.sent.append((batch, calls))

    def reply(self, ok=True, message='ok', index=-1):
        from dual_arm_hmi.sources.ros_command import Reply
        batch, calls = self.sent[index]
        self.queued += [(batch, Reply(service, ok, message)) for service, _ in calls]

    def results(self):
        done, self.queued = self.queued, []
        return done

    def close(self):
        self.closed = True


@pytest.fixture
def commanded(monkeypatch):
    monkeypatch.setattr(live_source, 'gazebo_processes', lambda partition=None: [])
    ros, launcher, clock, made = Ros(), Launcher(), [100.0], []

    def make(domain):
        made.append(Commander(domain))
        return made[-1]
    source = LiveSource(ros, launcher, PROFILES, '/ws', Store(), clock=lambda: clock[0], commander=make)
    source.invoke(Action.START_SYSTEM)
    ros.base = connected(task=TaskStatus())
    source.snapshot()
    return source, ros, made, clock


def test_task_actions_are_wired_only_with_a_commander(commanded, parts):
    source, *_ = commanded
    wired = source.snapshot().wired_actions
    assert {Action.STOP, Action.START_TASK, Action.GO_HOME, Action.RECOVER, Action.SAFETY_RESET} <= wired
    assert Action.TORQUE_ON not in wired and Action.SUCTION_OK not in wired
    assert Action.START_TASK not in parts[0].snapshot().wired_actions


def test_start_task_follows_sent_accepted_and_the_result(commanded):
    source, ros, made, clock = commanded
    source.invoke(Action.START_TASK)
    assert made[0].sent[-1][1][0][0] == '/dual_arm/start' and source.snapshot().feedback.phase == '已送出'
    made[0].reply(True, 'Accepted')
    assert source.snapshot().feedback.phase == '已接受'
    ros.base = connected(task=TaskStatus(state='ARM1:PICK', busy=True))
    assert source.snapshot().feedback.phase == '已接受'
    ros.base = connected(task=TaskStatus(state='SUCCEEDED'))
    feedback = source.snapshot().feedback
    assert feedback.phase == '完成' and 'SUCCEEDED' in feedback.message


def test_a_refused_start_shows_the_reason(commanded):
    source, _, made, _ = commanded
    source.invoke(Action.START_TASK)
    made[0].reply(False, 'Busy, faulted or full')
    feedback = source.snapshot().feedback
    assert feedback.phase == '已拒絕' and 'Busy' in feedback.message


def test_a_faulted_run_is_reported_as_failed(commanded):
    source, ros, made, _ = commanded
    source.invoke(Action.START_TASK)
    made[0].reply()
    source.snapshot()
    ros.base = connected(task=TaskStatus(state='ARM2:PLACE', busy=True))
    source.snapshot()
    ros.base = connected(task=TaskStatus(state='FAULT', message='Task canceled'))
    feedback = source.snapshot().feedback
    assert feedback.phase == '失敗' and 'Task canceled' in feedback.message


def test_stop_calls_the_supervisor_and_the_task(commanded):
    source, ros, made, clock = commanded
    source.invoke(Action.STOP)
    assert [service for service, _ in made[0].sent[-1][1]] == ['/safety/trigger_stop', '/dual_arm/cancel']
    made[0].queued = [(made[0].sent[-1][0], live_reply('/safety/trigger_stop', True)),
                      (made[0].sent[-1][0], live_reply('/dual_arm/cancel', False, 'No task is running'))]
    # One refusal does not undo the stop that did happen.
    assert source.snapshot().feedback.phase == '已接受'
    ros.base = connected(task=TaskStatus(), safety=SafetyStatus(latched=True, reason='Operator software stop'))
    clock[0] += 2
    feedback = source.snapshot().feedback
    assert feedback.phase == '完成' and '鎖定' in feedback.message


def test_stop_skips_missing_services_and_refuses_when_none_exist(commanded):
    source, _, made, _ = commanded
    made[0].services = {'/dual_arm/cancel'}
    source.invoke(Action.STOP)
    assert [service for service, _ in made[0].sent[-1][1]] == ['/dual_arm/cancel']
    made[0].services = set()
    count = len(made[0].sent)
    source.invoke(Action.STOP)
    assert len(made[0].sent) == count and source.snapshot().feedback.phase == '已拒絕'


def test_recover_sends_the_published_token_and_the_confirmation(commanded):
    source, ros, made, _ = commanded
    ros.base = connected(task=TaskStatus(state='FAULT', recovery_token='abc'))
    source.snapshot()
    source.invoke(Action.RECOVER, cleared=True)
    service, request = made[0].sent[-1][1][0]
    assert service == '/dual_arm/recover' and request.token == 'abc' and request.success is True
    made[0].reply(True, 'Recovered; send a new start')
    assert source.snapshot().feedback.phase == '完成'


def test_go_home_without_the_tick_sends_no_confirmation(commanded):
    source, _, made, _ = commanded
    source.invoke(Action.GO_HOME)
    assert made[0].sent[-1][1][0][1].success is False


def test_go_home_is_judged_by_the_reported_position(commanded):
    source, ros, made, clock = commanded
    source.invoke(Action.GO_HOME, cleared=True)
    made[0].reply()
    source.snapshot()
    ros.base = connected(task=TaskStatus(state='FAULT', busy=True))
    source.snapshot()
    ros.base = connected(task=TaskStatus(state='FAULT', message='arm1 home: MoveIt planning failed'), arms_at_home=False)
    feedback = source.snapshot().feedback
    assert feedback.phase == '失敗' and 'MoveIt' in feedback.message
    source.invoke(Action.GO_HOME, cleared=True)
    made[0].reply()
    source.snapshot()
    ros.base = connected(task=TaskStatus(state='FAULT'), arms_at_home=True)
    clock[0] += 2
    assert source.snapshot().feedback.phase == '完成'


def test_late_replies_to_an_older_command_are_ignored(commanded):
    source, _, made, _ = commanded
    source.invoke(Action.START_TASK)
    source.invoke(Action.CANCEL_TASK)
    made[0].reply(False, 'old', index=0)
    assert source.snapshot().feedback.action is Action.CANCEL_TASK
    assert source.snapshot().feedback.phase == '已送出'


def test_hardware_gets_only_the_stop(commanded):
    source, ros, made, _ = commanded
    ros.base = connected(mode=Mode.HARDWARE_MOTION, task=TaskStatus())
    snapshot = source.snapshot()
    assert Action.STOP in snapshot.wired_actions and Action.SAFETY_RESET not in snapshot.wired_actions
    count = len(made[0].sent)
    source.invoke(Action.SAFETY_RESET)
    assert len(made[0].sent) == count and '階段 5' in source.snapshot().feedback.message


def test_prototype_gets_the_task_actions(commanded):
    source, ros, _, _ = commanded
    ros.base = connected(mode=Mode.HARDWARE_PROTOTYPE, task=TaskStatus())
    wired = source.snapshot().wired_actions
    assert {Action.START_TASK, Action.SAFETY_RESET, Action.CANCEL_TASK, Action.STOP} <= wired


def test_commands_follow_the_monitor_to_another_domain(monkeypatch):
    monkeypatch.setattr(live_source, 'gazebo_processes', lambda partition=None: [])
    monkeypatch.setenv('ROS_DOMAIN_ID', '43')
    made, monitors = [], Monitors()

    def make(domain):
        made.append(Commander(domain, services=()))
        return made[-1]
    source = LiveSource(monitors(43), Launcher(), HARDWARE_PROFILES, '/ws', Store(), clock=lambda: 100.0,
                        reconnect=monitors, commander=make)
    source.select_mode(Mode.HARDWARE_READ_ONLY)
    assert [item.domain for item in made] == [None, 0] and made[0].closed


def live_reply(service, ok, message='ok'):
    from dual_arm_hmi.sources.ros_command import Reply
    return Reply(service, ok, message)


def test_interface_and_ros_events_are_merged_newest_first(parts, monkeypatch):
    from dual_arm_hmi.model.state import EventRecord, Level
    source, ros, *_ = parts
    now = [1000.0]
    monkeypatch.setattr(live_source.time, 'time', lambda: now[0])
    source.invoke(Action.STOP)  # an interface event at 1000
    ros.base = replace(ros.base, events=(EventRecord('t', Level.NEUTRAL, 'ros later', 1001.0),
                                         EventRecord('t', Level.NEUTRAL, 'ros earlier', 999.0)))
    messages = [event.message for event in source.snapshot().events]
    assert messages[0] == 'ros later' and messages[-1] == 'ros earlier'


def test_interface_events_are_capped(parts):
    source, *_ = parts
    for _ in range(live_source.EVENT_LIMIT + 20):
        source.invoke(Action.STOP)
    assert len(source.snapshot().events) == live_source.EVENT_LIMIT
