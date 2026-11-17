# Mock Serial run after the speed-up — 2026-11-18

`run.sh` starts `hardware_prototype.launch.py` on the CM-530 firmware simulator (driver:
`calibration_mock.yaml`; coordinator: prototype config and HOME), switches the hardware and both
arm controllers on, moves each arm through its controller to `[0, -0.3, 0.6, 0.6]` (away from
HOME, inside the URDF limits), calls `/dual_arm/go_home`, then `/dual_arm/start`. No camera, so the
task stops at its first zone observation. Nothing real moves.

## Run 1 — FAIL (kept in `run1_validity_timeout/`)

- Torque on, controllers active, both arms moved away: PASS.
- `go_home`: both arms HOME (PASS), but each fixed transit was refused with
  `State validity timed out` and fell back to MoveIt.
- Cause: `_require_valid_all` (speed-up step 3) sent every waypoint request at once; a HOME
  transit is about 157 points and the validity service's request queue holds about 10 (default
  QoS depth), so the rest were dropped and the wait ran into `goal_submit_s` (20 s). Contact moves
  use the same check without a fallback, so on the real arms they would have faulted.
- Timing record: `TIMING` per step, `TIMING SUMMARY` and the CSV were written: PASS.

## Fix

`_require_valid_all` keeps at most `_VALIDITY_IN_FLIGHT` = 8 requests outstanding and checks the
answers in path order (every waypoint still checked). New tests use a fake service that drops
requests beyond a queue of 10: a 130-point path is fully checked with nothing dropped, and a late
invalid point still faults. Coordinator 501 tests pass (`coordinator_tests.txt`).

## Run 2 — PASS (files in this folder)

| Step | Result |
|---|---|
| Build, launch, hardware active, controllers active | PASS |
| Arms moved away from HOME through their controllers | PASS |
| `go_home` | PASS: `arm1 home: fixed joint path, 157 points`, `arm2 home: fixed joint path, 157 points`, `Both arms are HOME`; no validity timeout |
| `start`: INITIAL_HOME (already HOME, 2-point fixed paths), then stop at the first zone observation | PASS (expected without a camera): `No new image from env after the arm settled` |
| Timing record | PASS: `TIMING SUMMARY 0 object(s), 63.09 s`, 98 % `camera_wait` (no camera); `both:RESUME` entry from auto resume |
| Shutdown | SIGINT left the launch up (known camera-switch behaviour), SIGTERM stopped it; no leftover processes |

Not covered here: anything after the first camera query (A/B/C moves, suction, contact lines,
direct transfer), overlap (off), real arms.
