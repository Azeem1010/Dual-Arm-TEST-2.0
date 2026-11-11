#!/usr/bin/env bash
# Ten start and stop cycles of the simulation through the interface, plus adoption after a crash.
set -o pipefail
SCRATCH=/mnt/c/Users/39165/AppData/Local/Temp/claude/62dced9ccf5db4ee/bc98ecf6-865b-474e-8be3-5efe92a383f3/scratchpad
WS=/mnt/e/dual_arm_system/dual_arm_ws
OUT="$WS/docs/evidence/hmi/stage2"
STATE=$(mktemp -d /tmp/hmi_stage2_state.XXXXXX)
export FONTCONFIG_FILE="$HOME/.cache/hmi_stage0_fonts/fonts.conf"
export ROS_DOMAIN_ID=79 GZ_PARTITION=hmi_stage2
source /opt/ros/jazzy/setup.bash
source "$WS/install/setup.bash"
export AMENT_PREFIX_PATH="/opt/ros/jazzy:${AMENT_PREFIX_PATH}"
if pgrep -f 'gz sim' >/dev/null; then echo 'A simulation is already running; refusing to start another'; exit 3; fi
mkdir -p "$OUT/screens"
cd "$STATE" || exit 1
python3 "$SCRATCH/stage2_live_check.py" "$OUT/screens" "$STATE" "${1:-10}" 2>&1 | tee "$OUT/03_live_check.log"
echo "check_rc=${PIPESTATUS[0]}"
cp -r "$STATE/logs" "$OUT/launch_logs" 2>/dev/null
echo "leftover:"; pgrep -af 'gz sim|ros2 launch|coordinator_node|vision_node|move_group' | grep -v pgrep || echo none
