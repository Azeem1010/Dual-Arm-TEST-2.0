"""E0: send suction commands 1-4 one by one and time each echo."""
import threading
import time

import rclpy
from rclpy.node import Node
from std_msgs.msg import Int32

PLAN = [(1, 'module 1 grasp', 5.0), (2, 'module 1 release', 3.0),
        (3, 'module 2 grasp', 5.0), (4, 'module 2 release', 0.0)]

rclpy.init()
node = Node('e0_suction_check')
pub = node.create_publisher(Int32, '/suction_command', 10)
echo, got = [None], threading.Event()


def on_status(msg):
    echo[0] = (msg.data, time.monotonic())
    got.set()


node.create_subscription(Int32, '/suction_status', on_status, 10)
threading.Thread(target=rclpy.spin, args=(node,), daemon=True).start()

deadline = time.monotonic() + 10
while not (node.count_subscribers('/suction_command') and node.count_publishers('/suction_status')):
    if time.monotonic() > deadline:
        raise SystemExit('ESP32 not connected')
    time.sleep(0.05)
time.sleep(0.5)

sent_release = set()
try:
    for command, label, hold in PLAN:
        got.clear()
        t0 = time.monotonic()
        pub.publish(Int32(data=command))
        print(f'{time.strftime("%H:%M:%S")} sent {command} ({label})', flush=True)
        if got.wait(3.0):
            value, t1 = echo[0]
            print(f'    echo {value} after {(t1 - t0) * 1000:.0f} ms', flush=True)
        else:
            print('    NO ECHO within 3 s', flush=True)
        if command in (2, 4):
            sent_release.add(command)
        time.sleep(hold)
finally:
    for command in (2, 4):
        if command not in sent_release:
            pub.publish(Int32(data=command))
            print(f'cleanup: sent release {command}', flush=True)
    time.sleep(1.0)
    node.destroy_node()
    rclpy.shutdown()
