"""Arm 2 moves the object in zone B into the next slot of zone C."""
import math

from .ports import TaskFault

ARM = 'arm2'


class Arm2Workflow:
    def __init__(self, context, on_b_released=None):
        """on_b_released (overlapped run) is called once arm 2 has left zone B with the object."""
        self.ctx = context
        self._on_b_released = on_b_released

    def _validated_b_target(self, target):
        """The observed object in B, which must lie near where arm 2 will grasp it.

        With a taught B arm 2 always goes to its taught contact pose, so the object must lie
        under that pose; b_place_xy_m is not where the taught hand-over happens (field run
        2026-11-17: the object lay 3 mm from arm 2's taught point and 20 mm from b_place_xy_m).
        """
        settings = self.ctx.settings
        if not target.success:
            raise TaskFault(f'B pick target invalid: {target.message}')
        values = (target.x, target.y, target.z)
        if not all(math.isfinite(value) for value in values):
            raise TaskFault('B pick target is not finite')
        if settings.b_joints:
            reference, name = self.ctx.io.b_grasp_xy(ARM), f"{ARM}'s taught B point"
        else:
            reference, name = settings.b_place, 'the B place point'
        offset = math.hypot(target.x - reference[0], target.y - reference[1])
        if offset > settings.b_pick_tolerance:
            raise TaskFault(f'B pick target {values} is {offset:.3f} m from {name}')
        if abs(target.z - settings.cap_top_z) > settings.pick_z_tolerance:
            raise TaskFault(f'B pick target height {target.z} differs from the object top')
        return (target.x, target.y)

    def _release_b_empty(self, view):
        if view.b_has_object or not view.b_arm_clear:
            raise TaskFault('Zone B is not empty and clear after pickup')
        self.ctx.release_b(ARM, view)
        if self._on_b_released is not None:
            self._on_b_released()

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

        taught, taught_b = settings.c_slot_joints, settings.b_joints
        ctx.step(ARM, 'PREFLIGHT')
        points = (() if taught_b else (above_b, at_b)) + (() if taught else (above_c, at_c))
        for point in points:
            io.check_reachable(ARM, point)
        # Taught B poses are not checked here: arm 1's object is still in the scene and the taught
        # contact pose presses on it, so it would always collide. Transfer._preflight_next_slot
        # checked them at the start of this cycle, with zone B empty (field review 2026-11-17).
        if taught:
            io.check_slot(ARM, slot)

        ctx.step(ARM, 'RESERVE_B')
        ctx.acquire_b(ARM, view)
        # The object must leave the world scene before the tool may touch it.
        io.scene_remove_b_object()
        # With a taught B the observed object only confirms that B holds one near the place point;
        # arm 2 goes to its taught pose, which meets arm 1's taught pose.
        ctx.step(ARM, 'APPROACH_B')
        if taught_b:
            io.move_b(ARM, 'above')
        else:
            io.move_to(ARM, above_b)
        ctx.step(ARM, 'DESCEND_B')
        if taught_b:
            io.move_b(ARM, 'contact', contact=True)
        else:
            io.move_to(ARM, at_b, contact=True)
        ctx.set_holding(ARM, 'unknown')
        ctx.step(ARM, 'GRASP_B')
        io.suction(ARM, 'grasp')
        ctx.set_holding(ARM, 'held')
        ctx.step(ARM, 'ATTACH')
        io.attach(ARM)
        ctx.step(ARM, 'LIFT_B')
        if taught_b:
            io.move_b(ARM, 'above', contact=True)
        else:
            io.move_to(ARM, above_b, contact=True)
        direct = settings.direct_transfer
        if not direct:
            ctx.step(ARM, 'HOME_HOLDING')
            io.move_home(ARM)

            ctx.step(ARM, 'VERIFY_B_EMPTY')
            self._release_b_empty(ctx.zone_view())

        ctx.step(ARM, 'APPROACH_C')
        if taught:
            io.move_slot(ARM, slot, 'above')
        else:
            io.move_to(ARM, above_c)
        ctx.step(ARM, 'DESCEND_C')
        if taught:
            io.move_slot(ARM, slot, 'release', contact=True)
        else:
            io.move_to(ARM, at_c, contact=True)
        ctx.set_holding(ARM, 'unknown')
        ctx.step(ARM, 'RELEASE_C')
        io.suction(ARM, 'release')
        ctx.set_holding(ARM, 'empty')
        ctx.step(ARM, 'DETACH')
        io.detach(ARM)
        ctx.step(ARM, 'LIFT_C')
        if taught:
            io.move_slot(ARM, slot, 'above', contact=True)
        else:
            io.move_to(ARM, above_c, contact=True)
        ctx.step(ARM, 'HOME_EMPTY')
        io.move_home(ARM)

        ctx.step(ARM, 'VERIFY_C')
        view = ctx.zone_view()
        if direct:
            # Arm 2 kept B through the placement; it is HOME now, so one view checks B and C.
            self._release_b_empty(view)
        if view.c_object_count != sum(occupied) + 1:
            raise TaskFault('C count did not increase by one')
        place = io.verify_place(slot)
        if not place.success:
            raise TaskFault(f'Placement observation invalid: {place.message}')
        ctx.slots.commit(slot, placed=place.placed, order_ok=place.order_ok)
        occupied[slot - 1] = True
        ctx.journal.update(occupied=occupied, slot=0)
        io.scene_add_slot_object(slot)
