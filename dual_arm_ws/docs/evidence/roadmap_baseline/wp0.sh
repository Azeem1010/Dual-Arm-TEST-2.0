#!/usr/bin/env bash
# WP0 baseline runner. Usage: wp0.sh build|unit|cm530|mock|pipeline
cd /mnt/e/dual_arm_system/dual_arm_ws || exit 90
B=docs/evidence/roadmap_baseline
mkdir -p "$B"
export PYTHONDONTWRITEBYTECODE=1
step=$1
record() { echo "$(date -Is) $1=$2" >> "$B/00_context.txt"; echo "$1=$2"; }
source_ws() { source /opt/ros/jazzy/setup.bash; source install/setup.bash; }

case "$step" in
build)
  { date -Is; git rev-parse HEAD; git status --short | grep -v third_party; } >> "$B/00_context.txt"
  bash scripts/build.sh > "$B/01_build.log" 2>&1
  rc=$?
  record build_exit "$rc"
  grep -E '^Summary|Failed|Aborted' "$B/01_build.log" | tail -8
  git status --short | grep -v third_party
  exit "$rc"
  ;;
unit)
  source_ws
  overall=0
  for spec in "02_coordinator:src/dual_arm_coordinator:test" "03_vision_adapter:src/dual_arm_vision_adapter:test" "04_vision_pkg:src/vision_pkg:"; do
    IFS=: read -r name dir target <<< "$spec"
    ( cd "$dir" && python3 -m pytest -q -p no:cacheprovider $target ) > "$B/${name}_pytest.log" 2>&1
    rc=$?
    record "${name}_exit" "$rc"
    tail -1 "$B/${name}_pytest.log"
    [ "$rc" -eq 0 ] || overall=$rc
  done
  exit "$overall"
  ;;
cm530)
  source_ws
  colcon test --base-paths src --packages-select cm530_hardware dual_arm_gripper --event-handlers console_direct+ > "$B/05_colcon_test.log" 2>&1
  rc=$?
  record colcon_test_exit "$rc"
  colcon test-result --all --test-result-base build/cm530_hardware --verbose > "$B/06_cm530_test_result.txt" 2>&1
  record cm530_result_exit "$?"
  colcon test-result --all --test-result-base build/dual_arm_gripper --verbose > "$B/07_gripper_test_result.txt" 2>&1
  record gripper_result_exit "$?"
  tail -3 "$B/06_cm530_test_result.txt"
  tail -3 "$B/07_gripper_test_result.txt"
  grep -E 'tests passed|Global test environment|\[  PASSED|\[  FAILED' "$B/05_colcon_test.log" | head -30
  exit "$rc"
  ;;
mock)
  pgrep -af 'gz sim' && { record mock_exit blocked_gz_running; exit 91; }
  source_ws
  timeout 900 python3 scripts/test_cm530_mock.py > "$B/08_cm530_mock.log" 2>&1
  rc=$?
  record cm530_mock_exit "$rc"
  mkdir -p "$B/cm530_mock"
  cp docs/evidence/cm530_mock_integration.json docs/evidence/cm530_mock_*.log "$B/cm530_mock/" 2>/dev/null
  tail -12 "$B/08_cm530_mock.log"
  exit "$rc"
  ;;
pipeline)
  pgrep -af 'gz sim' && { record pipeline_exit blocked_gz_running; exit 91; }
  source_ws
  export AMENT_PREFIX_PATH="/opt/ros/jazzy:${AMENT_PREFIX_PATH}"
  export ROS_DOMAIN_ID=43 GZ_PARTITION=dual_arm_pipeline_demo
  setsid bash scripts/start_sim.sh headless > "$B/09_sim_launch.log" 2>&1 &
  sim=$!
  ready=0
  for i in $(seq 1 120); do
    out=$(timeout 15 ros2 control list_controllers 2>/dev/null)
    if [ "$(printf '%s\n' "$out" | grep -E 'arm[12]_controller|joint_state_broadcaster' | grep -c ' active')" -ge 3 ]; then ready=1; break; fi
    sleep 5
  done
  record sim_ready "$ready"
  printf '%s\n' "$out" > "$B/10_controllers.txt"
  rc=95
  if [ "$ready" -eq 1 ]; then
    sleep 10
    timeout 1800 bash scripts/run_pipeline.sh --count 2 > "$B/11_pipeline.log" 2>&1
    rc=$?
  fi
  record pipeline_exit "$rc"
  cp docs/evidence/transfer_pipeline.json "$B/12_transfer_pipeline.json" 2>/dev/null
  # Known issue: launch may not exit on SIGINT. Record what shutdown actually does.
  kill -INT -- "-$sim" 2>/dev/null
  stopped=0
  for i in $(seq 1 45); do kill -0 "$sim" 2>/dev/null || { stopped=1; break; }; sleep 1; done
  record sim_sigint_stopped_within_45s "$stopped"
  kill -TERM -- "-$sim" 2>/dev/null
  sleep 5
  kill -KILL -- "-$sim" 2>/dev/null
  sleep 2
  pgrep -af 'gz sim|move_group|ros2_control_node' > "$B/13_leftover_processes.txt" || true
  record leftover_process_lines "$(wc -l < "$B/13_leftover_processes.txt")"
  tail -6 "$B/11_pipeline.log"
  exit "$rc"
  ;;
*) echo "unknown step"; exit 2 ;;
esac
