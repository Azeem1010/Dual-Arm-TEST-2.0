import json, math, sys
import numpy as np
d=json.load(open(sys.argv[1]))['axis_geometry']
K=0.005118267601156392
zero=[None,631.35,699.55,512]
def rot(axis,q):
    a=np.array(axis)/np.linalg.norm(axis);x,y,z=a;c,s=math.cos(q),math.sin(q);C=1-c
    return np.array([[c+x*x*C,x*y*C-z*s,x*z*C+y*s],[y*x*C+z*s,c+y*y*C,y*z*C-x*s],[z*x*C-y*s,z*y*C+x*s,c+z*z*C]])
def fk(arm,raw):
    g=d[arm];P=[np.array(p) for p in g['pivots_m']];A=g['axes'];tcp=np.array(g['tcp_m'])
    q=[0]+[(raw[i]-zero[i])*K for i in (1,2,3)]
    pts=list(P[1:])+[tcp]; # chain j2..j4 then tcp
    # apply from distal: rotate points beyond joint i about joint i
    pts=[p.copy() for p in pts]
    for i in (3,2,1):
        R=rot(A[i],q[i]);piv=P[i]
        for k in range(i,len(pts)): pts[k]=piv+R@(pts[k]-piv)
    t=pts[-1]; base=P[0]
    r=math.hypot(*(t[:2]-base[:2])); return r, t[2]
teach={'C1':[630,926,602],'C2':[636,906,600],'C3':[645,885,596],'C4':[666,838,629],'C5':[701,767,664],'C6':[721,724,694],'C7':[779,602,758],'C8':[803,557,760],'B2':[703,756,700],'homeC':[567,712,825],'straight':[512,512,512]}
meas={'C1':(75,35),'C2':(75,70),'C3':(110,35),'C4':(110,70),'C5':(145,35),'C6':(145,70),'C7':(180,35),'C8':(180,70)}
for k,v in teach.items():
    r,z=fk('arm2',[0]+v)
    m=meas.get(k); mr=math.hypot(m[0]+5,m[1]-5) if m else float('nan')  # axis at (F -5, L 205)
    print(f"{k:8s} r_fk={r*1000:6.1f} mm  z_fk={z*1000:6.1f} mm   r_meas={mr:6.1f} mm")
