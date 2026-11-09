#!/usr/bin/env bash
# WP1 verification. Usage: wp1.sh build|pipeline
cd /mnt/e/dual_arm_system/dual_arm_ws || exit 90
B=docs/evidence/wp1
export PYTHONDONTWRITEBYTECODE=1
record() { echo "$(date -Is) $1=$2" >> "$B/00_context.txt"; echo "$1=$2"; }
source_ws() { source /opt/ros/jazzy/setup.bash; source install/setup.bash; }

case "$1" in
build)
  bash scripts/build.sh > "$B/01_build.log" 2>&1
  rc=$?
  record build_exit "$rc"
  grep -E '^Summary|Failed|Aborted' "$B/01_build.log" | tail -6
  [ "$rc" -eq 0 ] || exit "$rc"
  source_ws
  ( cd src/dual_arm_coordinator && python3 -m pytest -q -p no:cacheprovider test ) > "$B/02_coordinator_pytest.log" 2>&1
  record coordinator_pytest_exit "$?"
  tail -1 "$B/02_coordinator_pytest.log"
  { ros2 interface show dual_arm_interfaces/srv/ConfirmStep; echo ===; ros2 interface show dual_arm_interfaces/srv/ManualXY; } > "$B/03_interfaces.txt" 2>&1
  record interface_show_exit "$?"
  share="$(ros2 pkg prefix dual_arm_coordinator)/share/dual_arm_coordinator/config"
  ros2 run dual_arm_coordinator check_task_config "$share/sim/coordinator.yaml" > "$B/04_check_sim.txt" 2>&1
  record check_sim_exit_expected_0 "$?"
  ros2 run dual_arm_coordinator check_task_config "$share/hardware/coordinator.yaml" > "$B/05_check_hardware.txt" 2>&1
  record check_hardware_exit_expected_1 "$?"
  cut -c1-200 "$B/04_check_sim.txt" "$B/05_check_hardware.txt"
  ;;
pipeline)
  pgrep -af 'gz sim' && { record pipeline_exit blocked_gz_running; exit 91; }
  source_ws
  export AMENT_PREFIX_PATH="/opt/ros/jazzy:${AMENT_PREFIX_PATH}"
  export ROS_DOMAIN_ID=43 GZ_PARTITION=dual_arm_pipeline_demo
  setsid bash scripts/start_sim.sh headless > "$B/06_sim_launch.log" 2>&1 &
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
    timeout 1800 bash scripts/run_pipeline.sh --count 2 > "$B/07_pipeline.log" 2>&1
    rc=$?
  fi
  record pipeline_exit "$rc"
  cp docs/evidence/transfer_pipeline.json "$B/08_transfer_pipeline.json" 2>/dev/null
  kill -INT -- "-$sim" 2>/dev/null
  for i in $(seq 1 45); do kill -0 "$sim" 2>/dev/null || break; sleep 1; done
  kill -TERM -- "-$sim" 2>/dev/null
  sleep 5
  kill -KILL -- "-$sim" 2>/dev/null
  sleep 2
  pgrep -af 'gz sim|move_group|ros2_control_node' > "$B/09_leftover_processes.txt" || true
  record leftover_process_lines "$(wc -l < "$B/09_leftover_processes.txt")"
  tail -3 "$B/07_pipeline.log" | cut -c1-160
  exit "$rc"
  ;;
*) echo "usage: wp1.sh build|pipeline"; exit 2 ;;
esac
