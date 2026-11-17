# Prototype fixed transits — 2026-11-17

Step 4 of the prototype speed-up plan: non-contact moves (HOME, above A, above B, above C) no longer
plan with MoveIt each time.

## Change (`fixed_transits: true`, prototype only)

- `MotionGateway._plan_and_move` first tries the joint line from the current joints to the target
  (0.01 rad steps), run at transport speed (`max_velocity_rad_s` × `transport_scale` = 0.3 rad/s,
  same acceleration as before) through ExecuteTrajectory, starting from the joints read just before.
- It is refused, and the move plans with MoveIt as before, when
  - any waypoint fails the planning-scene validity check (other arm, attached cap, scene objects), or
  - the tool goes more than 5 mm below the lower end of the line anywhere: the board has no
    collision geometry in the planning scene, so validity checks cannot see it.
- A cancel or safety stop during the checks is raised, never turned into a fallback (TaskCancelled
  derives from TaskFault; a test covers this).
- Each move logs `fixed joint path, N points` or `fixed joint path refused (...); planning with MoveIt`.
- `_execute_path` and `_move_joint_line` now share the same timed-path helper (`_run_timed_path`).

## Model check of the prototype moves (`transits_check.py`, `transits_check.txt`)

Every transit the direct-transfer flow makes, from the prototype calibration HOME, taught B and
taught C poses, and above-A points on the model: all 22 pass the dip check (lowest tool height
50 mm, the slot 8 approach height itself); joint paths 0.76–2.11 rad, 3.5–8.0 s each at 0.3 rad/s.
Three of the chosen above-A test points are out of reach on the model, which is a choice of the
check's points, not of the flow. Validity checks (collisions) need move_group and were not run here.

## Checks

| Check | Result | File |
|---|---|---|
| Coordinator unit tests (10 new) | PASS 472 | coordinator_tests.txt |
| HMI unit tests | PASS 320 | hmi_tests.txt |
| Prototype config validation | PASS | prototype_config_check.txt |
| Dip check of every prototype transit on the model | PASS 22/22 | transits_check.txt |
| Validity of the fixed paths in move_group, real arms | NOT_RUN | |

To watch on the real arms: the joint line is not the path MoveIt would have chosen; look for
`fixed joint path refused` in the log and how close the arms pass each other.
