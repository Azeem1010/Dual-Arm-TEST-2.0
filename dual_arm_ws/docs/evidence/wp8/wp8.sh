#!/usr/bin/env bash
# WP8 verification. Usage: wp8.sh build|mock|sanitize
cd /mnt/e/dual_arm_system/dual_arm_ws || exit 90
B=docs/evidence/wp8
export PYTHONDONTWRITEBYTECODE=1
record() { echo "$(date -Is) $1=$2" >> "$B/00_context.txt"; echo "$1=$2"; }
source /opt/ros/jazzy/setup.bash
source install/setup.bash

case "$1" in
build)
  colcon build --base-paths src --packages-select cm530_hardware dual_arm_controllers dual_arm_bringup --event-handlers console_direct+ > "$B/01_build.log" 2>&1
  record build_exit "$?"
  source install/setup.bash
  colcon test --base-paths src --packages-select cm530_hardware --event-handlers console_direct+ > "$B/02_colcon_test.log" 2>&1
  record colcon_test_exit "$?"
  colcon test-result --all --test-result-base build/cm530_hardware --verbose > "$B/03_test_result.txt" 2>&1
  record test_result_exit "$?"
  grep -E 'tests,|Summary' "$B/03_test_result.txt" | cut -c1-120
  grep -E '\[  FAILED|error:' "$B/01_build.log" "$B/02_colcon_test.log" | cut -c1-200 | head -20
  ;;
mock)
  pgrep -af 'gz sim|move_group' && { record mock_exit blocked_sim_running; exit 91; }
  timeout 1200 python3 scripts/test_cm530_mock.py > "$B/04_cm530_mock.log" 2>&1
  rc=$?
  record cm530_mock_exit "$rc"
  mkdir -p "$B/cm530_mock"
  cp docs/evidence/cm530_mock_integration.json docs/evidence/cm530_mock_*.log "$B/cm530_mock/" 2>/dev/null
  tail -10 "$B/04_cm530_mock.log" | cut -c1-200
  exit "$rc"
  ;;
sanitize)
  log="$B/05_sanitizers.log"
  : > "$log"
  overall=0
  for san in address,undefined thread; do
    dir=/tmp/dual_arm_wp8/${san%%,*}
    echo "=== sanitizer $san" >> "$log"
    cmake -S src/cm530_hardware -B "$dir" -DCM530_SANITIZE="$san" -DBUILD_TESTING=ON >> "$log" 2>&1 || overall=1
    cmake --build "$dir" --parallel 6 --target cm530_protocol_test cm530_calibration_test cm530_link_test cm530_scheduler_test >> "$log" 2>&1 || overall=1
    runner=""
    [ "$san" = thread ] && runner="setarch -R"   # the WSL address layout breaks TSan otherwise
    for test in cm530_protocol_test cm530_calibration_test cm530_link_test cm530_scheduler_test; do
      output=$(CM530_TEMPLATE="$PWD/src/cm530_hardware/config/calibration.yaml" $runner "$dir/$test" --gtest_repeat=20 --gtest_brief=1 2>&1)
      rc=$?
      reports=$(printf '%s\n' "$output" | grep -c -E 'ERROR: AddressSanitizer|WARNING: ThreadSanitizer|runtime error:|LeakSanitizer')
      echo "$test exit=$rc sanitizer_reports=$reports" | tee -a "$log"
      [ "$rc" -eq 0 ] && [ "$reports" -eq 0 ] || { overall=1; printf '%s\n' "$output" | tail -30 >> "$log"; }
    done
  done
  record sanitizers_exit "$overall"
  exit "$overall"
  ;;
*) echo "usage: wp8.sh build|mock|sanitize"; exit 2 ;;
esac
