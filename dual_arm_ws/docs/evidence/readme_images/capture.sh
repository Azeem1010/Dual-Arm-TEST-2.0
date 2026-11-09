#!/usr/bin/env bash
# Capture README screenshots from a two-object run of the coordinator demo.
cd /mnt/e/dual_arm_system/dual_arm_ws || exit 90
B=docs/evidence/readme_images
RAW=$B/raw
JOURNAL=/tmp/dual_arm_readme_journal.json
export PYTHONDONTWRITEBYTECODE=1 ROS_DOMAIN_ID=44 GZ_PARTITION=dual_arm_readme
source /opt/ros/jazzy/setup.bash
source install/setup.bash
record() { echo "$(date -Is) $1=$2" | tee -a "$B/00_context.txt"; }

if pgrep -af 'gz sim' | grep -v pgrep; then record existing_sim 1; exit 91; fi
rm -f "$JOURNAL" "$JOURNAL".lock
rm -rf "$RAW"
: > "$B/00_context.txt"
git rev-parse HEAD > "$B/commit.txt"

setsid ros2 launch dual_arm_bringup demo_pick_place.launch.py cycles:=2 "journal_path:=$JOURNAL" > "$B/01_demo_launch.log" 2>&1 &
SIM=$!
ready=1
for i in $(seq 1 120); do
  out=$(timeout 15 ros2 control list_controllers 2>/dev/null)
  if [ "$(printf '%s\n' "$out" | grep -E 'arm[12]_controller|joint_state_broadcaster' | grep -c ' active')" -ge 3 ]; then ready=0; break; fi
  sleep 5
done
record sim_ready "$ready"

if [ "$ready" = 0 ]; then
  python3 scripts/capture_readme_images.py capture "$RAW" > "$B/02_capture.log" 2>&1 &
  CAP=$!
  sleep 8
  timeout 60 ros2 run dual_arm_coordinator operator_console start > "$B/03_start.txt" 2>&1
  record start_exit "$?"
  wait "$CAP"
  record capture_exit "$?"
  timeout 30 ros2 run dual_arm_coordinator operator_console status > "$B/04_status.txt" 2>&1
  record final_state "$(grep -o '"state": "[A-Z0-9:_]*"' "$B/04_status.txt")"
  record completed "$(grep -o '"completed": [0-9]*' "$B/04_status.txt")"
fi

kill -INT -- "-$SIM" 2>/dev/null
for i in $(seq 1 45); do kill -0 "$SIM" 2>/dev/null || break; sleep 1; done
kill -TERM -- "-$SIM" 2>/dev/null
sleep 5
kill -KILL -- "-$SIM" 2>/dev/null
sleep 3
pgrep -af 'gz sim|coordinator_node|move_group|ruby' | grep -v pgrep > "$B/05_leftover_processes.txt"
record leftover_process_lines "$(wc -l < "$B/05_leftover_processes.txt")"
