"""Read-only check of a CM-530 board; never sends motion, HOLD or torque commands.

Only one process may own the port, so stop the ROS driver first. Any error ends the
probe without retrying, because the protocol cannot match a late reply to a request.
"""
import argparse
import errno
import fcntl
import json
import os
import re
import select
import sys
import termios
import time

ALLOWED_COMMANDS = ('VERSION', 'PING', 'GET_HOME,arm1', 'GET_HOME,arm2', 'READ,arm1', 'READ,arm2')
_POSE = r',(\d{1,4}),(\d{1,4}),(\d{1,4}),(\d{1,4})'
_REPLIES = {'VERSION': r'VERSION,5\Z', 'PING': r'PONG\Z', 'GET_HOME,arm1': rf'HOME,arm1{_POSE}\Z',
            'GET_HOME,arm2': rf'HOME,arm2{_POSE}\Z', 'READ,arm1': rf'POS,arm1{_POSE}\Z', 'READ,arm2': rf'POS,arm2{_POSE}\Z'}
_FIRMWARE_LINE_BYTES = 96
_STARTUP_LISTEN_S = 0.2


class ProbeError(RuntimeError):
    """The probe stopped; the board state is reported as far as it is known."""


class SerialPort:
    """Exclusive raw access to a serial device at the board's fixed 57600 8N1."""

    def __init__(self, path):
        self._fd = os.open(path, os.O_RDWR | os.O_NOCTTY | os.O_NONBLOCK)
        try:
            fcntl.ioctl(self._fd, termios.TIOCEXCL)
            attributes = termios.tcgetattr(self._fd)
            attributes[0] = 0
            attributes[1] = 0
            attributes[2] = termios.CS8 | termios.CREAD | termios.CLOCAL
            attributes[3] = 0
            attributes[4] = attributes[5] = termios.B57600
            termios.tcsetattr(self._fd, termios.TCSANOW, attributes)
        except Exception:
            os.close(self._fd)
            raise

    def write(self, data):
        deadline = time.monotonic() + 2.0
        while data:
            try:
                data = data[os.write(self._fd, data):]
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise ProbeError('Serial write timed out') from None
                select.select([], [self._fd], [], 0.05)

    def read(self, timeout):
        ready, _, _ = select.select([self._fd], [], [], timeout)
        if not ready:
            return b''
        try:
            return os.read(self._fd, 256)
        except OSError as error:
            if error.errno in (errno.EAGAIN, errno.EWOULDBLOCK):
                return b''
            raise

    def close(self):
        os.close(self._fd)


class Probe:
    def __init__(self, port, timeout, clock=time.monotonic):
        self._port, self._timeout, self._clock = port, timeout, clock
        self._buffer = b''
        self.exchanges = []

    def _read_line(self, deadline):
        while True:
            self._buffer = self._buffer.lstrip(b'\r\n')
            match = re.search(b'[\r\n]', self._buffer)
            if match:
                line = self._buffer[:match.start()]
                self._buffer = self._buffer[match.end():]
                return line.decode('ascii', errors='replace')
            remaining = deadline - self._clock()
            if remaining <= 0:
                return None
            self._buffer += self._port.read(remaining)

    def prepare(self):
        """Clear a partial line left in the firmware and tolerate a READY from a recent boot."""
        self._port.write(b'\x7f' * _FIRMWARE_LINE_BYTES)
        deadline = self._clock() + _STARTUP_LISTEN_S
        while True:
            line = self._read_line(deadline)
            if line is None:
                return
            if line != 'READY,5':
                raise ProbeError(f'Unexpected startup line: {line}')

    def send(self, command):
        if command not in ALLOWED_COMMANDS:
            raise ProbeError(f'{command} is not a read-only probe command')
        self._port.write(command.encode('ascii') + b'\n')
        reply = self._read_line(self._clock() + self._timeout)
        self.exchanges.append({'tx': command, 'rx': reply})
        if reply is None:
            raise ProbeError(f'No reply to {command}; the result is unknown')
        match = re.match(_REPLIES[command], reply)
        if match is None:
            raise ProbeError(f'Unexpected reply to {command}: {reply}')
        return [int(value) for value in match.groups()]


def run_probe(port, timeout):
    probe = Probe(port, timeout)
    report = {'status': 'FAIL', 'exchanges': probe.exchanges, 'home': {}, 'position': {}}
    try:
        probe.prepare()
        probe.send('VERSION')
        probe.send('PING')
        for arm in ('arm1', 'arm2'):
            report['home'][arm] = probe.send(f'GET_HOME,{arm}')
            report['position'][arm] = probe.send(f'READ,{arm}')
        report['status'] = 'PASS'
    except ProbeError as error:
        report['error'] = str(error)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description='Read-only CM-530 check. Moves nothing.')
    parser.add_argument('--port', required=True)
    parser.add_argument('--timeout', type=float, default=1.0)
    args = parser.parse_args(argv)
    try:
        port = SerialPort(args.port)
    except OSError as error:
        print(json.dumps({'status': 'FAIL', 'error': f'Cannot open {args.port} exclusively: {error}'}))
        return 1
    try:
        report = run_probe(port, args.timeout)
    finally:
        port.close()
    print(json.dumps(report, indent=2))
    return 0 if report['status'] == 'PASS' else 1


if __name__ == '__main__':
    sys.exit(main())
