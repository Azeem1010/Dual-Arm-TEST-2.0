"""Resource state; only physical/vision evidence permits release and commit."""
import threading
import uuid


class ZoneManager:
    def __init__(self):
        self.owner = None
        self._token = None
        self.faulted = False
        self._lock = threading.Lock()

    def acquire(self, arm, *, observation_clear):
        with self._lock:
            if arm not in ('arm1', 'arm2') or self.owner is not None or self.faulted or observation_clear is not True:
                raise RuntimeError('B zone unavailable or observation not clear')
            self.owner, self._token = arm, str(uuid.uuid4())
            return self._token

    def fault(self, token):
        with self._lock:
            if not self._token or token != self._token:
                raise RuntimeError('Not B owner')
            self.faulted = True

    def release(self, token, *, withdrawn, observation_clear):
        with self._lock:
            if not self._token or token != self._token or withdrawn is not True or observation_clear is not True:
                raise RuntimeError('B release requires owner and verified withdrawal')
            self.owner, self._token = None, None
            self.faulted = False

    def restore(self, arm):
        """Rebuild ownership from the journal after a restart; stays faulted until recovery."""
        with self._lock:
            if arm not in ('arm1', 'arm2') or self.owner is not None:
                raise RuntimeError('B zone ownership cannot be restored')
            self.owner, self._token, self.faulted = arm, str(uuid.uuid4()), True
            return self._token


def _contiguous_count(occupied):
    if len(occupied) != 8 or any(type(v) is not bool for v in occupied):
        raise RuntimeError('Exactly eight boolean slot observations required')
    count = sum(occupied)
    if occupied != [True]*count+[False]*(8-count):
        raise RuntimeError('Nonsequential or regressed slot observation')
    return count


class SlotManager:
    def __init__(self):
        self.committed = 0
        self.reserved = None

    def restore(self, occupied):
        """Adopt a verified observation after recovery; discards any open reservation."""
        self.committed, self.reserved = _contiguous_count(occupied), None

    def reserve(self, occupied):
        count = _contiguous_count(occupied)
        if count < self.committed:
            raise RuntimeError('Nonsequential or regressed slot observation')
        if self.reserved is not None:
            raise RuntimeError('Outstanding placement must be resolved')
        if count == 8:
            raise RuntimeError('C zone full')
        self.committed = count
        self.reserved = count + 1
        return self.reserved

    def commit(self, slot, *, placed, order_ok):
        if slot != self.reserved or placed is not True or order_ok is not True:
            raise RuntimeError('Placement unverified; reservation retained')
        self.committed, self.reserved = slot, None
