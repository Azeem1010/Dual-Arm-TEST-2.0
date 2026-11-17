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
        ctx, io, settings = self.ctx, self.ctx.io, self.ctx.settings
        ctx.step(ARM, 'CHECK_ZONES')
        view = ctx.zone_view()
        if not view.a_has_object:
            raise TaskFault('Zone A has no object')
        if view.b_has_object or not view.b_arm_clear:
            raise TaskFault('Zone B is not empty and clear')

        ctx.step(ARM, 'QUERY_TARGET')
        observed = self._validated_target(io.pick_target())
        # The zone check uses the observation; the correction only moves where the cup goes.
        a_xy = (observed[0] + settings.a_pick_offset[0], observed[1] + settings.a_pick_offset[1])
        above_a = ctx.point(a_xy, settings.approach_z)
        at_a = ctx.point(a_xy, settings.contact_z - settings.a_press)
        above_b = ctx.point(settings.b_place, settings.approach_z)
        at_b = ctx.point(settings.b_place, settings.contact_z)

        taught = settings.b_joints
        ctx.step(ARM, 'PREFLIGHT')
        for point in (above_a, at_a) if taught else (above_a, at_a, above_b, at_b):
            io.check_reachable(ARM, point)
        if taught:
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
