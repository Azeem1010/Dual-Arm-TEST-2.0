"""One-shot operator commands for the coordinator services.

Confirmations and recovery state a physical fact, so each needs an explicit flag.
"""
import argparse
import json
import sys
import time

STATUS_WAIT_S = 5.0
SERVICE_WAIT_S = 10.0


class ConsoleError(RuntimeError):
    """The command cannot be sent."""


def confirmation_token(status):
    if not status or not status.get('suction_token'):
        raise ConsoleError('No suction step is waiting for confirmation')
    return status['suction_token']


def recovery_token(status):
    if not status or not status.get('recovery_token'):
        raise ConsoleError('The coordinator is not waiting for recovery')
    return status['recovery_token']


def parse_arguments(argv):
    parser = argparse.ArgumentParser(description='Operator commands for the dual arm coordinator.')
    commands = parser.add_subparsers(dest='command', required=True)
    commands.add_parser('status')
    commands.add_parser('start')
    commands.add_parser('cancel')
    confirm = commands.add_parser('confirm', help='report the result of the suction step in progress')
    result = confirm.add_mutually_exclusive_group(required=True)
    result.add_argument('--success', action='store_true')
    result.add_argument('--failed', action='store_true')
    confirm.add_argument('--message', default='')
    recover = commands.add_parser('recover', help='after clearing the tools and zone B by hand')
    recover.add_argument('--cleared', action='store_true', required=True, help='both tools and zone B were checked and are clear')
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_arguments(argv)
    import os
    import threading

    import rclpy
    from rclpy.executors import MultiThreadedExecutor
    from rclpy.node import Node
    from rclpy.qos import DurabilityPolicy, QoSProfile
    from std_msgs.msg import String
    from std_srvs.srv import Trigger

    from dual_arm_interfaces.srv import ConfirmStep

    rclpy.init()
    node = Node('operator_console')
    executor = MultiThreadedExecutor(num_threads=2)
    executor.add_node(node)
    threading.Thread(target=executor.spin, daemon=True).start()
    latest = {}
    qos = QoSProfile(depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL)
    node.create_subscription(String, '/dual_arm/status', lambda message: latest.update(json.loads(message.data)), qos)
    deadline = time.monotonic() + STATUS_WAIT_S
    while not latest and time.monotonic() < deadline:
        time.sleep(0.02)

    def call(kind, name, request):
        client = node.create_client(kind, name)
        if not client.wait_for_service(timeout_sec=SERVICE_WAIT_S):
            raise ConsoleError(f'{name} is unavailable')
        future = client.call_async(request)
        limit = time.monotonic() + 60.0
        while not future.done():
            if time.monotonic() >= limit:
                raise ConsoleError(f'{name} timed out')
            time.sleep(0.01)
        return future.result()

    code = 0
    try:
        if args.command == 'status':
            if not latest:
                raise ConsoleError('No status from the coordinator')
            output = latest
        elif args.command in ('start', 'cancel'):
            response = call(Trigger, f'/dual_arm/{args.command}', Trigger.Request())
            output = {'accepted': response.success, 'message': response.message}
            code = 0 if response.success else 1
        elif args.command == 'confirm':
            request = ConfirmStep.Request(token=confirmation_token(latest), success=args.success, message=args.message)
            response = call(ConfirmStep, '/dual_arm/confirm', request)
            output = {'accepted': response.accepted, 'message': response.message}
            code = 0 if response.accepted else 1
        else:
            request = ConfirmStep.Request(token=recovery_token(latest), success=True, message='operator recovery')
            response = call(ConfirmStep, '/dual_arm/recover', request)
            output = {'accepted': response.accepted, 'message': response.message}
            code = 0 if response.accepted else 1
    except ConsoleError as error:
        output, code = {'error': str(error)}, 1
    print(json.dumps(output, indent=2, sort_keys=True), flush=True)
    os._exit(code)


if __name__ == '__main__':
    sys.exit(main())
