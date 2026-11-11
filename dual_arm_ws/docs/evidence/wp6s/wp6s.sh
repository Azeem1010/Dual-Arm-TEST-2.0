#!/usr/bin/env bash
# WP6S verification: faster simulation speeds. Usage: wp6s.sh unit|two
cd /mnt/e/dual_arm_system/dual_arm_ws || exit 90
B=docs/evidence/wp6s
export PYTHONDONTWRITEBYTECODE=1
record() { echo "$(date -Is) $1=$2" >> "$B/00_context.txt"; echo "$1=$2"; }
source /opt/ros/jazzy/setup.bash
source install/setup.bash

case "$1" in
unit)
  colcon build --base-paths src --packages-select dual_arm_coordinator --event-handlers console_direct+ > "$B/01_build.log" 2>&1
  record build_exit "$?"
  source install/setup.bash
  ( cd src/dual_arm_coordinator && timeout 280 python3 -m pytest -q -p no:cacheprovider test ) > "$B/02_coordinator_pytest.log" 2>&1
  rc=$?
  record coordinator_pytest_exit "$rc"
  tail -3 "$B/02_coordinator_pytest.log" | cut -c1-170
  exit "$rc"
  ;;
two)
  pgrep -af 'gz sim|move_group' && { record two_exit blocked_sim_running; exit 91; }
  export AMENT_PREFIX_PATH="/opt/ros/jazzy:${AMENT_PREFIX_PATH}"
  export ROS_DOMAIN_ID=47 GZ_PARTITION=dual_arm_wp6s
  D="$B/two"
  mkdir -p "$D"
  setsid bash scripts/start_sim.sh headless > "$D/sim_launch.log" 2>&1 &
  sim=$!
  ready=0
  for i in $(seq 1 120); do
    out=$(timeout 15 ros2 control list_controllers 2>/dev/null)
    if [ "$(printf '%s\n' "$out" | grep -E 'arm[12]_controller|joint_state_broadcaster' | grep -c ' active')" -ge 3 ]; then ready=1; break; fi
    sleep 5
  done
  record two_sim_ready "$ready"
  # Real-time factor at idle: simulated seconds per wall-clock second.
  s1=$(timeout 20 ros2 topic echo --once --field clock.sec /clock 2>/dev/null | grep -m1 -E '^[0-9]+$')
  t1=$(date +%s)
  sleep 30
  s2=$(timeout 20 ros2 topic echo --once --field clock.sec /clock 2>/dev/null | grep -m1 -E '^[0-9]+$')
  t2=$(date +%s)
  record idle_sim_seconds "$((s2 - s1))"
  record idle_wall_seconds "$((t2 - t1))"
  rc=95
  if [ "$ready" -eq 1 ]; then
    started=$(date +%s)
    timeout 3000 python3 scripts/test_transfer_regression.py two /tmp/dual_arm_wp6s/two "$D/report.json" > "$D/test.log" 2>&1
    rc=$?
    record two_run_wall_seconds "$(( $(date +%s) - started ))"
  fi
  record two_exit "$rc"
  cp /tmp/dual_arm_wp6s/two/coordinator_*.log /tmp/dual_arm_wp6s/two/*.json "$D/" 2>/dev/null
  kill -INT -- "-$sim" 2>/dev/null
  for i in $(seq 1 45); do kill -0 "$sim" 2>/dev/null || break; sleep 1; done
  kill -TERM -- "-$sim" 2>/dev/null
  sleep 5
  kill -KILL -- "-$sim" 2>/dev/null
  sleep 3
  pgrep -af 'gz sim|move_group|ros2_control_node|coordinator_node' > "$D/leftover_processes.txt" || true
  record two_leftover_lines "$(wc -l < "$D/leftover_processes.txt")"
  tail -12 "$D/test.log" | cut -c1-230
  python3 docs/evidence/wp6/analyze.py ../wp6s/two 2>&1 | tail -3 | tee "$B/03_timing.txt"
  exit "$rc"
  ;;
*) echo "usage: wp6s.sh unit|two"; exit 2 ;;
esac
