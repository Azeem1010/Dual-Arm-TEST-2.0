# Firmware v18 / protocol 6: Moving Speed, 1 Mbps, faster prototype (2026-11-18)

No hardware. Nothing was flashed and no motor was driven.

## Why

v17 never wrote AX-12A Moving Speed (register 32). If it is 0 after power-up, each small AX step from the
driver runs at full speed and then waits for the next one, which matches the stutter and the fore-aft sway seen
on the arms (user report and videos IMG_9711/IMG_9714, 2026-11-18; the videos could not quantify it).

## What changed

- Firmware `third_party/CM530_ROS_BRIDGE/18 ROS to CM530 ver. dual arm/` (copy of v17, which is unchanged):
  every goal write is one SYNC_WRITE from address 30 with 4 bytes per motor (Goal Position, Moving Speed).
  `AX,armN,p1..p4` uses the default speed 100; `AX,armN,p1..p4,s1..s4` sets each speed (1..1023, 0 refused).
  HOME and HOLD always use 100. Host link 1 Mbps (was 57600). `READY,6` / `VERSION,6`. HOME is the board's
  2026-11-13 `GET_HOME` (256,512,512,512 for both arms), so flashing does not change HOME.
- Driver `cm530_hardware`: 1 Mbps, accepts only protocol 6, and every AX carries per-joint speeds:
  `max(1.2 x commanded velocity, remaining error / 0.25 s)`, clamped to 20..300 units (about 13..200 deg/s).
  The commanded velocity comes from successive JTC position commands in rad, not from rounded counts.
  Optional hardware parameters `speed_gain`, `speed_catch_up_ms`, `speed_min`, `speed_max`. `max_step_raw` unchanged.
- `cm530_probe`: 1 Mbps, protocol 6. Mock fixtures and tests use the v18 HOME.
- Prototype speeds (`coordinator/config/prototype/coordinator.yaml`): transport_scale 0.6 -> 1.0
  (0.3 -> 0.5 rad/s, the URDF limit), acceleration_scale 0.3 -> 0.6. URDF, joint_limits and simulation unchanged.

## Results

| Check | Result | Log |
|---|---|---|
| Firmware ARM build (arm-none-eabi-gcc 14.2) and `verify_firmware.py` | PASS | firmware_arm_build.log, firmware_verify_and_python.log |
| Firmware C harness incl. new speed test, gcc 13 -Werror, plain and ASan+UBSan | PASS | firmware_host_tests.log |
| Firmware Python terminal tests (26) | PASS | firmware_verify_and_python.log |
| colcon build cm530_hardware, dual_arm_coordinator | PASS | colcon_build.log |
| colcon test cm530_hardware (45) | PASS | colcon_test_result_cm530.log |
| cm530_hardware gtests under ASan+UBSan | PASS (calibration test needs CM530_TEMPLATE, rerun with run_asan_calibration.sh) | asan_*.log |
| coordinator pytest (508) | PASS | coordinator_pytest.log |
| `scripts/test_cm530_mock.py`, 7 phases against the v18 parser | PASS | cm530_mock_*.log, test_cm530_mock_stdout.log |
| `scripts/test_operator_tools.py` probe checks (4) and worksheet check | PASS | operator_tools.json |
| `scripts/test_operator_tools.py` manual and console phases | FAIL here: they need the T2 simulation, which was not running (KeyError on joint states). Not caused by this change; NOT_RUN in the proper setup | operator_tools_stdout.log |

The first colcon test run failed `LinkTest.ReadsFirmwareHomePresets` (still expected the v17 HOME); fixed and rerun.

## Not done

- Flashing v18, the 1 Mbps link on the board, speed control and HOME on the real arms: NOT_RUN.
- FTDI latency timer 1 ms on the Orin (udev rule in ORIN_DEPLOYMENT.md): NOT_RUN.
- Real cycle time, stutter and sway after the change: NOT_RUN.
- `docs/evidence/hardware/20261111_H1/pose_guide.py` still speaks v17 (57600) and was not changed (evidence).

## Alignment pass (same day, later)

Comments, the HMI demo counts (`fake_source.py`), the formal `calibration.yaml` `expected_home` (the board's
2026-11-13 `GET_HOME`, 256,512,512,512) and the operating docs (HARDWARE_TEST_GUIDE H0/H1/HOME, ORIN_DEPLOYMENT,
REQUIREMENTS, HOME_POSES, TEST_PLAN, RESUME, handoff prompts; notes on SOURCE_AUDIT and FUTURE_ROADMAP) now
describe v18. `run_alignment_tests.sh`: cm530_hardware 45 PASS, HMI 322 PASS, coordinator test_tools 32 PASS.
The first HMI run failed `test_hardware_motion_shows_both_counts` (still expected the old demo count 90); fixed.
Simulation HOME (`runtime.json`) still derives from the old v17 values and was not changed.
