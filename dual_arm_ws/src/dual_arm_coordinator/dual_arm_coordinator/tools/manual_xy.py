"""Move one arm above an XY point at the configured travel height. Plans only by default.

Refuses while the coordinator is running a task. The hardware template cannot load,
so this tool cannot move real arms until the task configuration has been measured.
"""
import argparse
import json
import math
from pathlib import Path
import sys
import threading
import time

from ..workflow.ports import TaskFault

ARMS = ('arm1', 'arm2')
STATUS_WAIT_S = 2.0


def manual_move(motion, config, arm, x, y, execute, to_world, status):
    """Check the target and optionally move; raises TaskFault on any refusal."""
    if arm not in ARMS:
        raise TaskFault(f'Unknown arm {arm}')
    if not all(math.isfinite(value) for value in (x, y)):
        raise TaskFault('Target must be finite')
    if status is not None and status.get('busy'):
        raise TaskFault('The coordinator is running a task')
    height = config['heights']['approach_z_m']
    target_x, target_y = to_world(arm, x, y)
    target = (target_x, target_y, height)
    motion.check_reachable(arm, target)
    report = {'arm': arm, 'target_world_m': list(target), 'reachable': True, 'executed': False}
    if execute:
        motion.move_to(arm, target)
        report['executed'] = True
        report['tcp_after'] = motion.tcp_report(arm)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description='Plan, and only with --execute perform, a move above an XY point.')
    parser.add_argument('--arm', choices=ARMS, default='arm1')
    parser.add_argument('--x', type=float, required=True)
    parser.add_argument('--y', type=float, required=True)
    parser.add_argument('--frame', choices=('base', 'world'), default='base', help='base is the arm vision frame, world the URDF root')
    parser.add_argument('--execute', action='store_true')
    parser.add_argument('--config', default='')
    parser.add_argument('--runtime', default='')
    parser.add_argument('--calibration', default='')
    args = parser.parse_args(argv)

    from ament_index_python.packages import get_package_share_directory as share
    import rclpy
    from rclpy.callback_groups import ReentrantCallbackGroup
    from rclpy.executors import MultiThreadedExecutor
    from rclpy.node import Node
    from rclpy.qos import DurabilityPolicy, QoSProfile
    from std_msgs.msg import String

    from ..gateways.motion import MotionGateway
    from ..gateways.vision import make_transformer
    from ..homes import load_homes
    from ..task_config import TaskConfigError, load

    package = Path(share('dual_arm_coordinator')) / 'config' / 'sim'
    try:
        config = load(args.config or package / 'coordinator.yaml')
    except TaskConfigError as error:
        print(json.dumps({'status': 'FAIL', 'error': str(error)}))
        return 1
    urdf = (Path(share('dual_arm_description')) / 'urdf' / 'dual_arm_cad.urdf.xacro').read_text(encoding='utf-8')
    homes = load_homes(config, runtime_path=args.runtime or package / 'runtime.json', calibration_path=args.calibration or None)

    rclpy.init()
    node = Node('manual_xy')
    executor = MultiThreadedExecutor(num_threads=3)
    executor.add_node(node)
    threading.Thread(target=executor.spin, daemon=True).start()
    group = ReentrantCallbackGroup()
    latest = {}
    qos = QoSProfile(depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL)
    node.create_subscription(String, '/dual_arm/status', lambda message: latest.update(json.loads(message.data)), qos, callback_group=group)
    time.sleep(STATUS_WAIT_S)
    motion = MotionGateway(node, config, urdf, homes, lambda: None, group)
    transform = make_transformer(node, config)

    def to_world(arm, x, y):
        if args.frame == 'world':
            return x, y
        deadline = time.monotonic() + 5.0
        while True:
            try:
                return transform(arm, x, y, 0.0)[:2]
            except TaskFault:
                if time.monotonic() >= deadline:
                    raise
                time.sleep(0.05)

    try:
        report = manual_move(motion, config, args.arm, args.x, args.y, args.execute, to_world, latest or None)
        report['status'] = 'PASS'
        code = 0
    except TaskFault as error:
        report, code = {'status': 'FAIL', 'error': str(error)}, 1
    print(json.dumps(report, indent=2), flush=True)
    import os
    os._exit(code)


if __name__ == '__main__':
    sys.exit(main())
