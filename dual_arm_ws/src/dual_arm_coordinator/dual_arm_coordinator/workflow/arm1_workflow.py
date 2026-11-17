"""Arm 1 moves one object from zone A to the shared zone B."""
import math

from .ports import TaskFault

ARM = 'arm1'


class Arm1Workflow:
    def __init__(self, context):
        self.ctx = context

    def _validated_target(self, target):
        settings = self.ctx.settings
        if not target.success:
            raise TaskFault(f'Pick target invalid: {target.message}')
        values = (target.x, target.y, target.z)
        if not all(math.isfinite(value) for value in values):
            raise TaskFault('Pick target is not finite')
        for low, value, high in zip(settings.a_min, values[:2], settings.a_max):
            if not low <= value <= high:
                raise TaskFault(f'Pick target {values} is outside zone A')
        if abs(target.z - settings.cap_top_z) > settings.pick_z_tolerance:
            raise TaskFault(f'Pick target height {target.z} differs from the object top')
        return (target.x, target.y)

    def run(self):
        self.pick_a()
        self.place_b()

    def pick_a(self, overlapped=False):
        """Take one object from zone A and stop HOME holding it.

        overlapped: arm 2 may be in B or carrying an object meanwhile, so zone B is not checked
        here; the overlapped run checked the B poses at its start and place_b checks B itself.
        """
        ctx, io, settings = self.ctx, self.ctx.io, self.ctx.settings
        ctx.step(ARM, 'CHECK_ZONES')
        view = ctx.zone_view()
        if not view.a_has_object:
            raise TaskFault('Zone A has no object')
        if not overlapped and (view.b_has_object or not view.b_arm_clear):
            raise TaskFault('Zone B is not empty and clear')

        ctx.step(ARM, 'QUERY_TARGET')
        observed = self._validated_target(io.pick_target())
        # The zone check uses the observation; the correction only moves where the cup goes.
        a_xy = (observed[0] + settings.a_pick_offset[0], observed[1] + settings.a_pick_offset[1])
        above_a = ctx.point(a_xy, settings.approach_z)
        at_a = ctx.point(a_xy, settings.contact_z - settings.a_press)
        taught = settings.b_joints
        ctx.step(ARM, 'PREFLIGHT')
        b_points = () if taught or overlapped else self._b_points()
        for point in (above_a, at_a) + b_points:
            io.check_reachable(ARM, point)
        if taught and not overlapped:
            io.check_b(ARM)

        ctx.step(ARM, 'APPROACH_A')
        io.move_to(ARM, above_a)
        ctx.step(ARM, 'DESCEND_A')
        io.move_to(ARM, at_a, contact=True)
        # Once suction is commanded the tool can no longer be assumed empty.
        ctx.set_holding(ARM, 'unknown')
        ctx.step(ARM, 'GRASP_A')
        io.suction(ARM, 'grasp')
        ctx.set_holding(ARM, 'held')
        ctx.step(ARM, 'ATTACH')
        io.attach(ARM)
        ctx.step(ARM, 'LIFT_A')
        io.move_to(ARM, above_a, contact=True)
        ctx.step(ARM, 'HOME_HOLDING')
        io.move_home(ARM)

    def _b_points(self):
        settings = self.ctx.settings
        return (self.ctx.point(settings.b_place, settings.approach_z), self.ctx.point(settings.b_place, settings.contact_z))

    def check_b_poses(self):
        """Where arm 1 will put objects down in B is valid (with B empty and arm 2 out of it)."""
        if self.ctx.settings.b_joints:
            self.ctx.io.check_b(ARM)
            return
        for point in self._b_points():
            self.ctx.io.check_reachable(ARM, point)

    def place_b(self):
        """From HOME holding an object: put it down in zone B, return HOME and verify it lies there."""
        ctx, io, settings = self.ctx, self.ctx.io, self.ctx.settings
        taught = settings.b_joints
        above_b, at_b = self._b_points()
        ctx.step(ARM, 'RESERVE_B')
        view = ctx.zone_view()
        if view.b_has_object or not view.b_arm_clear:
            raise TaskFault('Zone B is not empty and clear before reservation')
        ctx.acquire_b(ARM, view)

        ctx.step(ARM, 'APPROACH_B')
        if taught:
            io.move_b(ARM, 'above')
        else:
            io.move_to(ARM, above_b)
        ctx.step(ARM, 'DESCEND_B')
        if taught:
            io.move_b(ARM, 'contact', contact=True)
        else:
            io.move_to(ARM, at_b, contact=True)
        ctx.set_holding(ARM, 'unknown')
        ctx.step(ARM, 'RELEASE_B')
        io.suction(ARM, 'release')
        ctx.set_holding(ARM, 'empty')
        ctx.step(ARM, 'DETACH')
        io.detach(ARM)
        ctx.step(ARM, 'LIFT_B')
        if taught and settings.b_release_lift_z is not None:
            # Straight up from where the cup is: the joint line back to the taught pose also
            # turned j1 while the cup touched the object and pushed it (field run 2026-11-17).
            io.lift_vertical(ARM, settings.b_release_lift_z)
        elif taught:
            io.move_b(ARM, 'above', contact=True)
        else:
            io.move_to(ARM, above_b, contact=True)
        # The cup still touches the object until the lift ends, so the object may only enter the
        # world scene now; added earlier, every lift state collides with it (field run 2026-11-17).
        io.scene_add_b_object()
        ctx.step(ARM, 'HOME_EMPTY')
        io.move_home(ARM)

        ctx.step(ARM, 'VERIFY_B')
        view = ctx.zone_view()
        if not view.b_has_object or not view.b_arm_clear:
            raise TaskFault('Placement in zone B or arm withdrawal is unverified')
        ctx.release_b(ARM, view)
