# Field diagnosis: arm sway and missed picks (2026-11-19, Jetson Orin)

Prototype mode, CM-530 firmware v18 (`VERSION,6`, 1 Mbps), estimated calibration. None of this counts as calibration or H stage evidence.

User report: (1) the arms sometimes sway more, (2) some caps are not picked up. Asked on site: the sway happens on the way from HOME to a zone A cap, both arms rock fore and aft.

## Conclusion

| Problem | Cause (judgement) | Status |
|---|---|---|
| Sway | Servo-level oscillation at about 4 Hz, only on moves leaving HOME outward, with gravity pulling in the direction of motion. Firmware v18 writes only goal position, Moving Speed and torque, so Compliance Margin/Slope and Punch stay at the AX-12A factory defaults. The 11-18 speed increase (0.3 to 0.5 rad/s, 0.3 to 0.6 rad/s2) most likely made it larger. | Cause FAIL (sway still present). FTDI latency fix PASS as a link fix, did not remove the sway. |
| Missed picks | Position-dependent bias in zone A from the estimated camera/arm calibration. Caps are 25 mm (radius 12.5 mm, cup 9 mm), so the geometric margin is about 3.5 mm; failed picks show 2-3 mm arrival error on top of the camera/calibration bias; the single global `a_pick_offset_xy_m` cannot correct a regional bias. | Cause inferred from logs; the on-site checks are NOT_RUN. |

The two problems are independent. Less sway may make arrival slightly better but will not remove the regional bias.

## 1. Link latency (FTDI latency timer)

- Before: `/sys/bus/usb-serial/devices/ttyUSB0/latency_timer` = 16. Read-only `READ` round trip 16.0 ms median, 200 per arm (`rtt_latency16.txt`). The udev rule from ORIN_DEPLOYMENT had not been installed.
- Installed `/etc/udev/rules.d/99-ftdi-latency.rules`:
  `ACTION=="add", SUBSYSTEM=="usb-serial", DRIVER=="ftdi_sio", ATTR{latency_timer}="1"`
  and applied it with `udevadm trigger --action=add --subsystem-match=usb-serial`.
- After: latency_timer 1, round trip 2.0 ms median, max 3.0 ms, 0 bad (`rtt_latency1.txt`). `/joint_states` about 91 Hz during the run (rclpy counter; `ros2 topic hz` printed nothing under `timeout`).
- Run 13:38 with latency 1 ms (`run_1338_latency1/`: driver log, coordinator log, TIMING CSV). The user cancelled it; the user reported the sway was not more stable.

Result: link PASS, sway unchanged. The rule is kept.

## 2. Sway: bag analysis

Bag `bag_sway_baseline_1344/` (426 s, 162,163 messages, about 121 MB mcap). **The mcap is excluded from git** (`.gitignore`), and only `metadata.yaml` is committed. Scripts and outputs are in `sway_analysis_1344/`: `extract.py` (joint_states to arrays), `sway.py` (per-segment ripple: travel, max error to the smooth command, ripple RMS, peak-to-peak, velocity reversals), `series.py`, `segments.txt`, `arm1_home_to_A_series.txt`, `coord_log.txt`.

Findings:

- **Only on moves leaving HOME.** Lift (j2) ripple peak-to-peak on all 7 segments arm1 HOME to A above and arm2 HOME to B above: 20-26 counts (0.29 deg/count: about 6-7.5 deg). Other 15 segments: 3-10 counts.
- **Depends on direction, not on size.** B to HOME moves the same joints by similar amounts (lift -181 / -177 counts) at the same speed and stays smooth (p2p 6-9). Extending outward, with gravity in the direction of motion, oscillates.
- **Seen by the encoders.** The oscillation is in `/joint_states`, so the servo itself moves; it is not gear backlash or structural bending invisible to the encoder.
- About 4 Hz; amplitude grows as the lift moves forward. The pan joint steps and lags about 20 counts with the same period.
- Example rows (`segments.txt`): arm1 to A, lift p2p 21.9 / 22.2, velocity reversals 27 / 23; arm2 B above, lift p2p 21.6, reversals 29; arm1 home, lift p2p 6.7, reversals 2.

Mechanism (judgement, not measured): the driver sets each AX Moving Speed to `max(1.2 x |v_cmd|, |error| / 0.25 s) / 2.27`, clamped 20..300. On the outward move gravity drives the joint past the speed-limited profile, the servo brakes with its default compliance (slope 32, margin 1, punch 32), overshoots back, and repeats.

Web reports with the same behaviour (heavy-loaded AX-12 with speed limit oscillating; fixed with compliance slope/punch): forum.robosavvy.com threads f=5 t=975 and t=7992; ROBOTIS e-Manual AX-12A control table (compliance and punch are RAM, reset at power-up).

## 3. Missed picks: zone A positions

`zone_a_picks_20261118_19.txt` (`picks.py` over the 11-18 and 11-19 coordinator logs, 71 picks): camera x, y; arrival z; arrival xy error; whether descent correction ran; joint error; result.

| Region (zone A, mm) | OK | FAIL |
|---|---|---|
| y < -40 | 5 | 8 |
| x < -185 | 3 | 6 |
| elsewhere | about 31 | 6 |

- The camera repeats the same cap within 0.7 mm (for example x -143.5..-144.0, y -50.2..-50.9, 4 attempts, all FAIL), so this is a fixed regional bias, not noise.
- Cup radius 9 mm (`cup_radius_m 0.009`). The logged runs used `cap_radius_m 0.01` (20 mm caps); the real caps are 25 mm and the prototype config was changed to 0.0125 at 16:02, after these runs. Correction (2026-11-19): the analysis first stated a 1 mm margin from the old value; with 25 mm caps the geometric margin is about 3.5 mm. Failed picks show 2-3 mm arrival xy error from the joints alone, before the camera/calibration bias, so a regional bias of a few mm can still use up the margin.
- Current correction: one global `a_pick_offset_xy_m [0.002, 0.0]`; a regional bias needs a region-based offset or recalibration.
- Not excluded: a bad cap at a specific spot (the 11-18 cap at x -125, y 0 failed 3 times in the middle region).

The 25 mm `cap_diameter_mm` in env_scene and the 491 mm2 comment in env_vision were changed together with the coordinator value (16:02); effect on the camera area limits NOT_RUN.

Also seen today: arm1 bus DXL_CORRUPT (ID 15, 3) and DXL_TIMEOUT (ID 17) earlier, none in the later runs; one ESP32 "no suction controller reply" stop.

## Next steps (proposed, none done)

1. Speed back to 0.3 / 0.3: `transport_scale` 1.0 to 0.6, `acceleration_scale` 0.6 to 0.3 in `dual_arm_coordinator/config/prototype/coordinator.yaml`, rebuild, record one bag and compare the HOME-outward segments with `sway.py`. Config only.
2. Firmware v19 (new directory in CM530_ROS_BRIDGE): write configurable Compliance Slope/Margin and Punch at torque-on, compare a few values on site. Needs an on-site decision to flash.
3. Raise `speed_gain` (driver param, not set in the xacro; needs `dual_arm_cad.urdf.xacro` and `scripts/generate_cad_robot.py`). Uncertain effect.
4. Picks on site: swap a failing-region cap with one that succeeds in the middle; lower the cup at (-143, -50) mm and measure the offset of the cup centre from the cap centre (size and direction). Then a region-based offset or recalibration.

## 4. Gravity torque along arm1 HOME to A above (added 2026-11-19, development PC, no hardware)

Files: `gravity_torque/gravity.py` (planar model, run with `py -3 gravity.py` or `python3`), output `gravity_torque/gravity_home_to_A.txt`.

- Model: the URDF `dual_arm_cad` joint offsets (lift to elbow 0.0536/0.0766 m, elbow to wrist 0.0935 m, wrist to TCP 0.071 m). The URDF masses are placeholders (0.08 kg at each joint origin), so the masses are estimates: AX-12A 54.6 g at the elbow and wrist axes, brackets and suction end in three sets (light / nominal / heavy). Suction tube and cables are not modelled.
- HOME (raw 512 on every joint; lift -119.35, elbow -187.55, wrist 0 counts from the calibration zero) is the arm **straight up**: gravity torque on lift and elbow is zero there.
- Path: lift -119 to +112, elbow -188 to -96 counts (from `arm1_home_to_A_series.txt`), wrist 0 to 290 counts (tool pointing down at the end; matches the 290 count wrist travel in `segments.txt`).
- Result: the gravity torque points in the direction of motion on the whole outward path for all three mass sets. Lift 0 to +0.20..+0.30 N m at A above (13-20 % of the 1.5 N m stall torque; ROBOTIS advises at most 1/5), elbow up to +0.08..+0.13 N m. Going back to HOME, gravity works against the motion. The sign comes from the geometry; the size is only as good as the mass estimate (about +/-30 %).

What this changes in section 2:

- It supports "gravity in the direction of motion" for HOME-outward moves. In `arm1_home_to_A_series.txt` the first part (about 0-2.1 s, arm near vertical, small torque) shows the lift lagging and stalling, then catching up; the later part (larger torque) swings about +/-10 counts with overshoot, and after the stop the lift rests about 3 counts beyond the goal in the gravity direction.
- On the way out the motor load changes from driving (against gear friction) to braking (against gravity), so the gears change flank inside the move. The AX-12A potentiometer is on the output shaft, so backlash IS visible in `/joint_states`; the statement in section 2 that the encoder view excludes backlash does not hold. Judgement, not measured: Present Load is not read by v18.
- Catch-up jumps reach about 200-270 counts/s (for example 1.63 to 1.66 s), 2-3 times the Moving Speed of about 42 units (about 95 counts/s): gravity moves the joint faster than the speed limit.
- Ideas, none done: in v19, try a stiffer Compliance Slope (16) first and keep Punch 32 (the load is braking, not stalling); read Present Load (40-41) to see where the flank changes. A HOME tilted a few degrees forward would keep the lift loaded on one flank from the start; HOME is used by the firmware HOME command and `expected_home`, so this needs a user decision.

## 5. arm2 gravity torque and the measured sway (added 2026-11-20, development PC, no hardware)

Files: `gravity_torque/gravity_arm2.py` (same planar model; arm2 uses the same lift/elbow/wrist zeros), output `gravity_torque/gravity_arm2.txt`. B contact and C release poses are the taught counts in `config/prototype/coordinator.yaml`; each "above" pose raises the wrist by approach_z - contact/release_z with the tool down. Model B above is raw (668, 760, 730); the travel in `segments.txt` (144 / 253 / 217 from HOME) gives about (656, 765, 729).

| arm2 move | lift gravity load (nominal) | lift travel / p2p in `segments.txt` |
|---|---|---|
| HOME -> B above | 0 -> +0.19 N m, assists the motion, **starts at zero load** | 144 / 21.0-21.7 (sways like arm1) |
| B above -> C6 / C7 / C8 above | +0.19 -> +0.21..0.25, assists, starts loaded | 38 / 4.1, 76 / 4.5, 137 / 10.3 |
| B above -> C1..C4 above | +0.19 -> +0.11..0.17, opposes | not in the 13:44 bag |
| C above -> HOME | +0.21..0.25 -> 0, opposes | 181-277 / 8.4-12.0 |

No path crosses zero gravity torque in the middle of a move; zero is only at HOME. All three mass sets give the same labels.

What this changes in section 4: "gravity in the direction of motion" alone does not cause the sway, because B above -> C6/C7 is also an assisting move and stays at 4-5 counts. The moves that sway (arm1 HOME -> A, arm2 HOME -> B) are the ones that **start from HOME, where the lift carries no gravity load**. Holding a tilted arm already rests the gears on the flank that also brakes an assisting move, so a move from a loaded rest does not change flank; a move from HOME does, once the tilt builds up load. Judgement, not measured. It points the same way as the earlier ideas: a forward-tilted ready pose (lift loaded before the transport starts) or a stiffer Compliance Slope. B above -> C8 (10.3 counts, the largest lift travel after HOME moves) is the borderline case.

## 6. Failing coordinator test `Homes::test_measured_calibration_is_converted` (2026-11-20)

Command (WSL, ROS Jazzy and `install/setup.bash` sourced): a temporary detached worktree per commit, then `python3 -m pytest -q -p no:cacheprovider test/test_motion_math.py::Homes` in `src/dual_arm_coordinator`.

| commit | result |
|---|---|
| 6e5cf20 (acceleration 0.3) | FAIL: 1 failed, 6 passed |
| 926232c | FAIL: 1 failed, 6 passed |
| 1f24a25 (align configs with firmware v18) | FAIL: 1 failed, 6 passed |
| dcba30e (parent of 1f24a25) | PASS: 7 passed |

Cause: 1f24a25 changed `expected_home` in `cm530_hardware/config/calibration.yaml` to the v18 HOME 256/512/512/512; the test copies that file and still expects the v17 HOME (90/590, 567, 712, 825) at line 186-187. The test is stale, the code is not wrong, and the acceleration change in 6e5cf20 is unrelated.

Fixed 2026-11-20 (user decision): the test now expects 256/512/512/512 on both arms. `python3 -m pytest -q -p no:cacheprovider test` in `src/dual_arm_coordinator` (WSL, same environment): PASS, 508 passed in 58.14 s.

## 7. Follow-up: firmware v19 built (2026-11-20, no hardware)

Next step 2 above and the v19 ideas of section 4 are implemented but not flashed: [fw_v19_20261120](../fw_v19_20261120/README.md). READ now carries Present Load (published as `raw_load`), COMP/GET_COMP set and read back compliance and punch at every activation from `cm530_hardware/config/motor_settings_prototype.yaml` (factory values for now), DIAG reads voltage and temperature. The driver accepts only v19, so the board must be flashed before the next run on the arms.
