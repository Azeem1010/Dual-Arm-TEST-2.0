#!/usr/bin/env bash
# Stage 3 acceptance: one cycle, stop with nothing held then recover and restart, stop while holding then reset.
# Optional argument "holding" runs only the last part on a fresh simulation, with its own log and screens.
PART=${1:-all}
SUFFIX=$([ "$PART" = all ] || echo "_$PART")
set -o pipefail
WS=/mnt/e/dual_arm_system/dual_arm_ws
OUT="$WS/docs/evidence/hmi/stage3"
STATE=$(mktemp -d /tmp/hmi_stage3_state.XXXXXX)
export FONTCONFIG_FILE="$HOME/.cache/hmi_stage0_fonts/fonts.conf"
export ROS_DOMAIN_ID=78 GZ_PARTITION=hmi_stage3
source /opt/ros/jazzy/setup.bash
source "$WS/install/setup.bash"
if pgrep -f 'gz sim' >/dev/null; then echo 'A simulation is already running; refusing to start another'; exit 3; fi
mkdir -p "$OUT/screens$SUFFIX"
cd "$STATE" || exit 1
python3 "$OUT/stage3_live_check.py" "$OUT/screens$SUFFIX" "$STATE" "$PART" 2>&1 | tee "$OUT/03_live_check$SUFFIX.log"
echo "check_rc=${PIPESTATUS[0]}" | tee -a "$OUT/03_live_check$SUFFIX.log"
cp -r "$STATE/logs" "$OUT/launch_logs$SUFFIX" 2>/dev/null
echo "leftover:"; pgrep -af 'gz sim|ros2 launch|coordinator_node|vision_node|move_group|safety_supervisor' | grep -v pgrep || echo none
