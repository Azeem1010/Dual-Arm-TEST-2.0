#!/usr/bin/env bash
# Builds the interface package and runs its offline tests.
set -o pipefail
WS=/mnt/e/dual_arm_system/dual_arm_ws
OUT="$WS/docs/evidence/hmi/stage2"
export FONTCONFIG_FILE="$HOME/.cache/hmi_stage0_fonts/fonts.conf"
source /opt/ros/jazzy/setup.bash
cd "$WS" || exit 1
mkdir -p "$OUT"
colcon build --base-paths src --packages-select dual_arm_hmi --event-handlers console_direct+ 2>&1 | tee "$OUT/01_build.log" | tail -3
echo "build_rc=${PIPESTATUS[0]}"
source install/setup.bash
(cd src/dual_arm_hmi && python3 -m pytest -q -p no:cacheprovider test 2>&1) | tee "$OUT/02_pytest.log" | tail -40
echo "pytest_rc=${PIPESTATUS[0]}"
