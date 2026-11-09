#!/usr/bin/env bash
# Builds the changed packages and runs the offline tests.
set -o pipefail
WS=/mnt/e/dual_arm_system/dual_arm_ws
OUT="$WS/docs/evidence/hmi/stage1"
export FONTCONFIG_FILE="$HOME/.cache/hmi_stage0_fonts/fonts.conf"
source /opt/ros/jazzy/setup.bash
cd "$WS" || exit 1
mkdir -p "$OUT"
colcon build --base-paths src --packages-select vision_pkg dual_arm_bringup dual_arm_hmi --event-handlers console_direct+ 2>&1 | tee "$OUT/01_build.log" | tail -4
echo "build_rc=${PIPESTATUS[0]}"
source install/setup.bash
(cd src/dual_arm_hmi && python3 -m pytest -q -p no:cacheprovider test 2>&1) | tee "$OUT/02_pytest.log" | tail -40
echo "pytest_rc=${PIPESTATUS[0]}"
