#!/usr/bin/env bash
# Mock serial only. Which startup order works with the safety supervisor latched?
cd /mnt/e/dual_arm_system/dual_arm_ws || exit 90
B=${B:-docs/evidence/safety_order}
F=$PWD/src/cm530_hardware/test/fixtures
export PYTHONDONTWRITEBYTECODE=1 ROS_DOMAIN_ID=45
source /opt/ros/jazzy/setup.bash
source install/setup.bash
: > "$B/results.txt"
say() { echo "$*" | tee -a "$B/results.txt"; }
step() { say "--- $1"; shift; timeout 40 "$@" 2>&1 | tr -d '\000' | tail -12 | tee -a "$B/results.txt"; say "exit=${PIPESTATUS[0]}"; }
controllers() { step controllers ros2 control list_controllers; step hardware ros2 control list_hardware_components; step safety ros2 topic echo --once /safety/status; }

setsid ros2 launch dual_arm_bringup hardware.launch.py use_mock_serial:=true enable_motion:=true use_moveit:=false \
  "calibration_file:=$F/calibration_mock.yaml" "controllers_file:=$F/controllers_mock.yaml" > "$B/launch.log" 2>&1 &
LAUNCH=$!
sleep 25
setsid ros2 run dual_arm_coordinator safety_supervisor > "$B/supervisor.log" 2>&1 &
SUP=$!
sleep 6
say "=== supervisor up, no heartbeat yet"
controllers
setsid ros2 topic pub -r 5 /safety/estop std_msgs/msg/Bool '{data: false}' > "$B/heartbeat.log" 2>&1 &
PUB=$!
sleep 5
say "=== order in ORIN_DEPLOYMENT: reset while hardware is inactive"
step reset_inactive ros2 service call /safety/reset std_srvs/srv/Trigger '{}'
controllers
say "=== then hardware active, reset"
step activate_hardware ros2 control set_hardware_component_state DualArmSystem active
sleep 2
step reset_active ros2 service call /safety/reset std_srvs/srv/Trigger '{}'
sleep 2
controllers
say "=== heartbeat lost"
kill -TERM -- "-$PUB" 2>/dev/null
sleep 5
controllers
say "=== latched with no heartbeat: does a manual switch_controllers get past the latch?"
step manual_switch ros2 control switch_controllers --activate arm1_controller arm2_controller
sleep 5
controllers
kill -TERM -- "-$SUP" 2>/dev/null
kill -INT -- "-$LAUNCH" 2>/dev/null
sleep 12
kill -KILL -- "-$LAUNCH" 2>/dev/null
kill -KILL -- "-$SUP" 2>/dev/null
pkill -TERM -f 'lib/cm530_hardware/cm530_mock_serial'
sleep 2
pgrep -af 'cm530_mock_serial|safety_supervisor' | grep -v pgrep | tee -a "$B/results.txt"
say done
