#!/usr/bin/env bash
# WP6 verification. Usage: wp6.sh unit | wp6.sh group two|faults|batch
cd /mnt/e/dual_arm_system/dual_arm_ws || exit 90
B=docs/evidence/wp6
export PYTHONDONTWRITEBYTECODE=1
record() { echo "$(date -Is) $1=$2" >> "$B/00_context.txt"; echo "$1=$2"; }
source /opt/ros/jazzy/setup.bash
source install/setup.bash

run_group() {
  group=$1
  pgrep -af 'gz sim|move_group' && { record "${group}_exit" blocked_sim_running; return 91; }
  export AMENT_PREFIX_PATH="/opt/ros/jazzy:${AMENT_PREFIX_PATH}"
  export ROS_DOMAIN_ID=46 GZ_PARTITION=dual_arm_wp6
  D="$B/$group"
  mkdir -p "$D"
  setsid bash scripts/start_sim.sh headless > "$D/sim_launch.log" 2>&1 &
  sim=$!
  ready=0
  for i in $(seq 1 120); do
    out=$(timeout 15 ros2 control list_controllers 2>/dev/null)
    if [ "$(printf '%s\n' "$out" | grep -E 'arm[12]_controller|joint_state_broadcaster' | grep -c ' active')" -ge 3 ]; then ready=1; break; fi
    sleep 5
  done
  record "${group}_sim_ready" "$ready"
  rc=95
  if [ "$ready" -eq 1 ]; then
    sleep 10
    timeout 7000 python3 scripts/test_transfer_regression.py "$group" "/tmp/dual_arm_wp6/$group" "$D/report.json" > "$D/test.log" 2>&1
    rc=$?
  fi
  record "${group}_exit" "$rc"
  cp /tmp/dual_arm_wp6/$group/coordinator_*.log /tmp/dual_arm_wp6/$group/*.json "$D/" 2>/dev/null
  kill -INT -- "-$sim" 2>/dev/null
  for i in $(seq 1 45); do kill -0 "$sim" 2>/dev/null || break; sleep 1; done
  kill -TERM -- "-$sim" 2>/dev/null
  sleep 5
  kill -KILL -- "-$sim" 2>/dev/null
  sleep 3
  pgrep -af 'gz sim|move_group|ros2_control_node|coordinator_node' > "$D/leftover_processes.txt" || true
  record "${group}_leftover_lines" "$(wc -l < "$D/leftover_processes.txt")"
  tail -40 "$D/test.log" | cut -c1-230
  return "$rc"
}

case "$1" in
unit)
  colcon build --base-paths src --packages-select dual_arm_coordinator dual_arm_bringup --event-handlers console_direct+ > "$B/01_build.log" 2>&1
  record build_exit "$?"
  source install/setup.bash
  ( cd src/dual_arm_coordinator && timeout 280 python3 -m pytest -q -p no:cacheprovider test ) > "$B/02_coordinator_pytest.log" 2>&1
  rc=$?
  record coordinator_pytest_exit "$rc"
  tail -20 "$B/02_coordinator_pytest.log" | cut -c1-170
  exit "$rc"
  ;;
group)
  run_group "$2"
  exit $?
  ;;
*) echo "usage: wp6.sh unit | wp6.sh group two|faults|batch"; exit 2 ;;
esac
