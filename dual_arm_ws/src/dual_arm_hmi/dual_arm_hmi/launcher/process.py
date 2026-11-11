"""Starts and stops the system as its own process group, so it outlives the interface.

The session is written to disk; a restarted interface adopts it instead of starting another.
Stopping escalates SIGINT, SIGTERM, SIGKILL and then removes Gazebo servers left in this
partition, which is a known problem when the launch ends.
"""
from dataclasses import dataclass
import json
import os
from pathlib import Path
import re
import signal
import subprocess
import threading
import time
import uuid

STATE_DIR = Path('~/.ros/dual_arm_hmi').expanduser()
GAZEBO_PATTERN = re.compile(r'(^|\s|/)gz sim(\s|$)')
# Every started process inherits this, so leftovers that left the process group can still be found.
SESSION_VARIABLE = 'DUAL_ARM_HMI_SESSION'
INTERRUPT_WAIT_S = 20.0
TERMINATE_WAIT_S = 5.0
_POLL_S = 0.2


@dataclass(frozen=True)
class LaunchStatus:
    state: str = 'idle'  # idle, running, stopping, failed
    mode: str = ''
    started_at: float = 0.0
    log_path: str = ''
    message: str = ''
    adopted: bool = False


def _alive(pgid):
    try:
        os.killpg(pgid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def _processes():
    """(pid, command line, environment) for every process this user can read."""
    for entry in Path('/proc').iterdir():
        if not entry.name.isdigit():
            continue
        try:
            command = (entry / 'cmdline').read_bytes().replace(b'\0', b' ').decode(errors='replace').strip()
            environ = (entry / 'environ').read_bytes().split(b'\0')
        except OSError:
            continue
        yield int(entry.name), command, environ


def tagged_processes(session):
    """Pids still carrying this session's tag."""
    token = f'{SESSION_VARIABLE}={session}'.encode()
    return [pid for pid, _, environ in _processes() if pid != os.getpid() and token in environ]


def gazebo_processes(partition=None):
    """Gazebo server pids, optionally only those started with this GZ_PARTITION."""
    wanted = None if partition is None else f'GZ_PARTITION={partition}'.encode()
    found = []
    for pid, command, environ in _processes():
        if pid == os.getpid() or not GAZEBO_PATTERN.search(command):
            continue
        if wanted is None or wanted in environ:
            found.append(pid)
    return found


class Launcher:
    def __init__(self, state_dir=STATE_DIR, clock=time.time):
        self._dir = Path(state_dir)
        self._dir.mkdir(parents=True, exist_ok=True)
        (self._dir / 'logs').mkdir(exist_ok=True)
        self._session_file = self._dir / 'session.json'
        self._clock = clock
        self._lock = threading.Lock()
        self._process, self._pgid, self._log, self._session = None, None, None, ''
        self._status = LaunchStatus()
        self._stopping_thread = None
        self._adopt()

    # --- persistence ---

    def _save(self):
        data = {'pgid': self._pgid, 'session': self._session, 'mode': self._status.mode, 'started_at': self._status.started_at,
                'log_path': self._status.log_path, 'partition': os.environ.get('GZ_PARTITION', '')}
        self._session_file.write_text(json.dumps(data), encoding='utf-8')

    def _forget(self):
        self._session_file.unlink(missing_ok=True)

    def _adopt(self):
        """Take over a session left by an earlier interface, or discard it if it has ended."""
        try:
            data = json.loads(self._session_file.read_text(encoding='utf-8'))
            pgid = int(data['pgid'])
        except (OSError, ValueError, KeyError, TypeError):
            self._forget()
            return
        if not _alive(pgid):
            self._forget()
            return
        self._pgid, self._session = pgid, str(data.get('session', ''))
        self._status = LaunchStatus('running', data.get('mode', ''), float(data.get('started_at', 0.0)),
                                    data.get('log_path', ''), '接回先前啟動的系統', adopted=True)

    # --- control ---

    def status(self):
        with self._lock:
            self._check_exit()
            return self._status

    def _check_exit(self):
        if self._status.state != 'running':
            return
        if self._process is not None:
            code = self._process.poll()
            if code is None:
                return
            self._process = None
        elif self._pgid is not None and _alive(self._pgid):
            return
        else:
            code = None
        self._close_log()
        self._forget()
        reason = '系統意外結束' + ('' if code is None else f'（代碼 {code}）')
        self._status = LaunchStatus('failed', self._status.mode, self._status.started_at, self._status.log_path, reason)
        self._pgid = None

    def start(self, mode, command, environment=None):
        """Start a command in a new session. Returns an error message, or '' on success."""
        with self._lock:
            self._check_exit()
            if self._status.state in ('running', 'stopping'):
                return '系統已在執行'
            stamp = time.strftime('%Y%m%d_%H%M%S')
            log_path = self._dir / 'logs' / f'{stamp}_{mode}.log'
            self._log = open(log_path, 'w', encoding='utf-8')
            self._session = uuid.uuid4().hex
            env = {**os.environ, **(environment or {}), SESSION_VARIABLE: self._session}
            try:
                self._process = subprocess.Popen(list(command), stdout=self._log, stderr=subprocess.STDOUT,
                                                 stdin=subprocess.DEVNULL, start_new_session=True, env=env)
            except OSError as error:
                self._close_log()
                self._status = LaunchStatus('failed', mode, self._clock(), str(log_path), f'無法啟動：{error}')
                return self._status.message
            self._pgid = self._process.pid
            self._status = LaunchStatus('running', mode, self._clock(), str(log_path))
            self._save()
            return ''

    def stop_async(self):
        """Begin stopping without blocking the caller."""
        with self._lock:
            self._check_exit()
            if self._status.state != 'running':
                return False
            self._status = LaunchStatus('stopping', self._status.mode, self._status.started_at, self._status.log_path,
                                        adopted=self._status.adopted)
            self._stopping_thread = threading.Thread(target=self._stop, daemon=True)
            self._stopping_thread.start()
            return True

    def wait_stopped(self, timeout=None):
        thread = self._stopping_thread
        if thread is not None:
            thread.join(timeout)

    def _wait_gone(self, deadline):
        while self._clock() < deadline:
            if self._process is not None:
                self._process.poll()
            if not _alive(self._pgid):
                return True
            time.sleep(_POLL_S)
        return not _alive(self._pgid)

    def _signal(self, number):
        try:
            os.killpg(self._pgid, number)
        except ProcessLookupError:
            pass

    def _stop(self):
        partition = os.environ.get('GZ_PARTITION')
        for number, wait in ((signal.SIGINT, INTERRUPT_WAIT_S), (signal.SIGTERM, TERMINATE_WAIT_S), (signal.SIGKILL, TERMINATE_WAIT_S)):
            self._signal(number)
            if self._wait_gone(self._clock() + wait):
                break
        if self._process is not None:
            try:
                self._process.wait(timeout=TERMINATE_WAIT_S)
            except subprocess.TimeoutExpired:
                pass
        leftover = remove_gazebo(partition) if partition else []
        escaped = remove_tagged(self._session) if self._session else []
        with self._lock:
            self._close_log()
            self._forget()
            self._process, self._pgid, self._session = None, None, ''
            removed = leftover + [pid for pid in escaped if pid not in leftover]
            message = f'已清除殘留程序 {removed}' if removed else ''
            self._status = LaunchStatus('idle', self._status.mode, message=message)

    def _close_log(self):
        if self._log is not None:
            self._log.close()
            self._log = None


def remove_gazebo(partition, wait=TERMINATE_WAIT_S):
    """Terminate Gazebo servers left in this partition. Returns the pids that had to be removed."""
    pids = gazebo_processes(partition)
    for number in (signal.SIGTERM, signal.SIGKILL):
        for pid in pids:
            try:
                os.kill(pid, number)
            except ProcessLookupError:
                pass
        deadline = time.monotonic() + wait
        while time.monotonic() < deadline and gazebo_processes(partition):
            time.sleep(_POLL_S)
        if not gazebo_processes(partition):
            break
    return pids


def remove_tagged(session, wait=TERMINATE_WAIT_S):
    """Kill processes from this session that escaped its process group. Returns their pids."""
    pids = tagged_processes(session)
    for pid in pids:
        try:
            os.kill(pid, signal.SIGKILL)
        except ProcessLookupError:
            pass
    deadline = time.monotonic() + wait
    while time.monotonic() < deadline and tagged_processes(session):
        time.sleep(_POLL_S)
    return pids


def tail(path, lines=20):
    try:
        return Path(path).read_text(encoding='utf-8', errors='replace').splitlines()[-lines:]
    except OSError:
        return []
