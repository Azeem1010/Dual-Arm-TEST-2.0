import sys, subprocess, numpy as np, yaml, warnings
warnings.filterwarnings('ignore')
sys.path.insert(0,'src/dual_arm_coordinator')
from dual_arm_coordinator.kinematics import CadKinematics
from dual_arm_coordinator.homes import load_homes, load_b_joints, load_slot_joints
from dual_arm_coordinator.motion_math import joint_line
urdf=subprocess.run(['xacro','install/dual_arm_description/share/dual_arm_description/urdf/dual_arm_cad.urdf.xacro'],capture_output=True,text=True).stdout
cfg=yaml.safe_load(open('src/dual_arm_coordinator/config/prototype/coordinator.yaml'))
cal='src/cm530_hardware/config/calibration_prototype.yaml'
H=load_homes(cfg,calibration_path=cal); B=load_b_joints(cfg,cal); S=load_slot_joints(cfg,cal)['release']
M={a:CadKinematics(urdf,a,9) for a in ('arm1','arm2')}
c=cfg['overlap']['clearance_m']
def sweep(a,path):
    lo,hi=np.inf,-np.inf
    for p,q in zip(path,path[1:]):
        for s in joint_line(p,q,0.02):
            xs=M[a].frame_points(s)[:,0]; lo=min(lo,xs.min()); hi=max(hi,xs.max())
    return lo-c,hi+c
z=cfg['heights']
arm1A=[]
for x in np.arange(-0.30,-0.099,0.02):
  for y in np.arange(-0.12,0.121,0.02):
    try:
      qa=M['arm1'].solve((x,y,z['approach_z_m']),H['arm1']); qc=M['arm1'].solve((x,y,z['contact_z_m']-0.006),qa)
      arm1A.append(((round(x,2),round(y,2)),sweep('arm1',[H['arm1'],qa,qc,qa,H['arm1']])))
    except Exception: pass
print('arm1 A segment poses reachable:',len(arm1A),' worst high x (padded):',max(r[1][1] for r in arm1A))
b1=sweep('arm1',[H['arm1'],B['arm1'],H['arm1']]); print('arm1 HOME<->B padded',np.round(b1,3))
b2=sweep('arm2',[H['arm2'],B['arm2'],H['arm2']]); print('arm2 HOME<->B padded',np.round(b2,3))
cs=[sweep('arm2',[H['arm2'],q,H['arm2']]) for q in S]; print('arm2 HOME<->C lows (padded)',[round(r[0],3) for r in cs])
print('conflict arm1 A vs arm2 B:', any(r[1][1]>b2[0] for r in arm1A))
print('conflict arm1 B vs arm2 C:', [i+1 for i,r in enumerate(cs) if b1[1]>r[0]])
