#!/usr/bin/env bash
# Mock Serial run of the prototype launch with overlap ON (2026-11-18). Moves nothing real.
# The launch reads config/prototype/coordinator.yaml at a fixed path, so this script rewrites it
# for the run (direct_transfer false, overlap block on, optionally fixed_transits removed) and
# restores the original on exit.
#   bash docs/evidence/mock_overlap_20261118/run.sh fixed   # overlap + fixed transits (lane-reserved joint lines)
#   bash docs/evidence/mock_overlap_20261118/run.sh plan    # overlap without fixed transits (MoveIt plan-only + FollowJointTrajectory)
MODE=${1:?fixed or plan}
cd /home/orin/projects/dual_arm_system/dual_arm_ws || exit 90
source /opt/ros/jazzy/setup.bash
source install/setup.bash
E=/tmp/claude-2002/-home-orin-projects-dual-arm-system/7ef838ad-1ff1-4941-b2c9-42c6651a07e8/scratchpad/mock_overlap/$MODE
mkdir -p $E
step() { echo "== $(date +%T) $*" | tee -a $E/steps.log; }
: > $E/steps.log

CFG=src/dual_arm_coordinator/config/prototype/coordinator.yaml
BACKUP=$(mktemp)
cp $CFG $BACKUP
trap 'cp $BACKUP $CFG; rm -f $BACKUP; echo "config restored" >> $E/steps.log' EXIT
python3 - "$CFG" "$MODE" <<'PY'
import sys
path, mode = sys.argv[1], sys.argv[2]
text = open(path, encoding='utf-8').read()
text = text.replace('\ndirect_transfer: true\n', '\ndirect_transfer: false\n')
text = text.replace('# overlap:\n#   clearance_m: 0.025\n#   wait_s: 240.0\n', 'overlap:\n  clearance_m: 0.025\n  wait_s: 240.0\n')
if mode == 'plan':
    text = text.replace('\nfixed_transits: true\n', '\n')
open(path, 'w', encoding='utf-8').write(text)
PY
grep -n -E '^(direct_transfer|fixed_transits|overlap|  clearance_m|  wait_s)' $CFG >> $E/steps.log
(cd src/dual_arm_coordinator && python3 -m dual_arm_coordinator.task_config config/prototype/coordinator.yaml) >> $E/steps.log 2>&1 \
  || { step 'config refused, stopping'; exit 1; }

JOURNAL=$(mktemp -d)/journal.json
step "launch with overlap on, mode $MODE (journal $JOURNAL)"
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

step 'torque on'
ros2 service call /controller_manager/set_hardware_component_state controller_manager_msgs/srv/SetHardwareComponentState \
  "{name: DualArmSystem, target_state: {id: 3, label: active}}" >> $E/steps.log 2>&1
ros2 service call /controller_manager/switch_controller controller_manager_msgs/srv/SwitchController \
  "{activate_controllers: [arm1_controller, arm2_controller], strictness: 2}" >> $E/steps.log 2>&1

for ARM in arm1 arm2; do
  step "move $ARM away from HOME through its controller"
  timeout 40 ros2 action send_goal /${ARM}_controller/follow_joint_trajectory control_msgs/action/FollowJointTrajectory \
    "{trajectory: {joint_names: [${ARM}_arm_shoulder_pan_joint, ${ARM}_arm_shoulder_lift_joint, ${ARM}_arm_elbow_flex_joint, ${ARM}_arm_wrist_flex_joint],
      points: [{positions: [0.0, -0.3, 0.6, 0.6], time_from_start: {sec: 8}}]}}" 2>&1 | grep -E 'status|error' >> $E/steps.log
done
sleep 3

step 'go_home'
ros2 service call /dual_arm/go_home dual_arm_interfaces/srv/ConfirmStep "{token: '', success: true, message: mock overlap run}" >> $E/steps.log 2>&1
for _ in $(seq 1 120); do
  grep -q -E 'Both arms are HOME|HOME stopped' $E/launch.log && break
  sleep 2
done

step 'start a task (overlap run; no camera: stops at its first zone observation)'
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

grep -n -E 'fixed joint path|planning with MoveIt|planning\b.*failed|lane|Both arms are HOME|HOME stopped|Task stopped|Task finished|TIMING SUMMARY|follow_joint_trajectory|controller code|exceeds max_step_raw|Traceback|coordinator.*died|state is invalid|did not settle|did not stop|Received new action goal|Goal reached' \
  $E/launch.log > $E/key_lines.txt
step done
