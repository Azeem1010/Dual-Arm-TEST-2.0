# Mock Serial run with overlap on — 2026-11-18

First run of the overlap motion path outside unit tests (it had never run on Mock Serial or the
arms). `run.sh <mode>` rewrites `config/prototype/coordinator.yaml` for the run (the launch reads it
at a fixed path): `direct_transfer: false` and the `overlap` block on; mode `plan` also removes
`fixed_transits`. The original file is restored on exit (`config restored` in each `steps.log`;
`git status` showed no change to it afterwards). Same steps as evidence/mock_run_20261118: torque
on, both arms moved away from HOME through their controllers, `/dual_arm/go_home`, `/dual_arm/start`.
No camera, so the overlapped task stops at its first zone observation. Nothing real moves.

| Check | fixed (overlap + fixed transits) | plan (overlap, MoveIt plan-only) |
|---|---|---|
| Config with overlap on, direct transfer off, validates | PASS | PASS |
| `go_home`: both arms HOME | PASS: `fixed joint path, 157 points` per arm, lane-reserved, sent to `follow_joint_trajectory` | PASS: 4 plan-only MoveGroup requests, planned trajectories sent to `follow_joint_trajectory` |
| Trajectories bypass MoveIt execution | PASS: 0 execution requests to move_group | PASS: 0 execution requests to move_group |
| Controller goals | 6 received, 6 reached | 6 received, 6 reached |
| Overlapped task start → INITIAL_HOME → stop at first camera query | PASS (expected without a camera) | PASS (expected without a camera) |
| TIMING SUMMARY written | PASS | PASS |
| No leftover processes | PASS | PASS |

For comparison, the sequential run (evidence/mock_run_20261118) sends the same moves through
move_group's ExecuteTrajectory (4 execution requests).

Not covered: both arms moving at once and waiting for each other's lane (that needs the camera so
the flow gets past the first observation), suction, contact lines, real arms. The HOME moves here
run one arm after the other.
