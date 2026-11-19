"""Dump the complete ROS 2 graph (nodes, topics, services, actions) to Graphviz .dot files.

Usage: python3 gen_ros_graph.py <out_prefix>
Writes <prefix>_full.dot (everything) and <prefix>_clean.dot (no rosout /
parameter_events / per-node parameter services / ros2cli daemon / rqt).
"""
import sys
import time

import rclpy
from rclpy.node import Node

prefix = sys.argv[1]
rclpy.init()
n = Node('full_graph_dumper')

# wait until discovery is stable (node count unchanged for 3 s, max 20 s)
last, stable, t0 = -1, 0.0, time.time()
while time.time() - t0 < 20 and stable < 3.0:
    rclpy.spin_once(n, timeout_sec=0.5)
    c = len(n.get_node_names_and_namespaces())
    if c == last:
        stable += 0.5
    else:
        last, stable = c, 0.0

me = n.get_fully_qualified_name()
nodes = []
for name, ns in n.get_node_names_and_namespaces():
    fq = (ns.rstrip('/') + '/' + name) if ns != '/' else '/' + name
    if fq != me:
        nodes.append((name, ns, fq))

PARAM_SRV = ('describe_parameters', 'get_parameter_types', 'get_parameters',
             'get_type_description', 'list_parameters', 'set_parameters',
             'set_parameters_atomically')

topics, services, actions = {}, {}, {}
edges = set()  # (src_id, dst_id, style)
for name, ns, fq in nodes:
    nid = 'n:' + fq
    try:
        pubs = n.get_publisher_names_and_types_by_node(name, ns)
        subs = n.get_subscriber_names_and_types_by_node(name, ns)
        srvs = n.get_service_names_and_types_by_node(name, ns)
        clis = n.get_client_names_and_types_by_node(name, ns)
    except Exception as e:
        print('skip', fq, e)
        continue

    def classify(nm):
        # collapse action plumbing into a single action node
        for key in ('/_action/feedback', '/_action/status',
                    '/_action/send_goal', '/_action/get_result', '/_action/cancel_goal'):
            if nm.endswith(key):
                return 'a', nm[: -len(key)]
        return None, nm

    for t, ty in pubs:
        k, base = classify(t)
        if k == 'a':
            actions[base] = 1
            edges.add(('a:' + base, nid, 'action_srv'))  # server publishes feedback
        else:
            topics[t] = ty[0]
            edges.add((nid, 't:' + t, 'topic'))
    for t, ty in subs:
        k, base = classify(t)
        if k == 'a':
            actions[base] = 1
            edges.add((nid, 'a:' + base, 'action_cli'))
        else:
            topics[t] = ty[0]
            edges.add(('t:' + t, nid, 'topic'))
    for s, ty in srvs:
        k, base = classify(s)
        if k == 'a':
            continue
        services[s] = ty[0]
        edges.add(('s:' + s, nid, 'srv'))
    for s, ty in clis:
        k, base = classify(s)
        if k == 'a':
            continue
        services[s] = ty[0]
        edges.add((nid, 's:' + s, 'srv'))

print(f'{len(nodes)} nodes, {len(topics)} topics, {len(services)} services, '
      f'{len(actions)} actions, {len(edges)} edges')


def is_noise(id_):
    kind, nm = id_.split(':', 1)
    if kind == 't' and nm in ('/rosout', '/parameter_events'):
        return True
    if kind == 's' and nm.rsplit('/', 1)[-1] in PARAM_SRV:
        return True
    if kind == 'n' and ('_ros2cli_daemon' in nm or nm.startswith('/rqt_gui')
                        or nm.startswith('/transform_listener_impl')):
        return True
    return False


def write(path, clean):
    q = lambda s: '"' + s + '"'
    L = ['digraph G {', 'rankdir=LR; ranksep=1.4; nodesep=0.12; concentrate=false;',
         'node [fontname="Helvetica", fontsize=11];', 'edge [arrowsize=0.6];']
    used = set()
    E = []
    for a, b, st in sorted(edges):
        if clean and (is_noise(a) or is_noise(b)):
            continue
        used.update((a, b))
        attr = {'topic': '', 'srv': ' [style=dashed, color="#2e7d32"]',
                'action_srv': ' [color="#c62828", penwidth=1.4]',
                'action_cli': ' [color="#c62828", penwidth=1.4]'}[st]
        E.append(f'{q(a)} -> {q(b)}{attr};')
    for _, _, fq in sorted(nodes, key=lambda x: x[2]):
        i = 'n:' + fq
        if clean and (is_noise(i) or i not in used):
            continue
        L.append(f'{q(i)} [label="{fq}", shape=ellipse, style=filled, fillcolor="#cfe2ff", fontsize=13];')
    for t, ty in sorted(topics.items()):
        if 't:' + t in used:
            L.append(f'{q("t:" + t)} [label="{t}\\n[{ty}]", shape=box, fontsize=9];')
    for s, ty in sorted(services.items()):
        if 's:' + s in used:
            L.append(f'{q("s:" + s)} [label="{s}\\n<{ty}>", shape=box, style="rounded,filled", '
                     f'fillcolor="#e8f5e9", color="#2e7d32", fontsize=9];')
    for a in sorted(actions):
        if 'a:' + a in used:
            L.append(f'{q("a:" + a)} [label="{a}\\n(action)", shape=hexagon, style=filled, '
                     f'fillcolor="#ffebee", color="#c62828", fontsize=10];')
    L += E
    L.append('labelloc=t; fontsize=20; label="ROS 2 graph  —  ellipse=node  box=topic  '
             'green dashed=service  red hexagon=action";')
    L.append('}')
    open(path, 'w').write('\n'.join(L))


write(prefix + '_full.dot', clean=False)
write(prefix + '_clean.dot', clean=True)
n.destroy_node()
rclpy.shutdown()


# ---------------- focus view: only the key application flow ----------------
GROUPS = {
    'HMI': ['/dual_arm_hmi_command', '/dual_arm_hmi_monitor'],
    '任務協調': ['/dual_arm_coordinator'],
    '安全 / 吸盤': ['/safety_supervisor', '/suction_controller_node'],
    '視覺': ['/env_cam/usb_cam', '/env_scene_node', '/env_scene_bridge',
             '/arm1_cam/usb_cam', '/arm1_cam/image_rotate', '/arm_camera_switch'],
    'MoveIt 規劃': ['/move_group', '/moveit_simple_controller_manager'],
    'ros2_control': ['/controller_manager', '/arm1_controller', '/arm2_controller',
                     '/joint_state_broadcaster', '/robot_state_publisher'],
}
COLORS = {'HMI': '#fff3cd', '任務協調': '#f8d7da', '安全 / 吸盤': '#ffe5d0', '視覺': '#d1e7dd',
          'MoveIt 規劃': '#e2d9f3', 'ros2_control': '#cfe2ff'}
KEEP_N = {x for v in GROUPS.values() for x in v}
DROP_T_SUB = ('/compressed', 'compressedDepth', '/theora', '/zstd', 'camera_info',
              'transition_event', '/ground_truth/', '/display_', 'pipeline_state',
              'introspection', 'statistics', '/activity', 'tf_static', 'dynamic_joint_states',
              '/rosout', '/parameter_events', 'robot_description', 'speed_scaling', 'diagnostics',
              'controller_state', 'monitored_planning_scene')
KEEP_S_PREFIX = ('/dual_arm/', '/safety/', '/vision/')


def focus_keep(id_):
    kind, nm = id_.split(':', 1)
    if kind == 'n':
        return nm in KEEP_N
    if kind == 't':
        return not any(s in nm for s in DROP_T_SUB)
    if kind == 's':
        return nm.startswith(KEEP_S_PREFIX)
    return True  # actions


fe = [(a, b, st) for a, b, st in edges if focus_keep(a) and focus_keep(b)]
# keep only topics that have both a publisher and a subscriber among kept nodes
from collections import defaultdict
deg = defaultdict(lambda: [0, 0])
for a, b, _ in fe:
    deg[a][1] += 1
    deg[b][0] += 1
fe = [(a, b, st) for a, b, st in fe
      if not ((a.startswith('t:') and deg[a][0] == 0) or (b.startswith('t:') and deg[b][1] == 0))]

q = lambda s: '"' + s + '"'
L = ['digraph G {', 'rankdir=LR; ranksep=1.0; nodesep=0.25; newrank=true; compound=true;',
     'fontname="Noto Sans CJK TC"; node [fontname="Noto Sans CJK TC", fontsize=12];',
     'edge [arrowsize=0.7, fontname="Noto Sans CJK TC"];']
for i, (g, members) in enumerate(GROUPS.items()):
    L.append(f'subgraph cluster_{i} {{ label="{g}"; fontsize=16; style="rounded,filled"; '
             f'fillcolor="{COLORS[g]}"; color="#888888";')
    for m in members:
        L.append(f'  {q("n:" + m)} [label="{m}", shape=ellipse, style=filled, fillcolor=white, '
                 f'penwidth=1.5, fontsize=13];')
    L.append('}')
used = {x for a, b, _ in fe for x in (a, b)}
for t, ty in sorted(topics.items()):
    if 't:' + t in used:
        L.append(f'{q("t:" + t)} [label="{t}\\n[{ty.split("/")[-1]}]", shape=box, fontsize=10];')
for s, ty in sorted(services.items()):
    if 's:' + s in used:
        L.append(f'{q("s:" + s)} [label="{s}", shape=box, style="rounded,filled,dashed", '
                 f'fillcolor="#e8f5e9", color="#2e7d32", fontsize=10];')
for a in sorted(actions):
    if 'a:' + a in used:
        L.append(f'{q("a:" + a)} [label="{a}\\n(action)", shape=hexagon, style=filled, '
                 f'fillcolor="#ffebee", color="#c62828", fontsize=10];')
for a, b, st in sorted(fe):
    attr = {'topic': '', 'srv': ' [style=dashed, color="#2e7d32"]'}.get(st, ' [color="#c62828", penwidth=1.6]')
    L.append(f'{q(a)} -> {q(b)}{attr};')
L.append('labelloc=t; fontsize=22; label="雙臂系統 ROS 2 重點節點圖  —  橢圓=節點  方框=topic  綠虛線=service  紅六角=action";')
L.append('}')
open(prefix + '_focus.dot', 'w').write('\n'.join(L))
print('focus edges', len(fe))
