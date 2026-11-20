# Firmware v19 / protocol 7: Present Load, COMP, GET_COMP, DIAG (2026-11-20, development PC, no hardware)

Plan step C and D from the 2026-11-19 sway diagnosis ([diag_20261119](../diag_20261119/README.md), sections 4-5): the sway starts on moves leaving HOME, where the lift carries no gravity load, and the AX-12A compliance stays at the factory values because v18 never writes it. v19 makes the compliance settable and the load visible. User decisions 2026-11-20: load inside every READ (not a separate command); the settings in their own file (not in the calibration file).

**Nothing here ran on the board. v19 is not flashed; the driver now accepts only protocol 7, so the arms cannot be started until v19 is flashed (on-site decision).**

## What changed

Firmware, new directory `third_party/CM530_ROS_BRIDGE/19 ROS to CM530 ver. dual arm/` (v18 untouched):

| Command | Reply | Notes |
|---|---|---|
| `READ,armN` | `POS,armN,p1..p4,l1..l4` | one READ of 36-41 per motor (was 36-37); load 0..1023 plus 1024 for CW |
| `COMP,armN,m1..m4,s1..s4,p1..p4` | `OK,COMP,armN` | margin 0..254, slope 2/4/8/16/32/64/128, punch 32..1023; CW = CCW; SYNC_WRITE 26 (width 4) then 48 (width 2); refused whole on any bad value; no target or torque change |
| `GET_COMP,armN` | `COMP,armN,...` | READ of 26-49 per motor; `ERR,DXL_ASYM` when CW and CCW differ |
| `DIAG,armN` | `DIAG,armN,v1..v4,t1..t4` | READ of 42-43 per motor |
| `VERSION` / boot | `VERSION,7` / `READY,7` | |

The firmware never writes compliance by itself: without COMP the motors behave as on v18.

Driver `cm530_hardware`: protocol 7 only; `raw_load` state interface (signed, CCW positive) from every READ; optional hardware parameter `motor_settings_file` (`MotorSettings`, all eight joints required, unknown keys refused). At configure it logs each arm's `GET_COMP` and `DIAG`; at activation, with a settings file, it sends COMP and compares GET_COMP before torque, refusing activation on any difference. The prototype launch passes `config/motor_settings_prototype.yaml`, which holds the factory values on every joint, so a flashed v19 first behaves like v18. Also changed: `dual_arm_cad.urdf.xacro` and `generate_cad_robot.py` (new xacro arg and `raw_load` in hardware mode only), `hardware.launch.py`, `hardware_prototype.launch.py`, `cm530_probe` (protocol 7; also reads GET_COMP and DIAG, never COMP), `scripts/test_cm530_mock.py` (checks COMP read-back and `raw_load`; `CM530_MOCK_EVIDENCE` writes a run into its own folder).

## Results

| Check | Result | Evidence |
|---|---|---|
| Firmware ARM build (arm-none-eabi-gcc 14.2, WinARM make) and `verify_firmware.py` | PASS | BIN 13860 bytes; SHA256 in the firmware's `SHA256SUMS`; warnings only the existing dxl_hal.c implicit declarations and stm32f10x_vector.c |
| Firmware C harness (new `comp` test), gnu89 `-Wall -Wextra -Werror`, plain and ASan+UBSan; LED harness | PASS | [firmware_host_tests.txt](firmware_host_tests.txt) |
| Mutation check: punch floor 32 -> 31, CCW slope comparison removed | both caught (FAIL 3 and 4 checks) | [firmware_mutation_check.txt](firmware_mutation_check.txt) |
| Python terminal self-test | PASS, 27 tests | `python manual_position_terminal.py --self-test` |
| Driver gtest (protocol 4, calibration 8, motor settings 3, link 23, scheduler 13 = 51), plain, ASan+UBSan, TSan | PASS | [driver_gtest_sanitizers.txt](driver_gtest_sanitizers.txt); TSan needs `setarch -R` on this WSL kernel (otherwise "unexpected memory mapping" before any test) |
| Mock Serial end to end (7 phases) with the v19 parser, incl. COMP 32,16,16,32 written and read back on both arms and `raw_load` on all 8 joints | PASS | [mock_integration/](mock_integration/cm530_mock_integration.json) |
| `cm530_probe` tests (in coordinator `test_tools.py`) | PASS, 33 tests | |
| Tier t1 (model, build, HOME, IK, unit tests, collision) after the xacro change | PASS, all 11 steps exit 0: coordinator 509, HMI 322, vision 104, HOME collision valid | [t1/summary.tsv](t1/summary.tsv). `generate_cad_robot.py` regenerated the xacro identical to the hand edit. The script's `git restore` of the overwritten tracked logs did not take effect from WSL; `colcon_build.log`, `home_collision.json` and `moveit_rebuild.log` were restored by hand from Windows git (copies in `t1/outputs/`) |
| Gazebo regression `two` (TEST_PLAN for URDF changes) | NOT_RUN | the change is limited to the `mode == hardware` branch of `<ros2_control>` and a new xacro argument; simulation and mock expand as before (t1 build and model checks PASS) |
| Flashing v19, COMP / GET_COMP / load / DIAG on the board | NOT_RUN | needs an on-site decision to flash |
| Effect of a stiffer slope on the sway | NOT_RUN | |

## Review notes (Trail of Bits differential-review method, done by hand)

The c-review skill needs a multi-agent workflow that this session does not have and excludes bare-metal code, so the changed C was reviewed by hand along its checklist:

- Buffers: every READ uses a local buffer of exactly the requested length (6, 24, 2); the SDK receiver already refuses a reply whose LENGTH is not length + 2, and `readBlock` checks it again before copying. 24 bytes is below `MAXNUM_RXPARAM` (60).
- Parser: the token array grew from 12 to 16 and `split` stops before writing past it; the longest valid COMP line is about 61 bytes, under the 96-byte line buffer. All 12 COMP tokens are parsed before any range check, and nothing is sent unless all are valid.
- Partial writes: if the second SYNC_WRITE (punch) fails after the first, the motors hold the new margin/slope with the old punch; the reply is `DXL_TX` and the driver reads back before torque, so this cannot pass unnoticed.
- State: COMP does not touch the target flag or torque; COMP/GET_COMP/DIAG are locked after `INIT_FAILED` like the other motor commands.
- Bus time: READ now returns 6 instead of 2 data bytes per motor, about 0.16 ms more per two-arm cycle at 1 Mbps; GET_COMP and DIAG run only at configure/activation.
- Driver: `Compliance` comparison is exact; the activation path writes before torque and returns ERROR on any failure, with torque still off. Configure now also needs GET_COMP and DIAG to succeed, so a motor that answers READ but not those reads now blocks the connection (fail closed).
- Not covered: the real AX-12A response to COMP (register widths, write timing) is only simulated; a motor power cycle restores the factory values until the next activation, which the driver cannot notice while running.

## Commands

Firmware (from the v19 directory): ARM build and `verify_firmware.py` as in its README; host tests in WSL with gcc as in [firmware_host_tests.txt](firmware_host_tests.txt). Driver: `cmake <src/cm530_hardware> -DBUILD_TESTING=ON -DCM530_SANITIZE=<address,undefined|thread>` then `ctest`. Mock Serial: `CM530_MOCK_EVIDENCE=docs/evidence/fw_v19_20261120/mock_integration python3 scripts/test_cm530_mock.py` after `colcon build --packages-select cm530_hardware dual_arm_description dual_arm_bringup`.

## On site, after flashing (proposed, not done)

1. Flash `19 ROS to CM530 ver. dual arm/CM530.hex`; on the Orin pull and rebuild.
2. Read-only: `cm530_probe` must show `VERSION,7`, HOME 256,512,512,512 and factory compliance (margin 1, slope 32, punch 32) on all 8 motors.
3. Round 1 of the sway test as planned (acceleration 0.3) with the factory file; `raw_load` is now in the bag, so the lift load's sign change on HOME-outward moves can be checked directly.
4. Then one change: `compliance_slope` 16 on both lifts and elbows in `motor_settings_prototype.yaml`, same moves, compare `sway.py` lift p2p (target <= 10 counts) and the DIAG temperatures.
