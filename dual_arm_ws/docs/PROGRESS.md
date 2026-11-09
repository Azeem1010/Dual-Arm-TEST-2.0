# Development status — 2026-11-10

Current status by work package is in MODIFICATION_PLAN.md section 6. Each section below records one result at the time it was made, so later sections supersede what older ones list as not run.

## Latest result: C32 safety latch enforced

- `safety_supervisor` now checks the arm controllers every 0.2 s while latched and stops any that are active. `controllers_stopped` in `/safety/status` is now the verified result: it is false while a controller is active or cannot be checked. A reset is excluded from this check while it runs, and a failed reset stops the controllers again.
- PASS: coordinator 259 tests (6 new, over real ROS services against a stand-in controller manager; 5 of 5 repeat runs). MoveIt mock 29 checks; manual activation stopped in about 0.29 s. Mock serial: controllers inactive again after a manual switch. The correct startup order still works, and the wrong order is still refused. Evidence: evidence/c32/.
- Remaining: a window of about 0.3 s before the controllers are stopped again, so manual switching stays forbidden. NOT_RUN: hardware and Gazebo physics.

## Latest result: README images, hardware guide, safety finding

- README images recaptured from a two-object run of `demo_pick_place.launch.py cycles:=2` (SUCCEEDED, completed 2, no leftover processes) with new `scripts/capture_readme_images.py`. They replace the old-layout images noted as stale below. The first capture attempt missed short states and was discarded before publishing. Evidence: evidence/readme_images/.
- New HARDWARE_TEST_GUIDE.md walks through every stage in order, and HANDOFF_PROMPT_NEXT_COMPUTER.md is for continuing on another machine. Every hardware step in the guide is NOT_RUN.
- FAIL found on mock serial (evidence/safety_order/): the documented order, `/safety/reset` before activating the hardware, is refused with "Controller activation was refused". Activating the hardware first and then resetting works; ORIN_DEPLOYMENT.md and the README are corrected.
- FAIL, not fixed (conflict C32): while the supervisor is latched and has stopped the controllers, a manual `switch_controllers --activate` activates them, and `/safety/status` still reports `controllers_stopped: true`. The guide forbids that command until the supervisor is fixed.
- New decision D8: the source of the `/safety/estop` heartbeat. H4 and later stay BLOCKED until it is decided.

## Latest result: documentation audit

- All project documents were compared with the code and corrected: both READMEs, AGENTS.md, ARCHITECTURE, COORDINATE_FRAMES, HOME_POSES, IMPLEMENTATION_PLAN, PIPELINE_DEMO, SLOT_ADJUSTMENT, SOURCE_AUDIT, VISION_CALIBRATION, VISION_INTEGRATION, FUTURE_ROADMAP, MODIFICATION_PLAN, HANDOFF_PROMPT, ROS_INTERFACES and RESUME. REQUIREMENTS.md and historical evidence were not changed.
- PASS: `demo_pick_place.launch.py` with `operator_console start` ended SUCCEEDED for its default one cycle, its first full run. The old `run_pipeline.sh --count 2` also passed at the current 1.0/0.5/1.0 speeds. Coordinator pytest 253 passed. Links: 24 documents, none broken. Evidence: evidence/docs_audit/.
- FAIL, then corrected: the README unit test command gave 3 import errors, because it replaced PYTHONPATH and lost rclpy. With the ROS entries kept, all 253 tests pass. The README now uses the pytest command.
- Still stale, needs a new capture: the README screenshots show the old layout and the old simultaneous pipeline; they are labelled as such. NOT_RUN: hardware.

## Latest result: WP12 ESP32 suction backend

- New `Esp32Suction` in gateways/gripper.py, using /suction_command and /suction_status from ray000518/micro-ros commit 0c28c7f. It publishes the command, requires a matching echo, waits for vacuum on grasp, then asks the operator to confirm, because the firmware has no vacuum sensor. The hardware template now selects this backend and leaves module mapping and timings null. A fault never sends the all-off command, which would drop a held object.
- PASS: coordinator 253 tests, including two across real ROS topics against a stand-in that behaves like the firmware. Evidence: evidence/wp12/. ORIN_DEPLOYMENT.md section 6.1 covers the agent build, start order and first power-on checks.
- NOT_RUN: a real ESP32, actual suction and the micro-ROS agent. Module mapping, relay polarity and vacuum time need checking on the rig. Gazebo regression was not rerun; the Gazebo backend did not change.

## Latest result: WP13 documentation

- New TEST_PLAN.md and ORIN_DEPLOYMENT.md. ROS_INTERFACES.md now covers the coordinator and safety supervisor, from a capture on the MoveIt mock (evidence/wp13/04_node_info.txt), and its known gaps are current. HANDOFF_PROMPT.md state is current.
- NOT_RUN: every deployment step in ORIN_DEPLOYMENT.md has been written from the code and has not been executed on an Orin or real arms.
- All work that needs no hardware or user decision is done. Remaining: WP7 (D7), WP11 (D0, D3), WP12 (D5), READ retry (D2), and hardware stages H0 to H8.

## Latest result: WP10 operator tools

- New in dual_arm_coordinator/tools: `cm530_probe` (allow-listed read-only commands, exclusive port, no retry), `check_calibration_sheet` (offline; reports candidates, writes nothing, limits have no defaults), `manual_xy` (plans only unless `--execute`, refuses while a task runs) and `operator_console` (one-shot commands; confirm and recover need explicit flags).
- PASS: coordinator 233 unit tests; 18 integration checks on mock serial and MoveIt mock, including an independent check that planning leaves the joints still. Evidence: evidence/wp10/.
- NOT_RUN: real board, and `check_calibration_sheet` on real measurements. `manual_xy` is a command-line tool, so the ManualXY service defined in WP1 currently has no server. A hardware `arm1_base` transform still does not exist.

## Latest result: WP9 safety supervisor

- New safety_monitor.py and safety_supervisor.py. On an asserted emergency stop, a missing or stale heartbeat, or a coordinator that stops reporting, the arm controllers are deactivated and the state latches until `/safety/reset` succeeds with healthy inputs. hardware.launch.py starts it whenever motion is enabled on a real port.
- PASS on MoveIt mock: 26 checks over heartbeat loss, killed coordinator and asserted emergency stop; motion is refused while latched and reset is refused until inputs recover. Coordinator unit tests: 201. Evidence: evidence/wp9/.
- Conflict C29 measured: the arm stopped about 1.2 s after the coordinator was killed, against about 22 s before. Heartbeat loss stopped it in about 2.7 s, which includes the 2 s age limit; an asserted stop took about 0.3 s.
- The first run failed because the test reset before the restarted coordinator had reported in, and reset was correctly refused; kept as run1_reset_before_coordinator_ready/.
- NOT_RUN: Gazebo physics, hardware. This is a software interlock and does not replace a physical emergency stop; no hardware heartbeat source exists yet.

## Latest result: WP8 driver hardening

- cm530_hardware: the handshake first sends 96 DEL characters to clear a partial line left in the firmware, which unlike a line ending cannot execute it. Activation is refused before any torque if a joint rests outside its limits. `on_error` stops the scheduler and sends one HOLD per arm only while the link is synchronized. New all-null controllers_hardware.template.yaml, which hardware.launch.py refuses.
- PASS: 35 gtests (29 before), seven-phase mock serial, ASan/UBSan and TSan with 20 repetitions and no reports. Evidence: evidence/wp8/.
- Not done: READ retry waits for decision D2. c-review NOT_RUN because its Workflow tool is unavailable here. Whether the DEL flush cures the real `ERR,BAD_CMD` is NOT_RUN, since that cause is a hypothesis. No hardware was used.

## Latest result: WP7 vision gateway (partial, BLOCKED)

- New gateways/vision.py: vision services behind calibration status, a new-image-after-settling check, finite and frame checks, and TF conversion to the world frame. Simulated homographies and validity records are generated from the known Gazebo camera geometry and the measured error.
- PASS: with no calibration record the run stops before touching any object; with a record, arm1 takes its pick target from vision and two objects reach slots 3 and 4. Measured arm1 detection error 0.94 mm or less against a 1 mm budget. Coordinator unit tests: 186. Evidence: evidence/wp7/.
- Reliability: 1 of 5 runs passed first (before_timing_fixes/), with three causes: a calibration age limit in wall time against a publisher on simulated time, an arrival timeout too short for 0.2x real time, and an arrival tolerance equal to the plugin contact limit. After tightening the tolerance to 0.5 mm and lengthening the wall-clock timeouts, 3 of 3 passed. Three runs is a small sample.
- BLOCKED (decision D7, conflict C31): zone and slot state still come from ground truth, because the fixed overhead simulated cameras are occluded by the arms at HOME.
- Rerun with final parameters: two objects and all 21 fault checks PASS. The time reduction is now 48.6%, below the 50% target (WP6S). NOT_RUN: hardware, hardware frame_id fix (C20).

## Latest result: WP6S faster simulation speeds

- Simulation scales changed from transport/contact/acceleration 0.5/0.25/0.25 to 1.0/0.5/1.0 in runtime.json and config/sim/coordinator.yaml. No joint limit, model or hardware setting changed.
- PASS: two-object regression at the new speeds. Trajectory span fell from 727.6 s to 351.8 s (-51.6%), and the whole run from about 12.4 min to 6.0 min. Evidence: evidence/wp6s/.
- Limits: transport is now at the URDF velocity limit of 0.5 rad/s, and Gazebo ran at about 0.2 times real time at idle, so further gains need higher limits (user approval) or a lighter simulation.
- NOT_RUN at the new speeds: fault scenarios, the old pipeline, hardware. These scales must not be used on hardware.

## Latest result: WP6 simulation regression

- PASS through the coordinator node in Gazebo: two objects into slots 3 and 4 (record, ground truth and planning scene agree), and fault scenarios: failed release, emergency-stop heartbeat loss, latched emergency stop, cancel while holding. Coordinator unit tests: 170. Evidence: evidence/wp6/.
- FAIL, recorded as results: eight objects from an empty C stops at slot 1 before any object moves; six objects placed 4 and then found no reachable cap. Only cap_3 to cap_6 are inside arm1 downward IK (conflict C30), so the current layout cannot transfer eight objects.
- Two gaps found and fixed while preparing this work: recovery now clears leftover planning scene objects, and the next slot is checked before an object is taken from A so none is stranded in B.
- The first fault run failed because the test called start before the first heartbeat arrived, and start was correctly refused; kept as faults_run1_start_before_heartbeat/.
- NOT_RUN: vision-driven transfer, hardware. The old pipeline was not retired.

## Latest result: WP5 coordinator node

- New coordinator_node.py with /dual_arm/start, cancel, confirm, recover, status, /handoff/b_state and /dual_arm/permit, plus gateways/truth.py and demo_pick_place.launch.py. Hardware mode refuses to start until the vision gateway and safety supervisor exist.
- PASS in Gazebo with ground truth: cancel stops a moving arm and ends in FAULT, wrong and off-HOME recovery are refused, FAULT and interrupted runs survive a restart, and one full A->B->C finished with the real suction plugin (cap in slot 3 by ground truth, slots 1 and 2 prefilled per C25). Coordinator unit tests: 165. Evidence: evidence/wp5/.
- Two earlier Gazebo runs failed because of test timing, both kept: run 1 canceled while MoveIt was still planning; run 2 commanded the arm while the killed run's trajectory was still executing.
- New conflict C29, measured here: after the coordinator is killed the sent trajectory keeps running (about 22 s, 0.26 rad). WP9 must close this before any hardware motion.
- NOT_RUN: `demo_pick_place.launch.py` beyond argument parsing, eight objects, vision-driven transfer, hardware.

## Latest result: WP4 suction gateway

- New gateways/gripper.py with Gazebo and manual-token backends behind one `suction(arm, operation)` call, plus a factory that refuses auto-confirm and the Gazebo backend on hardware. The ESP32 backend stays BLOCKED until a protocol exists.
- Commands follow the plugin parser in dual_arm_gripper/policy.hpp. Every command has a timeout because the plugin drops bad commands silently, and it waits for topic discovery before publishing.
- PASS: coordinator 142 tests, including 41 new for protocol format, sequences, fault replies, timeouts, late or stale tokens, cancel and factory refusals. Two of them cross real ROS topics against a stand-in node. Evidence: evidence/wp4/.
- NOT_RUN: the real Gazebo suction plugin (WP6) and any physical suction. New conflict C28: the 1 mm plugin contact limit versus the 1.09 mm recorded simulated vision error.

## Latest result: WP3 motion gateway

- New gateways/motion.py, motion_math.py and homes.py. Non-contact moves use MoveGroup joint goals solved by CadKinematics; contact moves follow a sampled vertical line with every waypoint collision-checked. Arrival needs consecutive new joint states within the TCP limit. HOME comes from runtime.json or a measured calibration, never the SRDF.
- PASS on MoveIt mock: full A->B->C path, planning scene attach/detach, removing an absent B object, refusal of unreachable and colliding targets, refused descent leaves the arm still, cancel stops the motion. Coordinator unit tests: 101. Evidence: evidence/wp3/.
- The first mock run reported PASS for a collision check that was actually refused by IK. The test was corrected to require a collision reason and rerun; the first run is kept as 04a/05a.
- NOT_RUN: Gazebo physics and hardware. Mock joints follow commands exactly, so the micrometre errors say nothing about positioning accuracy.

## Latest result: WP2 ROS-free task logic

- New in dual_arm_coordinator: workflow/ (arm1, arm2, batch transfer, IO contract), journal.py (atomic record, file lock, configuration fingerprint) and confirmation.py (one-time expiring tokens). ZoneManager and SlotManager gained restore support.
- Each state, tool status and B owner is written to disk before the action that depends on it. A fault keeps B ownership and marks the tool unknown; recovery needs a token, both arms at HOME, B empty and a contiguous C observation.
- PASS: coordinator 81 tests with a fake IO world (cancel after every motion, suction failures, invalid vision, B conflicts, C mismatch, restart, fingerprint change, tokens, recovery); installed modules do not load rclpy. The first run had 2 failures from inconsistent exception types, fixed in code; log kept as evidence/wp2/02a_first_run_2_failed.log.
- NOT_RUN: nothing here has run against ROS, MoveIt, Gazebo or hardware. Full build and pipeline were not rerun because only the coordinator package changed and the old pipeline does not use these modules.
- New conflicts C25-C27 are in MODIFICATION_PLAN.md: slot 1 versus sequential filling, environment camera occlusion versus the C count check, and removing an absent B scene object.

## Latest result: WP1 interfaces and coordinator skeleton

- New package dual_arm_interfaces (ConfirmStep, ManualXY). dual_arm_coordinator now declares its dependencies and has a strict task configuration loader with a `check_task_config` command.
- config/sim/coordinator.yaml holds values taken from the existing pipeline and world generator. config/hardware/coordinator.yaml is an all-null template that the loader refuses.
- PASS: build of 12 packages, coordinator 27 tests (8 existing, 19 new), interface show, installed sim config accepted, hardware template refused, two-object pipeline regression (74 events). Evidence: evidence/wp1/.
- Not done: no coordinator node yet (WP5). The pipeline places into slots 3 and 4, so its PASS says nothing about slot 1.

## Latest result: WP0 baseline before the roadmap work

- Plan is now [MODIFICATION_PLAN.md](MODIFICATION_PLAN.md); handoff text is [HANDOFF_PROMPT.md](HANDOFF_PROMPT.md). No code, model or calibration changed.
- PASS at commit c7dfba3: build, coordinator 8, vision adapter 10, vision_pkg 99, cm530_hardware 29 gtests, gripper 1, five-phase mock serial, two-object Gazebo ground-truth pipeline (74 events). Evidence: evidence/roadmap_baseline/.
- Correction: the "33 unit tests" below counts 29 gtests plus 4 CTest wrappers.
- BLOCKED: zone A side and j1 direction have conflicting evidence, and j2 direction/zero is contradictory. See FUTURE_ROADMAP.md section 3. This also puts the far-side layout below in question for hardware.
- Gazebo shutdown was not retested by the original method. A process-group SIGINT exited in about 1 s with no leftovers, which does not clear the earlier FAIL.

## Latest result: far-side simulation layout (supersedes the BLOCKED note and C reach row below)

- Simulation now follows the user-stated layout: arm bases on the side far from the user, facing -Y, zone A on the arm's left. Source CAD is unchanged; the generators apply the layout. Layout itself is NOT_RUN against hardware (no photo or measurement).
- PASS: CAD pose transform (264 visuals), HOME FK/limits, HOME self/inter-arm collision, 8 coordinator tests, simulation static TF, three cameras and four views, both_arms execution, two-object A->B->C regression with Gazebo ground truth (74 events).
- FAIL: slot 1 is out of reach by downward IK at its current position, and it is the first slot in the fill order. IK is still 16/18, the same two mirrored targets as before. A +Y 10 mm move passes IK and box self-collision with 5.06 deg margin, but nothing is applied. See SLOT_ADJUSTMENT.md.
- j1 simulation direction changed to -1 by inference. Motor direction, Arm 1 j1 zero, base-to-edge distances, arm2 axis convention, hardware TF and the vision target adapter remain NOT_RUN. Eight-object and vision-driven transfer remain NOT_RUN. README screenshots in docs/images still show the old layout.

## Latest result: coordinate axis definitions

- New [COORDINATE_FRAMES.md](COORDINATE_FRAMES.md) records the OpenCV-side X/Y definitions. User stated the physical arm bases are on the side far from the user, with zone A on the left when facing the field from the base.
- The loaded CAD model puts zone A on the arm's right, so model and hardware are mirrored. Vision-to-URDF conversion is BLOCKED until that is resolved. Base-to-edge measurements and the `calibrate_caps` input method are NOT_RUN. Documentation only; no code or test changed.

## Latest result: ROS interface specification

- New [ROS_INTERFACES.md](ROS_INTERFACES.md) lists actual topics, services and actions, checked against a live headless vision_sim graph (evidence/ros_graph_vision_sim). mock, hardware and vision.launch.py graphs remain NOT_RUN; `/vision/calibration_status` content NOT_RUN.
- The task layer is not wired: no coordinator node, no client of any `/vision/*` service. Other gaps, including the hardware camera frame_id mismatch, are listed in that file. No code changed.

## Latest result: cm530_hardware on mock serial (supersedes the Hardware row below)

- New package src/cm530_hardware: protocol-5 parser, single-owner link, background scheduler, strict calibration and CM530SystemInterface plugin. New hardware.launch.py and URDF mode:=hardware.
- Tested against the unmodified v17 bridge.c, ax12.c and dynamixel.c with only the AX-12 bus simulated, including over a pseudo-terminal. 33 unit tests PASS; ASan/UBSan and TSan 20 repetitions PASS; five-phase launch integration PASS. Real UART timing, motors and the Orin remain NOT_RUN.
- Read-only by default. Motion is refused without measured calibration, verified Moving Speed, max_step_raw and a controllers_file with measured goal tolerances. Hardware starts inactive even then.
- Next hardware steps: fill calibration.yaml from real measurements (Arm 1 j1 still BLOCKED), measure the achievable loop rate, then a supervised first motion with an independent emergency stop. c-review was not run because its Workflow tool is unavailable here.

## Latest result: raw-512 zero mapping (supersedes the HOME and regression bullets below)

- User stated the physical zero is all four motors at raw 512 with the arm straight. Read as vertical, CAD q=(0,-35,-55,0) deg, so runtime.json raw_at_cad_zero j2..j4 = 631.35/699.55/512. Directions are inferred. Mapping stays simulation_assumed; hardware_use_allowed=false.
- Arm 1 j1 is UNRESOLVED: raw 90 is 123.75 deg from raw 512, yet the user reports home_A faces zone A and raw 512 faces +Y. raw_at_cad_zero 192.3 is a simulation placeholder (-30 deg). Needs motor 17 readings; see HOME_POSES.md.
- Wrist upper limit widened from 1.5 to 1.65 rad in simulation only, with user approval, so raw 825 fits. Physical clearance NOT_RUN.
- Build PASS, 8 coordinator tests PASS, HOME FK/limits PASS, HOME self/inter-arm collision PASS (home_collision.json; arm model only, world and path NOT_RUN).
- Two-object A->B->C regression PASS with revised geometry and this HOME (transfer_pipeline.json, zero512_pipeline.log): Gazebo ground truth, headless. Full eight-object, vision-driven, and PlanningScene acceptance remain NOT_RUN.
- Gazebo shutdown still FAIL: launch did not exit within 45 s of SIGINT and Gazebo needed SIGTERM.

## Current revision (supersedes historical rows below)

- User approved correcting the reversed camera support and filling C slots flush. Ten terminal components corrected, axes/TCP unchanged, 264 visuals retained, eight 25 mm pads top z=14 mm. Geometry checks PASS.
- Corrected STEP and standalone SolidWorks 2019 multi-body SLDPRT exported; SLDPRT reopened with 342 solid bodies and no warnings. Original newer-version native feature-tree assembly cannot be edited by installed SolidWorks 2019. Intermediate imported SLDASM and PackAndGo directory have unresolved portability concerns; do not deliver them alone.
- User approved simulation-assumed HOME conversion. Firmware counts preserved; simulated home_A/home_C map to base −/+30°, shoulder −10°, elbow 40°, wrist 60°. Named states built. Hardware calibration NOT_RUN, hardware use forbidden.
- Runtime scales now transport .50 / contact .25 / acceleration .25. Windows/WSL and Orin README and launch wrappers provided; Orin actual build/runtime NOT_RUN.
- Historical three-object overlapping pickup/transfer demonstration completed PASS before these geometry/HOME changes. New two-object regression is in progress; startup delay traced to ament package lookup on Windows-mounted storage. No claim of revised transfer acceptance yet.

See RESUME.md and latest evidence for ongoing results.

The complete requirements are **not yet met**. Hardware remains disabled. This ledger distinguishes recorded component evidence from end-to-end acceptance.

User decision: preserve original CAD and measure/propose the smallest platform/slot adjustment. See [SLOT_ADJUSTMENT.md](SLOT_ADJUSTMENT.md). No candidate has been applied to runtime geometry.

| Work | Current evidence and limitation |
|---|---|
| Source integration | Four requested repositories pinned in sources.lock.json; integration copies under src. |
| CAD | 264 exported components; source-pose transform check recorded PASS. Axis assignments, real joint zeros, mass/inertia and limits need physical validation. |
| ROS / MoveIt | Packages built in WSL Ubuntu 24.04 / Jazzy. Recorded mock planning and shutdown PASS. |
| Gazebo | Recorded both_arms small joint Plan & Execute and feedback PASS, three camera streams and four rendered views PASS. Overall runtime FAIL because Gazebo does not terminate cleanly. This is not a pick/place test. |
| Vision | Recorded upstream suite: 99 passed. Saved Gazebo image detection sees 8 caps in arm1 and 8 holes in arm2; environment sees 4 caps due occlusion. Live service freshness and calibrated TF authorization are not completed. |
| Calibration | Recorded 10 validity/plane-validation tests passed. Static-scene held-out homography errors measured, but all operational and hardware calibration validity remains NOT_RUN. |
| Suction | Recorded isolated Gazebo fixed-joint attachment/release physics test PASS, policy ASan/UBSan test PASS. Runtime coordinator and PlanningScene attachment synchronization not completed. |
| C reach | Original layout fails downward approach checks. −Y 7 mm and 10 mm candidates each rechecked at 248 points: discrete IK/FK PASS, but MoveIt conservative-box self-collision FAIL (49/248 and 62/248). Six selected CAD surface witnesses show no crossings; not sufficient to clear collision rejection. No world-collision or hardware acceptance. |
| A→B→C | NOT_RUN. Coordinator has preliminary zone/slot helpers and CAD IK; no complete runtime sequence. |
| Hardware | Protocol source audited. Single-port ros2_control backend, ESP32 integration and Orin deployment acceptance not completed. |

Next engineering work:

1. Resolve Gazebo shutdown failure without suppressing the failure result.
2. Validate a more accurate arm collision model against source CAD, resolve link_2/link_4 box rejection, then add a complete collision scene and validate approach/withdrawal for original reachable targets and separately named proposed layouts.
3. Acquire independent calibration observations; integrate image acquisition timestamps, TF provenance and freshness gates. Current homographies are measurements, not motion authorization.
4. Implement runtime gripper/PlanningScene synchronization, B-zone ownership and verified eight-slot coordinator. Original geometry cannot meet all-eight-slot reach acceptance as currently modelled.
5. Complete the single CM530 backend and failure tests from actual v17 protocol, ESP32 interface and Orin deployment instructions.

Recorded artifacts are under docs/evidence. Re-run affected checks after changing model, launch, world or calibration. Raw logs may describe earlier intermediate states; the JSON filenames cited here hold the latest recorded result of their respective scripts.
