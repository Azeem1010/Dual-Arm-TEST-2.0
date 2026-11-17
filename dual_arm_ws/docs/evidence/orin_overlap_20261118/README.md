# Orin: update, build and overlap runs without hardware — 2026-11-18

Run on the Jetson Orin after fast-forwarding `main` to `47b9b5c`. Nothing real moved: no arm,
camera or ESP32 command was used (the old micro-ROS agent stayed open on the default ROS domain;
every run below used its own domain).

| Step | Result | Evidence |
|---|---|---|
| `bash scripts/build.sh`: colcon build | PASS: 15 packages, then `dual_arm_moveit_config` again | build_check/colcon_build.log |
| `validate_model.py` | PASS: 14 links, eight revolute joints | build_check/model_validation.log |
| Coordinator unit tests | PASS: 501 passed (63 s) | unit_tests/coordinator_tests.txt |
| HMI unit tests | PASS: 320 passed (17 s) | unit_tests/hmi_tests.txt |
| Mock Serial, prototype launch, overlap + fixed transits | PASS | mock_fixed/ |
| Gazebo regression `two` with overlap on (temporary local patch) | PASS | gazebo_two/ |

The tracked files `build.sh` overwrote (`colcon_build.log`, `dual_arm.urdf`, `moveit_rebuild.log`,
`model_validation.log` in docs/evidence/) were restored with `git restore`; the new build log and
model check are kept here.

## Mock Serial with overlap on (mock_fixed/)

Same script as evidence/mock_overlap_20261118/run.sh `fixed`, with output written outside the
repo (`run_used.sh` shows the two changed lines) and `ROS_DOMAIN_ID=77`. The prototype config was
switched to overlap on / direct transfer off for the run and restored on exit (`config restored`).

- Config validates; hardware active and both controllers on; both arms moved away from HOME.
- `go_home`: `fixed joint path, 157 points` per arm, sent to `follow_joint_trajectory`; both arms HOME.
- 0 trajectories executed through move_group (the only `ExecuteTrajectory` lines are the
  capability load at start-up). 6 controller goals received, 6 reached.
- Task start → INITIAL_HOME → stop at the first zone observation (`No new image from env after the
  arm settled`), expected without a camera. TIMING SUMMARY written. The launch needed SIGTERM
  after SIGINT, as in the earlier run.
- Leftover processes: FAIL. `steps.log` says `no leftover processes`, but the script only checks
  `ros2_control_node|move_group|coordinator_node|cm530_mock`. A `robot_state_publisher` from this
  launch (started 02:34:58, `ROS_DOMAIN_ID=77`) was still running afterwards and was stopped by
  hand. The same check in evidence/mock_overlap_20261118/run.sh and mock_run_20261118/run.sh
  may have missed it too.

## Gazebo regression `two` with overlap on (gazebo_two/)

User decision 2026-11-18 (option 2): try overlap in Gazebo **without changing src/ or git**.
Overlap is only allowed in prototype mode (`task_config._check_overlap`), so the installed copies
were patched for this run only (`temp_install_patch.diff`): simulation mode allowed, and the
`overlap` block (`clearance_m` 0.025, `wait_s` 240) appended to the simulation config. The
simulation config has no `direct_transfer`. The patched config validated before the run.

Command: `STEPS=regress_two bash scripts/run_checks.sh t2 <OUT>` (Gazebo headless,
`ROS_DOMAIN_ID=47`, ground truth instead of cameras). After the run the src/ files were copied
back into install/ (a plain `colcon build --packages-select dual_arm_coordinator` did not replace
them because the patched files were newer), `cmp` against src/ matched, no `TEMP` marker remained,
and the prototype config validated again.

| Check (regress_two.json) | Result |
|---|---|
| start accepted | PASS |
| two objects, task SUCCEEDED | PASS |
| record: slots 1 and 2 occupied, completed 2, B free | PASS |
| ground truth: caps in slots 1 and 2 | PASS |
| planning scene: `cap_in_slot_1`, `cap_in_slot_2`, nothing attached | PASS |
| WARN / ERROR lines in coordinator_1.log | none |
| leftover processes | none |

Step 157 s; coordinator `TIMING SUMMARY 2 object(s), 150.76 s` (timing CSV included). The arms
did move at the same time (coordinator_1.log, ROS time):

- Cycle 2: arm 1 `APPROACH_A` 1794941049.6 → 1055.9 while arm 2 `APPROACH_B` 1049.7 → 1056.8; their
  descents, grasps and lifts also overlap.
- Arm 1 places object 2 into B (`APPROACH_B` … `LIFT_B`, 1071.0 → 1085.8) while arm 2 carries
  object 1 to C (`APPROACH_C` … `LIFT_C`, 1070.9 → 1090.2).
- Zone B hand-over order held: arm 1 `RESERVE_B` for object 2 only after arm 2 `VERIFY_B_EMPTY`.

`arm2:INITIAL_HOME 140.89 s` in the slowest-step list is arm 2's thread waiting, not motion.

## Not covered

- No lane wait happened (no log line of an arm waiting for the other's x range), so blocking and
  `wait_s` are untested outside unit tests.
- Only `two`; `faults` and `batch` with overlap NOT_RUN.
- Gazebo with ground truth and the simulation config: no cameras, no prototype taught poses, no
  fixed transits, simulated suction. It does not show that the real arms can move at once safely;
  `clearance_m` 0.025 is still an estimate. Overlap on the real arms NOT_RUN.
- Overlap stays off in the shipped prototype config, and simulation mode still refuses it.
