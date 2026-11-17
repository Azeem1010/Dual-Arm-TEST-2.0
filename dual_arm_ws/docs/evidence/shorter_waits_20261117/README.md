# Shorter waits around contact moves — 2026-11-17

Step 3 of the prototype speed-up plan (step 2, two-stage contact moves, was skipped by the user:
on the model a 52 mm → contact descent is 0.21–0.25 rad of joint path, and at the contact
acceleration 0.3 rad/s² two stages saved 0.1–0.3 s per move, about 1.5 s per object; arm1 A
2.82 → 2.54 s, B 2.42 → 2.36 s). A contact zone took 16–20 s in the 11-17 video while the arm moved
for about 5 s, so the waits around the moves are where the time is. Contact speed and acceleration
are unchanged.

## Changes

| Change | Where | Switch | Estimate |
|---|---|---|---|
| Grasp waits `grasp_settle_s` (1.2 s) instead of `vacuum_settle_s` (2.0 s); release keeps 2.0 s | `Esp32Suction`, task_config, prototype config | `grasp_settle_s`, prototype only, 1.0 s .. vacuum_settle_s | 0.8 s × 2 grasps per object |
| `_wait_still` first applies its own test (two `settle_s` windows, means within 1 count) to readings already received; if the arm stood still through them it does not wait two more windows | `MotionGateway._still_already`, joint-state history | none, all modes; same test as before, too few (< 3 per window) or old readings wait as before | up to 1 s per move that follows a wait (suction, camera, checks) |
| A contact line's waypoint validity checks are all sent before the first answer is awaited (every waypoint still checked, first invalid in path order faults) | `MotionGateway._require_valid_all`, used by `_execute_path` and `_move_joint_line` | none, all modes | part of the ~1 s per contact line (not measured) |

Estimates are not measured; the timing record (evidence/timing_20261117) will show them on the next
field run (kinds `vacuum`, `still`, `check`).

## Checks

| Check | Result | File |
|---|---|---|
| Coordinator unit tests (14 new: grasp wait, kept-readings stillness incl. a hunting joint, batched checks, config) | PASS 462 | coordinator_tests.txt |
| HMI unit tests | PASS 320 | hmi_tests.txt |
| Prototype config validation | PASS | prototype_config_check.txt |
| move_group answering batched validity requests | NOT_RUN | |
| Real arms | NOT_RUN | |

Risk to watch: a grasp that needs more than 1.2 s drops the cap on the lift (raise `grasp_settle_s`
or remove it).
