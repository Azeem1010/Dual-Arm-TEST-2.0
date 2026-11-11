#!/usr/bin/env bash
# WP5 verification. Usage: wp5.sh unit|sim
cd /mnt/e/dual_arm_system/dual_arm_ws || exit 90
B=docs/evidence/wp5
export PYTHONDONTWRITEBYTECODE=1
record() { echo "$(date -Is) $1=$2" >> "$B/00_context.txt"; echo "$1=$2"; }
source /opt/ros/jazzy/setup.bash
source install/setup.bash

case "$1" in
unit)
  colcon build --base-paths src --packages-select dual_arm_coordinator dual_arm_bringup --event-handlers console_direct+ > "$B/01_build.log" 2>&1
  record build_exit "$?"
  source install/setup.bash
  ( cd src/dual_arm_coordinator && timeout 280 python3 -m pytest -q -p no:cacheprovider test ) > "$B/02_coordinator_pytest.log" 2>&1
  rc=$?
  record coordinator_pytest_exit "$rc"
  tail -25 "$B/02_coordinator_pytest.log" | cut -c1-170
  ros2 launch dual_arm_bringup demo_pick_place.launch.py --show-args > "$B/03_launch_show_args.txt" 2>&1
  record launch_show_args_exit "$?"
  exit "$rc"
  ;;
sim)
  pgrep -af 'gz sim|move_group' && { record sim_exit blocked_sim_running; exit 91; }
  export AMENT_PREFIX_PATH="/opt/ros/jazzy:${AMENT_PREFIX_PATH}"
  export ROS_DOMAIN_ID=45 GZ_PARTITION=dual_arm_wp5
  setsid bash scripts/start_sim.sh headless > "$B/04_sim_launch.log" 2>&1 &
  sim=$!
  ready=0
  for i in $(seq 1 120); do
    out=$(timeout 15 ros2 control list_controllers 2>/dev/null)
    if [ "$(printf '%s\n' "$out" | grep -E 'arm[12]_controller|joint_state_broadcaster' | grep -c ' active')" -ge 3 ]; then ready=1; break; fi
    sleep 5
  done
  record sim_ready "$ready"
  rc=95
  if [ "$ready" -eq 1 ]; then
    sleep 10
    timeout 2400 python3 scripts/test_coordinator_sim.py /tmp/dual_arm_wp5 "$B/06_coordinator_sim.json" > "$B/05_coordinator_sim.log" 2>&1
    rc=$?
  fi
  record coordinator_sim_exit "$rc"
  mkdir -p "$B/coordinator_logs"
  cp /tmp/dual_arm_wp5/coordinator_*.log /tmp/dual_arm_wp5/journal.json "$B/coordinator_logs/" 2>/dev/null
  kill -INT -- "-$sim" 2>/dev/null
  for i in $(seq 1 45); do kill -0 "$sim" 2>/dev/null || break; sleep 1; done
  kill -TERM -- "-$sim" 2>/dev/null
  sleep 5
  kill -KILL -- "-$sim" 2>/dev/null
  sleep 2
  pgrep -af 'gz sim|move_group|ros2_control_node|coordinator_node' > "$B/07_leftover_processes.txt" || true
  record leftover_process_lines "$(wc -l < "$B/07_leftover_processes.txt")"
  tail -32 "$B/05_coordinator_sim.log" | cut -c1-210
  exit "$rc"
  ;;
*) echo "usage: wp5.sh unit|sim"; exit 2 ;;
esac
