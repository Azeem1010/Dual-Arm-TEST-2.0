"""Data and the IO contract between the task logic and the ROS gateways."""
from dataclasses import dataclass


class TaskFault(RuntimeError):
    """The task must stop; physical state is kept for a person to inspect."""


class TaskCancelled(TaskFault):
    """An operator or safety source stopped the task."""


@dataclass(frozen=True)
class ZoneView:
    success: bool
    message: str = ''
    a_has_object: bool = False
    b_has_object: bool = False
    b_arm_clear: bool = False
    c_object_count: int = 0


@dataclass(frozen=True)
class PickView:
    """Pick target in the task target frame; z is the top of the object."""
    success: bool
    message: str = ''
    x: float = 0.0
    y: float = 0.0
    z: float = 0.0


@dataclass(frozen=True)
class GridView:
    success: bool
    message: str = ''
    occupied: tuple = ()


@dataclass(frozen=True)
class PlaceView:
    success: bool
    message: str = ''
    placed: bool = False
    order_ok: bool = False


@dataclass(frozen=True)
class WorkflowSettings:
    cap_top_z: float
    contact_z: float
    release_z: float
    approach_z: float
    pick_z_tolerance: float
    a_min: tuple
    a_max: tuple
    b_place: tuple
    b_pick_tolerance: float
    c_slots: tuple
    # Prototype: arm 2 places at taught joint poses (TaskIO.move_slot) instead of c_slots xy.
    c_slot_joints: bool = False
    # Prototype: both arms hand over in B at taught joint poses (TaskIO.move_b) instead of b_place xy.
    b_joints: bool = False

    @classmethod
    def from_config(cls, config):
        heights, zones = config['heights'], config['zones']
        return cls(cap_top_z=heights['surface_z_m'] + heights['cap_height_m'],
                   contact_z=heights['contact_z_m'], release_z=heights['release_z_m'],
                   approach_z=heights['approach_z_m'], pick_z_tolerance=heights['pick_z_tolerance_m'],
                   a_min=tuple(zones['a_min_xy_m']), a_max=tuple(zones['a_max_xy_m']),
                   b_place=tuple(zones['b_place_xy_m']), b_pick_tolerance=zones['b_pick_tolerance_m'],
                   c_slots=tuple(tuple(slot) for slot in zones['c_slots_xy_m']),
                   c_slot_joints=config.get('c_slot_teach') is not None,
                   b_joints=config.get('b_teach') is not None)


class TaskIO:
    """Implemented by the ROS gateways and by fakes in tests.

    Every motion or suction method raises when it does not complete, and returns
    only after the result has been verified.
    """

    def guard(self):
        """Raise TaskCancelled when canceled or when a safety input is not valid."""
        raise NotImplementedError

    def zone(self):
        raise NotImplementedError

    def pick_target(self):
        raise NotImplementedError

    def b_pick_target(self):
        """Where arm 2 picks the object resting in zone B, as a PickView."""
        raise NotImplementedError

    def grid(self):
        raise NotImplementedError

    def verify_place(self, slot):
        raise NotImplementedError

    def check_reachable(self, arm, xyz):
        raise NotImplementedError

    def check_slot(self, arm, slot):
        """Taught slots only: the approach and release joints of slot are valid."""
        raise NotImplementedError

    def move_slot(self, arm, slot, pose, contact=False):
        """Taught slots only: move to slot's 'above' or 'release' joints."""
        raise NotImplementedError

    def check_b(self, arm):
        """Taught B only: the approach and contact joints of arm in B are valid."""
        raise NotImplementedError

    def move_b(self, arm, pose, contact=False):
        """Taught B only: move to arm's 'above' or 'contact' joints in B."""
        raise NotImplementedError

    def move_home(self, arm):
        raise NotImplementedError

    def move_to(self, arm, xyz, contact=False):
        raise NotImplementedError

    def at_home(self, arm):
        raise NotImplementedError

    def suction(self, arm, operation):
        """operation is 'grasp' or 'release'."""
        raise NotImplementedError

    def attach(self, arm):
        raise NotImplementedError

    def detach(self, arm):
        raise NotImplementedError

    def scene_reset(self):
        """Remove every task object from the planning scene, including attached ones."""
        raise NotImplementedError

    def scene_add_b_object(self):
        raise NotImplementedError

    def scene_remove_b_object(self):
        raise NotImplementedError

    def scene_add_slot_object(self, slot):
        raise NotImplementedError
