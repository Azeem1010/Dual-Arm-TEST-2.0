#!/usr/bin/env bash
# Capture the interfaces of the new nodes on the MoveIt mock.
cd /mnt/e/dual_arm_system/dual_arm_ws || exit 90
B=docs/evidence/wp13
source /opt/ros/jazzy/setup.bash
source install/setup.bash
export AMENT_PREFIX_PATH="/opt/ros/jazzy:${AMENT_PREFIX_PATH}"
export ROS_DOMAIN_ID=52
pgrep -af 'gz sim|move_group' && exit 91
setsid bash scripts/start_sim.sh mock > "$B/01_mock_launch.log" 2>&1 &
sim=$!
for i in $(seq 1 60); do
  out=$(timeout 15 ros2 control list_controllers 2>/dev/null)
  [ "$(printf '%s\n' "$out" | grep -E 'arm[12]_controller|joint_state_broadcaster' | grep -c ' active')" -ge 3 ] && break
  sleep 3
done
rm -f /tmp/dual_arm_wp13_journal.*
setsid ros2 run dual_arm_coordinator coordinator_node --ros-args -p journal_path:=/tmp/dual_arm_wp13_journal.json > "$B/02_coordinator.log" 2>&1 &
coordinator=$!
setsid ros2 run dual_arm_coordinator safety_supervisor > "$B/03_supervisor.log" 2>&1 &
supervisor=$!
for i in $(seq 1 40); do
  ros2 node list 2>/dev/null | grep -q dual_arm_coordinator && ros2 node list 2>/dev/null | grep -q safety_supervisor && break
  sleep 2
done
sleep 5
{ echo '=== node list'; ros2 node list; echo '=== coordinator'; ros2 node info /dual_arm_coordinator; echo '=== supervisor'; ros2 node info /safety_supervisor; } > "$B/04_node_info.txt" 2>&1
kill -KILL -- "-$coordinator" "-$supervisor" 2>/dev/null
kill -INT -- "-$sim" 2>/dev/null
for i in $(seq 1 30); do kill -0 "$sim" 2>/dev/null || break; sleep 1; done
kill -TERM -- "-$sim" 2>/dev/null
sleep 3
kill -KILL -- "-$sim" 2>/dev/null
pgrep -af 'move_group|ros2_control_node|coordinator_node|safety_supervisor' | wc -l
