"""Observations from the environment camera scene (env_scene), the only camera tasks rely on.

The scene service carries world coordinates in millimetres (origin at the field
centre, x from A to C, y away from the user), the same axes as the task target
frame `world`, so values are only rescaled. Each query first waits for an env
image that arrived after the arms settled, as the other vision gateways do.
Whether zone B is free of arms comes from joint feedback, not from the camera.
"""
import math
import time

from ..workflow.ports import GridView, PickView, PlaceView, TaskFault, ZoneView

ACCEPTED_SOURCES = ('standard', 'measured')
SLOT_COUNT = 8
# env_scene answers with its latest result (up to its image_timeout_s old) and switches a C slot only
# after occupied_frames (3) equal results at process_hz (10): 0.4 s. A query therefore waits for an
# env image that arrived this long after the arms settled.
SCENE_LAG_S = 0.5
_POLL_S = 0.01


def call_service(client, request, guard, timeout_s, clock=time.monotonic, sleep=time.sleep,
                 wait=lambda client, seconds: client.wait_for_service(timeout_sec=seconds)):
    """Call a ROS service, checking guard() throughout so a cancel never waits for the timeout."""
    deadline = clock() + timeout_s
    while True:
        guard()
        if wait(client, 0.1):
            break
        if clock() >= deadline:
            raise TaskFault(f'{client.srv_name} is unavailable')
    future = client.call_async(request)
    while not future.done():
        guard()
        if clock() >= deadline:
            raise TaskFault(f'{client.srv_name} timed out')
        sleep(_POLL_S)
    return future.result()


def require_world_frame(config):
    """env_scene coordinates are world coordinates; any other task frame needs a conversion that does not exist."""
    if config.get('target_frame') != 'world':
        raise ValueError(f"observation_source env_scene needs target_frame world, not {config.get('target_frame')!r}")


class EnvSceneObserver:
    def __init__(self, scene_call, images, home_state, can_reach, home_tcp, settings, guard, settle_s, image_timeout_s,
                 clock=time.monotonic, sleep=time.sleep):
        self._scene_call, self._images, self._home_state = scene_call, images, home_state
        self._can_reach, self._home_tcp, self._settings = can_reach, home_tcp, settings
        self._guard, self._settle, self._timeout, self._clock, self._sleep = guard, settle_s, image_timeout_s, clock, sleep

    def _wait_for_image(self):
        after = self._clock() + self._settle + SCENE_LAG_S
        deadline = after + self._timeout
        while True:
            self._guard()
            received = self._images.last('env')
            if received is not None and received > after:
                return None
            if self._clock() >= deadline:
                return 'No new image from env after the arm settled'
            self._sleep(_POLL_S)

    def _scene(self, *required):
        """(scene, None) when the scene and every named validity flag hold, else (None, reason)."""
        problem = self._wait_for_image()
        if problem:
            return None, problem
        response = self._scene_call()
        if not response.success:
            return None, response.message
        scene = response.scene
        if not scene.valid:
            return None, f'Env scene invalid: {scene.message}'
        if scene.coords_source not in ACCEPTED_SOURCES:
            return None, f'Env scene coordinates are {scene.coords_source}, not standard or measured'
        for flag in required:
            if not getattr(scene, flag):
                return None, f'Env scene {flag} is false'
        if 'c_slots_valid' in required and len(scene.c_occupied) != SLOT_COUNT:
            return None, f'Env scene has {len(scene.c_occupied)} C slots, expected {SLOT_COUNT}'
        return scene, None

    def _xy(self, item):
        return (item.x_mm / 1000.0, item.y_mm / 1000.0)

    def zone(self):
        scene, problem = self._scene('c_slots_valid')
        if problem:
            return ZoneView(False, problem)
        clear = all(self._home_state(arm) is True for arm in ('arm1', 'arm2'))
        return ZoneView(True, '', len(scene.a_objects) > 0, len(scene.b_objects) > 0, clear, int(scene.c_occupied_count))

    def pick_target(self):
        scene, problem = self._scene('arm1_valid')
        if problem:
            return PickView(False, problem)
        settings, home = self._settings, self._home_tcp('arm1')
        candidates = sorted((self._xy(item) for item in scene.a_objects),
                            key=lambda xy: math.hypot(xy[0] - home[0], xy[1] - home[1]))
        for x, y in candidates:
            try:
                self._can_reach('arm1', (x, y, settings.approach_z))
                self._can_reach('arm1', (x, y, settings.contact_z))
            except TaskFault:
                continue
            return PickView(True, '', x, y, settings.cap_top_z)
        return PickView(False, 'No reachable object in zone A')

    def b_pick_target(self):
        scene, problem = self._scene('arm2_valid')
        if problem:
            return PickView(False, problem)
        if len(scene.b_objects) != 1:
            return PickView(False, f'Zone B holds {len(scene.b_objects)} objects, expected exactly 1')
        x, y = self._xy(scene.b_objects[0])
        return PickView(True, '', x, y, self._settings.cap_top_z)

    def grid(self):
        scene, problem = self._scene('arm2_valid', 'c_slots_valid')
        if problem:
            return GridView(False, problem)
        return GridView(True, '', tuple(bool(value) for value in scene.c_occupied))

    def verify_place(self, slot):
        scene, problem = self._scene('arm2_valid', 'c_slots_valid')
        if problem:
            return PlaceView(False, problem)
        occupied = [bool(value) for value in scene.c_occupied]
        count = sum(occupied)
        return PlaceView(True, '', occupied[slot - 1], occupied == [True] * count + [False] * (len(occupied) - count))


def wire_env_scene(node, config, settings, motion, guard, callback_group=None):
    """Create the env_scene observer. Only imports ROS here so the logic above stays testable."""
    from env_scene_interfaces.srv import GetEnvScene
    from rclpy.qos import qos_profile_sensor_data
    from sensor_msgs.msg import Image

    from .vision import ImageMonitor

    require_world_frame(config)
    images = ImageMonitor()
    node.create_subscription(Image, '/env_cam/image_raw', lambda _message: images.on_image('env'),
                             qos_profile_sensor_data, callback_group=callback_group)
    client = node.create_client(GetEnvScene, '/vision/env_scene/get_scene', callback_group=callback_group)
    timeout = config['motion']['goal_submit_s']

    def scene_call():
        return call_service(client, GetEnvScene.Request(), guard, timeout)

    return EnvSceneObserver(scene_call, images, motion.home_state, motion.check_reachable, motion.home_tcp, settings,
                            guard, config['motion']['settle_s'], config['motion']['arrival_timeout_s'])
