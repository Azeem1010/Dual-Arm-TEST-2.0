"""Gravity torque along the arm2 paths (planar model from gravity.py; development PC, no hardware).

arm2 uses the same lift/elbow/wrist calibration zeros as arm1 (calibration_prototype.yaml), so the
planar model of gravity.py applies unchanged; the pan joint turns about the vertical and does not
change the gravity torque. Poses: HOME raw 512; B contact and C release from the taught counts in
config/prototype/coordinator.yaml; the "above" poses lift the wrist straight up by
approach_z - contact_z (B) and approach_z - release_z (C) with the tool kept pointing down.
Paths are joint-space straight lines (fixed_transits). Sign: + = gravity torque toward +q
(forward/down); torques below 0.005 N m (HOME) are ignored for the label. "assist" = gravity torque in the direction of motion of that joint (braking load),
"oppose" = against it (driving load).
"""
import os, sys
import numpy as np
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from gravity import C, points, torques, models

ZERO = np.array([631.35, 699.55, 512.0])           # lift, elbow, wrist zero_raw
def q_of_raw(r): return (np.asarray(r, float) - ZERO) / C
def cnt(q): return np.asarray(q) * C

def raise_wrist(q, dz):
    """Joint pose with the wrist point dz higher, tool still pointing down (Newton on lift/elbow)."""
    ql, qe, qw = q
    phi = ql + qe + qw                               # tool orientation, kept
    target = points(ql, qe, qw)[2] + np.array([0.0, dz])
    x = np.array([ql, qe])
    for _ in range(50):
        f = points(x[0], x[1], 0)[2] - target
        if np.linalg.norm(f) < 1e-9: break
        J = np.zeros((2, 2)); h = 1e-6
        for i in range(2):
            d = np.zeros(2); d[i] = h
            J[:, i] = (points(*(x + d), 0)[2] - points(*x, 0)[2]) / h
        x = x - np.linalg.solve(J, f)
    return np.array([x[0], x[1], phi - x[0] - x[1]])

HOME = q_of_raw([512, 512, 512])
B_CONTACT = q_of_raw([704, 764, 689])
B_ABOVE = raise_wrist(B_CONTACT, 0.052 - 0.0223)
C_RELEASE = [q_of_raw(r) for r in [
    [638, 919, 617], [652, 889, 618], [662, 867, 614], [678, 831, 618],
    [715, 740, 693], [733, 715, 696], [768, 633, 725], [803, 557, 760]]]
C_ABOVE = [raise_wrist(q, 0.052 - 0.0233) for q in C_RELEASE]

def path(name, qa, qb, steps=11):
    print(f'\n== {name}: counts from zero  lift {cnt(qa[0]):.0f}->{cnt(qb[0]):.0f}'
          f'  elbow {cnt(qa[1]):.0f}->{cnt(qb[1]):.0f}  wrist {cnt(qa[2]):.0f}->{cnt(qb[2]):.0f}')
    dq = qb - qa
    for mname, M in models.items():
        rows = []
        for s in np.linspace(0, 1, steps):
            q = qa + s * dq
            rows.append(torques(*q, M))
        rows = np.array(rows)
        flips = []
        for j, jn in enumerate(['lift', 'elbow']):
            live = np.abs(rows[:, j]) > 0.005          # HOME itself is the zero-torque point
            sgn = np.sign(rows[live, j] * dq[j])
            if abs(cnt(dq[j])) < 5: tag = 'still'
            elif np.all(sgn > 0): tag = 'assist'
            elif np.all(sgn < 0): tag = 'oppose'
            else: tag = 'FLIPS'
            flips.append(f'{jn} {tag} ({rows[0, j]:+.3f}..{rows[-1, j]:+.3f})')
        print(f'  {mname:8s}', '  '.join(flips))

if __name__ == '__main__':
    print('B above (raw):', np.round(cnt(B_ABOVE) + ZERO))
    path('HOME -> B above', HOME, B_ABOVE)
    path('B above -> B contact', B_ABOVE, B_CONTACT)
    for i, qa in enumerate(C_ABOVE, 1):
        print(f'\nC{i} above (raw):', np.round(cnt(qa) + ZERO))
        path(f'B above -> C{i} above', B_ABOVE, qa)
        path(f'C{i} above -> HOME', qa, HOME)
