from pathlib import Path
import subprocess
import json
import yaml
from dual_arm_coordinator.kinematics import CadKinematics

root=Path(__file__).resolve().parents[1]
urdf=(root/'src/dual_arm_description/urdf/dual_arm_cad.urdf.xacro').read_text()
# Targets follow the current layout: C slots and B from the simulation config; the arm1
# targets are the A-zone cap starts, which generate_world.py mirrors from the C slots.
zones=yaml.safe_load((root/'src/dual_arm_coordinator/config/sim/coordinator.yaml').read_text(encoding='utf-8'))['zones']
results=[]
for arm in ('arm1','arm2'):
    model=CadKinematics(urdf,arm)
    sign=-1 if arm=='arm1' else 1
    targets=[[sign*x,y,.024] for x,y in zones['c_slots_xy_m']]
    targets.append([*zones['b_place_xy_m'],.024])
    for target in targets:
        try:
            q=model.solve(target)
            results.append(dict(arm=arm,target=target,status='PASS',joints=q))
        except ValueError as exc:
            results.append(dict(arm=arm,target=target,status='FAIL',reason=str(exc)))
(root/'docs/evidence/ik_validation.json').write_text(json.dumps(results,indent=2)+'\n')
print(json.dumps(results,indent=2))
raise SystemExit(0 if all(r['status']=='PASS' for r in results) else 1)
