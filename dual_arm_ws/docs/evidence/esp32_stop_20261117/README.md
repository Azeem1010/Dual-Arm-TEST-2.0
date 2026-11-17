# ESP32 suction on the stop and shutdown buttons — 2026-11-17

User decisions 2026-11-17:

- **強制停止** also turns the ESP32 suction off (`/suction_command` 0). A held cap drops. This replaces the
  earlier rule "do not send 0 automatically on a fault" for the stop button only; coordinator faults still
  leave the suction as it is.
- **關閉系統** (prototype): the interface starts the micro-ROS agent with the system and stops it with it.
  Before the launch is stopped the interface sends 0 and waits for the echo, because a board without its
  agent keeps its last relay state.

## Change

- `dual_arm_hmi/sources/ros_command.py`: `/suction_command` is a command like the services. Publishes
  `Int32 0`, answered when `/suction_status` echoes 0 (2 s). Available only while the agent bridges the board.
- `dual_arm_hmi/sources/live_source.py`: stop = trigger_stop + cancel + suction 0, then suction 0 again once
  those replied (so it is the last suction command). Shutdown = suction 0 first, then stop the launch either
  way; no echo is logged as DANGER (泵可能仍在運轉).
- `dual_arm_coordinator/gateways/gripper.py`: `guard()` right before each ESP32 publish, so a canceled task
  cannot send a command after the stop.
- `hardware_prototype.launch.py`: `esp32_port`, `microros_setup`; runs
  `ros2 run micro_ros_agent micro_ros_agent serial --dev <port> -b 115200` from the agent workspace.
- `profiles.yaml` / `launcher/profiles.py`: prototype needs `hardware.esp32_port` and an existing
  `hardware.microros_setup`. Orin `~/.ros/dual_arm_hmi/profiles.yaml` has the CP2102 by-id path.

## Results

| Check | Result | Evidence |
|---|---|---|
| HMI unit tests | PASS | hmi_tests.txt, 320 passed (7 new) |
| Coordinator unit tests | PASS | coordinator_tests_without_motion_still.txt, 384 passed |
| Coordinator with `test_motion_still.py` | FAIL | coordinator_tests.txt. That file appeared untracked at 14:03 while this work ran, written by someone else; unrelated to suction |
| RosCommander against a stand-in ESP32 (domain 77) | PASS | esp32_stub_check.py/.txt: 0 sent, echo in 41 ms; board gone → 服務不存在. The script core-dumps on its own teardown (node destroyed while spinning), after the checks |
| Agent launch part: no port / missing setup / SIGINT | PASS | agent_launch.txt, agent_only.launch.py |
| t0 docs check | PASS | t0.log, t0/ |
| Real ESP32 from the interface (stop, shutdown) | NOT_RUN | the manually started agent (pid 34234) was left running |
| Full prototype launch with the agent | NOT_RUN | |
