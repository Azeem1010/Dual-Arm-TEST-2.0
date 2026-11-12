"""Observations from the vision services, gated on calibration and image freshness.

The upstream services carry no timestamps, so each query first waits for an image
that arrived after the arm settled. Results stay in the arm base frames until TF
converts them; they are never relabelled.
"""
import math
import threading
import time

from ..workflow.ports import GridView, PickView, PlaceView, TaskFault, ZoneView

CAMERAS = ('env', 'arm1', 'arm2')
_POLL_S = 0.01


class CalibrationMonitor:
    """Tracks /vision/calibration_status; anything but a recent PASS is a refusal."""

    def __init__(self, max_age_s, clock=time.monotonic):
        self._max_age, self._clock = max_age_s, clock
        self._lock = threading.Lock()
        self._state = {}

    def on_status(self, camera, passed, reasons):
        with self._lock:
            self._state[camera] = (passed, reasons, self._clock())

    def problem(self, camera):
        with self._lock:
            state = self._state.get(camera)
        if state is None:
            return f'No calibration status for {camera}'
        passed, reasons, received = state
        if self._clock() - received > self._max_age:
            return f'Calibration status for {camera} is stale'
        return None if passed else f'Calibration for {camera} is not valid: {reasons}'


class ImageMonitor:
    def __init__(self, clock=time.monotonic):
        self._clock = clock
        self._lock = threading.Lock()
        self._received = {}

    def on_image(self, camera):
        with self._lock:
            self._received[camera] = self._clock()

    def last(self, camera):
        with self._lock:
            return self._received.get(camera)


class VisionObserver:
    def __init__(self, services, to_target, calibration, images, guard, settle_s, image_timeout_s,
                 clock=time.monotonic, sleep=time.sleep):
        self._services, self._to_target, self._calibration, self._images = services, to_target, calibration, images
        self._guard, self._settle, self._timeout, self._clock, self._sleep = guard, settle_s, image_timeout_s, clock, sleep

    def _problem(self, camera):
        """Reason the camera cannot be trusted right now, or None once a settled image exists."""
        problem = self._calibration.problem(camera)
        if problem:
            return problem
        after = self._clock() + self._settle
        deadline = after + self._timeout
        while True:
            self._guard()
            received = self._images.last(camera)
            if received is not None and received > after:
                return self._calibration.problem(camera)
            if self._clock() >= deadline:
                return f'No new image from {camera} after the arm settled'
            self._sleep(_POLL_S)

    def zone(self):
        problem = self._problem('env')
        if problem:
            return ZoneView(False, problem)
        response = self._services.zone()
        if not response.success:
            return ZoneView(False, response.message)
        return ZoneView(True, '', response.a_has_object, response.b_has_object, response.b_arm_clear, response.c_object_count)

    def pick_target(self):
        problem = self._problem('arm1')
        if problem:
            return PickView(False, problem)
        response = self._services.pick()
        if not response.success:
            return PickView(False, response.message)
        values = (response.x, response.y, response.z)
        if not all(math.isfinite(value) for value in values):
            return PickView(False, 'Vision returned a non-finite target')
        try:
            x, y, z = self._to_target('arm1', *values)
        except TaskFault as error:
            return PickView(False, str(error))
        return PickView(True, '', x, y, z)

    def grid(self):
        problem = self._problem('arm2')
        if problem:
            return GridView(False, problem)
        response = self._services.grid()
        if not response.success:
            return GridView(False, response.message)
        return GridView(True, '', tuple(bool(value) for value in response.occupied))

    def verify_place(self, slot):
        problem = self._problem('arm2')
        if problem:
            return PlaceView(False, problem)
        response = self._services.verify(slot)
        if not response.success:
            return PlaceView(False, response.message)
        return PlaceView(True, '', response.placed, response.order_ok)


class VisionPickObserver:
    """Pick targets from vision, zones from ground truth, while simulated cameras are occluded at HOME."""

    def __init__(self, truth, vision):
        self._truth, self._vision = truth, vision

    def zone(self):
        return self._truth.zone()

    def pick_target(self):
        return self._vision.pick_target()

    def b_pick_target(self):
        return self._truth.b_pick_target()

    def grid(self):
        return self._truth.grid()

    def verify_place(self, slot):
        return self._truth.verify_place(slot)


class _Services:
    def __init__(self, node, guard, timeout_s, callback_group):
        from vision_interfaces.srv import GetGridState, GetPickTarget, GetZoneState, VerifyPlace
        self._types = (GetZoneState, GetPickTarget, GetGridState, VerifyPlace)
        self._guard, self._timeout = guard, timeout_s
        create = lambda kind, name: node.create_client(kind, name, callback_group=callback_group)
        self._zone = create(GetZoneState, '/vision/env/get_zone_state')
        self._pick = create(GetPickTarget, '/vision/arm1/get_pick_target')
        self._grid = create(GetGridState, '/vision/arm2/get_grid_state')
        self._verify = create(VerifyPlace, '/vision/arm2/verify_place')

    def _call(self, client, request):
        if not client.wait_for_service(timeout_sec=self._timeout):
            raise TaskFault(f'{client.srv_name} is unavailable')
        future = client.call_async(request)
        deadline = time.monotonic() + self._timeout
        while not future.done():
            self._guard()
            if time.monotonic() >= deadline:
                raise TaskFault(f'{client.srv_name} timed out')
            time.sleep(_POLL_S)
        return future.result()

    def zone(self):
        return self._call(self._zone, self._types[0].Request())

    def pick(self):
        return self._call(self._pick, self._types[1].Request(target_rank=0, peek_only=True))

    def grid(self):
        return self._call(self._grid, self._types[2].Request())

    def verify(self, slot):
        return self._call(self._verify, self._types[3].Request(slot=slot))


def make_transformer(node, config):
    """Return to_target(arm, x, y, z), converting an arm vision frame point through TF."""
    from rclpy.time import Time
    from scipy.spatial.transform import Rotation
    from tf2_ros import Buffer, TransformException, TransformListener

    buffer = Buffer()
    node._vision_tf_listener = TransformListener(buffer, node)
    target_frame = config['target_frame']

    def to_target(arm, x, y, z):
        frame = config['arms'][arm]['vision_base_frame']
        try:
            stamped = buffer.lookup_transform(target_frame, frame, Time())
        except TransformException as error:
            raise TaskFault(f'No transform from {frame} to {target_frame}: {error}') from error
        translation, rotation = stamped.transform.translation, stamped.transform.rotation
        point = Rotation.from_quat([rotation.x, rotation.y, rotation.z, rotation.w]).apply([x, y, z])
        return (point[0] + translation.x, point[1] + translation.y, point[2] + translation.z)

    return to_target


def wire_vision(node, config, guard, callback_group=None, status_max_age_s=3.0):
    """Create the vision observer. Only imports ROS here so the logic above stays testable."""
    from diagnostic_msgs.msg import DiagnosticArray, DiagnosticStatus
    import json
    from rclpy.qos import qos_profile_sensor_data
    from sensor_msgs.msg import Image

    calibration, images = CalibrationMonitor(status_max_age_s), ImageMonitor()
    to_target = make_transformer(node, config)

    def on_status(message):
        for status in message.status:
            camera = status.hardware_id
            reasons = next((item.value for item in status.values if item.key == 'reasons'), '[]')
            calibration.on_status(camera, status.level == DiagnosticStatus.OK, json.loads(reasons))

    node.create_subscription(DiagnosticArray, '/vision/calibration_status', on_status, 10, callback_group=callback_group)
    for camera in CAMERAS:
        node.create_subscription(Image, f'/{camera}_cam/image_raw',
                                 lambda _message, name=camera: images.on_image(name),
                                 qos_profile_sensor_data, callback_group=callback_group)

    motion = config['motion']
    services = _Services(node, guard, motion['goal_submit_s'], callback_group)
    return VisionObserver(services, to_target, calibration, images, guard, motion['settle_s'], motion['arrival_timeout_s'])
