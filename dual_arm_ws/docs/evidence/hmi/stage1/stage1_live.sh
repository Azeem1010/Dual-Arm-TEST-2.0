#!/usr/bin/env bash
# Starts an isolated headless simulation and runs the live window check against it.
set -o pipefail
SCRATCH=/mnt/c/Users/39165/AppData/Local/Temp/claude/ae0e369463302a21/bc98ecf6-865b-474e-8be3-5efe92a383f3/scratchpad
WS=/mnt/e/dual_arm_system/dual_arm_ws
OUT="$WS/docs/evidence/hmi/stage1"
WORK=$(mktemp -d /tmp/hmi_stage1.XXXXXX)
export FONTCONFIG_FILE="$HOME/.cache/hmi_stage0_fonts/fonts.conf"
export ROS_DOMAIN_ID=78 GZ_PARTITION=hmi_stage1
source /opt/ros/jazzy/setup.bash
source "$WS/install/setup.bash"
export AMENT_PREFIX_PATH="/opt/ros/jazzy:${AMENT_PREFIX_PATH}"
if pgrep -f 'gz sim' >/dev/null; then echo 'A simulation is already running; refusing to start another'; exit 3; fi
cd "$WORK" || exit 1
mkdir -p "$OUT/screens"
setsid ros2 launch dual_arm_bringup hmi_sim.launch.py journal_path:="$WORK/journal.json" > "$OUT/03_launch.log" 2>&1 &
PID=$!
echo "launch_pid=$PID"
for attempt in $(seq 1 100); do
  ros2 control list_controllers 2>/dev/null | grep -E 'arm2_controller.*active' | grep -qv inactive && break
  sleep 3
done
sleep 10
echo "speed_without_ui:"
python3 "$SCRATCH/stage1_rtf.py" 30 | tee "$OUT/06_speed_without_ui.json"
python3 "$SCRATCH/stage1_live_check.py" "$OUT/screens" "$PID" 2>&1 | tee "$OUT/04_live_check.log"
echo "check_rc=${PIPESTATUS[0]}"
mv "$OUT/screens/04_live_check.json" "$OUT/screens/05_node_info.txt" "$OUT/" 2>/dev/null
sleep 8
kill -TERM -- "-$PID" 2>/dev/null
pkill -TERM -f 'gz sim' 2>/dev/null
sleep 3
echo "leftover:"; pgrep -af 'gz sim|hmi_sim|coordinator_node|vision_node' | grep -v pgrep || echo none
