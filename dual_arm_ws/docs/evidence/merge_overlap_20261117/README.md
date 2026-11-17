# Merge of the overlap branch, switched off — 2026-11-17

Step 5 of the prototype speed-up plan: Azeem1010/Dual-Arm-TEST-2.0 `prototype-overlap-20261117`
(`770f960`, two arms at once, see evidence/overlap_20261117/) merged into main after direct
transfer, timing, shorter waits and fixed transits. Overlap is **off**: it has not run on Mock
Serial or the real arms.

## How the two lines were joined

| Area | Resolution |
|---|---|
| Config | Both keys kept. `overlap` and `direct_transfer` cannot both be on (task_config refuses it): overlap waits HOME for zone B, direct transfer takes B before the pick and keeps it until arm 2 is HOME again. The prototype file keeps `direct_transfer: true`; the `overlap` block is commented out with how to switch. |
| Arm 1 workflow | The branch's `pick_a` / `place_b` split kept; `run()` passes `direct` to `pick_a` (take B in PREFLIGHT, no HOME after the lift) and `reserved` to `place_b` (skip RESERVE_B). Overlap calls them as before. |
| Arm 2 workflow | The branch's `on_b_released` callback is called from `_release_b_empty`, used by both the HOME path (VERIFY_B_EMPTY) and the direct path (VERIFY_C). |
| Motion | `_run_timed_path` (contact lines, taught joint lines, fixed transits) ends in the branch's `_send`, so with overlap every such trajectory also reserves its x lane and goes to FollowJointTrajectory; without overlap it is ExecuteTrajectory as before. `_run_action` keeps the timing decorator and moves MoveGroup `planning_time` to `plan` after the branch's result check. |
| Context | Both: the timing step mark and the branch's holding lock. |
| Docs | Both sides kept; the branch's sections are now earlier results. |

## Checks

| Check | Result | File |
|---|---|---|
| Coordinator unit tests (472 + 25 from the branch + 2 new: exclusion, shipped file has overlap off) | PASS 499 | coordinator_tests.txt |
| test_overlap.py repeated 5 times (thread timing) | PASS 17 each | overlap_repeat.txt |
| HMI unit tests | PASS 320 | hmi_tests.txt |
| Prototype config validation | PASS | prototype_config_check.txt |
| Overlap with fixed transits / timing / shorter waits together, through MoveIt and controllers | NOT_RUN | |
| Real arms | NOT_RUN | |

Before switching overlap on: one Mock Serial `/dual_arm/go_home` with the overlap block on (plan-only
plus FollowJointTrajectory has never run), then the real arms with `cycles:=2`, someone at the
CM-530 power switch.
