"""Republishes the env_scene result in the shapes the operator display already reads.

env_scene answers only through a service. This node asks it twice a second and
publishes /vision/env/zone_state (vision_interfaces/ZoneState) and an `env`
entry on /vision/calibration_status. It is a display path only; the
coordinator queries env_scene itself. Whether zone B is free of arms comes from
the coordinator's joint-based at_home report, not from the camera.
"""
import json

ACCEPTED_SOURCES = ('standard', 'measured')
ZONE_FLAGS = ('c_slots_valid',)
CALIBRATION_FLAGS = ('arm1_valid', 'arm2_valid', 'c_slots_valid')


def at_home_from_status(text):
    try:
        data = json.loads(text)
    except (TypeError, ValueError):
        return None
    if not isinstance(data, dict) or not isinstance(data.get('at_home'), dict):
        return None
    return data['at_home']


class AtHomeCache:
    """The coordinator's at_home report, forgotten when /dual_arm/status stops (coordinator gone)."""

    def __init__(self, max_age_s=2.0):
        self._max_age, self._value, self._received = max_age_s, None, None

    def on_status(self, text, now):
        value = at_home_from_status(text)
        self._value, self._received = value, (now if value is not None else None)

    def value(self, now):
        if self._received is None or now - self._received > self._max_age:
            return None
        return self._value


def _problems(response, flags):
    if not response.success:
        return [response.message]
    scene = response.scene
    if not scene.valid:
        return [f'Env scene invalid: {scene.message}']
    problems = []
    if scene.coords_source not in ACCEPTED_SOURCES:
        problems.append(f'Env scene coordinates are {scene.coords_source}, not standard or measured')
    problems += [f'Env scene {flag} is false' for flag in flags if not getattr(scene, flag)]
    return problems


def to_zone_fields(response, at_home):
    problems = _problems(response, ZONE_FLAGS)
    if problems:
        return dict(valid=False, message='; '.join(problems), a_has_object=False, b_has_object=False,
                    b_arm_clear=False, c_object_count=0)
    scene = response.scene
    clear = isinstance(at_home, dict) and all(at_home.get(arm) is True for arm in ('arm1', 'arm2'))
    return dict(valid=True, message='', a_has_object=len(scene.a_objects) > 0, b_has_object=len(scene.b_objects) > 0,
                b_arm_clear=clear, c_object_count=int(scene.c_occupied_count))


def env_calibration(response):
    problems = _problems(response, CALIBRATION_FLAGS)
    return (not problems, problems)


class ScenePoller:
    """One get_scene request at a time; a request that never returns (env_scene restarted) is dropped."""

    def __init__(self, call, clock, timeout_s=2.0):
        self._call, self._clock, self._timeout = call, clock, timeout_s
        self._pending, self._sent = None, 0.0

    def _send(self):
        self._pending = self._call()
        self._sent = self._clock()

    def tick(self):
        """The response that finished since the last tick, or None."""
        if self._pending is None:
            self._send()
            return None
        if self._pending.done():
            result = self._pending.result()
            self._send()
            return result
        if self._clock() - self._sent > self._timeout:
            self._send()
        return None


def main():
    from diagnostic_msgs.msg import DiagnosticArray, DiagnosticStatus, KeyValue
    from env_scene_interfaces.srv import GetEnvScene
    import rclpy
    from rclpy.node import Node
    from std_msgs.msg import String
    from vision_interfaces.msg import ZoneState

    rclpy.init()
    node = Node('env_scene_bridge')
    client = node.create_client(GetEnvScene, '/vision/env_scene/get_scene')
    zone_publisher = node.create_publisher(ZoneState, '/vision/env/zone_state', 10)
    calibration_publisher = node.create_publisher(DiagnosticArray, '/vision/calibration_status', 10)
    at_home = AtHomeCache()
    seconds = lambda: node.get_clock().now().nanoseconds / 1e9  # noqa: E731

    def on_status(message):
        at_home.on_status(message.data, seconds())

    def publish(response):
        stamp = node.get_clock().now().to_msg()
        zone = ZoneState(**to_zone_fields(response, at_home.value(seconds())))
        zone.header.stamp, zone.header.frame_id = stamp, 'env_camera_optical_frame'
        zone_publisher.publish(zone)
        passed, reasons = env_calibration(response)
        status = DiagnosticStatus(name='calibration/env', hardware_id='env', message='PASS' if passed else 'FAIL',
                                  level=DiagnosticStatus.OK if passed else DiagnosticStatus.ERROR,
                                  values=[KeyValue(key='reasons', value=json.dumps(reasons))])
        out = DiagnosticArray(status=[status])
        out.header.stamp = stamp
        calibration_publisher.publish(out)

    def call():
        return client.call_async(GetEnvScene.Request()) if client.service_is_ready() else None

    poller = ScenePoller(call, seconds)

    def on_timer():
        result = poller.tick()
        if result is not None:
            publish(result)

    node.create_subscription(String, '/dual_arm/status', on_status, 10)
    node.create_timer(0.5, on_timer)
    try:
        rclpy.spin(node)
    except KeyboardInterrupt:
        pass
    finally:
        node.destroy_node()
        if rclpy.ok():
            rclpy.shutdown()
