#!/usr/bin/env bash
# Verify commands the documentation tells readers to run.
cd /mnt/e/dual_arm_system/dual_arm_ws || exit 90
B=docs/evidence/docs_audit
export PYTHONDONTWRITEBYTECODE=1
record() { echo "$(date -Is) $1=$2" >> "$B/00_context.txt"; echo "$1=$2"; }
source /opt/ros/jazzy/setup.bash
source install/setup.bash

stop_sim() {
  kill -INT -- "-$1" 2>/dev/null
  for i in $(seq 1 45); do kill -0 "$1" 2>/dev/null || break; sleep 1; done
  kill -TERM -- "-$1" 2>/dev/null
  sleep 5
  kill -KILL -- "-$1" 2>/dev/null
  sleep 3
}

wait_ready() {
  for i in $(seq 1 120); do
    out=$(timeout 15 ros2 control list_controllers 2>/dev/null)
    if [ "$(printf '%s\n' "$out" | grep -E 'arm[12]_controller|joint_state_broadcaster' | grep -c ' active')" -ge 3 ]; then return 0; fi
    sleep 5
  done
  return 1
}

# 1. Old README unit test command, then the replacement.
( PYTHONPATH=src/dual_arm_coordinator python3 -m unittest discover -s src/dual_arm_coordinator/test ) > "$B/01_old_readme_unittest.log" 2>&1
record old_readme_unittest_exit "$?"
tail -4 "$B/01_old_readme_unittest.log" | cut -c1-150
( cd src/dual_arm_coordinator && python3 -m pytest -q -p no:cacheprovider test ) > "$B/02_pytest.log" 2>&1
record pytest_exit "$?"
tail -1 "$B/02_pytest.log"

export AMENT_PREFIX_PATH="/opt/ros/jazzy:${AMENT_PREFIX_PATH}"
export ROS_DOMAIN_ID=43 GZ_PARTITION=dual_arm_docs_audit

# 2. The documented old pipeline at the current speeds.
pgrep -af 'gz sim|move_group' && { record blocked sim_running; exit 91; }
setsid bash scripts/start_sim.sh headless > "$B/03_pipeline_sim.log" 2>&1 &
sim=$!
wait_ready; record pipeline_sim_ready "$?"
sleep 10
timeout 1800 bash scripts/run_pipeline.sh --count 2 > "$B/04_pipeline.log" 2>&1
record run_pipeline_exit "$?"
cp docs/evidence/transfer_pipeline.json "$B/05_transfer_pipeline.json"
tail -2 "$B/04_pipeline.log" | cut -c1-140
stop_sim "$sim"

# 3. The documented coordinator demo launch.
rm -f /tmp/dual_arm_docs_journal.*
setsid ros2 launch dual_arm_bringup demo_pick_place.launch.py journal_path:=/tmp/dual_arm_docs_journal.json > "$B/06_demo_launch.log" 2>&1 &
sim=$!
wait_ready; record demo_sim_ready "$?"
sleep 15
ros2 run dual_arm_coordinator operator_console start > "$B/07_demo_start.txt" 2>&1
record demo_start_exit "$?"
result=timeout
for i in $(seq 1 180); do
  ros2 run dual_arm_coordinator operator_console status > "$B/08_demo_status.txt" 2>&1
  if grep -q '"busy": false' "$B/08_demo_status.txt" && grep -q -E '"state": "(SUCCEEDED|FAULT)"' "$B/08_demo_status.txt"; then
    result=$(grep '"state"' "$B/08_demo_status.txt" | tr -d ' ",')
    break
  fi
  sleep 5
done
record demo_result "$result"
grep -E '"(message|occupied|state|completed)"' "$B/08_demo_status.txt" | cut -c1-140
stop_sim "$sim"
pgrep -af 'gz sim|move_group|ros2_control_node|coordinator_node' > "$B/09_leftover_processes.txt" || true
record leftover_process_lines "$(wc -l < "$B/09_leftover_processes.txt")"
