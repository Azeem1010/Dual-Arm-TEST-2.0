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
