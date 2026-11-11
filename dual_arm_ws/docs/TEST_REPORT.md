# Evidence report — 2026-11-08

## 2026-11-12 Phase C: measured field geometry and slot numbering

Board 600 × 240 mm, j1 axes at world (±0.10, 0.125), C slots numbered as on the real board, caps at the mirrored slots, B at (0, 0), arm cameras at x ±0.15. Final runs on the finished code; earlier partial runs and their fixes are listed in evidence/phase_c_20261111/README.md.

| Check | Result | Evidence / scope |
|---|---|---|
| t1: model and world generation, `test_cad_pose`, build, HOME, reach, HOME collision | PASS | evidence/phase_c_20261111/t1_final/ |
| t1: `test_ik.py` | FAIL | 16/18; cap_8 (-0.17, -0.055) and slot 8 (0.17, -0.055) have no downward-suction solution. The real arm reached slot 8 with the cup tilted about 9° |
| t1: unit tests coordinator / HMI / vision | PASS | 285 / 293 / 100 |
| t2: smoke test | FAIL | only `shutdown`: Gazebo did not stop within 5 s of SIGINT (known, intermittent; it passed in t2_camera/). Cameras, four views, controllers, MoveIt plan PASS |
| t2: simulated images, coordinate validation | PASS | t2_final/ |
| t2: regression `two` from an empty C area | PASS | caps in slots 1 and 2 |
| t2: legacy pipeline two objects | PASS | now reads the layout from coordinator.yaml and picks nearest arm1 HOME first (cap_4, cap_6) |
| t2: motion gateway, operator tools, safety supervisor (mock) | PASS | unreachable-target check now uses slot 8 |
| t2: vision pick | PASS | arm1 calibration error 0.70 mm (budget 1 mm); was 1.15 mm with the camera at x -0.20 |
| t2: README screenshots | PASS | docs/images/ retaken |
| Regression `batch` (8 objects from empty C) | FAIL | 7 placed in slots 1–7; FAULT at slot 8 (unreachable). The test expects this and reports PASS. evidence/phase_c_20261111/batch/ |
| Regression `faults` (B place point moved to (0, 0)) | PASS | 21 checks; evidence/phase_c_20261111/extra/ |
| Coordinator node in Gazebo (`test_coordinator_sim.py`) | FAIL, then PASS | first run: `/dual_arm/recover` reply lost after the coordinator restart (`failed to send response (timeout)` in its log), unrelated to the layout; rerun on a fresh simulation PASS, 22 checks including a full cycle into slot 1 (extra_rerun/). 1 of 2 passed |
| Zone and slot state by vision | BLOCKED | arm cameras at HOME: arm1 sees 3 caps, arm2 finds 0 slots (C31, D7 unchanged); tasks keep using ground truth for zones and slots |

## 2026-11-11 Field results imported (Orin, Dual-Arm-TEST-2.0 `13a5b4f`)

Results are the field tester's; this repo only copies the text records.

| Check | Result | Evidence / scope |
|---|---|---|
| UPDATE to `8ad9d47`: build, coordinator 285, HMI 293, CM530 42, Mock Serial 7 stages, mock start/stop | PASS | evidence/hardware/20261111_UPDATE/ |
| P0 daily recheck | PASS | evidence/hardware/20261111_P0/; e-stop verbal report, no video |
| H1 both arms (torque off) | NOT_RUN | in progress; Moving Speed not read, circle method skipped; j1, j2, straight, HOME, board width, C slots and teach readings taken (evidence/hardware/20261111_H1/) |
| V0 camera mapping | NOT_RUN | in progress; by-path mapping by covering each camera, arm1_cam rotate 180 still correct under a provisional definition (evidence/hardware/20261111_V0/) |
| Offline FK check of arm2 C-slot teach READs against tape-measured slots | PASS | radius within about 3 mm for 8 slots (evidence/hardware/20261111_fk_crosscheck/); H1-level evidence only, not calibration |

## 2026-11-11 Operator UI screenshots

| Check | Result | Evidence / scope |
|---|---|---|
| `scripts/capture_hmi_images.py` on a live simulation | PASS | docs/images/ui_working.png, ui_stopped.png; no process left |
| Environment camera zones at start-up (A-right layout) | FAIL | board not located; the first capture fell back to a 2026-11-08 old-layout `zones.yaml` and swapped A and C; that file was set aside and the shots retaken |

## 2026-11-11 Docs synchronised; event log order

| Check | Result | Evidence / scope |
|---|---|---|
| HMI unit tests after the event-log change | PASS | 293, including two new tests for merge order and the 200 limit |
| `check_docs.py` | PASS | links and zone-order statements |
| Gazebo rerun of stage 3 | NOT_RUN | the change affects only the event list |

## 2026-11-11 Operator UI stage 3 (task control)

Commands are in evidence/hmi/stage3/stage3_*.sh and stage3_live_check.py. Isolated with ROS_DOMAIN_ID=78, GZ_PARTITION=hmi_stage3 and a temporary state directory and journal; the window runs offscreen and confirmation dialogs answer yes.

| Check | Result | Evidence / scope |
|---|---|---|
| Build, HMI and coordinator unit tests | PASS | 01_build.log, 02_pytest.log; 291 / 285 |
| pyflakes on the changed files | PASS | 02_lint.log |
| One cycle through the start button | PASS | 04_live_check.json `cycle`; SUCCEEDED in 245.6 s |
| Stop while moving with nothing held, reset, HOME, recover, start again | PASS | `stop_empty`; latched and controllers stopped 0.3 s after the press; second run SUCCEEDED |
| Stop while holding, HOME refused, reset simulation | FAIL, then PASS | first run: the third pick faulted at the arm1 elbow limit before holding (C30); rerun on a fresh simulation, 04_live_check_holding.json |
| Shutdown leftovers | PASS | none in either run |
| HOME from a state past a joint limit | FAIL (known gap) | MoveIt `CheckStartStateBounds`; simulation must be reset |
| Suction confirmation, torque on, Mock and Mock Serial stop, hardware | NOT_RUN | |

## 2026-11-10 Tiered checks on the A-right layout

WSL Ubuntu 24.04 + Jazzy, `scripts/run_checks.sh` from `55196a5` plus this stage's working-tree changes. Index, failure causes and fixes in evidence/checks_20261110/README.md.

| Check | Result | Evidence / scope |
|---|---|---|
| t0 `check_docs.py` | PASS | 0 broken links; listed zone-order statements reviewed |
| t1: model generation, `test_cad_pose`, build, HOME poses, HOME collision | PASS | t1/ |
| t1 `test_ik.py` | FAIL | 16/18, known, unchanged |
| t1 `report_reach.py` | report | caps 4/8, slots 7/8, same as the old layout |
| t1 coordinator / HMI / vision_pkg pytest | PASS | 272 / 262 / 99 |
| t1 slot study, proposal verification, slot self-collision | PASS | rerun on the new layout; mirrors the old results |
| t2 `smoke_runtime.py sim` | FAIL | functional items PASS; shutdown check FAIL in t2/ and t2_rerun/, PASS in t2_aborted/ |
| t2 image and coordinate checks, regression `two` | PASS | t2/ |
| t2 old pipeline two objects | FAIL, then PASS | ROS domain mismatch in the runner; t2_rerun/ |
| t2 MotionGateway, safety supervisor (MoveIt mock) | PASS | t2/ |
| t2 operator tools (MoveIt mock) | PASS, FAIL, PASS | static TF left running in t2/; first fix lost the TF (t2_rerun/); second fix PASS with no leftover (t2_operator_tools/) |
| t2 vision probe and vision pick | FAIL, then PASS | parked caps counted in zone C; park point moved; t2_rerun/ |
| t2 README screenshots | PASS | published to docs/images/ |
| regression `faults`, `batch`, 3 vision picks, CM-530 tests, hardware | NOT_RUN | |

## 2026-11-10 Simulation layout: zone A on the arm's right

WSL Ubuntu 24.04 + Jazzy after `generate_cad_robot.py`, `generate_world.py` and `scripts/build.sh`. Index and caveats in evidence/a_right_layout_20261110/README.md.

| Check | Result | Evidence / scope |
|---|---|---|
| `test_cad_pose.py` | PASS | 264 components equal the source assembly turned 180 deg about Z |
| `build.sh`, `validate_model.py` | PASS | 02_build.log |
| `report_home_poses.py` | PASS | home_A (-166.3, -27.7, 140.8) mm, home_C (151.6, -35.0, 140.8) mm, inside limits |
| `test_ik.py` | FAIL | 16/18; arm1 (-0.2, -0.085) and arm2 slot 1 (0.1675, -0.09), mirrors of the previous two failures |
| coordinator / HMI / vision_pkg pytest | PASS | 259 / 262 / 99; coordinator first run had 5 fixture failures (park point and vision stub sides), fixed |
| HOME collision | PASS | 08_sim_checks.log (its exit codes are unreliable, see README) |
| slot proposals, slot self-collision | FAIL / not valid | `verify_slot_proposals.py` raised (old-layout joint solutions); self-collision checked those same old solutions. Corrected the same day after rerunning the slot study, see the checks entry above |
| `smoke_runtime.py sim` | FAIL | all functional items PASS; shutdown check FAIL twice (Gazebo SIGINT timeout) |
| `run_pipeline.sh --count 2`, first | FAIL | missed sign in the "cleared B" check |
| `run_pipeline.sh --count 2`, after fix | PASS | 11_transfer_pipeline.json, slots 3 and 4 |
| `demo_pick_place.launch.py`, one cycle | PASS | SUCCEEDED, no leftover processes |
| `test_motion_gateway.py`, `test_operator_tools.py`, `test_safety_supervisor.py` (MoveIt mock) | PASS | 14_mock_tests.log |

## 2026-11-10 Orin hardware session (on site, imported)

Run on site by the tester with code `3fd258c`; source records in Azeem1010/Dual-Arm-TEST-2.0 `fc4cd41`, copies in evidence/hardware/. Not rerun here.

| Check | Result | Evidence / scope |
|---|---|---|
| Install, first run | FAIL | ROS source Signed-By conflict, exit 100 (20261110_SETUP) |
| Install and build, retry | PASS | after source reuse, noble-updates and FFmpeg dev packages; 13 packages (20261110_SETUP_retry) |
| Offline tests on Orin | PASS | coordinator 259, HMI 262, CM530 42, Mock Serial 7 phases, mock start/stop |
| P0 | PASS | e-stop by spoken report only; power-cut scope not recorded |
| H0 read-only | PASS | `VERSION,5`, HOME as expected, 8 positions change by hand |
| H1 arm1 | NOT_RUN (partial) | j1 +1, A on the arm's own right, straight READ 200,505,498,513; j2 direction unclear |
| H1 arm2 | NOT_RUN | |
| Layout against model | FAIL | A side, base-to-edge distance and board width differ; model not changed |
| `install_jazzy.sh` change applied here | PASS (`bash -n` only) | not executed on this machine |

## 2026-11-10 Operator UI stage 2 (start and stop)

Commands are in evidence/hmi/stage2/stage2_*.sh and stage2_live_check.py. Isolated with ROS_DOMAIN_ID=79, GZ_PARTITION=hmi_stage2 and a temporary state directory. The copied check script excludes the interface's own node; the run itself used the earlier version.

| Check | Result | Evidence / scope |
|---|---|---|
| Offline tests | PASS | 02_pytest.log; 242 tests, launcher tests use real processes |
| Ten start and stop cycles of the simulation through the interface | PASS | 03, 04, 05_assessment.json; every cycle ready and stopped, no Gazebo, tagged process or ROS node left |
| Adoption after the interface was killed | PASS | adoption in 04_live_check.json; same session, stopped cleanly |
| Raw verdict `all_cycles_clean` | FAIL (check error) | it counted the interface's own node; corrected in 05_assessment.json |
| Mock, Mock Serial and hardware starts through the interface | NOT_RUN | command building is unit tested only |
| Windows `.bat` path conversion and Orin `.desktop` file | PASS | checked with an echo-only copy and a temporary home; not double-clicked |

## 2026-11-10 Operator UI stage 1 (read-only monitor)

Commands are in evidence/hmi/stage1/stage1_*.sh and stage1_*.py. Isolated with ROS_DOMAIN_ID=78 and GZ_PARTITION=hmi_stage1.

| Check | Result | Evidence / scope |
|---|---|---|
| Build of `vision_pkg`, `dual_arm_bringup`, `dual_arm_hmi` | PASS | 01_build.log |
| Offline tests | PASS | 02_pytest.log; 205 tests |
| Live data against `hmi_sim.launch.py` | PASS | 04_live_check.json, screens/; 8 joints with limits and commands, annotated differs from raw on all three cameras, four Gazebo views |
| One transfer observed to SUCCEEDED | PASS | 04_live_check.json; Gazebo ground truth decides zones |
| Lost system announced | PASS | after_stop in 04_live_check.json; ROS interrupted about 6 s after SIGINT |
| Interface is read-only | PASS | 05_node_info.txt; no publishers beyond /rosout and /parameter_events, no action clients |
| Interface load | PASS | 06_speed_without_ui.json against speed_with_ui; real-time factor 0.182 and 0.183, refresh mean 1.0 ms |
| 10 FPS camera target | NOT_RUN | WSL renders about 2 FPS with or without the interface |
| Real window with live data, Orin, hardware | NOT_RUN | Live checks ran off screen |

## 2026-11-10 Operator UI stage 0

Commands are in evidence/hmi/stage0/stage0_verify.sh and wslg_window_check.py. All data shown is invented.

| Check | Result | Evidence / scope |
|---|---|---|
| `dual_arm_hmi` build | PASS | 01_build.log; this package only |
| Unit and off-screen layout tests | PASS | 02_pytest.log; 166 tests, twelve scenarios at four resolutions |
| Screen captures | PASS | 03_screenshots.log, screens/; 18 images, reviewed by eye |
| Real window on WSLg | PASS | 04_wslg_window.log, wslg_window.json; xcb, real F12, refresh mean 7.0 ms with fake data |
| System CJK font in WSL | FAIL | Not installed, needs sudo; the checks above used a private font folder |
| 150% display scaling, user visual review, Orin | NOT_RUN | |
| ROS data, real cameras, hardware | NOT_RUN | Stage 1 onward |

## 2026-11-10 C32 safety latch enforcement

Commands are in evidence/c32/c32.sh.

| Check | Result | Evidence / scope |
|---|---|---|
| coordinator build and pytest | PASS | 01, 02; 259 tests |
| `test_safety_ros.py` repeated | PASS | 03; 5 of 5 runs, 6 tests each, stand-in controller manager |
| Safety scenarios including manual activation while latched | PASS | 05, 06; MoveIt mock, 29 checks, stopped again in 0.29 s |
| Startup order and manual switch on mock serial | PASS | mock_serial/results.txt; controllers inactive after manual switch, reset before hardware active still refused |
| Leftover processes | PASS | 07; none |
| Hardware, Gazebo physics | NOT_RUN | |

## 2026-11-10 README images and safety startup order

Commands are in evidence/readme_images/capture.sh and evidence/safety_order/run.sh.

| Check | Result | Evidence / scope |
|---|---|---|
| `demo_pick_place.launch.py cycles:=2` | PASS | readme_images; Gazebo ground truth, SUCCEEDED, completed 2, no leftovers |
| README images captured from real sensor frames | PASS | readme_images/raw; second attempt |
| First capture attempt | FAIL | status is 5 Hz and short states were missed; task itself SUCCEEDED, nothing published |
| `/safety/reset` before hardware active | FAIL | safety_order; refused, this was the documented order |
| Hardware active, then `/safety/reset` | PASS | safety_order; mock serial, controllers active |
| Heartbeat loss stops controllers | PASS | safety_order; mock serial |
| Manual `switch_controllers` blocked while latched | FAIL | safety_order; controllers become active, status still reports stopped (C32) |
| HARDWARE_TEST_GUIDE.md procedure | NOT_RUN | no hardware used |

## 2026-11-10 Documentation audit

Commands are in evidence/docs_audit/verify.sh and verify_unittest_sourced.sh.

| Check | Result | Evidence / scope |
|---|---|---|
| Old README `PYTHONPATH=... unittest` command | FAIL | 01; 3 import errors, the command replaced PYTHONPATH and lost rclpy |
| Same discovery with ROS entries kept in PYTHONPATH | PASS | 10; 253 tests |
| README pytest command | PASS | 02; 253 tests |
| `run_pipeline.sh --count 2` at 1.0/0.5/1.0 | PASS | 03, 04, 05; old pipeline, Gazebo ground truth |
| `demo_pick_place.launch.py` and `operator_console start` | PASS | 06, 07, 08; default one cycle, Gazebo ground truth, ended SUCCEEDED |
| Leftover processes after both runs | PASS | 09; none |
| Document links, referenced paths and executables | PASS | 24 documents, no broken links |
| Documented hardware and Orin procedures | NOT_RUN | no Orin or hardware used |

## 2026-11-10 WP12 ESP32 suction backend

Commands are in evidence/wp12/wp12.sh.

| Check | Result | Evidence / scope |
|---|---|---|
| coordinator build and pytest | PASS | 01, 02; 253 tests |
| ESP32 topic wiring | PASS | test_esp32_ros.py; stand-in node on domain 93 |
| Sim config accepted, hardware template refused | PASS | 03, 04; module mapping and timings must be measured |
| Real ESP32, micro-ROS agent, actual suction | NOT_RUN | |
| Gazebo regression | NOT_RUN | Gazebo backend unchanged |

## 2026-11-10 WP13 documentation

| Check | Result | Evidence / scope |
|---|---|---|
| Node interfaces captured from running nodes | PASS | evidence/wp13/04_node_info.txt; MoveIt mock |
| Document links, referenced scripts and installed executables | PASS | checked against the workspace |
| ORIN_DEPLOYMENT.md procedure | NOT_RUN | no Orin or hardware used |

## 2026-11-09 WP10 operator tools

Commands are in evidence/wp10/wp10.sh. Integration uses `scripts/test_operator_tools.py`.

| Check | Result | Evidence / scope |
|---|---|---|
| coordinator build and pytest | PASS | 01, 02; 233 tests |
| `cm530_probe` on mock serial | PASS | 05, 06; sent only the six read-only commands |
| `check_calibration_sheet` | PASS | shipped template refused; fitting and limits covered by unit tests |
| `manual_xy` on MoveIt mock | PASS | plan left joints still; execute reached the target; unreachable target and hardware template refused |
| `operator_console` with the coordinator node | PASS | status, start, and refusals for confirm and recover |
| Real board, real calibration measurements | NOT_RUN | |

## 2026-11-09 WP9 safety supervisor

Commands are in evidence/wp9/wp9.sh. Integration uses `scripts/test_safety_supervisor.py` against `start_sim.sh mock`.

| Check | Result | Evidence / scope |
|---|---|---|
| coordinator build and pytest | PASS | 01, 02; 201 tests |
| Mock run 1 | FAIL | run1_reset_before_coordinator_ready/; test reset before the restarted coordinator reported in; reset was correctly refused |
| Mock run 2 | PASS | 04, 05; 26 checks |
| Arm stop time after coordinator is killed | measurement | about 1.2 s; 22.2 s before WP9 (C29) |
| Arm stop time after heartbeat loss / asserted stop | measurement | about 2.7 s including the 2 s limit / about 0.3 s |
| Gazebo physics, hardware heartbeat source, hardware | NOT_RUN | |

## 2026-11-09 WP8 driver hardening

Commands are in evidence/wp8/wp8.sh.

| Check | Result | Evidence / scope |
|---|---|---|
| Build of cm530_hardware, controllers, bringup | PASS | 01 |
| cm530_hardware colcon test | PASS | 02, 03; 35 gtests plus 4 CTest wrappers |
| `test_cm530_mock.py` | PASS | 04, cm530_mock/; 7 phases, including template and rest-pose refusals |
| ASan + UBSan, 20 repetitions | PASS | 05; no reports |
| TSan, 20 repetitions | PASS | 05; run with `setarch -R` for the WSL address layout |
| c-review | NOT_RUN | needs a Workflow tool not available here |
| READ retry | NOT_RUN | waits for decision D2 |
| Real UART, motors, Orin | NOT_RUN | |

## 2026-11-09 WP7 vision gateway

Commands are in evidence/wp7/wp7.sh. Gazebo; simulated calibration from the known camera geometry.

| Check | Result | Evidence / scope |
|---|---|---|
| coordinator build and pytest | PASS | 10, 11; 186 tests |
| Live vision probe at HOME | measurement | 03, 04; arm1 error up to 0.94 mm; arm2 found 1 of 8 slots; environment camera could not locate the field |
| Missing calibration record refuses the run | PASS | every pick run; stops before any object moves |
| Vision-chosen picks, first five runs | FAIL | before_timing_fixes/, 13; 1 of 5 passed |
| Vision-chosen picks after timing fixes | PASS | pick_repeat_1..3, 14; 3 of 3, slots 3 and 4 |
| Two objects with final parameters | PASS | regress_two/; 5 checks |
| Fault scenarios with final parameters | PASS | regress_faults/; 21 checks |
| Time reduction of at least 50% with final parameters | FAIL | 15_timing_compare.txt; 727.6 s to 373.9 s, -48.6% |
| Zone and slot state from vision | BLOCKED | C31, decision D7 |
| Hardware | NOT_RUN | |

## 2026-11-09 WP6S faster simulation speeds

Commands are in evidence/wp6s/wp6s.sh. Scales changed to transport 1.0, contact 0.5, acceleration 1.0.

| Check | Result | Evidence / scope |
|---|---|---|
| coordinator build and pytest | PASS | 01, 02; 170 tests |
| First regression attempt | FAIL | two_run1_timing_probe_script_error/; a bug in the real-time-factor probe aborted the script before the test started |
| Two objects at the new speeds | PASS | two/; slots 3 and 4; record, ground truth and planning scene agree |
| Time reduction of at least 50% | PASS | 03_timing.txt versus wp6/03_analysis.txt; trajectory span 727.6 s to 351.8 s, -51.6% |
| Idle real-time factor | measurement | 7 simulated seconds in 34 wall seconds, about 0.2 |
| Fault scenarios and old pipeline at new speeds, hardware | NOT_RUN | |

## 2026-11-09 WP6 simulation regression

Commands are in evidence/wp6/wp6.sh; scenarios are in `scripts/test_transfer_regression.py`. Gazebo ground truth, simulated prefilled slots 1 and 2 unless stated.

| Check | Result | Evidence / scope |
|---|---|---|
| coordinator build and pytest | PASS | 01, 02; 170 tests |
| Two objects | PASS | two/; slots 3 and 4; record, ground truth and planning scene agree; about 12.4 min |
| Fault scenarios, first run | FAIL | faults_run1_start_before_heartbeat/; test timing, start correctly refused without a heartbeat |
| Fault scenarios | PASS | faults/; 21 checks: failed release, heartbeat loss, latched emergency stop, cancel while holding, scene cleanup on recovery |
| Eight objects from empty C | FAIL | batch/; slot 1 out of reach; the run stopped before any object moved, as designed |
| Six objects into slots 3 to 8 | FAIL | batch/; placed 4, then no reachable cap; 03_analysis.txt shows only cap_3 to cap_6 are reachable |
| Vision-driven transfer, hardware | NOT_RUN | |

## 2026-11-09 WP5 coordinator node

Commands are in evidence/wp5/wp5.sh. Integration uses `scripts/test_coordinator_sim.py` against `start_sim.sh headless` with Gazebo ground truth.

| Check | Result | Evidence / scope |
|---|---|---|
| coordinator build and pytest | PASS | 01, 02; 165 tests |
| `demo_pick_place.launch.py --show-args` | PASS | 03; argument parsing only |
| Gazebo run 1 | FAIL | run1_cancel_during_planning/; cancel landed during planning, so the arm had not left HOME and the test's assumptions did not hold |
| Gazebo run 2 | FAIL | run2_operator_before_arm_stopped/; MoveIt refused a new trajectory while the killed run's trajectory was still executing |
| Gazebo run 3 after correcting test timing | PASS | 05, 06; 22 checks; cancel, refusals, two restart recoveries, one full A->B->C with the real suction plugin |
| Motion after coordinator is killed | FAIL (known gap, C29) | 06 observations; about 22 s and 0.26 rad after SIGKILL |
| Eight objects, vision-driven transfer, hardware | NOT_RUN | |

## 2026-11-09 WP4 suction gateway

Commands are in evidence/wp4/wp4.sh.

| Check | Result | Evidence / scope |
|---|---|---|
| coordinator build and pytest | PASS | 01, 02; 142 tests, 41 new |
| ROS topic wiring | PASS | test_gripper_ros.py; stand-in node on domain 91, not the Gazebo plugin |
| Hardware refuses auto-confirm and Gazebo backend | PASS | test_gripper.py and task_config tests |
| Real Gazebo suction plugin | NOT_RUN | WP6 |
| Physical suction, ESP32 | NOT_RUN | no protocol available |

## 2026-11-09 WP3 motion gateway

Commands are in evidence/wp3/wp3.sh. Integration uses `scripts/test_motion_gateway.py` against `start_sim.sh mock`.

| Check | Result | Evidence / scope |
|---|---|---|
| coordinator build and pytest | PASS | 01, 02; 101 tests |
| Mock run 1 | FAIL | 04a, 05a; reported PASS, but the contact-path collision check was refused by IK, so it did not test collision |
| Mock run 2 after correcting the test | PASS | 04, 05; 16 checks, full A->B->C path, worst TCP error 2.9 um, worst tilt on contact moves about 1e-6 deg |
| Refusals | PASS | slot 1 and far target by IK; two colliding cases with a collision reason; refused descent moved no joint |
| Cancel during motion | PASS | stopped mid-move and stayed still on mock |
| Gazebo physics, hardware | NOT_RUN | mock joints follow commands exactly |

## 2026-11-09 WP2 ROS-free task logic

Commands are in evidence/wp2/wp2.sh.

| Check | Result | Evidence / scope |
|---|---|---|
| `colcon build --packages-select dual_arm_coordinator` | PASS | 01_build.log |
| coordinator pytest, first run | FAIL | 02a_first_run_2_failed.log; 79 passed, 2 failed; refusals from the resource managers were not raised as TaskFault |
| coordinator pytest after the fix | PASS | 02_coordinator_pytest.log; 81 tests with a fake IO world |
| Installed modules do not load rclpy | PASS | 05_import_check.txt |
| `check_task_config` sim / hardware template | PASS | accepted / refused with exit 1 |
| Full workspace build, pipeline, ROS or Gazebo execution | NOT_RUN | only the coordinator package changed |
| All hardware checks | NOT_RUN | |

## 2026-11-09 WP1 interfaces and coordinator skeleton

Commands are in evidence/wp1/wp1.sh.

| Check | Result | Evidence / scope |
|---|---|---|
| `scripts/build.sh` | PASS | 01_build.log; 12 packages |
| coordinator pytest | PASS | 27 tests; 8 existing and 19 new in test_task_config.py |
| `ros2 interface show` for both services | PASS | 03_interfaces.txt |
| `check_task_config` on installed sim config | PASS | 04_check_sim.txt; exit 0 |
| `check_task_config` on hardware template | PASS | 05_check_hardware.txt; refused with exit 1 as required |
| `run_pipeline.sh --count 2` | PASS | 07, 08; 74 events; Gazebo ground truth, slots 3 and 4 only |
| All hardware checks | NOT_RUN | |

Three older evidence files overwritten by build.sh and the pipeline were restored from git.

## 2026-11-09 WP0 baseline

Commit c7dfba3, WSL Ubuntu, no source changes. Commands are in evidence/roadmap_baseline/wp0.sh.

| Check | Result | Evidence / scope |
|---|---|---|
| `scripts/build.sh` | PASS | 01_build.log; 11 packages |
| coordinator / vision adapter / vision_pkg pytest | PASS | 8 / 10 / 99 tests |
| `cm530_hardware`, `dual_arm_gripper` colcon test | PASS | 29 gtests (reported as 33 with 4 CTest wrappers); 1 gripper CTest |
| `test_cm530_mock.py` | PASS | 5 phases; mock serial only |
| `run_pipeline.sh --count 2` | PASS | 74 events; Gazebo ground truth, not vision-driven |
| Gazebo shutdown by SIGINT to launch only | NOT_RUN | a process-group SIGINT exited cleanly, which is a different method |
| Sanitizers | NOT_RUN | outside WP0 |
| All hardware checks | NOT_RUN | |

The first attempt did not run the build because `wsl.exe` expanded the shell variables; see roadmap_baseline/README.md. Eight older evidence files overwritten by these scripts were restored from git.

## 2026-11-09 Far-side simulation layout

Commands ran in WSL Ubuntu after `generate_cad_robot.py`, `generate_world.py` and `scripts/build.sh`. Both generators were first run unmodified and reproduced the committed model and world. Prior evidence is in evidence/before_far_side_layout_20261109. The first background run never started, because Git Bash rewrote the `/mnt/c` script path and a pipe hid the failure with exit 0; its stale files were not used. It was rerun with `MSYS_NO_PATHCONV=1`, and file times and values were checked afterward.

| Check | Result | Evidence / scope |
|---|---|---|
| `test_cad_pose.py` | PASS | cad_pose_validation.json; 264 visuals match source CAD plus the documented layout transform; does not show the layout matches hardware |
| `verify_model_revision.py` | PASS | model_revision_validation.json; motor axes and TCP unchanged |
| `report_home_poses.py` | PASS | home_poses.json; FK and limits; j1 direction -1 is inferred |
| `check_home_collision.py` | PASS | home_collision.json; discrete self/inter-arm boxes only; world and path NOT_RUN |
| `test_ik.py` | FAIL | ik_validation.json; 16/18; arm1 (0.2, -0.085) and arm2 slot 1 (-0.1675, -0.09), the mirrored equivalents of the two previous failures |
| `measure_slot_adjustment.py` baseline | FAIL | slot_adjustment.json; slot 1 at 30 mm above contact |
| `verify_slot_proposals.py` | PASS | slot_proposal_verification.json; candidates +Y 6 mm, +X 18 mm, +Y 10 mm; solver self-consistency only |
| `check_slot_self_collision.py` | PASS | slot_self_collision.json; 0/248 invalid for each candidate; URDF boxes only |
| coordinator unit tests | PASS | 8 tests |
| `smoke_runtime.py sim --seconds 150 --group both_arms --execute` | PASS | sim_runtime.json; cameras, views, controllers, plan, execution feedback and shutdown |
| `analyze_sim_images.py` | FAIL for env grid only | sim_detection.json; arm1 8 caps and arm2 grid PASS; env finds 4 caps and 4 holes because the arms occlude it, unchanged from the previous record |
| `validate_sim_coordinates.py` | PASS (measurement) | sim_coordinate_validation.json; max error env 1.93 mm, arm1 1.09 mm, arm2 0.53 mm; calibration validity NOT_RUN |
| `tf2_echo armN_base_link armN_base` | PASS | far_side_checks.log; translation (0, 0, 0.014), yaw 90 deg |
| `run_pipeline.sh --count 2` | PASS | transfer_pipeline.json, far_side_pipeline.log; 74 events; Gazebo ground truth to slots 3 and 4 |

`check_slot_mesh_witnesses.py` was not rerun. Eight-object transfer, vision-driven transfer, world collision, continuous path and all hardware checks remain NOT_RUN.

## 2026-11-09 Live ROS graph capture

At commit b48eee8, headless `vision_sim.launch.py` plus `calibration.launch.py` ran on domain 77 and the graph was dumped with rclpy (evidence/ros_graph_vision_sim). Node, topic, service and action endpoints PASS against the source, and all three controllers were active. The first capture attempt never started because the capture script used `set -u` before sourcing ROS. `arm1_controller`'s spawner exited 1 after its first switch call timed out at 10 s and the retry found the controller already switched; the controller was active. `/vision/calibration_status` content NOT_RUN: `ros2 topic echo --once` got nothing within 15 s and the cause was not investigated. `arm2_vision_node` and `calibration_status` logged tracebacks during SIGINT shutdown, after the capture. No leftover processes. This shows endpoints exist, not that data or task flow is correct.

## 2026-11-09 README screenshots

docs/images comes from a two-object headless run at commit 6feea97, which reached PASS with 74 events. The first capture attempt never started the transfer because Gazebo's controller switch timed out after 120 s, while the capture script polled `list_controllers`; delaying the first poll by 45 s worked on the retry. One retry does not establish the cause, so treat this as an intermittent startup failure. transfer_pipeline.json was restored after the capture.

## 2026-11-09 Fresh GitHub clone check

Commit e345638 FAIL on a fresh clone (clone_build_check.log): `dual_arm_bringup` installed an empty `config` directory that git does not store. Removing that install entry gave 11 packages built, 33 cm530_hardware tests, coordinator tests and `start_sim.sh mock`, all PASS in a clone with the one-line fix. The earlier README flow check missed this because `tar` preserves empty directories.

## 2026-11-09 README flow check

The README steps were followed in a throwaway copy on the WSL Linux disk (readme_flow_check.log): copy 434 s and 578 MB, full build of 11 packages 300 s, then quick checks, 33 cm530_hardware tests, the mock-serial launch and `start_sim.sh mock`, all PASS. `install_jazzy.sh` was not rerun because the packages were already installed; its list was compared against the package dependency closure. All required ROS packages exist in the arm64 Jazzy repository, but an Orin build remains NOT_RUN.

## 2026-11-09 cm530_hardware on mock serial

Commands ran in WSL Ubuntu. The mock compiles the unmodified v17 firmware parser and AX-12 driver; only the motor bus and serial timing are simulated.

| Check | Result | Evidence / scope |
|---|---|---|
| `colcon build` of cm530_hardware, description, bringup | PASS | cm530_build.log; -Wall -Wextra -Wpedantic -Wconversion -Werror on project code |
| Unit tests (protocol, calibration, firmware-loop link and scheduler) | PASS | cm530_unit_tests.log; 33 tests |
| ASan + UBSan + LeakSanitizer, 20 repetitions | PASS | cm530_sanitizers.log |
| TSan, 20 repetitions | PASS | cm530_sanitizers.log; first attempt aborted at startup on the WSL mapping limit, rerun with `setarch -R` |
| `scripts/test_cm530_mock.py` | PASS | cm530_mock_integration.json; read-only, refused calibration, null template, missing tolerances, trajectory and mid-run link loss |
| URDF plugin selection in mock, sim, hardware and default modes | PASS | xacro output only; Gazebo was not rerun after this URDF edit |
| Real UART, motors, loop rate, Orin | NOT_RUN | No board connected |
| c-review security workflow | NOT_RUN | Its Workflow tool is unavailable in this environment |

## 2026-11-09 raw-512 zero mapping

Commands ran in WSL Ubuntu from `dual_arm_ws`.

| Check | Result | Evidence / scope |
|---|---|---|
| `bash scripts/build.sh` | PASS | colcon_build.log, model_validation.log; 10 packages |
| Coordinator unit tests | PASS | coordinator_zero512_tests.log; 8 tests |
| `scripts/report_home_poses.py` | PASS | home_poses.json; FK and limits only, simulation-assumed mapping |
| `scripts/check_home_collision.py` | PASS | home_collision.json; discrete self/inter-arm boxes, world and path NOT_RUN |
| Two-object A->B->C regression | PASS | transfer_pipeline.json, zero512_pipeline.log; Gazebo ground truth, headless, 74 events. cap_5 and cap_6 ended within 0.01 mm XY of their C targets |
| Simulation shutdown | FAIL | zero512_launch.log; launch still running 45 s after SIGINT, Gazebo stopped by SIGTERM |
| Arm 1 j1 zero | BLOCKED | Needs motor 17 readings on the real arm; 192.3 is a simulation placeholder |
| Hardware calibration, directions, wrist clearance | NOT_RUN | Hardware remains disabled |

A first collision attempt failed before running because the test command overrode PYTHONPATH and hid rclpy; it was rerun without the override. `transfer_pipeline.json` holds `FAIL` until a run completes, so a mid-run read is not a result.

## 2026-11-09 revision results

- `model_revision_validation.json`: PASS, ten prescribed component transforms, unchanged motor axes/TCP, eight white pads flush at 14 mm.
- `coordinator_revision_tests.log`: eight tests PASS, including HOME missing/invalid inputs and signed conversion.
- `home_named_states_build.log`: two affected packages built successfully after HOME named-state generation.
- `solidworks_standalone.log`: corrected geometry SLDPRT saved and reopened, 342 solid bodies, warnings=0. Not proof of original parametric mates or portable imported SLDASM references.
- Old three-object pipeline PASS is historical. Revised geometry / assumed HOME / 50% transport workflow is still undergoing runtime validation. Latest startup readiness failure is recorded, not counted as motion success.

All below refers to earlier component measurements unless explicitly regenerated.

These results cover separate components and measurements. Overall complete-system acceptance is **NOT_RUN**; the latest simulation runtime probe is **FAIL** because Gazebo shutdown fails. No hardware calibration or physical acceptance is claimed.

| Check | Recorded result | Evidence / scope |
|---|---|---|
| CAD source-pose transforms | PASS | evidence/cad_pose_validation.json; exported source pose, not dynamics |
| Original vision tests | PASS | evidence/vision_tests.log; 99 tests |
| Calibration validity and held-out plane checker | PASS | evidence/calibration_suite.log; 10 tests; no physical calibration |
| Mock controllers, MoveIt planning and shutdown | PASS | evidence/mock_runtime.json |
| Simulation both_arms small joint execution and feedback | PASS | evidence/sim_runtime.json; not A→B→C |
| Simulation shutdown | FAIL | evidence/sim_launch.log; Gazebo escalates to SIGTERM |
| Three camera streams and four views | PASS | evidence/sim_runtime.json; fixed simulation camera mounts |
| Suction isolated attachment/release physics | PASS | evidence/suction_physics.json; simple fixture, not dual-arm transfer |
| Suction policy sanitizers | PASS | evidence/gripper_sanitizers.log; policy test only |
| Saved slot-proposal FK and limits | PASS | evidence/slot_proposal_verification.json; 744 discrete points across three candidates |
| Proposal conservative-box self-collision | FAIL | evidence/slot_self_collision.json; −Y 7 mm: 49/248 invalid; −Y 10 mm and +X 19 mm: each 62/248 invalid |
| Selected CAD mesh surface witnesses | NOT_RUN (full clearance acceptance) | evidence/slot_mesh_witnesses.json; six representative states checked, no surface crossings found; containment and whole trajectory not covered |
| Full eight-object transfer and placement | NOT_RUN | Runtime coordinator, scene and validated target pipeline incomplete |
| CM530 / ESP32 / real cameras | NOT_RUN | Hardware disabled |

Saved-image coordinate measurements in evidence/sim_coordinate_validation.json are not calibration authorization. CameraInfo-derived maximum XY errors were approximately 1.97 mm (environment, 4 caps), 1.16 mm (arm1, 8 caps), and 1.61 mm (arm2, 8 holes). Four-point fitted homographies with four unused points in the same static scene reduce maximum held-out errors to approximately 0.17 mm and 0.09 mm for arm1 and arm2. Independent acquisition, timestamp/TF provenance and the measured combined error budget are still missing, so operational calibration remains NOT_RUN.

Reproduce the slot checks in WSL from the workspace:

```bash
python3 scripts/verify_slot_proposals.py
source /opt/ros/jazzy/setup.bash
source install/setup.bash
python3 scripts/check_slot_self_collision.py  # expected exit 1 for recorded collisions
python3 scripts/check_slot_mesh_witnesses.py prepare
.cad-venv/bin/python scripts/check_slot_mesh_witnesses.py inspect
```

The collision query launches an isolated mock graph and sends state-validity requests only. It uses installed URDF/SRDF and verifies installed URDF bytes match source. Evidence includes model and input hashes. Rebuild if source and installed model differ.
