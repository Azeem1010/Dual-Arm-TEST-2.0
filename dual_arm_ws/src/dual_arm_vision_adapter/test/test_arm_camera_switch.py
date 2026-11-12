import os
import sys
import tempfile
import unittest

from dual_arm_vision_adapter.arm_camera_switch import ArmCameraSwitch, active_arm_from_status
from dual_arm_vision_adapter.processes import device_in_use

DEVICES = {'arm1': '/dev/arm1-video', 'arm2': '/dev/arm2-video'}


class FakeProcess:
    def __init__(self, world, arm):
        self.world, self.arm = world, arm
        self.alive, self.ignores_term = False, world.ignore_term

    def start(self):
        self.world.events.append(('start', self.arm))
        self.alive = True
        self.world.busy.add(DEVICES[self.arm])
        self.world.check_overlap()

    def running(self):
        return self.alive

    def terminate(self):
        self.world.events.append(('term', self.arm))
        if not self.ignores_term:
            self.exit()

    def kill(self):
        self.world.events.append(('kill', self.arm))
        self.exit()

    def exit(self):
        self.alive = False
        self.world.busy.discard(DEVICES[self.arm])


class World:
    def __init__(self):
        self.events, self.processes, self.busy = [], [], set()
        self.ignore_term = False
        self.now = 0.0

    def launcher(self, arm):
        process = FakeProcess(self, arm)
        self.processes.append(process)
        return process

    def running(self):
        return sorted(p.arm for p in self.processes if p.alive)

    def check_overlap(self):
        assert len(self.running()) <= 1, f'two arm cameras streaming: {self.running()}'


class Base(unittest.TestCase):
    def setUp(self):
        self.world = World()
        self.switch = ArmCameraSwitch(self.world.launcher, DEVICES.get, self.world.busy.__contains__,
                                      clock=lambda: self.world.now, term_timeout_s=3.0, status_max_age_s=2.0)

    def run_ticks(self, count=5, step=0.2):
        for _ in range(count):
            self.switch.tick()
            self.world.check_overlap()
            self.world.now += step

    def status(self, arm):
        self.switch.on_status(arm)


class Switching(Base):
    def test_boot_starts_arm1(self):
        self.run_ticks()
        self.assertEqual(self.world.running(), ['arm1'])
        self.assertEqual(self.switch.state(), {'want': 'arm1', 'streaming': 'arm1', 'phase': 'on', 'message': ''})

    def test_switch_stops_before_start(self):
        self.status('arm1')
        self.run_ticks()
        self.status('arm2')
        self.run_ticks()
        self.assertEqual(self.world.events, [('start', 'arm1'), ('term', 'arm1'), ('start', 'arm2')])
        self.assertEqual(self.world.running(), ['arm2'])

    def test_escalates_to_sigkill_before_starting_next(self):
        self.world.ignore_term = True
        self.run_ticks()
        self.status('arm2')
        self.run_ticks(count=10, step=0.2)
        self.assertEqual(self.switch.state()['phase'], 'switching')
        self.assertNotIn(('start', 'arm2'), self.world.events)
        self.run_ticks(count=10, step=0.2)
        events = self.world.events
        self.assertLess(events.index(('kill', 'arm1')), events.index(('start', 'arm2')))
        self.assertEqual(self.world.running(), ['arm2'])

    def test_refuses_to_start_when_other_device_busy(self):
        self.world.busy.add(DEVICES['arm2'])
        self.run_ticks()
        state = self.switch.state()
        self.assertEqual(state['phase'], 'error')
        self.assertIn(DEVICES['arm2'], state['message'])
        self.assertEqual(self.world.events, [])
        self.world.busy.discard(DEVICES['arm2'])
        self.run_ticks()
        self.assertEqual(self.world.running(), ['arm1'])

    def test_waits_until_old_device_released(self):
        self.run_ticks()
        self.status('arm2')
        self.world.processes[0].terminate = lambda: (self.world.events.append(('term', 'arm1')),
                                                    setattr(self.world.processes[0], 'alive', False))
        self.run_ticks()
        self.assertEqual(self.switch.state()['phase'], 'switching')
        self.assertNotIn(('start', 'arm2'), self.world.events)
        self.world.busy.discard(DEVICES['arm1'])
        self.run_ticks()
        self.assertEqual(self.world.running(), ['arm2'])

    def test_rapid_changes_never_overlap(self):
        self.world.ignore_term = True
        self.run_ticks()
        for arm in ('arm2', 'arm1', 'arm2'):
            self.status(arm)
            self.run_ticks(count=2)
        self.run_ticks(count=30)
        self.assertEqual(self.world.running(), ['arm2'])
        self.assertEqual(self.switch.state()['phase'], 'on')

    def test_stale_status_keeps_current(self):
        self.status('arm2')
        self.run_ticks()
        self.world.now += 10.0
        self.run_ticks()
        self.assertEqual(self.world.running(), ['arm2'])
        self.assertEqual(self.world.events.count(('start', 'arm2')), 1)

    def test_crash_restarts_only_wanted(self):
        self.run_ticks()
        self.world.processes[0].exit()
        self.run_ticks()
        self.assertEqual(self.world.events, [('start', 'arm1'), ('start', 'arm1')])
        self.assertEqual(self.world.running(), ['arm1'])

    def test_unknown_status_means_idle(self):
        self.status('arm2')
        self.run_ticks()
        self.status('')
        self.run_ticks()
        self.assertEqual(self.world.running(), ['arm1'])

    def test_stop_ends_streaming(self):
        self.run_ticks()
        self.switch.shutdown()
        self.assertEqual(self.world.running(), [])


class StatusParsing(unittest.TestCase):
    def test_active_arm_from_status(self):
        self.assertEqual(active_arm_from_status('{"active_arm": "arm2", "state": "ARM2:APPROACH_B"}'), 'arm2')
        self.assertEqual(active_arm_from_status('{"active_arm": ""}'), '')
        self.assertEqual(active_arm_from_status('{"active_arm": "arm9"}'), '')
        self.assertIsNone(active_arm_from_status('not json'))


@unittest.skipUnless(sys.platform.startswith('linux'), 'reads /proc')
class DeviceInUse(unittest.TestCase):
    def test_device_in_use_detects_open_fd(self):
        with tempfile.NamedTemporaryFile() as handle:
            self.assertTrue(device_in_use(handle.name))
            path = handle.name
        self.assertFalse(os.path.exists(path))
        with tempfile.TemporaryDirectory() as folder:
            closed = os.path.join(folder, 'video')
            open(closed, 'w').close()
            self.assertFalse(device_in_use(closed))


if __name__ == '__main__':
    unittest.main()
