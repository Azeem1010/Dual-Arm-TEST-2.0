"""Measure what the vision nodes actually report in Gazebo; moves only to HOME.

Usage: probe_sim_vision.py REPORT.json
Requires vision_sim.launch.py with simulated homographies in calib_dir.
"""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import threading
import time
import traceback

from ament_index_python.packages import get_package_share_directory as share
import numpy as np
import rclpy
from rclpy.callback_groups import ReentrantCallbackGroup
from rclpy.executors import MultiThreadedExecutor
from rclpy.node import Node
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import CameraInfo, Image
from tf2_msgs.msg import TFMessage

from dual_arm_coordinator.gateways.motion import MotionGateway
from dual_arm_coordinator.homes import load_homes
from dual_arm_coordinator.task_config import load
from vision_interfaces.msg import PickDetections
from vision_interfaces.srv import GetGridState, GetPickTarget, GetZoneState, RecalibrateZones

BASES = {'arm1': (0.10, 0.08725), 'arm2': (-0.10, 0.08725)}
GZ = shutil.which('gz') or '/opt/ros/jazzy/opt/gz_tools_vendor/bin/gz'


def base_to_world(arm, x, y):
    x_origin, y_origin = BASES[arm]
    return (x_origin + y, y_origin - x)


class Probe:
    def __init__(self, report_path):
        self.report_path, self.report = Path(report_path), {}
        self.node = Node('sim_vision_probe')
        group = ReentrantCallbackGroup()
        self.executor = MultiThreadedExecutor(num_threads=4)
        self.executor.add_node(self.node)
        threading.Thread(target=self.executor.spin, daemon=True).start()
        self.poses, self.frames, self.infos, self.detections = {}, {}, {}, None
        for index in range(1, 9):
            name = f'cap_{index}'
            self.node.create_subscription(TFMessage, f'/ground_truth/{name}', self.pose_callback(name), qos_profile_sensor_data, callback_group=group)
        for camera in ('env', 'arm1', 'arm2'):
            self.node.create_subscription(Image, f'/{camera}_cam/image_raw', self.image_callback(camera), qos_profile_sensor_data, callback_group=group)
            self.node.create_subscription(CameraInfo, f'/{camera}_cam/camera_info', self.info_callback(camera), qos_profile_sensor_data, callback_group=group)
        self.node.create_subscription(PickDetections, '/vision/arm1/detections', self.on_detections, 10, callback_group=group)
        self.zone = self.node.create_client(GetZoneState, '/vision/env/get_zone_state', callback_group=group)
        self.recal = self.node.create_client(RecalibrateZones, '/vision/env/recalibrate_zones', callback_group=group)
        self.pick = self.node.create_client(GetPickTarget, '/vision/arm1/get_pick_target', callback_group=group)
        self.grid = self.node.create_client(GetGridState, '/vision/arm2/get_grid_state', callback_group=group)
        package = Path(share('dual_arm_coordinator')) / 'config' / 'sim'
        config = load(package / 'coordinator.yaml')
        urdf = (Path(share('dual_arm_description')) / 'urdf' / 'dual_arm_cad.urdf.xacro').read_text(encoding='utf-8')
        self.gateway = MotionGateway(self.node, config, urdf, load_homes(config, runtime_path=package / 'runtime.json'), lambda: None, group)
        self.slots = config['zones']['c_slots_xy_m']

    def pose_callback(self, name):
        def receive(message):
            if message.transforms:
                p = message.transforms[0].transform.translation
                self.poses[name] = (p.x, p.y, p.z)
        return receive

    def image_callback(self, camera):
        def receive(message):
            self.frames[camera] = {'frame_id': message.header.frame_id, 'size': [message.width, message.height],
                                   'stamp': message.header.stamp.sec + message.header.stamp.nanosec * 1e-9}
        return receive

    def info_callback(self, camera):
        def receive(message):
            self.infos[camera] = {'fx': message.k[0], 'fy': message.k[4], 'cx': message.k[2], 'cy': message.k[5]}
        return receive

    def on_detections(self, message):
        self.detections = message

    def call(self, client, request, timeout=30):
        if not client.wait_for_service(timeout_sec=120):
            raise RuntimeError(f'{client.srv_name} unavailable')
        future = client.call_async(request)
        deadline = time.monotonic() + timeout
        while not future.done():
            if time.monotonic() > deadline:
                raise RuntimeError(f'{client.srv_name} timed out')
            time.sleep(0.01)
        return future.result()

    def save(self):
        self.report_path.write_text(json.dumps(self.report, indent=2, default=float) + '\n', encoding='utf-8')

    def wait_for(self, predicate, timeout, label):
        deadline = time.monotonic() + timeout
        while time.monotonic() < deadline:
            if predicate():
                return
            time.sleep(0.05)
        raise RuntimeError(f'Timed out waiting for {label}')

    def move_cap(self, name, x, y):
        request = f'name: "{name}", position: {{x: {x}, y: {y}, z: 0.019}}, orientation: {{w: 1}}'
        result = subprocess.run([GZ, 'service', '-s', '/world/dual_arm_workspace/set_pose', '--reqtype', 'gz.msgs.Pose',
                                 '--reptype', 'gz.msgs.Boolean', '--timeout', '5000', '--req', request],
                                capture_output=True, text=True, env=os.environ)
        return result.stdout.strip() + result.stderr.strip()

    def zone_snapshot(self):
        response = self.call(self.zone, GetZoneState.Request())
        return {key: getattr(response, key) for key in ('success', 'message', 'a_has_object', 'b_has_object', 'b_arm_clear', 'c_object_count')}

    def grid_snapshot(self):
        response = self.call(self.grid, GetGridState.Request())
        result = {'success': response.success, 'message': response.message, 'occupied': list(response.occupied)}
        if response.success:
            world = [base_to_world('arm2', x, y) for x, y in zip(response.place_x, response.place_y)]
            errors = [float(np.hypot(w[0] - s[0], w[1] - s[1])) for w, s in zip(world, self.slots)]
            result.update(place_world=world, place_z=list(response.place_z), slot_errors_m=errors, max_slot_error_m=max(errors))
        return result

    def pick_snapshot(self):
        response = self.call(self.pick, GetPickTarget.Request(target_rank=0, peek_only=True))
        result = {'success': response.success, 'message': response.message, 'x_base': response.x, 'y_base': response.y, 'z_base': response.z}
        if response.success:
            result['world'] = base_to_world('arm1', response.x, response.y)
        return result

    def detection_errors(self):
        self.detections = None
        self.wait_for(lambda: self.detections is not None, 30, 'detections')
        message = self.detections
        result = {'valid': message.valid, 'message': message.message, 'count': message.count, 'base_valid': message.base_valid, 'base_z': message.base_z}
        if message.base_valid and message.count:
            matches = {}
            for x, y in zip(message.base_x, message.base_y):
                world = base_to_world('arm1', x, y)
                name = min(self.poses, key=lambda cap: np.hypot(self.poses[cap][0] - world[0], self.poses[cap][1] - world[1]))
                matches[name] = {'detected_world': world, 'error_m': float(np.hypot(self.poses[name][0] - world[0], self.poses[name][1] - world[1]))}
            result.update(per_cap=matches, max_error_m=max(item['error_m'] for item in matches.values()))
        return result

    def run(self):
        self.wait_for(lambda: len(self.poses) == 8 and len(self.frames) == 3 and len(self.infos) == 3, 180, 'camera and truth topics')
        self.report['camera_frames'], self.report['camera_info'] = dict(self.frames), dict(self.infos)
        self.gateway._cfg = {**self.gateway._cfg, 'goal_submit_s': 60.0}
        self.gateway.move_home('arm1')
        self.gateway.move_home('arm2')
        self.report['at_home'] = [self.gateway.at_home('arm1'), self.gateway.at_home('arm2')]
        self.save()
        recalibrated = self.call(self.recal, RecalibrateZones.Request(), timeout=60)
        self.report['recalibrate_zones'] = {'success': recalibrated.success, 'message': recalibrated.message}
        time.sleep(2.0)
        self.report['initial'] = {'zone': self.zone_snapshot(), 'grid': self.grid_snapshot(), 'pick': self.pick_snapshot(), 'detections': self.detection_errors()}
        self.save()
        self.report['move_caps'] = [self.move_cap('cap_1', *self.slots[0]), self.move_cap('cap_2', *self.slots[1])]
        time.sleep(4.0)
        self.report['after_moving_caps_to_slots_1_2'] = {'truth': {k: self.poses[k] for k in ('cap_1', 'cap_2')}, 'zone': self.zone_snapshot(),
                                                         'grid': self.grid_snapshot(), 'pick': self.pick_snapshot(), 'detections': self.detection_errors()}
        self.save()
        self.report['status'] = 'measurement complete'
        self.save()


def main():
    rclpy.init()
    probe = Probe(sys.argv[1])
    code = 0
    try:
        probe.run()
    except Exception as error:
        probe.report['error'] = f'{error}\n{traceback.format_exc()}'
        probe.save()
        print(probe.report['error'], flush=True)
        code = 1
    print(json.dumps(probe.report, indent=1, default=float)[:6000], flush=True)
    os._exit(code)


if __name__ == '__main__':
    main()
