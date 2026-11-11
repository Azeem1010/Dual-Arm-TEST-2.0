"""Measures simulation speed and camera rate over a wall-clock window. Usage: stage1_rtf.py SECONDS"""
import json
import sys
import time

from rosgraph_msgs.msg import Clock
import rclpy
from rclpy.qos import qos_profile_sensor_data
from sensor_msgs.msg import Image

rclpy.init()
node = rclpy.create_node('stage1_rtf_probe')
clock, frames = [], [0]
node.create_subscription(Clock, '/clock', lambda m: clock.append((time.monotonic(), m.clock.sec + m.clock.nanosec * 1e-9)), qos_profile_sensor_data)
node.create_subscription(Image, '/env_cam/image_raw', lambda _m: frames.__setitem__(0, frames[0] + 1), qos_profile_sensor_data)
end = time.monotonic() + float(sys.argv[1])
while time.monotonic() < end:
    rclpy.spin_once(node, timeout_sec=0.05)
wall = clock[-1][0] - clock[0][0]
print(json.dumps({'real_time_factor': round((clock[-1][1] - clock[0][1]) / wall, 3), 'env_cam_fps': round(frames[0] / wall, 2), 'wall_s': round(wall, 1)}), flush=True)
