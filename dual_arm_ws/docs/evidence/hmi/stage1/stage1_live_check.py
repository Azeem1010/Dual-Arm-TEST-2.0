"""Runs the real window against a running simulation and records what it shows.

Usage: stage1_live_check.py OUT_DIR LAUNCH_PID
Starts one transfer through the coordinator's own service, which only exists in this
simulation, then stops the launch to check that a lost system is announced.
"""
import json
import os
import signal
import subprocess
import sys
import time

os.environ['QT_QPA_PLATFORM'] = 'offscreen'

from PyQt5.QtTest import QTest  # noqa: E402

from dual_arm_hmi.app import create_application  # noqa: E402
from dual_arm_hmi.model.state import Phase, banner, evaluate_actions  # noqa: E402
from dual_arm_hmi.sources.ros_source import RosSource  # noqa: E402
from dual_arm_hmi.ui.main_window import MainWindow  # noqa: E402

out, launch_pid = sys.argv[1], int(sys.argv[2])
app = create_application(['check'])
source = RosSource()
window = MainWindow(source)
window.resize(1920, 1080)
window.show()
QTest.qWait(500)
result = {}


def pump(seconds):
    end = time.monotonic() + seconds
    while time.monotonic() < end:
        window.refresh()
        app.processEvents()
        QTest.qWait(100)


def capture(name):
    window.refresh()
    app.processEvents()
    window.grab().save(f'{out}/{name}.png')


def summary(snapshot):
    return {'mode': snapshot.mode.value, 'phase': snapshot.phase.value, 'connected': snapshot.ros_connected,
            'monitor_only': snapshot.monitor_only, 'controllers_active': snapshot.controllers_active,
            'decision_source': snapshot.decision_source, 'task_state': snapshot.task.state if snapshot.task else None,
            'busy': snapshot.busy, 'joints': len(snapshot.joints), 'joint_age_s': snapshot.joint_age_s,
            'commands_seen': sum(1 for joint in snapshot.joints if joint.command is not None),
            'limits_seen': sum(1 for joint in snapshot.joints if joint.lower is not None),
            'cameras': {name: {'fps': round(c.fps, 1), 'age_s': round(c.age_s, 3) if c.age_s is not None else None,
                               'calibration': c.calibration, 'annotation': c.has_annotation} for name, c in snapshot.cameras.items()},
            'gazebo_views': {name: round(c.fps, 1) for name, c in snapshot.gazebo_views.items()},
            'zones': None if snapshot.zones is None else snapshot.zones.__dict__, 'safety': None if snapshot.safety is None else snapshot.safety.__dict__,
            'banner': banner(snapshot).title}


deadline = time.monotonic() + 300
while time.monotonic() < deadline:
    pump(1.0)
    snapshot = source.snapshot()
    ready = snapshot.phase is Phase.READY and snapshot.task is not None and len(snapshot.cameras) == 3 and len(snapshot.joints) == 8
    annotated = all(c.has_annotation for c in snapshot.cameras.values()) if snapshot.cameras else False
    if ready and annotated and snapshot.gazebo_views:
        break
pump(6.0)
snapshot = source.snapshot()
result['ready'] = summary(snapshot)
probe = subprocess.Popen([sys.executable, os.path.dirname(os.path.abspath(__file__)) + '/stage1_rtf.py', '30'], stdout=subprocess.PIPE, text=True)
while probe.poll() is None:
    pump(1.0)
result['speed_with_ui'] = json.loads(probe.stdout.read())
result['every_action_refused'] = all(not state.enabled for state in evaluate_actions(snapshot, True).values())
capture('live_ready')

# Annotated and raw images must differ, otherwise the toggle would prove nothing.
differs = {}
for name in ('env', 'arm1', 'arm2'):
    annotated_frame, raw_frame = source.frame(name, True), source.frame(name, False)
    differs[name] = bool(annotated_frame is not None and raw_frame is not None and (annotated_frame != raw_frame).any())
result['annotation_differs_from_raw'] = differs

# The keyboard stop has to be refused visibly, never silently accepted.
window._send(__import__('dual_arm_hmi.model.state', fromlist=['Action']).Action.STOP)
pump(0.3)
result['stop_feedback'] = source.snapshot().feedback.phase

window.control.gazebo.click()
pump(2.0)
for index in range(window.gazebo_panel.selector.count()):
    window.gazebo_panel.selector.setCurrentIndex(index)
    pump(1.5)
    result[f'gazebo_image_{window.gazebo_panel.current_view()}'] = window.gazebo_panel.view.image is not None
capture('live_gazebo_view')
window.control.gazebo.click()
pump(0.5)

info = subprocess.run(['ros2', 'node', 'info', '/dual_arm_hmi_monitor'], capture_output=True, text=True, timeout=60)
with open(f'{out}/05_node_info.txt', 'w', encoding='utf-8') as handle:
    handle.write(info.stdout + info.stderr)

started = subprocess.run(['ros2', 'service', 'call', '/dual_arm/start', 'std_srvs/srv/Trigger', '{}'], capture_output=True, text=True, timeout=60)
result['start_call'] = started.stdout.strip().splitlines()[-1] if started.stdout.strip() else started.stderr

seen, timings, shots = [], [], set()
deadline = time.monotonic() + 420
while time.monotonic() < deadline:
    tick = time.monotonic()
    window.refresh()
    timings.append(time.monotonic() - tick)
    app.processEvents()
    QTest.qWait(100)
    snapshot = source.snapshot()
    state = snapshot.task.state if snapshot.task else None
    if state and (not seen or seen[-1] != state):
        seen.append(state)
    for key, name in (('ARM1:DESCEND_B', 'live_arm1_in_b'), ('ARM2:APPROACH_C', 'live_arm2_to_c')):
        if state == key and name not in shots:
            shots.add(name)
            capture(name)
    if len(seen) > 2 and state in ('SUCCEEDED', 'FAULT', 'FULL') and snapshot.task and not snapshot.task.busy:
        break
result['states_seen'] = seen
result['refresh_ms'] = {'mean': round(1000 * sum(timings) / len(timings), 1), 'max': round(1000 * max(timings), 1), 'samples': len(timings)}
pump(2.0)
result['finished'] = summary(source.snapshot())
capture('live_finished')

os.killpg(os.getpgid(launch_pid), signal.SIGINT)
pump(6.0)
result['after_stop'] = summary(source.snapshot())
capture('live_system_lost')
with open(f'{out}/04_live_check.json', 'w', encoding='utf-8') as handle:
    json.dump(result, handle, indent=2, ensure_ascii=False, default=str)
print(json.dumps(result, indent=2, ensure_ascii=False, default=str), flush=True)
window.close()
