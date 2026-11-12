"""Generate the dimensioned simulation fixture (SI units)."""
from pathlib import Path
from xml.sax.saxutils import escape
import xml.etree.ElementTree as ET

from field_layout import CAPS_XY_M, SLOT_COLUMNS_X_M, SLOT_ROWS_Y_M, SLOTS_XY_M

ROOT = Path(__file__).resolve().parents[1]
parts = ['''<?xml version="1.0"?><sdf version="1.9"><world name="dual_arm_workspace">
<physics name="physics" type="ignored"><max_step_size>0.001</max_step_size><real_time_factor>1</real_time_factor></physics>
<gravity>0 0 -9.81</gravity>
<plugin filename="gz-sim-physics-system" name="gz::sim::systems::Physics"/>
<plugin filename="gz-sim-user-commands-system" name="gz::sim::systems::UserCommands"/>
<plugin filename="gz-sim-scene-broadcaster-system" name="gz::sim::systems::SceneBroadcaster"/>
<plugin filename="gz-sim-sensors-system" name="gz::sim::systems::Sensors"><render_engine>ogre2</render_engine></plugin>
<light name="sun" type="directional"><pose>0 0 5 0 0 0</pose><diffuse>0.9 0.9 0.9 1</diffuse><direction>0.1 0.2 -1</direction></light>
<scene><ambient>0.7 0.7 0.7 1</ambient><background>0.18 0.2 0.25 1</background></scene>
''']

def box(name, xyz, size, color, static=True):
    geom = f'<box><size>{size}</size></box>'
    parts.append(f'<model name="{name}"><static>{str(static).lower()}</static><pose>{xyz} 0 0 0</pose><link name="link"><collision name="collision"><geometry>{geom}</geometry></collision><visual name="visual"><geometry>{geom}</geometry><material><ambient>{color}</ambient><diffuse>{color}</diffuse></material></visual></link></model>')

box('table', '0 0 -0.025', '0.8 0.7 0.05', '0.3 0.3 0.3 1')
# Board A|B|C as the user sees it: x left-to-right, y away from the user; the arm
# bases are on the +Y edge (generate_cad_robot.py). Field geometry measured 2026-11-11
# (docs/evidence/hardware/20261111_H1/): board 600 x 240 mm centred on the world
# origin, j1 axes at (+-0.10, +0.125), about 5 mm outside the arm-side edge. Arm
# axes, C slots and cap starts come from field_layout.py.
BOARD_X_M, BOARD_Y_M = 0.6, 0.24
PAD_M = 0.025
# 10 mm base under the whole board, then a 4 mm foam layer whose top (z = 0.014) is
# the working surface. In C the foam has 25 mm openings filled flush by white pads.
box('board_base', '0 0 0.005', f'{BOARD_X_M} {BOARD_Y_M} 0.01', '1 0.15 0.55 1')
box('foam_AB', '-0.1 0 0.012', f'0.4 {BOARD_Y_M} 0.004', '1 0.15 0.55 1')
half = PAD_M / 2
xs = sorted({0.1, BOARD_X_M / 2, *(round(x + d, 5) for x in SLOT_COLUMNS_X_M for d in (-half, half))})
ys = sorted({-BOARD_Y_M / 2, BOARD_Y_M / 2, *(round(y + d, 5) for y in SLOT_ROWS_Y_M for d in (-half, half))})
for i in range(len(xs) - 1):
    for j in range(len(ys) - 1):
        cx, cy = (xs[i] + xs[i + 1]) / 2, (ys[j] + ys[j + 1]) / 2
        if any(abs(cx - x) < half and abs(cy - y) < half for x, y in SLOTS_XY_M):
            continue
        box(f'foam_C_{i}_{j}', f'{cx:.5f} {cy:.5f} 0.012', f'{xs[i + 1] - xs[i]:.5f} {ys[j + 1] - ys[j]:.5f} 0.004', '1 0.15 0.55 1')
for index, (x, y) in enumerate(SLOTS_XY_M):
    box(f'slot_{index + 1}_pad', f'{x} {y} 0.012', f'{PAD_M} {PAD_M} 0.004', '1 1 1 1')
for i, (cap_x, cap_y) in enumerate(CAPS_XY_M):
    parts.append(f'''<model name="cap_{i+1}"><pose>{cap_x} {cap_y} 0.019 0 0 0</pose><link name="body"><inertial><mass>0.002</mass><inertia><ixx>0.000000067</ixx><iyy>0.000000067</iyy><izz>0.0000001</izz></inertia></inertial><collision name="collision"><geometry><cylinder><radius>0.01</radius><length>0.01</length></cylinder></geometry></collision><visual name="visual"><geometry><cylinder><radius>0.01</radius><length>0.01</length></cylinder></geometry><material><ambient>0 0.1 1 1</ambient><diffuse>0 0.1 1 1</diffuse></material></visual></link></model>''')
bridge = []
# Arm cameras sit over the cap and slot groups (x about -+0.15): the cap-wall error grows
# away from the image centre and must stay inside the 1 mm suction budget (C31).
for name, x, height, fov in [('env', 0, 0.8, 0.9), ('arm1', -0.15, 0.5, 0.7), ('arm2', 0.15, 0.5, 0.7)]:
    # Gazebo camera +X forward; optical z forward, x right, y down.
    parts.append(f'''<model name="{name}_camera"><static>true</static><pose>{x} 0 {height} 0 1.57079632679 1.57079632679</pose><link name="link"><sensor name="camera" type="camera"><always_on>true</always_on><update_rate>15</update_rate><topic>/{name}_cam/image_raw</topic><gz_frame_id>{name}_camera_optical_frame</gz_frame_id><camera><horizontal_fov>{fov}</horizontal_fov><image><width>640</width><height>480</height><format>R8G8B8</format></image><clip><near>0.01</near><far>5</far></clip><camera_info_topic>/{name}_cam/camera_info</camera_info_topic></camera></sensor></link></model>''')
    for suffix, ros, gz in [('image_raw', 'sensor_msgs/msg/Image', 'gz.msgs.Image'), ('camera_info', 'sensor_msgs/msg/CameraInfo', 'gz.msgs.CameraInfo')]:
        bridge.append(f'- ros_topic_name: /{name}_cam/{suffix}\n  gz_topic_name: /{name}_cam/{suffix}\n  ros_type_name: {ros}\n  gz_type_name: {gz}\n  direction: GZ_TO_ROS\n')
bridge.append('- ros_topic_name: /clock\n  gz_topic_name: /clock\n  ros_type_name: rosgraph_msgs/msg/Clock\n  gz_type_name: gz.msgs.Clock\n  direction: GZ_TO_ROS\n')
bridge.append('- ros_topic_name: /gazebo/ground_truth\n  gz_topic_name: /world/dual_arm_workspace/pose/info\n  ros_type_name: tf2_msgs/msg/TFMessage\n  gz_type_name: gz.msgs.Pose_V\n  direction: GZ_TO_ROS\n')
for arm in (1,2):
    for suffix,direction in [('command','ROS_TO_GZ'),('state','GZ_TO_ROS')]:
        topic=f'/gripper/arm{arm}/{suffix}'
        bridge.append(f'- ros_topic_name: {topic}\n  gz_topic_name: {topic}\n  ros_type_name: std_msgs/msg/String\n  gz_type_name: gz.msgs.StringMsg\n  direction: {direction}\n')
for name, pose in [('isometric','0.6 -0.6 0.5 0 0.46 2.35619449'),('top','0 0 0.85 0 1.57079632679 1.57079632679'),('front','0 -0.65 0.3 0 0.326 1.57079632679'),('side','0.65 0 0.3 0 0.326 3.14159265359')]:
    parts.append(f'''<model name="view_{name}"><static>true</static><pose>{pose}</pose><link name="link"><sensor name="camera" type="camera"><always_on>true</always_on><update_rate>2</update_rate><topic>/view_{name}/image_raw</topic><camera><horizontal_fov>1.05</horizontal_fov><image><width>960</width><height>720</height><format>R8G8B8</format></image><clip><near>0.01</near><far>5</far></clip></camera></sensor></link></model>''')
    bridge.append(f'- ros_topic_name: /view_{name}/image_raw\n  gz_topic_name: /view_{name}/image_raw\n  ros_type_name: sensor_msgs/msg/Image\n  gz_type_name: gz.msgs.Image\n  direction: GZ_TO_ROS\n')
parts.append('</world></sdf>')
tree=ET.fromstring('\n'.join(parts))
for model in tree.find('world').findall('model'):
    if model.get('name','').startswith('cap_'):
        plugin=ET.SubElement(model,'plugin',filename='gz-sim-pose-publisher-system',name='gz::sim::systems::PosePublisher')
        for key,value in [('publish_model_pose','true'),('publish_link_pose','false'),('use_pose_vector_msg','true'),('update_frequency','30')]:
            ET.SubElement(plugin,key).text=value
        name=model.get('name')
        bridge.append(f'- ros_topic_name: /ground_truth/{name}\n  gz_topic_name: /model/{name}/pose\n  ros_type_name: tf2_msgs/msg/TFMessage\n  gz_type_name: gz.msgs.Pose_V\n  direction: GZ_TO_ROS\n')
ET.ElementTree(tree).write(ROOT / 'src/dual_arm_gazebo/worlds/dual_arm_workspace.sdf',encoding='unicode')
(ROOT / 'src/dual_arm_gazebo/config/bridge.yaml').write_text(''.join(bridge))
print("Generated the measured 600 x 240 mm board, eight flush white pads, eight caps and three fixed simulation cameras")
