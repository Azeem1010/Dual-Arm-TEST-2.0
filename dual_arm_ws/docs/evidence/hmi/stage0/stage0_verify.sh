#!/usr/bin/env bash
# Builds only the new package, runs its tests and captures the screens.
set -o pipefail
WS=/mnt/e/dual_arm_system/dual_arm_ws
OUT="$WS/docs/evidence/hmi/stage0"
export FONTCONFIG_FILE="$HOME/.cache/hmi_stage0_fonts/fonts.conf"
source /opt/ros/jazzy/setup.bash
cd "$WS" || exit 1
mkdir -p "$OUT"
echo "== build"
colcon build --base-paths src --packages-select dual_arm_hmi --event-handlers console_direct+ 2>&1 | tee "$OUT/01_build.log" | tail -5
echo "build_rc=${PIPESTATUS[0]}"
source install/setup.bash
echo "== tests"
(cd src/dual_arm_hmi && python3 -m pytest -q -p no:cacheprovider test 2>&1) | tee "$OUT/02_pytest.log" | tail -60
echo "pytest_rc=${PIPESTATUS[0]}"
echo "== screenshots"
ros2 run dual_arm_hmi hmi_screenshots --out "$OUT/screens" 2>&1 | tee "$OUT/03_screenshots.log" | tail -30
echo "shots_rc=${PIPESTATUS[0]}"
echo "== wslg window"
python3 /mnt/c/Users/39165/AppData/Local/Temp/claude/ae0e369463302a21/bc98ecf6-865b-474e-8be3-5efe92a383f3/scratchpad/wslg_window_check.py "$OUT" 2>&1 | tee "$OUT/04_wslg_window.log"
echo "wslg_rc=${PIPESTATUS[0]}"
