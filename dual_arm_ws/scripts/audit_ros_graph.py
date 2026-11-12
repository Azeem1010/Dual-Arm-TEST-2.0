#!/usr/bin/env python3
"""Check how the running nodes connect: topics, QoS, services and actions.

Usage: audit_ros_graph.py REPORT.json [--seconds N] [--with-hmi] [--expect FILE]

Run it against a live system (for example hmi_sim.launch.py or mock.launch.py) in
the same ROS domain. With --with-hmi the operator interface's two ROS nodes are
created here too (monitor and command), so their endpoints are part of the graph.

Reported problems:
- a topic with more than one type;
- a subscriber with no publisher, unless listed as optional in --expect;
- incompatible QoS: a reliable subscriber on a best-effort publisher, or a
  transient-local subscriber on a volatile publisher (DDS drops those matches);
- a service or action client whose server does not exist;
- a node name that appears more than once.
Publishers without subscribers are listed for information only.
The graph shows that endpoints match, not that the data in them is right.
"""
import argparse
import json
import sys
import time

import rclpy
from rclpy.node import Node
from rclpy.qos import DurabilityPolicy, ReliabilityPolicy

# Infrastructure topics every node creates, or that ROS tools use; not part of the system design.
_IGNORED_TOPICS = {'/parameter_events', '/rosout'}
_ACTION_SUFFIXES = ('/_action/feedback', '/_action/status')


def _qos_problem(pub, sub):
    p, s = pub.qos_profile, sub.qos_profile
    if p.reliability == ReliabilityPolicy.BEST_EFFORT and s.reliability == ReliabilityPolicy.RELIABLE:
        return 'subscriber wants reliable, publisher is best-effort'
    if p.durability == DurabilityPolicy.VOLATILE and s.durability == DurabilityPolicy.TRANSIENT_LOCAL:
        return 'subscriber wants transient-local, publisher is volatile'
    return None


def _label(info):
    return f'{info.node_namespace.rstrip("/")}/{info.node_name}'


def audit(node, expect):
    optional_topics = set(expect.get('optional_subscriptions', []))
    optional_services = set(expect.get('optional_services', []))
    report = {'topics': {}, 'problems': [], 'unread_publishers': [], 'services': {}, 'actions': {}}
    names = node.get_node_names_and_namespaces()
    seen = {}
    for name, namespace in names:
        full = f'{namespace.rstrip("/")}/{name}'
        seen[full] = seen.get(full, 0) + 1
    report['nodes'] = sorted(seen)
    report['problems'] += [f'node {name} appears {count} times' for name, count in seen.items() if count > 1]

    for topic, types in sorted(node.get_topic_names_and_types()):
        if topic in _IGNORED_TOPICS or topic.endswith(_ACTION_SUFFIXES):
            continue
        pubs = node.get_publishers_info_by_topic(topic)
        subs = node.get_subscriptions_info_by_topic(topic)
        report['topics'][topic] = {'types': types, 'publishers': sorted({_label(p) for p in pubs}),
                                   'subscribers': sorted({_label(s) for s in subs})}
        if len(types) > 1:
            report['problems'].append(f'{topic}: more than one type {types}')
        if subs and not pubs and topic not in optional_topics:
            report['problems'].append(f'{topic}: {len(subs)} subscriber(s) {sorted({_label(s) for s in subs})} but no publisher')
        if pubs and not subs:
            report['unread_publishers'].append(topic)
        for pub in pubs:
            for sub in subs:
                problem = _qos_problem(pub, sub)
                if problem:
                    report['problems'].append(f'{topic}: {_label(pub)} -> {_label(sub)}: {problem}')

    servers, clients = {}, {}
    for name, namespace in names:
        for service, types in node.get_service_names_and_types_by_node(name, namespace):
            servers.setdefault(service, set()).update(types)
        for service, types in node.get_client_names_and_types_by_node(name, namespace):
            clients.setdefault(service, {}).setdefault(f'{namespace.rstrip("/")}/{name}', set()).update(types)
    for service, users in sorted(clients.items()):
        if service.endswith(('/get_parameters', '/set_parameters', '/list_parameters', '/describe_parameters',
                             '/get_parameter_types', '/set_parameters_atomically', '/get_type_description')):
            if service not in servers and service not in optional_services:
                report['problems'].append(f'{service}: client(s) {sorted(users)} but no server')
            continue
        types = set().union(*users.values())
        report['services'][service] = {'clients': sorted(users), 'server': service in servers,
                                       'types': sorted(types | servers.get(service, set()))}
        if service.endswith(('/_action/send_goal', '/_action/get_result', '/_action/cancel_goal')):
            action = service.rsplit('/_action/', 1)[0]
            report['actions'].setdefault(action, {'clients': sorted(users), 'server': service in servers})
            if service not in servers and action not in optional_services:
                report['problems'].append(f'{action}: action client(s) {sorted(users)} but no server')
            continue
        if service not in servers and service not in optional_services:
            report['problems'].append(f'{service}: client(s) {sorted(users)} but no server')
        elif service in servers and len(types | servers[service]) > 1:
            report['problems'].append(f'{service}: client and server types differ {sorted(types | servers[service])}')
    report['problems'] = sorted(set(report['problems']))
    report['status'] = 'PASS' if not report['problems'] else 'FAIL'
    return report


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('report')
    parser.add_argument('--seconds', type=float, default=15.0, help='discovery time before reading the graph')
    parser.add_argument('--with-hmi', action='store_true')
    parser.add_argument('--expect', help='JSON with optional_subscriptions and optional_services')
    args = parser.parse_args()
    expect = json.loads(open(args.expect, encoding='utf-8').read()) if args.expect else {}
    hmi = []
    if args.with_hmi:
        from dual_arm_hmi.sources.ros_command import RosCommander
        from dual_arm_hmi.sources.ros_source import RosSource
        hmi = [RosSource(), RosCommander()]
    rclpy.init()
    node = Node('graph_audit')
    try:
        deadline = time.monotonic() + args.seconds
        while time.monotonic() < deadline:
            rclpy.spin_once(node, timeout_sec=0.2)
        report = audit(node, expect)
    finally:
        node.destroy_node()
        rclpy.shutdown()
        for item in hmi:
            item.close()
    with open(args.report, 'w', encoding='utf-8') as handle:
        json.dump(report, handle, indent=2, ensure_ascii=False)
        handle.write('\n')
    for problem in report['problems']:
        print('PROBLEM', problem)
    print(f"{report['status']}: {len(report['nodes'])} nodes, {len(report['topics'])} topics, "
          f"{len(report['problems'])} problem(s), {len(report['unread_publishers'])} unread publisher(s)")
    return 0 if report['status'] == 'PASS' else 1


if __name__ == '__main__':
    sys.exit(main())
