"""Fixed transits of the prototype flow on the model: dip check, joint path length, time at 0.3 rad/s."""
import itertools, sys
from pathlib import Path
import yaml
W = Path('/mnt/e/dual_arm_system/dual_arm_ws/src')
sys.path.insert(0, str(W / 'dual_arm_coordinator'))
from dual_arm_coordinator.gateways import motion
from dual_arm_coordinator.gateways.motion import MotionGateway
from dual_arm_coordinator.homes import load_b_joints, load_homes, load_slot_joints
from dual_arm_coordinator.kinematics import CadKinematics
from dual_arm_coordinator.motion_math import (joint_line, prepare_b_poses, prepare_slot_poses, solve_line_holding_tool,
                                              line_points, tcp_position, trapezoid_times)
config = yaml.safe_load((W / 'dual_arm_coordinator/config/prototype/coordinator.yaml').read_text())
calib = W / 'cm530_hardware/config/calibration_prototype.yaml'
urdf = (W / 'dual_arm_description/urdf/dual_arm_cad.urdf.xacro').read_text()
models = {arm: CadKinematics(urdf, arm, config['motion']['max_tool_tilt_deg']) for arm in ('arm1', 'arm2')}
homes = load_homes(config, calibration_path=calib)
approach = config['heights']['approach_z_m']
slots = prepare_slot_poses(models['arm2'], load_slot_joints(config, calib)['release'], config['c_slot_teach'], approach)
b = prepare_b_poses(models, load_b_joints(config, calib), config['b_teach'].get('contact_lift_m', 0.0), approach)
g = MotionGateway.__new__(MotionGateway)
g._models = models
def solve(arm, xyz):
    for seed in itertools.product((-1.0, 0.0, 1.0), (-0.6, 0.0, 0.6), (-1.0, 0.0, 1.0), (-1.0, 0.0, 1.0)):
        try:
            return list(models[arm].solve(xyz, list(seed)))
        except ValueError:
            pass
    return None
def b_lifted():
    q = b['arm1']['release']
    p = tcp_position(models['arm1'], q)
    z = approach + config['b_release_lift_extra_m']
    return solve_line_holding_tool(models['arm1'], q, line_points(p, (p[0], p[1], z), 0.002), 0.15)[-1]
rows = []
for xy in [(-0.20, 0.0), (-0.25, 0.08), (-0.15, -0.08), (-0.28, -0.10), (-0.12, 0.10)]:
    a = solve('arm1', (xy[0], xy[1], approach))
    if a is None:
        rows.append((f'arm1 A{xy} unreachable', None, None)); continue
    rows.append((f'arm1 HOME -> above A{xy}', homes['arm1'], a))
    rows.append((f'arm1 above A{xy} -> above B', a, b['arm1']['above']))
rows.append(('arm1 B lifted -> HOME', b_lifted(), homes['arm1']))
rows.append(('arm2 HOME -> above B', homes['arm2'], b['arm2']['above']))
for i, s in enumerate(slots, 1):
    rows.append((f'arm2 above B -> above C{i}', b['arm2']['above'], s['above']))
    rows.append((f'arm2 above C{i} -> HOME', s['above'], homes['arm2']))
print('move | joint path rad | time s | dip check')
for name, start, end in rows:
    if start is None:
        print(name); continue
    arm = name.split()[0]
    path = joint_line(list(start), list(end), motion._JOINT_LINE_STEP_RAD)
    length = sum(max(abs(x - y) for x, y in zip(p, q)) for p, q in zip(path, path[1:]))
    t = trapezoid_times(path, 0.3, 0.3)
    zs = [float(tcp_position(models[arm], q)[2]) for q in path]
    problem = g._fixed_problem(arm, path)
    print(f'{name} | {length:.2f} | {t[-1] if t else 0:.1f} | {"OK" if problem is None else "REFUSED " + problem} (ends {zs[0]*1000:.0f}/{zs[-1]*1000:.0f}, min {min(zs)*1000:.0f} mm)')
