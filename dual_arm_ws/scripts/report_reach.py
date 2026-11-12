"""Suction IK reach of every A-zone cap start and C slot; reads files only.

Usage: report_reach.py [REPORT.json]   (default docs/evidence/reach.json)

Cap starts come from the generated world, slots and heights from the simulation
coordinator config, so the report follows the current layout. The suction axis is
straight down where possible, otherwise tilted up to motion.max_tool_tilt_deg. Geometric
feasibility in the model only: no collision, path or hardware limit is checked.
"""
import json
from pathlib import Path
import re
import sys

import yaml

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'src/dual_arm_coordinator'))
from dual_arm_coordinator.kinematics import CadKinematics  # noqa: E402
from dual_arm_coordinator.motion_math import tool_tilt_deg  # noqa: E402

URDF = (ROOT / 'src/dual_arm_description/urdf/dual_arm_cad.urdf.xacro').read_text(encoding='utf-8')
WORLD = (ROOT / 'src/dual_arm_gazebo/worlds/dual_arm_workspace.sdf').read_text(encoding='utf-8')
CONFIG = yaml.safe_load((ROOT / 'src/dual_arm_coordinator/config/sim/coordinator.yaml').read_text(encoding='utf-8'))


def tilt(model, xy, z):
    """Suction tilt in degrees at the solution, or None when unreachable."""
    try:
        return round(tool_tilt_deg(model, model.solve([xy[0], xy[1], z])), 2)
    except ValueError:
        return None


def main():
    heights = CONFIG['heights']
    levels = {'approach': heights['approach_z_m'], 'contact': heights['contact_z_m']}
    caps = {name: (float(x), float(y)) for name, x, y in
            re.findall(r'<model name="(cap_\d)"><pose>(\S+) (\S+) ', WORLD)}
    targets = [('arm1', name, xy) for name, xy in sorted(caps.items())]
    targets += [('arm2', f'slot_{i + 1}', tuple(xy)) for i, xy in enumerate(CONFIG['zones']['c_slots_xy_m'])]
    limit = CONFIG['motion']['max_tool_tilt_deg']
    models = {arm: CadKinematics(URDF, arm, limit) for arm in ('arm1', 'arm2')}
    rows = []
    for arm, name, xy in targets:
        tilts = {level: tilt(models[arm], xy, z) for level, z in levels.items()}
        result = {level: value is not None for level, value in tilts.items()}
        rows.append({'arm': arm, 'target': name, 'xy_m': list(xy), **result, 'tilt_deg': tilts,
                     'reachable': all(result.values())})
    caps_ok = [r['target'] for r in rows if r['arm'] == 'arm1' and r['reachable']]
    slots_ok = [r['target'] for r in rows if r['arm'] == 'arm2' and r['reachable']]
    report = {'scope': 'Suction IK in the simulation model at approach and contact heights; '
                       'not collision, path or hardware validation.',
              'max_tool_tilt_deg': limit, 'heights_m': levels, 'caps_reachable': caps_ok, 'slots_reachable': slots_ok, 'targets': rows}
    out = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / 'docs/evidence/reach.json'
    out.write_text(json.dumps(report, indent=2) + '\n', encoding='utf-8')
    for r in rows:
        print(f"{r['arm']} {r['target']:7} ({r['xy_m'][0]:+.4f}, {r['xy_m'][1]:+.4f})  "
              f"approach={'ok' if r['approach'] else 'NO_IK'}  contact={'ok' if r['contact'] else 'NO_IK'}  "
              f"tilt_deg={r['tilt_deg']}")
    print(f'caps reachable {len(caps_ok)}/{len(caps)}: {caps_ok}')
    print(f"slots reachable {len(slots_ok)}/{len(CONFIG['zones']['c_slots_xy_m'])}: {slots_ok}")
    return 0


if __name__ == '__main__':
    sys.exit(main())
