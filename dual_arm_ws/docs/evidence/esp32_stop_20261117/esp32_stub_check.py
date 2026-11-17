"""Stand-in ESP32 (echoes /suction_command on /suction_status) against RosCommander."""
import threading, time
import rclpy
from rclpy.node import Node
from std_msgs.msg import Int32
from dual_arm_hmi.sources.ros_command import RosCommander, SUCTION_OFF, request_for

rclpy.init()
stub = Node('suction_controller_node')
got = []
pub = stub.create_publisher(Int32, '/suction_status', 10)
stub.create_subscription(Int32, '/suction_command', lambda m: (got.append(m.data), pub.publish(Int32(data=m.data))), 10)
threading.Thread(target=rclpy.spin, args=(stub,), daemon=True).start()
cmd = RosCommander()
deadline = time.monotonic() + 10
while not cmd.available(SUCTION_OFF) and time.monotonic() < deadline:
    time.sleep(0.1)
print('available', cmd.available(SUCTION_OFF))
t0 = time.monotonic()
cmd.send(1, [(SUCTION_OFF, request_for(SUCTION_OFF))])
replies = []
while not replies and time.monotonic() - t0 < 3:
    replies = cmd.results(); time.sleep(0.02)
print('reply', replies, f'{time.monotonic()-t0:.3f}s', 'stub received', got)
stub.destroy_node()
time.sleep(1.0)
print('available after stub gone', cmd.available(SUCTION_OFF))
cmd.send(2, [(SUCTION_OFF, request_for(SUCTION_OFF))]); print('reply without board', cmd.results())
cmd.close(); rclpy.shutdown()
