#!/usr/bin/env python3
"""Save README screenshots of the operator interface from a live simulation.

The window (offscreen, 1920x1080) starts the simulation through its own button,
starts one transfer, and presses the stop button during it. Everything shown is the
real system state; nothing is staged. Run it with no other simulation running:

    capture_hmi_images.py IMAGES_DIR STATE_DIR

Writes ui_ready.png, ui_working.png and ui_stopped.png, then shuts the system down.
"""
import os
from pathlib import Path
import sys
import time

os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')

from ament_index_python.packages import get_package_prefix, get_package_share_directory  # noqa: E402
from PyQt5.QtTest import QTest  # noqa: E402

from dual_arm_hmi.app import create_application  # noqa: E402
from dual_arm_hmi.launcher.process import Launcher  # noqa: E402
from dual_arm_hmi.launcher.profiles import load_profiles, workspace_from_prefix  # noqa: E402
from dual_arm_hmi.model.state import Action, Mode, Phase  # noqa: E402
from dual_arm_hmi.sources.live_source import LiveSource, SettingsStore  # noqa: E402
from dual_arm_hmi.sources.ros_command import RosCommander  # noqa: E402
from dual_arm_hmi.sources.ros_source import RosSource  # noqa: E402
from dual_arm_hmi.ui.main_window import MainWindow  # noqa: E402

READY_TIMEOUT_S = 420
STEP_TIMEOUT_S = 900
# Arm 1 carries the cap into zone B: cameras, motors, task steps and the B interlock are all in use.
WORKING_STATE = 'ARM1:DESCEND_B'


def main(images, state_dir):
    app = create_application(['capture'])
    profiles = load_profiles(os.path.join(get_package_share_directory('dual_arm_hmi'), 'config', 'profiles.yaml'),
                             Path(state_dir) / 'none.yaml')
    store = SettingsStore(str(Path(state_dir) / 'settings.json'))
    store.save({'mode': Mode.SIMULATION.value, 'cycles': 1, 'journal_path': str(Path(state_dir) / 'journal.json')})
    launcher = Launcher(state_dir)
    source = LiveSource(RosSource(), launcher, profiles, workspace_from_prefix(get_package_prefix('dual_arm_hmi')), store,
                        commander=lambda domain: RosCommander(domain_id=domain))
    window = MainWindow(source)
    window._ask = lambda *args: True
    window.resize(1920, 1080)
    window.show()

    def pump(seconds):
        end = time.monotonic() + seconds
        while time.monotonic() < end:
            window.refresh()
            app.processEvents()
            QTest.qWait(100)

    def wait(predicate, timeout, label):
        end = time.monotonic() + timeout
        while time.monotonic() < end:
            pump(0.2)
            if predicate(source.snapshot()):
                print(f'{label}: reached', flush=True)
                return
        raise SystemExit(f'{label}: timed out')

    def save(name):
        window.refresh()
        app.processEvents()
        path = Path(images) / f'{name}.png'
        window.grab().save(str(path))
        print(f'saved {path}', flush=True)

    def press(action):
        row = window.control.rows[action]
        assert row.button.isEnabled(), f'{action.value} disabled: {row.reason.text()}'
        row.button.click()

    try:
        press(Action.START_SYSTEM)
        wait(lambda s: s.phase is Phase.READY and s.task is not None and s.controllers_active
             and len(s.cameras) == 3 and all(camera.has_signal for camera in s.cameras.values()), READY_TIMEOUT_S, 'ready')
        pump(4)  # let every camera and annotation refresh
        save('ui_ready')
        press(Action.START_TASK)
        wait(lambda s: s.task is not None and s.task.state == WORKING_STATE, STEP_TIMEOUT_S, WORKING_STATE)
        pump(1.5)
        save('ui_working')
        window.control.stop.click()
        wait(lambda s: s.latched and s.safety.controllers_stopped and s.task.state == 'FAULT' and not s.busy, 60, 'stopped')
        pump(2)
        save('ui_stopped')
    finally:
        if launcher.status().state == 'running':
            launcher.stop_async()
            launcher.wait_stopped(120)
        window.close()
    return 0


if __name__ == '__main__':
    sys.exit(main(sys.argv[1], sys.argv[2]))
