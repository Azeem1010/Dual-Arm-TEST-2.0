"""Batch A-to-B-to-C transfer with one owner for the journal and zone B."""
import uuid

from ..resources import SlotManager, ZoneManager
from .arm1_workflow import Arm1Workflow
from .arm2_workflow import Arm2Workflow
from .context import TaskContext
from .ports import TaskFault

ARMS = ('arm1', 'arm2')
RECOVERY = 'recovery'
_NEEDS_RECOVERY = ('FAULT', 'FULL')


class Transfer:
    def __init__(self, io, settings, journal, gate):
        self.io, self.journal, self.gate = io, journal, gate
        self.zone, self.slots = ZoneManager(), SlotManager()
        self.ctx = TaskContext(io, settings, journal, self.zone, self.slots)
        data = journal.data
        if data['b_owner']:
            self.ctx.b_token = self.zone.restore(data['b_owner'])
        if data['state'] == 'FAULT':
            self.gate.issue(RECOVERY)
        else:
            self.slots.restore(data['occupied'])
            if data['state'] == 'FULL':
                self.gate.issue(RECOVERY)

    def run(self, limit):
        if type(limit) is not int or not 1 <= limit <= 8:
            raise ValueError('limit must be an integer in 1..8')
        if self.journal.data['state'] in _NEEDS_RECOVERY:
            raise TaskFault('Recovery is required before a new run')
        try:
            return self._run(limit)
        except TaskFault as error:
            self._fault(error)
            raise
        except Exception as error:
            # Resource managers and gateways report refusals with other exception types.
            self._fault(error)
            raise TaskFault(str(error)) from error

    def _run(self, limit):
        self.journal.update(state='STARTING', cycle_id=uuid.uuid4().hex, completed=0, message='')
        for arm in ARMS:
            self.ctx.step(arm, 'INITIAL_HOME')
            self.io.move_home(arm)
        for _ in range(limit):
            self.io.guard()
            if all(self.ctx.occupied()):
                break
            view = self.ctx.zone_view()
            if not view.b_arm_clear:
                raise TaskFault('Zone B is not clear at the start of a cycle')
            self.ctx.require_consistent_c(view)
            self._preflight_next_slot()
            if not view.b_has_object:
                Arm1Workflow(self.ctx).run()
            Arm2Workflow(self.ctx).run()
            self.journal.update(completed=self.journal.data['completed'] + 1)
        if all(self.ctx.occupied()):
            self.journal.update(state='FULL', active_arm='')
            self.gate.issue(RECOVERY)
            return 'FULL'
        self.journal.update(state='SUCCEEDED', active_arm='')
        return 'SUCCEEDED'

    def _preflight_next_slot(self):
        """Stop before taking an object that could not be delivered, so none is stranded in B."""
        settings = self.ctx.settings
        slot_xy = settings.c_slots[self.ctx.occupied().index(False)]
        for height in (settings.approach_z, settings.release_z):
            self.io.check_reachable('arm2', self.ctx.point(slot_xy, height))

    def _fault(self, error):
        if self.ctx.b_token is not None:
            self.zone.fault(self.ctx.b_token)
        self.journal.update(state='FAULT', message=str(error))
        self.gate.issue(RECOVERY)

    def recover(self, token, cleared):
        """Return to IDLE after a person cleared the tools and zone B.

        The token is single use, so a refused attempt issues a fresh one.
        """
        if self.journal.data['state'] not in _NEEDS_RECOVERY:
            raise TaskFault('Nothing to recover')
        self.gate.consume(token, RECOVERY)
        try:
            occupied = self._verified_scene(cleared)
            # A fault can leave attached or recorded objects behind in the planning scene.
            self.io.scene_reset()
            for index, filled in enumerate(occupied):
                if filled:
                    self.io.scene_add_slot_object(index + 1)
        except Exception:
            self.gate.issue(RECOVERY)
            raise
        if self.ctx.b_token is not None:
            self.zone.release(self.ctx.b_token, withdrawn=True, observation_clear=True)
            self.ctx.b_token = None
        self.slots.restore(occupied)
        self.journal.update(state='IDLE', active_arm='', holding={arm: 'empty' for arm in ARMS}, b_owner='',
                            occupied=occupied, slot=0, message='',
                            config_fingerprint=self.journal.fingerprint)

    def _verified_scene(self, cleared):
        if cleared is not True:
            raise TaskFault('Operator did not confirm that the tools and zone B are clear')
        for arm in ARMS:
            if not self.io.at_home(arm):
                raise TaskFault(f'{arm} is not at HOME')
        view = self.ctx.zone_view()
        if view.b_has_object or not view.b_arm_clear:
            raise TaskFault('Zone B must be empty and clear for recovery')
        grid = self.io.grid()
        if not grid.success:
            raise TaskFault(f'Grid observation invalid: {grid.message}')
        occupied = list(grid.occupied)
        count = sum(occupied)
        if occupied != [True] * count + [False] * (8 - count):
            raise TaskFault('C slots are not filled contiguously')
        if view.c_object_count != count:
            raise TaskFault('C count and grid observation disagree')
        return occupied
