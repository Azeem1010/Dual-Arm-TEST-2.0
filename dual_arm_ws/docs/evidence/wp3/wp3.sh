#!/usr/bin/env bash
# WP3 verification. Usage: wp3.sh unit|mock
cd /mnt/e/dual_arm_system/dual_arm_ws || exit 90
B=docs/evidence/wp3
export PYTHONDONTWRITEBYTECODE=1
record() { echo "$(date -Is) $1=$2" >> "$B/00_context.txt"; echo "$1=$2"; }
source /opt/ros/jazzy/setup.bash
source install/setup.bash

case "$1" in
unit)
  colcon build --base-paths src --packages-select dual_arm_coordinator --event-handlers console_direct+ > "$B/01_build.log" 2>&1
  record build_exit "$?"
  source install/setup.bash
  ( cd src/dual_arm_coordinator && python3 -m pytest -q -p no:cacheprovider test ) > "$B/02_coordinator_pytest.log" 2>&1
  rc=$?
  record coordinator_pytest_exit "$rc"
  tail -20 "$B/02_coordinator_pytest.log" | cut -c1-170
  exit "$rc"
  ;;
mock)
  pgrep -af 'gz sim|move_group' && { record mock_exit blocked_sim_running; exit 91; }
  export AMENT_PREFIX_PATH="/opt/ros/jazzy:${AMENT_PREFIX_PATH}"
  export ROS_DOMAIN_ID=44
  setsid bash scripts/start_sim.sh mock > "$B/03_mock_launch.log" 2>&1 &
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
    timeout 600 python3 scripts/test_motion_gateway.py "$B/05_motion_gateway.json" > "$B/04_motion_gateway.log" 2>&1
    rc=$?
  fi
  record motion_gateway_exit "$rc"
  kill -INT -- "-$sim" 2>/dev/null
  for i in $(seq 1 30); do kill -0 "$sim" 2>/dev/null || break; sleep 1; done
  kill -TERM -- "-$sim" 2>/dev/null
  sleep 3
  kill -KILL -- "-$sim" 2>/dev/null
  sleep 1
  pgrep -af 'move_group|ros2_control_node' > "$B/06_leftover_processes.txt" || true
  record leftover_process_lines "$(wc -l < "$B/06_leftover_processes.txt")"
  tail -30 "$B/04_motion_gateway.log" | cut -c1-200
  exit "$rc"
  ;;
*) echo "usage: wp3.sh unit|mock"; exit 2 ;;
esac
