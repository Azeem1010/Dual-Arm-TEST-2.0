"""Vision-chosen pick targets through the coordinator in Gazebo.

Usage: test_vision_pick_sim.py WORK_DIR REPORT.json CALIB_DIR PROBE.json REVISION
Requires vision_sim.launch.py and calibration.launch.py. Zone and slot state still
come from ground truth, because the fixed simulated cameras are occluded at HOME.
"""
import math
import os
import shutil
import subprocess
import sys
import time
import traceback

from diagnostic_msgs.msg import DiagnosticArray, DiagnosticStatus
import rclpy
from rclpy.qos import qos_profile_sensor_data
from tf2_msgs.msg import TFMessage
from vision_interfaces.srv import GetPickTarget

from test_transfer_regression import Regression

GZ = shutil.which('gz') or '/opt/ros/jazzy/opt/gz_tools_vendor/bin/gz'
PARK = (0.35, 0.30)
ARM1_BASE = (-0.10, 0.08725)


class VisionPick(Regression):
    def __init__(self, work_dir, report_path, calib_dir, probe, revision):
        super().__init__(work_dir, report_path)
        self.calib_dir, self.probe, self.revision = calib_dir, probe, revision
        self.calibration = {}
        self.node.create_subscription(DiagnosticArray, '/vision/calibration_status', self.on_calibration, 10)
        self.pick_client = self.node.create_client(GetPickTarget, '/vision/arm1/get_pick_target')
        self.poses, self.rotations = {}, {}
        for index in range(1, 9):
            name = f'cap_{index}'
            self.node.create_subscription(TFMessage, f'/ground_truth/{name}', self.pose_callback(name), qos_profile_sensor_data)

    def pose_callback(self, name):
        def receive(message):
            if message.transforms:
                position = message.transforms[0].transform.translation
                rotation = message.transforms[0].transform.rotation
                self.poses[name] = (position.x, position.y, position.z)
                self.rotations[name] = (rotation.x, rotation.y, rotation.z, rotation.w)
        return receive

    def on_calibration(self, message):
        for status in message.status:
            self.calibration[status.hardware_id] = (status.level == DiagnosticStatus.OK, [item.value for item in status.values])

    def park_cap(self, name):
        request = f'name: "{name}", position: {{x: {PARK[0]}, y: {PARK[1]}, z: 0.019}}, orientation: {{w: 1}}'
        result = subprocess.run([GZ, 'service', '-s', '/world/dual_arm_workspace/set_pose', '--reqtype', 'gz.msgs.Pose',
                                 '--reptype', 'gz.msgs.Boolean', '--timeout', '5000', '--req', request],
                                capture_output=True, text=True, env=os.environ)
        return 'true' in result.stdout

    def wait_calibration(self, passed, timeout):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            state = self.calibration.get('arm1')
            if state is not None and state[0] is passed:
                return state
            time.sleep(0.1)
        raise RuntimeError(f'arm1 calibration did not become {passed}: {self.calibration.get("arm1")}')

    def refused_without_calibration(self):
        reasons = self.wait_calibration(False, 60)
        self.observe('calibration_status_without_record', reasons[1])
        self.start_coordinator(journal=self.fresh_journal('no_record'), extra=['observation_source:=vision_pick', 'calibration_status_max_age_s:=30.0'])
        time.sleep(4.0)
        self.check('start_accepted', self.trigger('start').success)
        status = self.wait_end(240)
        self.check('missing_calibration_stops_before_touching_an_object',
                   status['state'] == 'FAULT' and 'not valid' in status['message'] and set(status['holding'].values()) == {'empty'}
                   and status['b_owner'] == '', status['message'])
        zone = self.truth.zone()
        self.check('no_object_moved', zone.success and not zone.b_has_object and zone.c_object_count == 0)
        self.kill_coordinator()

    def write_record(self):
        result = subprocess.run([sys.executable, 'scripts/generate_sim_vision_calibration.py', self.calib_dir, 'arm1', self.probe, self.revision],
                                capture_output=True, text=True)
        self.observe('calibration_record', (result.stdout + result.stderr).strip())
        state = self.wait_calibration(True, 60)
        self.check('record_passes_calibration_status', state[0], state[1])

    def vision_target_error(self):
        if not self.pick_client.wait_for_service(timeout_sec=30):
            raise RuntimeError('Pick service unavailable')
        response = self.call(self.pick_client, GetPickTarget.Request(target_rank=0, peek_only=True))
        if not response.success:
            return {'success': False, 'message': response.message}
        world = (ARM1_BASE[0] + response.y, ARM1_BASE[1] - response.x)
        name = min(self.poses, key=lambda cap: math.hypot(self.poses[cap][0] - world[0], self.poses[cap][1] - world[1]))
        return {'success': True, 'cap': name, 'world': world, 'error_m': math.hypot(self.poses[name][0] - world[0], self.poses[name][1] - world[1])}

    def two_objects_by_vision(self):
        first = self.vision_target_error()
        self.observe('first_vision_target', first)
        self.check('first_target_within_suction_tolerance', first.get('success') and first['error_m'] <= 0.001, first)
        self.start_coordinator(cycles=2, journal=self.fresh_journal('vision_two'), extra=['observation_source:=vision_pick', 'calibration_status_max_age_s:=30.0'])
        time.sleep(4.0)
        self.check('vision_run_accepted', self.trigger('start').success)
        status = self.wait_end(1400)
        self.check('two_objects_succeeded_with_vision_targets', status['state'] == 'SUCCEEDED', status['message'])
        slots = self.physical_slots()
        self.check('ground_truth_has_caps_in_slots_3_and_4', slots == [False, False, True, True] + [False] * 4, slots)
        self.observe('final_cap_positions', dict(self.poses))
        self.observe('final_cap_rotations_xyzw', dict(self.rotations))
        self.observe('final_tcp', {arm: self.operator.tcp_report(arm) for arm in ('arm1', 'arm2')})

    def run_all(self):
        deadline = time.monotonic() + 180
        while len(self.poses) < 8 and time.monotonic() < deadline:
            time.sleep(0.1)
        self.check('unreachable_caps_parked', self.park_cap('cap_1') and self.park_cap('cap_2'))
        time.sleep(4.0)
        self.refused_without_calibration()
        self.write_record()
        self.two_objects_by_vision()


def main():
    rclpy.init()
    harness = VisionPick(*sys.argv[1:6])
    try:
        harness.run_all()
        passed = all(item['status'] == 'PASS' for item in harness.report['checks'].values())
        harness.report['status'] = 'PASS' if passed else 'FAIL'
        harness.save()
    except Exception as error:
        harness.report['error'] = f'{error}\n{traceback.format_exc()}'
        harness.save()
        print(harness.report['error'], flush=True)
        passed = False
    harness.close()
    print(harness.report['status'], flush=True)
    os._exit(0 if passed else 1)


if __name__ == '__main__':
    main()
