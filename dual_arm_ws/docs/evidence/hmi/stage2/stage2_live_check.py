"""Ten start and stop cycles through the real window, then a crash and adoption.

Usage: stage2_live_check.py OUT_DIR STATE_DIR CYCLES
       stage2_live_check.py --crash-child OUT_DIR STATE_DIR
Uses its own state directory so the operator's session file is never touched.
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
from dual_arm_hmi.sources.ros_source import RosSource  # noqa: E402
from dual_arm_hmi.ui.main_window import MainWindow  # noqa: E402

READY_TIMEOUT_S = 420
STOP_TIMEOUT_S = 90
PARTITION = os.environ['GZ_PARTITION']


def open_window(app, state_dir):
    profiles = load_profiles(os.path.join(get_package_share_directory('dual_arm_hmi'), 'config', 'profiles.yaml'),
                             Path(state_dir) / 'none.yaml')
    launcher = Launcher(state_dir)
    source = LiveSource(RosSource(), launcher, profiles, workspace_from_prefix(get_package_prefix('dual_arm_hmi')),
                        SettingsStore(str(Path(state_dir) / 'settings.json')))
    source.select_mode(Mode.SIMULATION)
    window = MainWindow(source)
    window._ask = lambda *args: True  # the confirmation dialog is checked in the unit tests
    window.resize(1920, 1080)
    window.show()
    QTest.qWait(300)
    return window, source, launcher


def pump(app, window, seconds):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        window.refresh()
        app.processEvents()
        QTest.qWait(100)


def wait_phase(app, window, source, phases, timeout):
    end = time.monotonic() + timeout
    while time.monotonic() < end:
        pump(app, window, 0.5)
        if source.snapshot().phase in phases:
            return True
    return False


def press(window, action):
    row = window.control.rows[action]
    assert row.button.isEnabled(), f'{action.value} disabled: {row.reason.text()}'
    row.button.click()


def leftovers(session):
    names = [name for name in subprocess.run(['ros2', 'node', 'list', '--no-daemon'], capture_output=True, text=True, timeout=60).stdout.split()
             if name != '/dual_arm_hmi_monitor']  # the interface itself is still running
    return {'gazebo': gazebo_processes(PARTITION), 'tagged': tagged_processes(session) if session else [], 'ros_nodes': names}


def capture(window, out, name):
    window.refresh()
    window.grab().save(f'{out}/{name}.png')


def crash_child(out, state_dir):
    app = create_application(['child'])
    window, source, launcher = open_window(app, state_dir)
    press(window, Action.START_SYSTEM)
    ready = wait_phase(app, window, source, (Phase.READY,), READY_TIMEOUT_S)
    capture(window, out, 'crash_before')
    print(json.dumps({'ready': ready, 'session': launcher._session}), flush=True)
    os._exit(0)  # no cleanup, like a crash


def main(out, state_dir, cycles):
    app = create_application(['check'])
    window, source, launcher = open_window(app, state_dir)
    results = {'cycles': []}
    for index in range(cycles):
        record = {'cycle': index + 1, 'residual_before': gazebo_processes()}
        started = time.monotonic()
        press(window, Action.START_SYSTEM)
        session = launcher._session
        if index == 0:
            pump(app, window, 3)
            capture(window, out, 'starting')
        record['ready'] = wait_phase(app, window, source, (Phase.READY,), READY_TIMEOUT_S)
        record['ready_s'] = round(time.monotonic() - started, 1)
        snapshot = source.snapshot()
        record['managed_shutdown_enabled'] = evaluate_actions(snapshot)[Action.SHUTDOWN].enabled
        if index == 0:
            pump(app, window, 5)
            capture(window, out, 'ready')
        stopping = time.monotonic()
        press(window, Action.SHUTDOWN)
        if index == 0:
            pump(app, window, 1)
            capture(window, out, 'stopping')
        record['stopped'] = wait_phase(app, window, source, (Phase.STOPPED,), STOP_TIMEOUT_S)
        record['stop_s'] = round(time.monotonic() - stopping, 1)
        pump(app, window, 3)
        record['launcher_message'] = launcher.status().message
        record['leftovers'] = leftovers(session)
        record['banner_after'] = banner(source.snapshot()).title
        if index == 0:
            capture(window, out, 'stopped')
        results['cycles'].append(record)
        print(json.dumps(record, ensure_ascii=False), flush=True)
    window.close()

    child = subprocess.run([sys.executable, __file__, '--crash-child', out, state_dir], capture_output=True, text=True, timeout=READY_TIMEOUT_S + 120)
    crash = json.loads(child.stdout.strip().splitlines()[-1])
    window, source, launcher = open_window(app, state_dir)
    pump(app, window, 8)
    snapshot = source.snapshot()
    adopted = {'child_ready': crash['ready'], 'adopted': launcher.status().adopted, 'phase': snapshot.phase.value,
               'shutdown_enabled': evaluate_actions(snapshot)[Action.SHUTDOWN].enabled,
               'same_session': launcher._session == crash['session']}
    capture(window, out, 'adopted')
    press(window, Action.SHUTDOWN)
    adopted['stopped'] = wait_phase(app, window, source, (Phase.STOPPED,), STOP_TIMEOUT_S)
    pump(app, window, 3)
    adopted['leftovers'] = leftovers(crash['session'])
    results['adoption'] = adopted
    print(json.dumps(adopted, ensure_ascii=False), flush=True)
    clean = all(c['ready'] and c['stopped'] and not c['leftovers']['gazebo'] and not c['leftovers']['tagged']
                and not c['leftovers']['ros_nodes'] for c in results['cycles'])
    results['all_cycles_clean'] = clean
    results['adoption_clean'] = (adopted['adopted'] and adopted['stopped'] and adopted['same_session']
                                 and not adopted['leftovers']['gazebo'] and not adopted['leftovers']['tagged'])
    Path(out).parent.joinpath('04_live_check.json').write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps({'all_cycles_clean': clean, 'adoption_clean': results['adoption_clean']}), flush=True)
    window.close()


if __name__ == '__main__':
    if sys.argv[1] == '--crash-child':
        crash_child(sys.argv[2], sys.argv[3])
    else:
        main(sys.argv[1], sys.argv[2], int(sys.argv[3]))
