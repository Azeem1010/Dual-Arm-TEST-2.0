"""One-time operator confirmation tokens. Free of ROS so it can be unit tested."""
import threading
import time
import uuid


class TokenError(RuntimeError):
    """The token cannot confirm this operation."""


class TokenGate:
    """Holds at most one outstanding token; issuing a new one invalidates the old."""

    def __init__(self, ttl_s, clock=time.monotonic):
        if ttl_s <= 0:
            raise ValueError('ttl_s must be positive')
        self._ttl, self._clock = ttl_s, clock
        self._lock = threading.Lock()
        self._token, self._operation, self._expires = None, None, 0.0

    def issue(self, operation):
        with self._lock:
            self._token, self._operation = uuid.uuid4().hex, operation
            self._expires = self._clock() + self._ttl
            return self._token

    @property
    def current(self):
        with self._lock:
            return self._token, self._operation

    def revoke(self, token):
        """Invalidate token if still outstanding, so a late confirmation is refused."""
        with self._lock:
            if token == self._token:
                self._token, self._operation = None, None

    def consume(self, token, operation):
        with self._lock:
            if self._token is None or token != self._token or operation != self._operation:
                raise TokenError(f'Token does not confirm {operation}')
            if self._clock() > self._expires:
                self._token, self._operation = None, None
                raise TokenError(f'Token for {operation} has expired')
            self._token, self._operation = None, None
