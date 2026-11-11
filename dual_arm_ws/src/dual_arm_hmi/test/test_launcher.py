"""Real processes on Linux: start, stop, escalation, adoption after a crash and Gazebo leftovers."""
import json
import os
from pathlib import Path
import subprocess
import sys
import time

import pytest

pytestmark = pytest.mark.skipif(sys.platform != 'linux', reason='process groups and /proc are Linux only')

from dual_arm_hmi.launcher import process  # noqa: E402
from dual_arm_hmi.launcher.process import Launcher, gazebo_processes, remove_gazebo, tagged_processes  # noqa: E402


def wait_for(predicate, timeout=10.0):
    deadline = time.monotonic() + timeout
    while time.monotonic() < deadline:
        if predicate():
            return True
        time.sleep(0.05)
    return predicate()


def group_alive(pgid):
    try:
        os.killpg(pgid, 0)
        return True
    except ProcessLookupError:
        return False


@pytest.fixture(autouse=True)
def quick_escalation(monkeypatch):
    monkeypatch.setattr(process, 'INTERRUPT_WAIT_S', 1.0)
    monkeypatch.setattr(process, 'TERMINATE_WAIT_S', 1.0)


def test_start_records_a_session_and_stop_removes_every_child(tmp_path):
    launcher = Launcher(tmp_path)
    assert launcher.start('Mock', ['bash', '-c', 'sleep 60 & sleep 60 & wait']) == ''
    status = launcher.status()
    assert status.state == 'running' and Path(status.log_path).exists()
    pgid = json.loads((tmp_path / 'session.json').read_text())['pgid']
    assert group_alive(pgid)
    assert launcher.stop_async()
    assert launcher.status().state == 'stopping'
    launcher.wait_stopped(15)
    assert launcher.status().state == 'idle'
    assert not group_alive(pgid) and not (tmp_path / 'session.json').exists()


def test_a_process_ignoring_interrupt_is_still_stopped(tmp_path):
    launcher = Launcher(tmp_path)
    launcher.start('Mock', ['bash', '-c', 'trap "" INT TERM; while true; do sleep 0.1; done'])
    pgid = launcher._pgid
    launcher.stop_async()
    launcher.wait_stopped(15)
    assert not group_alive(pgid) and launcher.status().state == 'idle'


def test_a_child_that_left_the_process_group_is_still_removed(tmp_path):
    launcher = Launcher(tmp_path)
    launcher.start('Mock', ['bash', '-c', 'setsid sleep 60 & sleep 60'])
    session = launcher._session
    assert wait_for(lambda: len(tagged_processes(session)) >= 2)
    launcher.stop_async()
    launcher.wait_stopped(15)
    assert tagged_processes(session) == []
    assert '殘留' in launcher.status().message


def test_second_start_is_refused(tmp_path):
    launcher = Launcher(tmp_path)
    launcher.start('Mock', ['sleep', '60'])
    assert launcher.start('Mock', ['sleep', '60']) == '系統已在執行'
    launcher.stop_async()
    launcher.wait_stopped(15)


def test_unexpected_exit_is_reported_with_its_code(tmp_path):
    launcher = Launcher(tmp_path)
    launcher.start('Mock', ['bash', '-c', 'echo boom; exit 3'])
    assert wait_for(lambda: launcher.status().state == 'failed')
    status = launcher.status()
    assert '代碼 3' in status.message and 'boom' in Path(status.log_path).read_text()
    assert not (tmp_path / 'session.json').exists()
    assert launcher.start('Mock', ['true']) == ''


def test_a_restarted_interface_adopts_the_running_system(tmp_path):
    script = ('import sys; from dual_arm_hmi.launcher.process import Launcher; '
              f'l = Launcher({str(tmp_path)!r}); l.start("模擬", ["sleep", "60"]); import os; os._exit(0)')
    subprocess.run([sys.executable, '-c', script], check=True, env={**os.environ, 'PYTHONPATH': os.pathsep.join(sys.path)})
    adopted = Launcher(tmp_path)
    status = adopted.status()
    assert status.state == 'running' and status.adopted and status.mode == '模擬'
    pgid = adopted._pgid
    adopted.stop_async()
    adopted.wait_stopped(15)
    assert not group_alive(pgid) and adopted.status().state == 'idle'


def test_a_session_that_already_ended_is_discarded(tmp_path):
    finished = subprocess.Popen(['true'], start_new_session=True)
    finished.wait()
    (tmp_path / 'session.json').write_text(json.dumps({'pgid': finished.pid, 'mode': 'Mock'}))
    launcher = Launcher(tmp_path)
    assert launcher.status().state == 'idle' and not (tmp_path / 'session.json').exists()


def test_a_corrupt_session_file_is_discarded(tmp_path):
    (tmp_path / 'session.json').write_text('not json')
    assert Launcher(tmp_path).status().state == 'idle'


def test_gazebo_leftovers_are_found_and_removed_only_in_this_partition(tmp_path):
    env = {**os.environ, 'GZ_PARTITION': 'hmi_test_partition'}
    leftover = subprocess.Popen(['bash', '-c', 'exec -a "gz sim fake" sleep 60'], env=env, start_new_session=True)
    try:
        assert wait_for(lambda: leftover.pid in gazebo_processes('hmi_test_partition'))
        assert leftover.pid not in gazebo_processes('another_partition')
        assert remove_gazebo('hmi_test_partition', wait=2.0) == [leftover.pid]
        assert wait_for(lambda: leftover.poll() is not None)
    finally:
        if leftover.poll() is None:
            leftover.kill()
