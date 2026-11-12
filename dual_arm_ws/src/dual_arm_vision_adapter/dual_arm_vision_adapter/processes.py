"""Child process groups that die with their parent, and a check for who holds a device."""
import ctypes
import os
import signal
import subprocess

_PR_SET_PDEATHSIG = 1


def _die_with_parent():
    """Runs in the child before exec: SIGTERM it if the switch process dies."""
    libc = ctypes.CDLL('libc.so.6', use_errno=True)
    libc.prctl(_PR_SET_PDEATHSIG, signal.SIGTERM)


class GroupProcess:
    """One command in its own process group; signals reach every process it started."""

    def __init__(self, argv):
        self._argv, self._popen = list(argv), None
        # Once the group is gone its id may be reused by an unrelated group, so it is never signalled again.
        self._gone = False

    def start(self):
        self._popen = subprocess.Popen(self._argv, start_new_session=True, preexec_fn=_die_with_parent)

    def running(self):
        """True while any process of the group is left, not only the direct child."""
        if self._popen is None or self._gone:
            return False
        self._popen.poll()
        try:
            os.killpg(self._popen.pid, 0)
        except ProcessLookupError:
            self._gone = True
            return False
        except PermissionError:
            return True
        return True

    def _signal(self, number):
        if self._popen is None or not self.running():
            return
        try:
            os.killpg(self._popen.pid, number)
        except ProcessLookupError:
            pass
        self._popen.poll()

    def terminate(self):
        self._signal(signal.SIGTERM)

    def kill(self):
        self._signal(signal.SIGKILL)


def device_in_use(path):
    """True when any process has the device (after resolving links) open."""
    target = os.path.realpath(path)
    try:
        pids = [name for name in os.listdir('/proc') if name.isdigit()]
    except OSError:
        return False
    for pid in pids:
        folder = f'/proc/{pid}/fd'
        try:
            names = os.listdir(folder)
        except OSError:
            continue
        for name in names:
            try:
                if os.readlink(f'{folder}/{name}') == target:
                    return True
            except OSError:
                continue
    return False
