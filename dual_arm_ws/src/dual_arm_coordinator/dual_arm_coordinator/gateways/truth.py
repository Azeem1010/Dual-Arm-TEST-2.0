"""Zone and target observations from Gazebo ground truth. Simulation only.

Stands in for the vision gateway so the task can be exercised without cameras.
Passing with this source says nothing about calibration or perception.
"""
import math
import threading
import time

from ..workflow.ports import GridView, PickView, PlaceView, TaskFault, ZoneView

CAPS = tuple(f'cap_{index}' for index in range(1, 9))
ARMS = ('arm1', 'arm2')
MAX_POSE_AGE_S = 3.0
SLOT_TOLERANCE_M = 0.002
TOOL_SEARCH_RADIUS_M = 0.005


class TruthObserver:
    def __init__(self, config, tcp_of, can_reach, home_tcp, prefilled=0, clock=time.monotonic):
        if type(prefilled) is not int or not 0 <= prefilled <= 8:
            raise ValueError('prefilled must be an integer in 0..8')
        heights, zones = config['heights'], config['zones']
        self._top_z = heights['surface_z_m'] + heights['cap_height_m']
        self._half_height = heights['cap_height_m'] / 2.0
        self._contact_z, self._approach_z = heights['contact_z_m'], heights['approach_z_m']
        self._a_min, self._a_max = zones['a_min_xy_m'], zones['a_max_xy_m']
        # B is centred on x = 0 between A and C; its half width is the distance to A's inner edge.
        self._b_half_width = min(abs(zones['a_min_xy_m'][0]), abs(zones['a_max_xy_m'][0]))
        self._c_side = -1.0 if zones['a_min_xy_m'][0] + zones['a_max_xy_m'][0] > 0 else 1.0
        self._slots = zones['c_slots_xy_m']
        self._tcp_of, self._can_reach, self._home_tcp = tcp_of, can_reach, home_tcp
        self._prefilled, self._clock = prefilled, clock
        self._lock = threading.Lock()
        self._poses = {}

    def on_pose(self, name, xyz):
        with self._lock:
            self._poses[name] = (tuple(xyz), self._clock())

    def _resting(self):
        """Resting cap positions, or None when any cap pose is missing or stale."""
        now = self._clock()
        with self._lock:
            poses = dict(self._poses)
        if any(name not in poses or now - poses[name][1] > MAX_POSE_AGE_S for name in CAPS):
            return None
        return {name: poses[name][0] for name in CAPS if poses[name][0][2] <= self._top_z}

    def _in_a(self, xyz):
        return all(low <= value <= high for low, value, high in zip(self._a_min, xyz[:2], self._a_max))

    def _in_b(self, xyz):
        return abs(xyz[0]) < self._b_half_width

    def _in_c(self, xyz):
        return self._c_side * xyz[0] >= self._b_half_width

    def _slot_occupancy(self, resting):
        occupied = [index < self._prefilled for index in range(8)]
        for index, slot in enumerate(self._slots):
            if any(math.hypot(xyz[0] - slot[0], xyz[1] - slot[1]) <= SLOT_TOLERANCE_M for xyz in resting.values()):
                occupied[index] = True
        return occupied

    def zone(self):
        resting = self._resting()
        if resting is None:
            return ZoneView(False, 'Ground truth pose missing or stale')
        positions = list(resting.values())
        arm_in_b = any(self._in_b(self._tcp_of(arm)) for arm in ARMS)
        return ZoneView(True, '', any(self._in_a(xyz) for xyz in positions),
                        any(self._in_b(xyz) for xyz in positions), not arm_in_b,
                        self._prefilled + sum(1 for xyz in positions if self._in_c(xyz)))

    def pick_target(self):
        resting = self._resting()
        if resting is None:
            return PickView(False, 'Ground truth pose missing or stale')
        home = self._home_tcp('arm1')
        candidates = sorted((xyz for xyz in resting.values() if self._in_a(xyz)),
                            key=lambda xyz: math.hypot(xyz[0] - home[0], xyz[1] - home[1]))
        for xyz in candidates:
            try:
                self._can_reach('arm1', (xyz[0], xyz[1], self._approach_z))
                self._can_reach('arm1', (xyz[0], xyz[1], self._contact_z))
            except TaskFault:
                continue
            return PickView(True, '', xyz[0], xyz[1], xyz[2] + self._half_height)
        return PickView(False, 'No reachable object in zone A')

    def grid(self):
        resting = self._resting()
        if resting is None:
            return GridView(False, 'Ground truth pose missing or stale')
        return GridView(True, '', tuple(self._slot_occupancy(resting)))

    def verify_place(self, slot):
        resting = self._resting()
        if resting is None:
            return PlaceView(False, 'Ground truth pose missing or stale')
        occupied = self._slot_occupancy(resting)
        count = sum(occupied)
        return PlaceView(True, '', occupied[slot - 1], occupied == [True] * count + [False] * (8 - count))

    def cap_under_tool(self, arm):
        resting = self._resting()
        if resting is None:
            raise TaskFault('Ground truth pose missing or stale')
        tcp = self._tcp_of(arm)
        distances = {name: math.hypot(xyz[0] - tcp[0], xyz[1] - tcp[1]) for name, xyz in resting.items()}
        name = min(distances, key=distances.get) if distances else None
        if name is None or distances[name] > TOOL_SEARCH_RADIUS_M:
            raise TaskFault(f'No object under the {arm} tool')
        return name


def wire_truth(node, observer, callback_group=None):
    from rclpy.qos import qos_profile_sensor_data
    from tf2_msgs.msg import TFMessage

    def callback(name):
        def receive(message):
            if message.transforms:
                position = message.transforms[0].transform.translation
                observer.on_pose(name, (position.x, position.y, position.z))
        return receive

    for name in CAPS:
        node.create_subscription(TFMessage, f'/ground_truth/{name}', callback(name), qos_profile_sensor_data,
                                 callback_group=callback_group)
