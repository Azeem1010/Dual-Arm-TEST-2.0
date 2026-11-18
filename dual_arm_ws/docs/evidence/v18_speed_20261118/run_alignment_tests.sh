#!/usr/bin/env bash
# Rechecks after aligning configs, HMI demo data and docs with firmware v18.
set -o pipefail
cd "$(dirname "$0")/../../.."
OUT=docs/evidence/v18_speed_20261118
source /opt/ros/jazzy/setup.bash
colcon build --base-paths src --packages-select cm530_hardware dual_arm_hmi > "$OUT/alignment_build.log" 2>&1; echo "build exit=$?"
colcon test --base-paths src --packages-select cm530_hardware > "$OUT/alignment_test_cm530.log" 2>&1
colcon test-result --test-result-base build/cm530_hardware > "$OUT/alignment_test_result_cm530.log" 2>&1; echo "cm530 result exit=$?"; tail -1 "$OUT/alignment_test_result_cm530.log"
source install/setup.bash
(cd src/dual_arm_hmi && QT_QPA_PLATFORM=offscreen python3 -m pytest -q -p no:cacheprovider test) > "$OUT/alignment_hmi_pytest.log" 2>&1; echo "hmi exit=$?"; tail -1 "$OUT/alignment_hmi_pytest.log"
(cd src/dual_arm_coordinator && python3 -m pytest -q -p no:cacheprovider test/test_tools.py) > "$OUT/alignment_tools_pytest.log" 2>&1; echo "tools exit=$?"; tail -1 "$OUT/alignment_tools_pytest.log"
