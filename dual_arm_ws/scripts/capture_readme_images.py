#!/usr/bin/env python3
"""Save README screenshots from a running coordinator demo, keyed on its task states.

Run while `demo_pick_place.launch.py` is up, before starting the task. Frames are
real Gazebo sensor images; nothing is staged or moved for the pictures.

    capture_readme_images.py capture RAW_DIR      # waits for the task to finish
    capture_readme_images.py publish RAW_DIR IMAGES_DIR   # crops and labels
"""
import json
from pathlib import Path
import sys
import time

import cv2
import numpy as np

VIEWS = {'isometric': '/view_isometric/image_raw', 'top': '/view_top/image_raw', 'env': '/env_cam/image_raw',
         'arm1': '/arm1_cam/image_raw', 'arm2': '/arm2_cam/image_raw'}
# Status is published at 5 Hz, so a short state can be missed. Each group fires on the
# first of its consecutive states; images come from the first frame after that.
SHOTS = [
    (('ARM1:CHECK_ZONES', 'ARM1:QUERY_TARGET', 'ARM1:PREFLIGHT', 'ARM1:APPROACH_A'),
     {'home': 'isometric', 'layout_top': 'top', 'camera_env': 'env', 'camera_arm1': 'arm1', 'camera_arm2': 'arm2'}),
    (('ARM1:GRASP_A', 'ARM1:ATTACH', 'ARM1:LIFT_A'), {'step1_arm1_pick_A': 'isometric'}),
    (('ARM1:RELEASE_B', 'ARM1:DETACH', 'ARM1:LIFT_B'), {'step2_arm1_place_B': 'isometric'}),
    (('ARM2:GRASP_B', 'ARM2:ATTACH', 'ARM2:LIFT_B'), {'step3_handover': 'isometric'}),
    (('ARM2:DESCEND_C', 'ARM2:RELEASE_C'), {'step4_arm2_carry_C': 'isometric'}),
    (('SUCCEEDED',), {'step5_done': 'isometric'}),
]
TIMEOUT_S = 1200.0
# view_top: 960 px wide, 1.05 rad field of view, 0.85 m above the foam top (z = 0.01).
TOP_PX_PER_M = (480 / np.tan(0.525)) / 0.84
TOP_CENTER = (480, 360)
ISOMETRIC_CROP = (170, 185, 810, 625)  # x0, y0, x1, y1


def to_bgr(message):
    if message.encoding not in ('rgb8', 'bgr8'):
        raise ValueError(f'Unexpected encoding {message.encoding}')
    pixels = np.frombuffer(message.data, dtype=np.uint8).reshape(message.height, message.step)
    pixels = pixels[:, :message.width * 3].reshape(message.height, message.width, 3)
    return cv2.cvtColor(pixels, cv2.COLOR_RGB2BGR) if message.encoding == 'rgb8' else pixels


def capture(raw_dir):
    import rclpy
    from rclpy.node import Node
    from rclpy.qos import DurabilityPolicy, QoSProfile, qos_profile_sensor_data
    from sensor_msgs.msg import Image
    from std_msgs.msg import String

    raw_dir.mkdir(parents=True, exist_ok=True)
    rclpy.init()
    node = Node('capture_readme_images')
    frames, pending, seen, saved, log = {}, [], set(), set(), []
    wanted = {name for _states, shots in SHOTS for name in shots}
    for view, topic in VIEWS.items():
        node.create_subscription(Image, topic, lambda m, v=view: frames.__setitem__(v, (time.monotonic(), m)), qos_profile_sensor_data)

    def on_status(message):
        state = json.loads(message.data).get('state', '')
        for index, (states, shots) in enumerate(SHOTS):
            if state in states and index not in seen:
                seen.add(index)
                now = time.monotonic()
                pending.extend((name, view, now) for name, view in shots.items())
                log.append({'state': state, 'monotonic': now})
                print('state', state, flush=True)

    qos = QoSProfile(depth=1, durability=DurabilityPolicy.TRANSIENT_LOCAL)
    node.create_subscription(String, '/dual_arm/status', on_status, qos)
    deadline = time.monotonic() + TIMEOUT_S
    try:
        while saved != wanted and time.monotonic() < deadline:
            rclpy.spin_once(node, timeout_sec=0.05)
            for shot in list(pending):
                name, view, trigger = shot
                frame = frames.get(view)
                if frame is not None and frame[0] > trigger:
                    if not cv2.imwrite(str(raw_dir / f'{name}.png'), to_bgr(frame[1])):
                        raise RuntimeError(f'Could not write {name}')
                    pending.remove(shot)
                    saved.add(name)
                    print('saved', name, f'{frame[0] - trigger:.2f}s after state', flush=True)
    finally:
        (raw_dir / 'capture_log.json').write_text(json.dumps({'states': log, 'saved': sorted(saved), 'missing': sorted(wanted - saved)}, indent=2))
        node.destroy_node()
        rclpy.shutdown()
    return 0 if saved == wanted else 1


def outlined(image, text, center, scale=0.9):
    font = cv2.FONT_HERSHEY_DUPLEX
    (width, height), _ = cv2.getTextSize(text, font, scale, 2)
    origin = (center[0] - width // 2, center[1] + height // 2)
    cv2.putText(image, text, origin, font, scale, (40, 40, 40), 6, cv2.LINE_AA)
    cv2.putText(image, text, origin, font, scale, (255, 255, 255), 2, cv2.LINE_AA)


def publish(raw_dir, images_dir):
    missing = [name for _states, shots in SHOTS for name in shots if not (raw_dir / f'{name}.png').exists()]
    if missing:
        print('Not publishing; missing raw images:', missing)
        return 1
    for name in ('camera_env', 'camera_arm1', 'camera_arm2'):
        cv2.imwrite(str(images_dir / f'{name}.png'), cv2.imread(str(raw_dir / f'{name}.png')))
    x0, y0, x1, y1 = ISOMETRIC_CROP
    for name in ('home', 'step1_arm1_pick_A', 'step2_arm1_place_B', 'step3_handover', 'step4_arm2_carry_C', 'step5_done'):
        cv2.imwrite(str(images_dir / f'{name}.png'), cv2.imread(str(raw_dir / f'{name}.png'))[y0:y1, x0:x1])

    top = cv2.imread(str(raw_dir / 'layout_top.png'))
    cx, cy = TOP_CENTER
    half_w, half_h = int(0.325 * TOP_PX_PER_M), int(0.172 * TOP_PX_PER_M)
    boundary = int(0.1 * TOP_PX_PER_M)
    foam_top, foam_bottom = cy - int(0.12 * TOP_PX_PER_M), cy + int(0.12 * TOP_PX_PER_M)  # 240 mm board
    for x in (cx - boundary, cx + boundary):
        for y in range(foam_top, foam_bottom, 20):
            cv2.line(top, (x, y), (x, min(y + 11, foam_bottom)), (255, 255, 255), 3)
    label_y = foam_bottom - 26  # The arms are on the far side, at the top of this view.
    # The top camera shows world -X on the image left, where zone A is (A | B | C, measured 2026-11-10).
    for text, x in (('Zone A', cx - 2 * boundary), ('Zone B', cx), ('Zone C', cx + 2 * boundary)):
        outlined(top, text, (x, label_y))
    cv2.imwrite(str(images_dir / 'layout_top.png'), top[cy - half_h:cy + half_h, cx - half_w:cx + half_w])
    return 0


def main():
    if len(sys.argv) == 3 and sys.argv[1] == 'capture':
        return capture(Path(sys.argv[2]))
    if len(sys.argv) == 4 and sys.argv[1] == 'publish':
        return publish(Path(sys.argv[2]), Path(sys.argv[3]))
    print(__doc__)
    return 2


if __name__ == '__main__':
    sys.exit(main())
