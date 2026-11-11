"""Dump the live ROS 2 graph (per-node interfaces and per-topic QoS) as JSON."""
import json
import sys
import time

import rclpy
from rclpy.action import graph as action_graph


def qos(info):
    profile = info.qos_profile
    return {
        'node': info.node_namespace.rstrip('/') + '/' + info.node_name,
        'reliability': profile.reliability.name,
        'durability': profile.durability.name,
        'depth': profile.depth,
    }


def main(path):
    rclpy.init()
    node = rclpy.create_node('graph_dump_probe')
    time.sleep(10.0)
    result = {'nodes': {}, 'topics': {}, 'services': {}}
    for name, namespace in sorted(node.get_node_names_and_namespaces()):
        if name == 'graph_dump_probe':
            continue
        full = namespace.rstrip('/') + '/' + name
        try:
            result['nodes'][full] = {
                'pub': sorted(node.get_publisher_names_and_types_by_node(name, namespace)),
                'sub': sorted(node.get_subscriber_names_and_types_by_node(name, namespace)),
                'srv': sorted(node.get_service_names_and_types_by_node(name, namespace)),
                'cli': sorted(node.get_client_names_and_types_by_node(name, namespace)),
                'action_srv': sorted(action_graph.get_action_server_names_and_types_by_node(node, name, namespace)),
                'action_cli': sorted(action_graph.get_action_client_names_and_types_by_node(node, name, namespace)),
            }
        except Exception as exc:  # A node can vanish mid-dump; record it instead of hiding it.
            result['nodes'][full] = {'error': repr(exc)}
    for topic, types in sorted(node.get_topic_names_and_types()):
        result['topics'][topic] = {
            'types': types,
            'publishers': [qos(i) for i in node.get_publishers_info_by_topic(topic)],
            'subscribers': [qos(i) for i in node.get_subscriptions_info_by_topic(topic)],
        }
    result['services'] = sorted(node.get_service_names_and_types())
    with open(path, 'w', encoding='utf-8') as handle:
        json.dump(result, handle, indent=1, ensure_ascii=False)
    print('nodes', len(result['nodes']), 'topics', len(result['topics']), 'services', len(result['services']))
    node.destroy_node()
    rclpy.shutdown()


if __name__ == '__main__':
    main(sys.argv[1])
