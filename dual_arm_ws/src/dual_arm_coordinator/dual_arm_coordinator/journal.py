"""Persistent task record. Every state is on disk before the motion it describes."""
import copy
import fcntl
import hashlib
import json
import os
from pathlib import Path
import threading

ARMS = ('arm1', 'arm2')
HOLDING_VALUES = ('empty', 'held', 'unknown')
CLEAN_STATES = ('IDLE', 'SUCCEEDED', 'FULL')
_FIELDS = ('state', 'active_arm', 'holding', 'b_owner', 'occupied', 'slot', 'completed',
           'cycle_id', 'message', 'config_fingerprint')


class JournalError(RuntimeError):
    """The record is unusable; a person must inspect the workstation."""


def config_fingerprint(config, model_text=''):
    canonical = json.dumps(config, sort_keys=True, separators=(',', ':'))
    return hashlib.sha256((canonical + model_text).encode('utf-8')).hexdigest()


def _validate(data):
    if not isinstance(data, dict) or any(key not in data for key in _FIELDS):
        raise JournalError('Journal is missing required fields')
    occupied = data['occupied']
    if not isinstance(occupied, list) or len(occupied) != 8 or any(type(v) is not bool for v in occupied):
        raise JournalError('Journal occupancy must be eight booleans')
    holding = data['holding']
    if not isinstance(holding, dict) or set(holding) != set(ARMS) or any(v not in HOLDING_VALUES for v in holding.values()):
        raise JournalError('Journal holding state is invalid')
    if data['b_owner'] not in ('', *ARMS):
        raise JournalError('Journal B owner is invalid')


class Journal:
    def __init__(self, path, fingerprint):
        self.path = Path(path).expanduser()
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._mutex = threading.RLock()
        self._lock_file = self.path.with_suffix('.lock').open('a')
        try:
            fcntl.flock(self._lock_file, fcntl.LOCK_EX | fcntl.LOCK_NB)
        except OSError as error:
            self._lock_file.close()
            raise JournalError(f'Journal {self.path} is held by another process') from error
        self.fingerprint = fingerprint
        try:
            self._data = self._load()
            self._write()
        except Exception:
            self.close()
            raise

    def _fresh(self):
        return dict(state='IDLE', active_arm='', holding={arm: 'empty' for arm in ARMS}, b_owner='',
                    occupied=[False] * 8, slot=0, completed=0, cycle_id='', message='',
                    config_fingerprint=self.fingerprint)

    def _load(self):
        if not self.path.exists():
            return self._fresh()
        try:
            data = json.loads(self.path.read_text(encoding='utf-8'))
        except (OSError, ValueError) as error:
            raise JournalError(f'Journal {self.path} cannot be read: {error}') from error
        _validate(data)
        if data['config_fingerprint'] != self.fingerprint:
            data.update(state='FAULT', message='Configuration or model changed since the last run; inspect and recover')
        elif (data['state'] not in CLEAN_STATES or data['b_owner']
              or any(value != 'empty' for value in data['holding'].values())):
            data.update(state='FAULT', message='Previous run did not finish; inspect and recover')
        return data

    def _write(self):
        temporary = self.path.with_suffix('.tmp')
        with temporary.open('w', encoding='utf-8') as handle:
            json.dump(self._data, handle, indent=2, sort_keys=True)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temporary, self.path)

    @property
    def data(self):
        with self._mutex:
            return copy.deepcopy(self._data)

    def update(self, **fields):
        unknown = set(fields) - set(_FIELDS)
        if unknown:
            raise JournalError(f'Unknown journal fields: {sorted(unknown)}')
        with self._mutex:
            candidate = {**self._data, **copy.deepcopy(fields)}
            _validate(candidate)
            self._data = candidate
            self._write()

    def close(self):
        fcntl.flock(self._lock_file, fcntl.LOCK_UN)
        self._lock_file.close()
