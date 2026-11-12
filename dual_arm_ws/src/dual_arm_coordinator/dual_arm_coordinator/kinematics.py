"""Four-axis CAD IK with explicit suction direction constraint (simulation model).

Uses the exact revolute origins/axes in the expanded URDF. Numerical position-only
IK is not sufficient for suction; the TCP +Z axis must point downward. A four-axis
arm cannot hold the cup straight down everywhere, so with max_tilt_deg > 0 a target
that has no straight-down solution may be reached with the cup tilted up to that
limit. The real arm reached slot 8 with the cup tilted about 9 degrees (2026-11-11).
"""
import math
import xml.etree.ElementTree as ET
import numpy as np
from scipy.optimize import least_squares, minimize
from scipy.spatial.transform import Rotation

_SEEDS = ([0., 0., 0., 0.], [0, -.5, .8, 1.2], [0, .5, .5, .5], [0, -1., 1.4, 1.2])
# Extra starts for the tilted search: elbow-down poses reaching far along the field.
_TILT_SEEDS = ([0, .96, -.96, 1.48], [0, .8, -.96, 1.6], [0, 1.2, -1.2, 1.4])


class CadKinematics:
    def __init__(self, urdf, arm, max_tilt_deg=0.0):
        if not 0.0 <= max_tilt_deg < 90.0:
            raise ValueError('max_tilt_deg must be within [0, 90)')
        self.max_tilt_deg = float(max_tilt_deg)
        robot=ET.fromstring(urdf)
        joints={j.find('child').get('link'):j for j in robot.findall('joint')}
        self.chain=[]
        child=f'{arm}_tcp'
        while child!='world':
            joint=joints[child]
            self.chain.insert(0,joint)
            child=joint.find('parent').get('link')
        active=[j for j in self.chain if j.get('type')=='revolute']
        self.names=[j.get('name') for j in active]
        self.lower=np.array([float(j.find('limit').get('lower')) for j in active])
        self.upper=np.array([float(j.find('limit').get('upper')) for j in active])
        if len(active)!=4:
            raise ValueError('Expected exactly four active joints')

    def forward(self,q):
        t=np.eye(4)
        index=0
        for joint in self.chain:
            origin=joint.find('origin')
            local=np.eye(4)
            if origin is not None:
                local[:3,3]=[float(x) for x in origin.get('xyz','0 0 0').split()]
                local[:3,:3]=Rotation.from_euler('xyz',[float(x) for x in origin.get('rpy','0 0 0').split()]).as_matrix()
            t=t@local
            if joint.get('type')=='revolute':
                axis=np.array([float(x) for x in joint.find('axis').get('xyz').split()])
                rotation=np.eye(4)
                rotation[:3,:3]=Rotation.from_rotvec(axis*q[index]).as_matrix()
                t=t@rotation
                index+=1
        return t

    def solve(self,target,seed=None):
        target=np.asarray(target,dtype=float)
        if target.shape!=(3,) or not np.isfinite(target).all():
            raise ValueError('Finite world XYZ target required')
        def residual(q):
            t=self.forward(q)
            return np.r_[t[:3,3]-target,.1*(t[:3,2]-[0,0,-1])]
        seeds=[np.array(s,dtype=float) for s in _SEEDS]
        if seed is not None:
            seeds.insert(0,np.asarray(seed,dtype=float))
        for start in seeds:
            result=least_squares(residual,np.clip(start,self.lower,self.upper),bounds=(self.lower,self.upper),max_nfev=300,gtol=1e-10,ftol=1e-10,xtol=1e-10)
            pose=self.forward(result.x)
            if np.linalg.norm(pose[:3,3]-target)<1e-5 and np.dot(pose[:3,2],[0,0,-1])>.99999:
                return result.x.tolist()
        if self.max_tilt_deg>0:
            q=self._solve_tilted(target,seed,seeds)
            if q is not None:
                return q
            raise ValueError(f'No four-DOF solution satisfies XYZ with the suction axis within {self.max_tilt_deg:g} deg of downward within model limits')
        raise ValueError('No four-DOF solution satisfies XYZ and downward suction axis within model limits')

    def _solve_tilted(self,target,seed,seeds):
        """Tilted solution within max_tilt_deg; None if there is none.

        With a seed (the current joints, or the previous point of a line), the
        solution nearest the seed: it keeps a descent on one branch, and from HOME
        or B it picks the low-shoulder branch the real arm used for slot 8. The
        smallest-tilt solution leans the shoulder into the base in the CAD model
        (MoveIt self-collision, 2026-11-12). Without a seed, the smallest tilt.
        """
        min_dot=math.cos(math.radians(self.max_tilt_deg))
        reach={'type':'eq','fun':lambda q:self.forward(q)[:3,3]-target}
        cone={'type':'ineq','fun':lambda q:-self.forward(q)[2,2]-min_dot}
        bounds=list(zip(self.lower,self.upper))
        if seed is not None:
            anchor=np.clip(np.asarray(seed,dtype=float),self.lower,self.upper)
            objective,constraints,starts=lambda q:float(np.sum((q-anchor)**2)),[reach,cone],[anchor]
        else:
            objective,constraints=lambda q:1.+self.forward(q)[2,2],[reach]
            j1=self._facing(target)
            starts=list(seeds)+[np.r_[j1,base[1:]] for base in _TILT_SEEDS]
        best=None
        for start in starts:
            result=minimize(objective,np.clip(start,self.lower,self.upper),method='SLSQP',
                            bounds=bounds,constraints=constraints,options={'maxiter':300,'ftol':1e-12})
            pose=self.forward(result.x)
            if np.linalg.norm(pose[:3,3]-target)<1e-5 and -pose[2,2]>=min_dot-1e-9:
                cost=objective(result.x)
                if best is None or cost<best[0]-1e-12:
                    best=(cost,result.x)
        if best is None and seed is not None:
            return self._solve_tilted(target,None,seeds)
        return None if best is None else best[1].tolist()

    def _facing(self,target):
        """j1 angle that turns the arm's plane toward target's XY (coarse, used as a start)."""
        angles=np.linspace(self.lower[0],self.upper[0],121)
        def miss(j1):
            q=np.r_[j1,0.,0.,0.]
            base=self._j1_origin(q)
            tip=self.forward(q)[:2,3]
            a,b=tip-base,target[:2]-base
            return -np.dot(a,b)/(np.linalg.norm(a)*np.linalg.norm(b)+1e-12)
        return float(min(angles,key=miss))

    def _j1_origin(self,q):
        t=np.eye(4)
        for joint in self.chain:
            origin=joint.find('origin')
            if origin is not None:
                local=np.eye(4)
                local[:3,3]=[float(x) for x in origin.get('xyz','0 0 0').split()]
                local[:3,:3]=Rotation.from_euler('xyz',[float(x) for x in origin.get('rpy','0 0 0').split()]).as_matrix()
                t=t@local
            if joint.get('type')=='revolute':
                return t[:2,3]
        return t[:2,3]
