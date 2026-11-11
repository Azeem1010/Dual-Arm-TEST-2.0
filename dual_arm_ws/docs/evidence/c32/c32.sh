#!/usr/bin/env bash
# C32 verification: build, unit tests, MoveIt mock scenarios, mock serial. No hardware.
cd /mnt/e/dual_arm_system/dual_arm_ws || exit 90
B=docs/evidence/c32
export PYTHONDONTWRITEBYTECODE=1
: > "$B/00_context.txt"
record() { echo "$(date -Is) $1=$2" | tee -a "$B/00_context.txt"; }
source /opt/ros/jazzy/setup.bash
source install/setup.bash

pgrep -af 'gz sim|move_group|safety_supervisor' | grep -v pgrep && { record blocked sim_running; exit 91; }
git rev-parse HEAD > "$B/commit.txt"

colcon build --base-paths src --packages-select dual_arm_coordinator --event-handlers console_direct+ > "$B/01_build.log" 2>&1
record build_exit "$?"
source install/setup.bash

( cd src/dual_arm_coordinator && timeout 280 python3 -m pytest -q -p no:cacheprovider test ) > "$B/02_pytest.log" 2>&1
record pytest_exit "$?"
tail -1 "$B/02_pytest.log"

: > "$B/03_repeat_ros_test.log"
passes=0
for i in 1 2 3 4 5; do
  ( cd src/dual_arm_coordinator && timeout 120 python3 -m pytest -q -p no:cacheprovider test/test_safety_ros.py ) >> "$B/03_repeat_ros_test.log" 2>&1 && passes=$((passes + 1))
done
record ros_test_passes_of_5 "$passes"

export AMENT_PREFIX_PATH="/opt/ros/jazzy:${AMENT_PREFIX_PATH}"
export ROS_DOMAIN_ID=49
setsid bash scripts/start_sim.sh mock > "$B/04_mock_launch.log" 2>&1 &
sim=$!
ready=0
for i in $(seq 1 60); do
  out=$(timeout 15 ros2 control list_controllers 2>/dev/null)
  if [ "$(printf '%s\n' "$out" | grep -E 'arm[12]_controller|joint_state_broadcaster' | grep -c ' active')" -ge 3 ]; then ready=1; break; fi
  sleep 3
done
record mock_ready "$ready"
rc=95
if [ "$ready" -eq 1 ]; then
  sleep 5
  timeout 900 python3 scripts/test_safety_supervisor.py /tmp/dual_arm_c32 "$B/06_safety.json" > "$B/05_safety.log" 2>&1
  rc=$?
fi
record moveit_mock_exit "$rc"
mkdir -p "$B/node_logs"
cp /tmp/dual_arm_c32/*.log "$B/node_logs/" 2>/dev/null
kill -INT -- "-$sim" 2>/dev/null
for i in $(seq 1 30); do kill -0 "$sim" 2>/dev/null || break; sleep 1; done
kill -TERM -- "-$sim" 2>/dev/null
sleep 3
kill -KILL -- "-$sim" 2>/dev/null
sleep 2

mkdir -p "$B/mock_serial"
B="$B/mock_serial" bash docs/evidence/safety_order/run.sh > /dev/null 2>&1
record mock_serial_run_exit "$?"
pgrep -af 'move_group|ros2_control_node|coordinator_node|safety_supervisor|cm530_mock_serial' | grep -v pgrep > "$B/07_leftover_processes.txt"
record leftover_process_lines "$(wc -l < "$B/07_leftover_processes.txt")"
