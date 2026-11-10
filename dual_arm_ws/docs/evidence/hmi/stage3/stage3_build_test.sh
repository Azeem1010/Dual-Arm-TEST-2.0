#!/usr/bin/env bash
# Build the changed packages, run both unit suites and lint the stage 3 files.
WS=/mnt/e/dual_arm_system/dual_arm_ws
OUT="$WS/docs/evidence/hmi/stage3"
cd "$WS" || exit 1
source /opt/ros/jazzy/setup.bash
colcon build --packages-select dual_arm_coordinator dual_arm_hmi dual_arm_bringup > "$OUT/01_build.log" 2>&1; echo "build_rc=$?" >> "$OUT/01_build.log"
source install/setup.bash
export ROS_DOMAIN_ID=87 QT_QPA_PLATFORM=offscreen
{ echo '--- dual_arm_hmi'; (cd src/dual_arm_hmi && python3 -m pytest -q -p no:cacheprovider test 2>&1 | tail -3)
  echo '--- dual_arm_coordinator'; (cd src/dual_arm_coordinator && python3 -m pytest -q -p no:cacheprovider test 2>&1 | tail -3); } > "$OUT/02_pytest.log"
{ echo '--- new pyflakes (F) findings in stage 3 files'
  python3 -m flake8 --select F src/dual_arm_hmi/dual_arm_hmi/sources/ros_command.py src/dual_arm_hmi/dual_arm_hmi/sources/live_source.py \
    src/dual_arm_coordinator/dual_arm_coordinator/coordinator_node.py src/dual_arm_coordinator/dual_arm_coordinator/workflow/transfer.py \
    src/dual_arm_coordinator/dual_arm_coordinator/safety_supervisor.py src/dual_arm_coordinator/dual_arm_coordinator/safety_monitor.py \
    docs/evidence/hmi/stage3/stage3_live_check.py; echo "flake8_F_rc=$?"; } > "$OUT/02_lint.log" 2>&1
cat "$OUT/01_build.log" | tail -2; cat "$OUT/02_pytest.log" "$OUT/02_lint.log"
