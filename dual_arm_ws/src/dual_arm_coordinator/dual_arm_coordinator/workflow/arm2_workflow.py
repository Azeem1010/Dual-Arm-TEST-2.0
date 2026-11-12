"""Arm 2 moves the object in zone B into the next slot of zone C."""
import math

from .ports import TaskFault

ARM = 'arm2'


class Arm2Workflow:
    def __init__(self, context):
        self.ctx = context

    def _validated_b_target(self, target):
        """The observed object in B, which must lie near where arm 1 put it down."""
        settings = self.ctx.settings
        if not target.success:
            raise TaskFault(f'B pick target invalid: {target.message}')
        values = (target.x, target.y, target.z)
        if not all(math.isfinite(value) for value in values):
            raise TaskFault('B pick target is not finite')
        offset = math.hypot(target.x - settings.b_place[0], target.y - settings.b_place[1])
        if offset > settings.b_pick_tolerance:
            raise TaskFault(f'B pick target {values} is {offset:.3f} m from the B place point')
        if abs(target.z - settings.cap_top_z) > settings.pick_z_tolerance:
            raise TaskFault(f'B pick target height {target.z} differs from the object top')
        return (target.x, target.y)

    def run(self):
        ctx, io, settings = self.ctx, self.ctx.io, self.ctx.settings
        ctx.step(ARM, 'CHECK_ZONES')
        view = ctx.zone_view()
        if not view.b_has_object or not view.b_arm_clear:
            raise TaskFault('Zone B has no object or an arm is inside it')
        ctx.require_consistent_c(view)
        occupied = ctx.occupied()

        ctx.step(ARM, 'QUERY_B_TARGET')
        b_xy = self._validated_b_target(io.b_pick_target())

        ctx.step(ARM, 'RESERVE_SLOT')
        slot = ctx.slots.reserve(occupied)
        ctx.journal.update(slot=slot)
        slot_xy = settings.c_slots[slot - 1]
        above_b = ctx.point(b_xy, settings.approach_z)
        at_b = ctx.point(b_xy, settings.contact_z)
        above_c = ctx.point(slot_xy, settings.approach_z)
        at_c = ctx.point(slot_xy, settings.release_z)

        ctx.step(ARM, 'PREFLIGHT')
        for point in (above_b, at_b, above_c, at_c):
            io.check_reachable(ARM, point)

        ctx.step(ARM, 'RESERVE_B')
        ctx.acquire_b(ARM, view)
        # The object must leave the world scene before the tool may touch it.
        io.scene_remove_b_object()
        ctx.step(ARM, 'APPROACH_B')
        io.move_to(ARM, above_b)
        ctx.step(ARM, 'DESCEND_B')
        io.move_to(ARM, at_b, contact=True)
        ctx.set_holding(ARM, 'unknown')
        ctx.step(ARM, 'GRASP_B')
        io.suction(ARM, 'grasp')
        ctx.set_holding(ARM, 'held')
        ctx.step(ARM, 'ATTACH')
        io.attach(ARM)
        ctx.step(ARM, 'LIFT_B')
        io.move_to(ARM, above_b, contact=True)
        ctx.step(ARM, 'HOME_HOLDING')
        io.move_home(ARM)

        ctx.step(ARM, 'VERIFY_B_EMPTY')
        view = ctx.zone_view()
        if view.b_has_object or not view.b_arm_clear:
            raise TaskFault('Zone B is not empty and clear after pickup')
        ctx.release_b(ARM, view)

        ctx.step(ARM, 'APPROACH_C')
        io.move_to(ARM, above_c)
        ctx.step(ARM, 'DESCEND_C')
        io.move_to(ARM, at_c, contact=True)
        ctx.set_holding(ARM, 'unknown')
        ctx.step(ARM, 'RELEASE_C')
        io.suction(ARM, 'release')
        ctx.set_holding(ARM, 'empty')
        ctx.step(ARM, 'DETACH')
        io.detach(ARM)
        ctx.step(ARM, 'LIFT_C')
        io.move_to(ARM, above_c, contact=True)
        ctx.step(ARM, 'HOME_EMPTY')
        io.move_home(ARM)

        ctx.step(ARM, 'VERIFY_C')
        view = ctx.zone_view()
        if view.c_object_count != sum(occupied) + 1:
            raise TaskFault('C count did not increase by one')
        place = io.verify_place(slot)
        if not place.success:
            raise TaskFault(f'Placement observation invalid: {place.message}')
        ctx.slots.commit(slot, placed=place.placed, order_ok=place.order_ok)
        occupied[slot - 1] = True
        ctx.journal.update(occupied=occupied, slot=0)
        io.scene_add_slot_object(slot)
