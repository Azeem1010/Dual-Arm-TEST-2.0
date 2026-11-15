#!/usr/bin/env bash
# Taught B hand-over (2026-11-15): report, config load, coordinator and HMI tests, rebuild, then
# hardware_prototype.launch.py on Mock Serial to check the coordinator loads the taught B and
# stays up, and the t0 docs check. Moves nothing real; the driver uses the mock calibration, the
# coordinator the prototype one (as in slot_teach_20261113).
# Run in WSL from anywhere: bash docs/evidence/b_teach_20261115/run.sh [t0]
cd "$(dirname "$0")/../../.." || exit 90
source /opt/ros/jazzy/setup.bash
E=docs/evidence/b_teach_20261115
if [ "$1" = t0 ]; then
  source install/setup.bash
  bash scripts/run_checks.sh t0 $E/t0 > $E/t0.log 2>&1
  echo "t0 $?"
  exit 0
fi
colcon build --symlink-install --packages-select dual_arm_coordinator > $E/build.log 2>&1
echo "build $?"
source install/setup.bash
python3 scripts/teach_to_slots.py --from-config > $E/teach_report.txt 2>&1
echo "report $?"
(cd src/dual_arm_coordinator && python3 -m dual_arm_coordinator.task_config config/prototype/coordinator.yaml) > $E/load_prototype.txt 2>&1
echo "load $?"
(cd src/dual_arm_coordinator && python3 -m pytest -q -p no:cacheprovider test) > $E/pytest_coordinator.log 2>&1
echo "coordinator $?"
(cd src/dual_arm_hmi && QT_QPA_PLATFORM=offscreen python3 -m pytest -q -p no:cacheprovider test) > $E/pytest_hmi.log 2>&1
echo "hmi $?"

JOURNAL=$(mktemp -d)/journal.json
ros2 launch dual_arm_bringup hardware_prototype.launch.py use_mock_serial:=true \
  calibration_file:=$PWD/src/cm530_hardware/test/fixtures/calibration_mock.yaml \
  home_calibration_file:=$PWD/src/cm530_hardware/config/calibration_prototype.yaml \
  journal_path:=$JOURNAL > $E/launch.log 2>&1 &
LAUNCH=$!
for _ in $(seq 1 60); do
  grep -q 'B hand-over uses taught' $E/launch.log && break
  grep -q 'process has died' $E/launch.log && break
  sleep 2
done
sleep 10
{
  echo "== nodes"; ros2 node list 2>&1 | sort
  echo "== status"; timeout 10 ros2 topic echo --once /dual_arm/status 2>&1 | head -5
} > $E/steps.log
kill -INT $LAUNCH
# slot_teach_20261113: the camera switch kept the launch alive after Ctrl-C, so stop it after 20 s.
for _ in $(seq 1 20); do kill -0 $LAUNCH 2>/dev/null || break; sleep 1; done
if kill -0 $LAUNCH 2>/dev/null; then
  echo "launch still running after SIGINT, sending SIGTERM"
  pkill -TERM -f 'hardware_prototype.launch.py|arm_camera_switch|ros2_control_node|move_group|coordinator_node'
  sleep 3
fi
wait $LAUNCH 2>/dev/null
echo "launch stopped"
pgrep -af 'hardware_prototype|arm_camera_switch|ros2_control_node|move_group|coordinator_node' || echo "no leftover processes"
grep -n -E 'B hand-over uses taught|C slots use taught|PROTOTYPE mode|Taught B|Traceback|dual_arm_coordinator.*died' $E/launch.log
