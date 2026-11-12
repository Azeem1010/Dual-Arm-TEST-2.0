"""Streams at most one arm camera, following the arm the coordinator is moving.

The two arm cameras share a USB 2.0 hub that cannot carry both uncompressed
streams. The arm cameras only feed the operator display, so this node never
affects the task: it starts and stops the camera processes and reports what it
did on /vision/arm_cameras/state. A camera starts only after the other one's
process group is gone and its device is no longer open by anyone.
"""
import json
import time

ARMS = ('arm1', 'arm2')
IDLE_ARM = 'arm1'
# A camera counts as on once its process has stayed up this long, and as healthy after RECOVERED_S.
STABLE_S, RECOVERED_S = 0.5, 5.0
# Restart delays after a camera exits by itself: 2, 4, 8 ... up to 30 s, so a missing camera costs no CPU.
BACKOFF_FIRST_S, BACKOFF_MAX_S = 2.0, 30.0


def active_arm_from_status(text):
    """The arm named by /dual_arm/status, '' when none, or None when the message is unreadable."""
    try:
        data = json.loads(text)
    except (TypeError, ValueError):
        return None
    if not isinstance(data, dict):
        return None
    arm = data.get('active_arm', '')
    return arm if arm in ARMS else ''


class ArmCameraSwitch:
    def __init__(self, launcher, device_of, device_in_use, clock=time.monotonic, term_timeout_s=3.0,
                 status_max_age_s=2.0):
        self._launcher, self._device_of, self._in_use = launcher, device_of, device_in_use
        self._clock, self._term_timeout, self._status_max_age = clock, term_timeout_s, status_max_age_s
        self._status = None            # (arm or '', received)
        self._current = None           # (arm, process)
        self._stopping = None          # [arm, process, deadline, killed]
        self._phase, self._message = 'switching', ''
        self._last_want = IDLE_ARM
        self._started_at, self._failures, self._next_start = 0.0, 0, 0.0

    def on_status(self, arm):
        self._status = (arm if arm in ARMS else '', self._clock())

    def _want(self):
        if self._status is not None and self._clock() - self._status[1] <= self._status_max_age:
            self._last_want = self._status[0] or IDLE_ARM
        # Without a recent status the coordinator may be gone; keep the last decision.
        return self._last_want

    def _set(self, phase, message=''):
        self._phase, self._message = phase, message

    def _advance_stop(self):
        """True once the camera being stopped has fully released its device."""
        arm, process, deadline, killed = self._stopping
        if process.running():
            if self._clock() >= deadline:
                if killed:
                    # Still alive after SIGKILL (a process stuck in the kernel): never start the other camera.
                    self._set('error', f'{arm} camera does not exit after SIGKILL')
                    return False
                process.kill()
                self._stopping[2:] = [self._clock() + self._term_timeout, True]
            self._set('switching', f'{arm} camera is stopping')
            return False
        device = self._device_of(arm)
        if self._in_use(device):
            late = self._clock() >= deadline
            self._set('error' if late else 'switching', f'{device} is still open after {arm} camera stopped')
            return False
        self._stopping = None
        return True

    def tick(self):
        if self._stopping is not None and not self._advance_stop():
            return
        want = self._want()
        if self._current is not None:
            arm, process = self._current
            if arm != want:
                self._failures, self._next_start = 0, 0.0
                process.terminate()
                self._stopping = [arm, process, self._clock() + self._term_timeout, False]
                self._current = None
                self._advance_stop()
                return
            up = self._clock() - self._started_at
            if process.running():
                if up >= RECOVERED_S:
                    self._failures = 0
                self._set('on') if up >= STABLE_S else self._set('switching', f'{arm} camera is starting')
                return
            # The wanted camera exited by itself: retry later, never in a tight loop.
            self._current = None
            self._failures += 1
            delay = min(BACKOFF_FIRST_S * 2 ** (self._failures - 1), BACKOFF_MAX_S)
            self._next_start = self._clock() + delay
            self._set('error', f'{arm} camera exited after {up:.1f} s; retrying in {delay:.0f} s')
            return
        if self._clock() < self._next_start:
            return
        busy = [self._device_of(arm) for arm in ARMS if self._in_use(self._device_of(arm))]
        if busy:
            self._set('error', f'{", ".join(busy)} is open by another process; not starting {want} camera')
            return
        process = self._launcher(want)
        process.start()
        self._current = (want, process)
        self._started_at = self._clock()
        self._set('switching', f'{want} camera is starting')

    def shutdown(self):
        """Stop every camera this switch started, waiting up to the term timeout before killing."""
        processes = [item[1] for item in (self._current, self._stopping) if item is not None]
        self._current = self._stopping = None
        for process in processes:
            process.terminate()
        deadline = self._clock() + self._term_timeout
        while any(process.running() for process in processes) and self._clock() < deadline:
            time.sleep(0.05)
        for process in processes:
            if process.running():
                process.kill()
        self._set('switching', 'stopped')

    def state(self):
        return {'want': self._want(), 'streaming': self._current[0] if self._current else '',
                'phase': self._phase, 'message': self._message}


def _camera_devices():
    """by-path device of each arm camera, from vision_pkg's cameras.yaml."""
    from pathlib import Path

    from ament_index_python.packages import get_package_share_directory
    import yaml

    path = Path(get_package_share_directory('vision_pkg')) / 'config' / 'cameras.yaml'
    config = yaml.safe_load(path.read_text(encoding='utf-8')) or {}
    return {arm: str((config.get(f'{arm}_cam') or {}).get('video_device', '')).strip() for arm in ARMS}


def main():
    import rclpy
    from rclpy.node import Node
    from rclpy.qos import DurabilityPolicy, QoSProfile
    from std_msgs.msg import String

    from .processes import GroupProcess, device_in_use

    rclpy.init()
    node = Node('arm_camera_switch')
    overrides = {arm: node.declare_parameter(f'{arm}_cam_device', '').value for arm in ARMS}
    devices = _camera_devices()
    devices.update({arm: path for arm, path in overrides.items() if path})

    def launcher(arm):
        return GroupProcess(['ros2', 'launch', 'vision_pkg', 'vision.launch.py', 'env_camera:=false',
                             'vision_nodes:=false', 'respawn:=false', f'arm_camera:={arm}',
                             f'{arm}_cam_device:={devices[arm]}'])

    switch = ArmCameraSwitch(launcher, lambda arm: devices[arm],
                             lambda path: bool(path) and device_in_use(path))
    publisher = node.create_publisher(String, '/vision/arm_cameras/state',
                                      QoSProfile(depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL))

    def on_status(message):
        arm = active_arm_from_status(message.data)
        if arm is not None:
            switch.on_status(arm)

    def on_timer():
        switch.tick()
        publisher.publish(String(data=json.dumps(switch.state(), sort_keys=True)))

    node.create_subscription(String, '/dual_arm/status', on_status, 10)
    node.create_timer(0.2, on_timer)
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        switch.shutdown()
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
