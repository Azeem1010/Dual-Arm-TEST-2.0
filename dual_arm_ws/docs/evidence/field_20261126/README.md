# Orin field run, firmware v19 on the board (2026-11-26, prototype)

Prototype results never count as calibration or H stage evidence.

Raw excerpts: `hmi_log_excerpts.txt` (grep of the 19 HMI logs `~/.ros/dual_arm_hmi/logs/20261126_*.log`), `dxl_error_counts.txt`. The full logs stay on the Orin, they are not in git. Snapshot taken at 15:31; the 15:27 run was still going.

## What was done

1. `main` fast-forwarded 1f24a25 to a06900a (firmware v19 driver), submodules updated.
2. The board already answered `VERSION,7` at 14:03 (v19 flashed on site before that; not part of this session). The installed driver was still the 11-19 v18 build, so the handshake failed: `Handshake failed: unexpected reply: VERSION,7` (14:03, 14:04).
3. `colcon build --base-paths src --parallel-workers 2`: 15 packages PASS at 14:07. `scripts/build.sh` (model validation, MoveIt rebuild) was not run, although `dual_arm_cad.urdf.xacro` changed in a06900a.
4. First start with the new driver (14:08): activation refused, arm1 out of the raw limits: shoulder_lift 329 (338..925), wrist_flex 840 (219..835). Moved by hand, then started again.
5. v19 on the board works: at configure the driver logged `compliance now: margin 1 slope 32 punch 32` and voltage 12.3-12.7 V on all 8 joints, and at activation `compliance set` with the same factory values (14:46 run).
6. arm2 hand camera rotated 180 degrees (`vision_pkg/config/cameras.yaml`, user request). Seen in the 15:23 run: `arm2_cam.image_rotate: 順時針旋轉 180°`. The orientation on screen was not confirmed by the user yet. The arm2 camera is monitor-only, no calibration.

## Results

| Run (HMI log) | Objects through VERIFY_C | How it ended |
|---|---|---|
| 14:14:57 | 4 | 14:24:01 `ERR,DXL_CORRUPT,arm1,15` |
| 14:46:43 | 5 | 14:55:22 `ERR,DXL_CORRUPT,arm1,15` |
| 15:18:26 | 0 | 15:19:13 `ERR,DXL_CORRUPT,arm1,3` |
| 15:19:56 | 0 | 15:20:27 `ERR,DXL_CORRUPT,arm1,3` |
| 15:22:02 | 1 | 15:24:08 `ERR,DXL_CORRUPT,arm1,2` |
| 15:27:27 | 1 at 15:31 | still running |

Each DXL error stops the driver (`CM-530 fault: communication stopped`), ros2_control deactivates the hardware and both arm controllers, the running trajectory ends as `fixed path failed: status 6, MoveIt code -4`, and the task goes to FAULT. That is the intended behaviour (no automatic resend, AGENTS.md).

Other stops today:

- CM-530 handshake `no reply before the deadline` at 13:52, 14:02, 14:14, 14:45 and 14:46; the next start worked each time.
- ESP32: `no suction controller reply to command 1` at 14:12 and 15:21, `the suction controller is not connected` at 14:13.

## arm1 bus

Across all 103 HMI logs since 11-13, the DXL errors are almost only on arm1 and spread over four IDs: 15 (wrist) 9, 17 (base) 6 timeouts and 1 corrupt, 3 (shoulder) 6, 2 (elbow) 2; arm2 once (ID 1). Today 5, all arm1 (15, 15, 3, 3, 2).

Judgement, not verified: errors on several IDs point at what the arm1 chain shares (cable from the CM-530 to the first arm1 servo, the arm1 port, power, or a loose daisy-chain connector) rather than one servo. Not yet known whether v19 (READ now also carries Present Load, longer replies) makes it more frequent; the counts before and after are too small to tell.

| Check | Result |
|---|---|
| v19 driver build on the Orin | PASS |
| Handshake with the v19 board | PASS (after the rebuild) |
| COMP write and GET_COMP read-back at activation, factory values | PASS |
| Transfer runs with v19 | FAIL: every run stopped on an arm1 DXL error, at most 5 objects in one run |
| arm2 camera rotated 180 degrees | PASS for the node starting; orientation on screen NOT_RUN |
| arm1 cable check or swap | NOT_RUN |
| `scripts/build.sh` model validation and MoveIt rebuild after a06900a | NOT_RUN |
| Sway round 1 (v19, factory compliance, acceleration 0.3): arm1 HOME to A | PASS as analysis, 2 segments only: lift p2p 4.7-4.8 counts (11-19: 21.9-22.7) |
| Sway round 1: arm2 HOME to B | NOT_RUN: arm2 never moved in the bag (B tolerance stop) |
| B pick tolerance at 15:59 and 16:00 | FAIL: object 10-11 mm from arm2's taught point, tolerance 10 mm; not changed |

## Sway bag, 15:57 (added 16:05)

Bag `~/bags/sway_v19_1557/` on the Orin (392 s, 147,449 messages, 117 MB mcap; only `bag_sway_v19_1557/metadata.yaml` is in git). Topics as on 11-19: `/joint_states`, `/dynamic_joint_states` (now with `raw_load`), `/rosout`, both `controller_state`. Analysis with the unchanged 11-19 scripts copied into `sway_analysis_1557/` (`extract.py`, `sway.py`; output `segments.txt`, `coord_log.txt`).

Conditions differ from the 11-19 baseline (bag 13:44) in three ways at once: firmware v19 with compliance written at activation (factory values, so the registers are the same as before), `acceleration_scale` 0.3 instead of 0.6, and different A targets.

| arm1 segment | 11-19 lift travel / p2p / ripple RMS | 11-26 lift travel / p2p / ripple RMS |
|---|---|---|
| HOME to A above | 150-241 / 21.9-22.7 / 5.2-5.6 (4 segments) | 81-90 / 4.7-4.8 / 0.75-0.81 (2 segments) |
| A to B above | 56 / 5.1 / 0.96 | 116-124 / 7.8-8.7 / 1.5-1.6 |
| B to HOME | 181 / 6.7 / 1.15 | 183 / 11.1-13.3 / 1.8-1.9 |

- The HOME-outward sway on arm1 is gone in these two moves (4 Hz ripple p2p 22 to 5 counts). Both moves took 5.3-5.4 s instead of 3.4-4.0 s, consistent with the lower acceleration.
- Not a clean comparison: the lift travel was only 81-90 counts (A targets near x -0.125 m) against 150-241, and only two segments. The cause (acceleration, travel, or both) is not separated.
- B to HOME is a little rougher than on 11-19 (lift p2p 11-13 against 6.7), still well below the old HOME-outward level.
- arm2 did not move: the task stopped before arm2 left HOME (next section), so arm2 HOME to B is not measured.
- `raw_load` is in the bag but not analysed yet.

## B pick tolerance stop, 15:59 and 16:00

arm1 put the object into B with 2.5 mm joint error (`arm1 B contact: ... xy error 2.5 mm`), but the env camera saw it at x 0.0306-0.0311 m, y about 0, which is 10-11 mm from arm2's taught B point; the prototype `b_pick_tolerance_m` is 0.01, so `_validated_b_target` raised a fault. Three automatic resumes measured the same position, the task stopped; a second start repeated it (8 measurements, 10-11 mm each). Judgement, not verified: the cap sat off-centre on arm1's cup from the A pick (offset toward C, +x), since arm1's own position error was small. The tolerance was not changed (AGENTS.md: no loosening without a user decision).

## Next

1. Power off and check or swap the arm1 servo cables, starting with the CM-530 to first-servo cable; move each joint by hand to see whether a cable gets pulled.
2. Run again and count DXL errors; if they continue after the swap, compare with v18 (needs the v18 driver back as well).
3. Record a longer sway bag with both arms moving (arm2 HOME to B) and A targets far from HOME, to separate acceleration from travel.
4. Run `scripts/build.sh` (or at least `validate_model.py` and the MoveIt rebuild) for the xacro change.
