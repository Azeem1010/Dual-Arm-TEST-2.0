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
| Sway test round 1 (v19, factory compliance) | NOT_RUN as a separate test; no bag recorded |

## Next

1. Power off and check or swap the arm1 servo cables, starting with the CM-530 to first-servo cable; move each joint by hand to see whether a cable gets pulled.
2. Run again and count DXL errors; if they continue after the swap, compare with v18 (needs the v18 driver back as well).
3. Run `scripts/build.sh` (or at least `validate_model.py` and the MoveIt rebuild) for the xacro change.
