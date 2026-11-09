#!/usr/bin/env bash
# Start headless vision_sim + calibration_status on an isolated domain, dump the graph, stop only what was started here.
OUT=/mnt/c/Users/39165/AppData/Local/Temp/claude/2ac850edad62554d/b854df76-69cf-4f41-86fd-34297761c61a/scratchpad
cd /mnt/e/dual_arm_system/dual_arm_ws
source /opt/ros/jazzy/setup.bash
source install/setup.bash
export AMENT_PREFIX_PATH="/opt/ros/jazzy:${AMENT_PREFIX_PATH}"
export ROS_DOMAIN_ID=77
export GZ_PARTITION=graph_capture_probe

if pgrep -f 'gz sim' >/dev/null; then echo 'ABORT: gz sim already running'; exit 3; fi

setsid ros2 launch dual_arm_bringup vision_sim.launch.py 'gz_args:=-r -s' >"$OUT/launch_vision_sim.log" 2>&1 &
SIM_PID=$!
setsid ros2 launch dual_arm_bringup calibration.launch.py >"$OUT/launch_calibration.log" 2>&1 &
CAL_PID=$!

stop_all() {
  kill -INT -- "-$CAL_PID" "-$SIM_PID" 2>/dev/null
  sleep 15
  kill -TERM -- "-$CAL_PID" "-$SIM_PID" 2>/dev/null
  pkill -TERM -f 'gz sim.*dual_arm_workspace' 2>/dev/null
  sleep 3
  ros2 daemon stop >/dev/null 2>&1
  echo "leftover: $(pgrep -fc 'gz sim.*dual_arm_workspace|move_group_lifetime|parameter_bridge|_vision_node')"
}
trap stop_all EXIT

READY=0
for i in $(seq 1 60); do
  sleep 5
  ACTIONS=$(timeout 20 ros2 action list 2>/dev/null)
  if grep -q '^/move_action$' <<<"$ACTIONS" && grep -q 'arm2_controller/follow_joint_trajectory' <<<"$ACTIONS"; then
    READY=1; echo "ready after ~$((i*5))s"; break
  fi
done
echo "READY=$READY"
sleep 15
python3 "$OUT/graph_dump.py" "$OUT/live_graph.json"
timeout 30 ros2 action list -t >"$OUT/live_actions.txt" 2>&1
timeout 30 ros2 control list_controllers >"$OUT/live_controllers.txt" 2>&1
timeout 15 ros2 topic echo --once --field status /vision/calibration_status >"$OUT/live_calibration_status.txt" 2>&1
echo capture-done
