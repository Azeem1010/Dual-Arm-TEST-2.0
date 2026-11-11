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
        a_xy = self._validated_target(io.pick_target())
        above_a, at_a = ctx.point(a_xy, settings.approach_z), ctx.point(a_xy, settings.contact_z)
        above_b = ctx.point(settings.b_place, settings.approach_z)
        at_b = ctx.point(settings.b_place, settings.contact_z)

        ctx.step(ARM, 'PREFLIGHT')
        for point in (above_a, at_a, above_b, at_b):
            io.check_reachable(ARM, point)

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
        io.move_to(ARM, above_b)
        ctx.step(ARM, 'DESCEND_B')
        io.move_to(ARM, at_b, contact=True)
        ctx.set_holding(ARM, 'unknown')
        ctx.step(ARM, 'RELEASE_B')
        io.suction(ARM, 'release')
        ctx.set_holding(ARM, 'empty')
        ctx.step(ARM, 'DETACH')
        io.detach(ARM)
        io.scene_add_b_object()
        ctx.step(ARM, 'LIFT_B')
        io.move_to(ARM, above_b, contact=True)
        ctx.step(ARM, 'HOME_EMPTY')
        io.move_home(ARM)

        ctx.step(ARM, 'VERIFY_B')
        view = ctx.zone_view()
        if not view.b_has_object or not view.b_arm_clear:
            raise TaskFault('Placement in zone B or arm withdrawal is unverified')
        ctx.release_b(ARM, view)
