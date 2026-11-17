#!/usr/bin/env bash
# Mock Serial run of the prototype launch after the 2026-11-17 speed-up (direct transfer, timing,
# shorter waits, fixed transits, overlap merged but off). Moves nothing real: the driver talks to
# the CM-530 firmware simulator (calibration_mock.yaml), the coordinator uses the prototype config
# and HOME. No camera, so a started task stops at its first zone observation; HOME moves and the
# timing record still run.
# Run in WSL: bash docs/evidence/mock_run_20261118/run.sh
cd "$(dirname "$0")/../../.." || exit 90
source /opt/ros/jazzy/setup.bash
E=docs/evidence/mock_run_20261118
step() { echo "== $(date +%T) $*" | tee -a $E/steps.log; }
: > $E/steps.log

step build
colcon build --symlink-install --packages-select dual_arm_coordinator dual_arm_hmi > $E/build.log 2>&1
echo "build exit $?" | tee -a $E/steps.log
source install/setup.bash

pgrep -af 'ros2_control_node|move_group|coordinator_node|cm530_mock' >> $E/steps.log && step 'WARNING: leftover processes before start'

JOURNAL=$(mktemp -d)/journal.json
step "launch (journal $JOURNAL)"
ros2 launch dual_arm_bringup hardware_prototype.launch.py use_mock_serial:=true \
  calibration_file:=$PWD/src/cm530_hardware/test/fixtures/calibration_mock.yaml \
  home_calibration_file:=$PWD/src/cm530_hardware/config/calibration_prototype.yaml \
  journal_path:=$JOURNAL > $E/launch.log 2>&1 &
LAUNCH=$!
for _ in $(seq 1 90); do
  grep -q 'PROTOTYPE mode' $E/launch.log && ros2 service list 2>/dev/null | grep -q /dual_arm/go_home && break
  grep -q 'process has died' $E/launch.log && break
  sleep 2
done
sleep 8
ros2 node list 2>&1 | sort > $E/nodes.txt

step 'torque on: hardware component active, then arm controllers'
ros2 service call /controller_manager/set_hardware_component_state controller_manager_msgs/srv/SetHardwareComponentState \
  "{name: DualArmSystem, target_state: {id: 3, label: active}}" >> $E/steps.log 2>&1
ros2 service call /controller_manager/switch_controller controller_manager_msgs/srv/SwitchController \
  "{activate_controllers: [arm1_controller, arm2_controller], strictness: 2}" >> $E/steps.log 2>&1
ros2 control list_controllers >> $E/steps.log 2>&1

step 'joints at start (firmware HOME on the simulator)'
timeout 10 ros2 topic echo --once /joint_states sensor_msgs/msg/JointState --field position >> $E/steps.log 2>&1

# Move both arms to a pose inside the URDF limits and away from the coordinator HOME, straight
# through each controller, so the HOME below is a real move that the fixed transit has to run.
for ARM in arm1 arm2; do
  step "move $ARM away from HOME through its controller"
  timeout 40 ros2 action send_goal /${ARM}_controller/follow_joint_trajectory control_msgs/action/FollowJointTrajectory \
    "{trajectory: {joint_names: [${ARM}_arm_shoulder_pan_joint, ${ARM}_arm_shoulder_lift_joint, ${ARM}_arm_elbow_flex_joint, ${ARM}_arm_wrist_flex_joint],
      points: [{positions: [0.0, -0.3, 0.6, 0.6], time_from_start: {sec: 8}}]}}" >> $E/steps.log 2>&1
done
sleep 3

step 'go_home (operator confirmed the tools and zone B are clear)'
ros2 service call /dual_arm/go_home dual_arm_interfaces/srv/ConfirmStep "{token: '', success: true, message: mock run}" >> $E/steps.log 2>&1
for _ in $(seq 1 90); do
  grep -q -E 'Both arms are HOME|HOME stopped' $E/launch.log && break
  sleep 2
done

step 'start a task (no camera: it should stop at its first zone observation, after INITIAL_HOME)'
ros2 service call /dual_arm/start std_srvs/srv/Trigger >> $E/steps.log 2>&1
for _ in $(seq 1 90); do
  grep -q -E 'Task stopped|Task finished' $E/launch.log && break
  sleep 2
done
sleep 3

step 'stop launch'
kill -INT $LAUNCH
for _ in $(seq 1 20); do kill -0 $LAUNCH 2>/dev/null || break; sleep 1; done
if kill -0 $LAUNCH 2>/dev/null; then
  step 'launch still running after SIGINT, sending SIGTERM'
  pkill -TERM -f 'hardware_prototype.launch.py|arm_camera_switch|ros2_control_node|move_group|coordinator_node|cm530_mock|env_scene|usb_cam'
  sleep 3
fi
wait $LAUNCH 2>/dev/null
pgrep -af 'ros2_control_node|move_group|coordinator_node|cm530_mock' >> $E/steps.log || echo 'no leftover processes' >> $E/steps.log

grep -n -E 'fixed joint path|planning with MoveIt|Both arms are HOME|HOME stopped|Task stopped|Task finished|TIMING|exceeds max_step_raw|Traceback|coordinator.*died|state is invalid|did not settle|did not stop' \
  $E/launch.log > $E/key_lines.txt
step done
