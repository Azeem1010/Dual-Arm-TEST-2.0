import numpy as np, sys
# Planar model of one arm in the lift plane (URDF dual_arm_cad joint offsets, y forward, z up).
# q in rad; at q=0: link2 = (0.0536, 0.0766) [lift->elbow], link3 = (0.0935, 0) [elbow->wrist],
# link4 tcp = (0.071, 0) [wrist->tcp]. All three pitch joints use axis -x: absolute angle = base - sum(q).
L2=np.array([0.0536,0.0766]); L3=np.array([0.0935,0.0]); L4=np.array([0.071,0.0])
C=1023/np.radians(300)
def rot(v,a): c,s=np.cos(a),np.sin(a); return np.array([c*v[0]-s*v[1], s*v[0]+c*v[1]])
def points(ql,qe,qw):
    e=rot(L2,-ql); w=e+rot(L3,-(ql+qe)); t=w+rot(L4,-(ql+qe+qw))
    return np.zeros(2),e,w,t
def masses(ql,qe,qw,M):
    o,e,w,t=points(ql,qe,qw)
    return [(M['br2'],(o+e)/2),(M['servo'],e),(M['br3'],(e+w)/2),(M['servo'],w),(M['eff'],w+0.55*(t-w))]
def torques(ql,qe,qw,M,g=9.81):
    o,e,w,t=points(ql,qe,qw); ms=masses(ql,qe,qw,M)
    # gravity torque toward +q (= tilting forward/down) is m*g*(y_com - y_axis) for every mass beyond the axis
    tl=sum(m*g*(p[0]-o[0]) for m,p in ms)
    te=sum(m*g*(p[0]-e[0]) for m,p in ms[2:])
    tw=sum(m*g*(p[0]-w[0]) for m,p in ms[4:])
    return tl,te,tw
models={
 'light': dict(br2=0.015,br3=0.015,servo=0.0546,eff=0.020),
 'nominal': dict(br2=0.020,br3=0.020,servo=0.0546,eff=0.035),
 'heavy': dict(br2=0.030,br3=0.030,servo=0.0546,eff=0.060),
}
if __name__=='__main__':
    # HOME raw 512 everywhere -> counts from calibration zero_raw: lift -119.35, elbow -187.55, wrist 0
    home=np.array([-119.35,-187.55,0.0])/C
    o,e,w,t=points(*home); print('HOME points (y,z):',np.round(e,4),np.round(w,4),np.round(t,4))
    # arm1 HOME -> A above (series): lift -119.4 -> 111.9, elbow -187.5 -> -95.5, wrist 0 -> ~290 (tool down)
    qend_l,qend_e=111.9/C,-95.5/C; qend_w=np.pi/2-(qend_l+qend_e)
    print('A-above wrist for tool-down: %.0f counts'%(qend_w*C))
    o,e,w,t=points(qend_l,qend_e,qend_w); print('A-above points (y,z):',np.round(e,4),np.round(w,4),np.round(t,4))
    print('\n s   lift  elbow wrist(cnt) | tau_lift tau_elbow tau_wrist [N*m, + = toward motion (outward)]')
    for name,M in models.items():
        print('--',name,M)
        for s in np.linspace(0,1,11):
            ql=home[0]+s*(qend_l-home[0]); qe=home[1]+s*(qend_e-home[1]); qw=home[2]+s*(qend_w-home[2])
            tl,te,tw=torques(ql,qe,qw,M)
            print(f'{s:4.1f} {ql*C:6.0f} {qe*C:6.0f} {qw*C:6.0f} | {tl:+.3f} {te:+.3f} {tw:+.3f}')
