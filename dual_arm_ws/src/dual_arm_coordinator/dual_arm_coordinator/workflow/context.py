"""Shared run state: persists each change before the action that depends on it."""
from .ports import TaskFault


class TaskContext:
    def __init__(self, io, settings, journal, zone, slots):
        self.io, self.settings, self.journal = io, settings, journal
        self.zone, self.slots = zone, slots
        self.b_token = None

    def step(self, arm, state):
        self.io.guard()
        self.journal.update(active_arm=arm, state=f'{arm.upper()}:{state}')

    def set_holding(self, arm, value):
        holding = self.journal.data['holding']
        holding[arm] = value
        self.journal.update(holding=holding)

    def occupied(self):
        return self.journal.data['occupied']

    def zone_view(self):
        view = self.io.zone()
        if not view.success:
            raise TaskFault(f'Zone observation invalid: {view.message}')
        return view

    def require_consistent_c(self, view):
        expected = self.occupied()
        if view.c_object_count != sum(expected):
            raise TaskFault(f'C count {view.c_object_count} differs from the record {sum(expected)}')
        grid = self.io.grid()
        if not grid.success:
            raise TaskFault(f'Grid observation invalid: {grid.message}')
        if list(grid.occupied) != expected:
            raise TaskFault('C grid observation differs from the record')

    def acquire_b(self, arm, view):
        self.b_token = self.zone.acquire(arm, observation_clear=view.b_arm_clear)
        self.journal.update(b_owner=arm)

    def release_b(self, arm, view):
        self.zone.release(self.b_token, withdrawn=self.io.at_home(arm), observation_clear=view.b_arm_clear)
        self.b_token = None
        self.journal.update(b_owner='')

    def point(self, xy, z):
        return (xy[0], xy[1], z)
