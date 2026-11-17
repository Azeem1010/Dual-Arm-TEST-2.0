# Per-step timing of a task run — 2026-11-17

User request 2026-11-17: speed up the prototype, but no Orin is at hand and few separate
measurements should be needed. So the coordinator now records where every run spends its time;
the next field run produces the numbers by itself.

## What it records

- Every workflow step (`TaskContext.step`) starts an entry; it lasts until the next step started
  by the same thread (the sequential run has one thread, an overlapped run one per arm).
  The HOME and recovery after a fault under auto resume is its own entry, `both:RESUME`.
- Inside a step the gateways mark what they wait for:

| Kind | Where |
|---|---|
| plan | MoveGroup `planning_time`, taken out of `move` |
| move | `MotionGateway._run_action` (MoveGroup or ExecuteTrajectory until its result) |
| arrive | `_confirm_arrival` (joint readings reaching the target) |
| still | `_wait_still` (`settle_s` windows) |
| check | `_require_valid` (state validity service) |
| camera_wait | env_scene `_wait_for_image` (`settle_s` + 0.5 s after the arms settled) |
| camera | env_scene scene service call |
| echo | ESP32 echo wait |
| vacuum | `vacuum_settle_s` wait |

  The rest of a step is `other`.
- Output: one `TIMING arm1:APPROACH_A 6.42 s (move 4.80, plan 1.20, ...)` log line per step,
  a `TIMING SUMMARY` at the end of the task (total, per object, totals by kind, slowest steps)
  and a CSV at `<journal folder>/timing/<YYYYmmdd_HHMMSS>.csv`; on the prototype that is
  `~/.ros/dual_arm/timing/`. A failure to write the report is logged as a warning and never
  stops the task. Nothing in the task's behaviour changes.

Not covered: vision_pick and truth observers (the prototype uses env_scene), go_home outside a task.

## Checks

| Check | Result | File |
|---|---|---|
| Coordinator unit tests (11 new in test_timing.py) | PASS 448 | coordinator_tests.txt |
| HMI unit tests | PASS 320 | hmi_tests.txt |
| flake8 on the two new files (ad hoc, not a project check) | style warnings only (docstrings, import order); existing files show the same kind, e.g. 195 for test_workflow.py + context.py | flake8.txt |
| Log lines and CSV from a real ROS run | NOT_RUN | |
