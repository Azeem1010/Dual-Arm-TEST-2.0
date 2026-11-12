from pathlib import Path
import subprocess
import json
import yaml
from dual_arm_coordinator.kinematics import CadKinematics
from dual_arm_coordinator.motion_math import tool_tilt_deg

from field_layout import CAPS_XY_M

root=Path(__file__).resolve().parents[1]
urdf=(root/'src/dual_arm_description/urdf/dual_arm_cad.urdf.xacro').read_text()
# Targets follow the current layout: C slots and B from the simulation config; the arm1
# targets are the A-zone cap starts of the simulated world (field_layout.py).
config=yaml.safe_load((root/'src/dual_arm_coordinator/config/sim/coordinator.yaml').read_text(encoding='utf-8'))
zones=config['zones']
# Straight down where possible, otherwise tilted up to the configured limit.
limit=config['motion']['max_tool_tilt_deg']
results=[]
for arm in ('arm1','arm2'):
    model=CadKinematics(urdf,arm,limit)
    xys=CAPS_XY_M if arm=='arm1' else zones['c_slots_xy_m']
    targets=[[x,y,.024] for x,y in xys]
    targets.append([*zones['b_place_xy_m'],.024])
    for target in targets:
        try:
            q=model.solve(target)
            results.append(dict(arm=arm,target=target,status='PASS',joints=q,tilt_deg=round(tool_tilt_deg(model,q),2)))
        except ValueError as exc:
            results.append(dict(arm=arm,target=target,status='FAIL',reason=str(exc)))
(root/'docs/evidence/ik_validation.json').write_text(json.dumps(results,indent=2)+'\n')
print(json.dumps(results,indent=2))
raise SystemExit(0 if all(r['status']=='PASS' for r in results) else 1)
