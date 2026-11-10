"""Stage 3 acceptance through the real window (offscreen) on a Gazebo simulation.

1. One transfer cycle to SUCCEEDED.
2. Stop before anything is held: reset the latch, HOME, recover, start again to SUCCEEDED.
3. Stop while arm 1 holds a cap: HOME is refused in simulation, reset the simulation instead.

Usage: stage3_live_check.py OUT_DIR STATE_DIR [all|holding]
"holding" runs only part 3, on the first pick of a fresh simulation.
Uses its own state directory and journal so the operator's session is never touched.
"""
import json
import os
from pathlib import Path
import subprocess
import sys
import time

os.environ['QT_QPA_PLATFORM'] = 'offscreen'

from ament_index_python.packages import get_package_prefix, get_package_share_directory  # noqa: E402
from PyQt5.QtTest import QTest  # noqa: E402

from dual_arm_hmi.app import create_application  # noqa: E402
from dual_arm_hmi.launcher.process import Launcher, gazebo_processes, tagged_processes  # noqa: E402
from dual_arm_hmi.launcher.profiles import load_profiles, workspace_from_prefix  # noqa: E402
from dual_arm_hmi.model.state import Action, Mode, Phase, banner, evaluate_actions  # noqa: E402
from dual_arm_hmi.sources.live_source import LiveSource, SettingsStore  # noqa: E402
from dual_arm_hmi.sources.ros_command import RosCommander  # noqa: E402
from dual_arm_hmi.sources.ros_source import RosSource  # noqa: E402
from dual_arm_hmi.ui.main_window import MainWindow  # noqa: E402

READY_TIMEOUT_S = 420
RUN_TIMEOUT_S = 2400
STEP_TIMEOUT_S = 900
STOP_TIMEOUT_S = 60
PARTITION = os.environ['GZ_PARTITION']
FINAL = ('完成', '失敗', '已拒絕')


class Check:
    def __init__(self, app, window, source, out):
        self.app, self.window, self.source, self.out = app, window, source, out
        self.started = time.monotonic()

    def log(self, **values):
        print(json.dumps({'t': round(time.monotonic() - self.started, 1), **values}, ensure_ascii=False), flush=True)

    def pump(self, seconds):
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            self.window.refresh()
            self.app.processEvents()
            QTest.qWait(100)

    def snapshot(self):
        return self.source.snapshot()

    def wait(self, predicate, timeout, label):
        start = time.monotonic()
        while time.monotonic() - start < timeout:
            self.pump(0.3)
            if predicate(self.snapshot()):
                seconds = round(time.monotonic() - start, 1)
                self.log(waited=label, seconds=seconds)
                return True, seconds
        self.log(waited=label, timed_out=timeout, state=self.describe())
        return False, timeout

    def describe(self):
        s = self.snapshot()
        task = s.task
        return {'phase': s.phase.value, 'latched': s.latched, 'controllers_active': s.controllers_active,
                'arms_at_home': s.arms_at_home, 'busy': s.busy,
                'state': task.state if task else None, 'message': task.message if task else None,
                'holding': dict(task.holding) if task else None, 'occupied': list(task.occupied) if task else None,
                'feedback': None if s.feedback is None else f'{s.feedback.action.value}|{s.feedback.phase}|{s.feedback.message}',
                'banner': (banner(s).title if banner(s) else None)}

    def state(self, name):
        return lambda s: s.task is not None and s.task.state == name

    def press(self, action, cleared=False):
        if cleared:
            self.window.control.tools_cleared.setChecked(True)
            self.pump(0.3)
        if action is Action.STOP:
            # The stop button is always enabled and has no dialog.
            self.window.control.stop.click()
        else:
            row = self.window.control.rows[action]
            assert row.button.isEnabled(), f'{action.value} disabled: {row.reason.text()}'
            row.button.click()
        self.log(pressed=action.value)

    def result(self, action, timeout):
        ok, seconds = self.wait(lambda s: s.feedback is not None and s.feedback.action is action and s.feedback.phase in FINAL,
                                timeout, f'{action.value} result')
        feedback = self.snapshot().feedback
        return {'phase': feedback.phase if ok else 'TIMEOUT', 'message': feedback.message if ok else '', 'seconds': seconds}

    def capture(self, name):
        self.window.refresh()
        self.window.grab().save(f'{self.out}/{name}.png')

    def enabled(self, action):
        state = evaluate_actions(self.snapshot(), self.window.control.tools_cleared.isChecked())[action]
        return {'enabled': state.enabled, 'reason': state.reason}


def stop_and_latch(check):
    pressed = time.monotonic()
    check.press(Action.STOP)
    latched, _ = check.wait(lambda s: s.latched and s.safety.controllers_stopped, STOP_TIMEOUT_S, 'latch and controllers stopped')
    latch_s = round(time.monotonic() - pressed, 1)
    settled, _ = check.wait(lambda s: not s.busy and s.task.state == 'FAULT', STOP_TIMEOUT_S, 'task FAULT')
    return {'latched': latched, 'latch_s': latch_s, 'faulted': settled, 'stop_feedback': check.result(Action.STOP, 30),
            'after_stop': check.describe()}


def leftovers(session):
    names = [name for name in subprocess.run(['ros2', 'node', 'list', '--no-daemon'], capture_output=True, text=True,
                                             timeout=60).stdout.split()
             if name not in ('/dual_arm_hmi_monitor', '/dual_arm_hmi_command')]
    return {'gazebo': gazebo_processes(PARTITION), 'tagged': tagged_processes(session) if session else [], 'ros_nodes': names}


def main(out, state_dir, parts):
    app = create_application(['check'])
    profiles = load_profiles(os.path.join(get_package_share_directory('dual_arm_hmi'), 'config', 'profiles.yaml'),
                             Path(state_dir) / 'none.yaml')
    store = SettingsStore(str(Path(state_dir) / 'settings.json'))
    store.save({'mode': Mode.SIMULATION.value, 'cycles': 1, 'journal_path': str(Path(state_dir) / 'journal.json')})
    launcher = Launcher(state_dir)
    source = LiveSource(RosSource(), launcher, profiles, workspace_from_prefix(get_package_prefix('dual_arm_hmi')), store,
                        commander=lambda domain: RosCommander(domain_id=domain))
    window = MainWindow(source)
    window._ask = lambda *args: True  # the confirmation dialogs are covered by the unit tests
    window.resize(1920, 1080)
    window.show()
    check = Check(app, window, source, out)
    results = {}

    check.press(Action.START_SYSTEM)
    ready, seconds = check.wait(lambda s: s.phase is Phase.READY and s.task is not None and s.controllers_active,
                                READY_TIMEOUT_S, 'system ready')
    session = launcher._session
    results['ready'] = {'ok': ready, 'seconds': seconds, 'state': check.describe()}
    check.pump(3)
    check.capture('01_ready')

    if parts == 'all':
        part_cycle_and_empty_stop(check, results)
    part_holding_stop(check, results)

    session = launcher._session or session
    check.press(Action.SHUTDOWN)
    stopped, _ = check.wait(lambda s: s.phase is Phase.STOPPED, 120, 'stopped')
    check.pump(3)
    results['shutdown'] = {'stopped': stopped, 'leftovers': leftovers(session)}
    held = results['stop_holding']
    results['criteria'] = {
        'stop_holding_reset_simulation': (held['reached_holding'] and held['latched'] and held['go_home']['phase'] == '已拒絕'
                                          and held['reset_simulation']['ok']),
        'clean_shutdown': stopped and not any(results['shutdown']['leftovers'].values()),
    }
    if parts == 'all':
        empty = results['stop_empty']
        results['criteria'].update({
            'one_cycle_succeeded': results['cycle']['result']['phase'] == '完成' and results['cycle']['state']['state'] == 'SUCCEEDED',
            'stop_empty_recovered_and_restarted': (empty['latched'] and empty['faulted'] and empty['reset']['phase'] == '完成'
                                                   and empty['go_home']['phase'] == '完成' and empty['recover']['phase'] == '完成'
                                                   and empty['restart']['phase'] == '完成'
                                                   and empty['after_restart']['state'] == 'SUCCEEDED')})
    name = '04_live_check.json' if parts == 'all' else f'04_live_check_{parts}.json'
    Path(out).parent.joinpath(name).write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(results['criteria']), flush=True)
    window.close()
    return 0 if all(results['criteria'].values()) else 1


def part_cycle_and_empty_stop(check, results):
    # 1. One cycle.
    check.press(Action.START_TASK)
    results['cycle'] = {'result': check.result(Action.START_TASK, RUN_TIMEOUT_S), 'state': check.describe()}
    check.capture('02_cycle_done')

    # 2. Stop with nothing held.
    check.press(Action.START_TASK)
    reached, _ = check.wait(lambda s: s.task is not None and s.task.state == 'ARM1:APPROACH_A', STEP_TIMEOUT_S, 'ARM1:APPROACH_A')
    check.pump(2)  # stop while the arm is moving
    empty = {'reached_approach': reached, 'holding_before_stop': dict(check.snapshot().task.holding)}
    empty.update(stop_and_latch(check))
    check.capture('03_stopped_empty')
    empty['start_while_latched'] = check.enabled(Action.START_TASK)
    empty['recover_before_reset'] = check.enabled(Action.RECOVER)
    check.press(Action.SAFETY_RESET)
    empty['reset'] = check.result(Action.SAFETY_RESET, 60)
    check.wait(lambda s: not s.latched and s.controllers_active, 30, 'latch cleared')
    empty['go_home_without_tick'] = check.enabled(Action.GO_HOME)
    check.press(Action.GO_HOME, cleared=True)
    empty['go_home'] = check.result(Action.GO_HOME, STEP_TIMEOUT_S)
    empty['after_home'] = check.describe()
    check.capture('04_home_after_stop')
    check.press(Action.RECOVER, cleared=True)
    empty['recover'] = check.result(Action.RECOVER, 120)
    check.wait(check.state('IDLE'), 30, 'IDLE after recovery')
    empty['after_recover'] = check.describe()
    check.press(Action.START_TASK)
    empty['restart'] = check.result(Action.START_TASK, RUN_TIMEOUT_S)
    empty['after_restart'] = check.describe()
    check.capture('05_restart_done')
    results['stop_empty'] = empty


def part_holding_stop(check, results):
    # 3. Stop while holding.
    check.press(Action.START_TASK)
    reached, _ = check.wait(lambda s: s.task is not None and s.task.held_by('arm1') == 'held', STEP_TIMEOUT_S, 'arm1 holding')
    held = {'reached_holding': reached, 'state_before_stop': check.snapshot().task.state}
    held.update(stop_and_latch(check))
    check.press(Action.SAFETY_RESET)
    held['reset'] = check.result(Action.SAFETY_RESET, 60)
    check.wait(lambda s: not s.latched, 30, 'latch cleared')
    check.capture('06_stopped_holding')
    held['recover_state'] = check.enabled(Action.RECOVER)
    check.press(Action.GO_HOME, cleared=True)
    held['go_home'] = check.result(Action.GO_HOME, 60)
    held['banner'] = check.describe()['banner']
    check.press(Action.RESET_SIMULATION)
    restarted, seconds = check.wait(lambda s: s.phase is Phase.READY and s.task is not None and s.task.state == 'IDLE'
                                    and s.controllers_active and not s.latched, READY_TIMEOUT_S + 120, 'reset simulation ready')
    held['reset_simulation'] = {'ok': restarted, 'seconds': seconds, 'state': check.describe()}
    check.pump(3)
    check.capture('07_after_reset_simulation')
    results['stop_holding'] = held


if __name__ == '__main__':
    sys.exit(main(sys.argv[1], sys.argv[2], sys.argv[3] if len(sys.argv) > 3 else 'all'))
