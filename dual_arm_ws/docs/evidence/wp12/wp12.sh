#!/usr/bin/env bash
# WP12 verification: rebuild the coordinator and run its unit tests.
cd /mnt/e/dual_arm_system/dual_arm_ws || exit 90
B=docs/evidence/wp12
export PYTHONDONTWRITEBYTECODE=1
record() { echo "$(date -Is) $1=$2" >> "$B/00_context.txt"; echo "$1=$2"; }
source /opt/ros/jazzy/setup.bash
source install/setup.bash
colcon build --base-paths src --packages-select dual_arm_coordinator --event-handlers console_direct+ > "$B/01_build.log" 2>&1
record build_exit "$?"
source install/setup.bash
( cd src/dual_arm_coordinator && timeout 280 python3 -m pytest -q -p no:cacheprovider test ) > "$B/02_coordinator_pytest.log" 2>&1
rc=$?
record coordinator_pytest_exit "$rc"
tail -25 "$B/02_coordinator_pytest.log" | cut -c1-180
share="$(ros2 pkg prefix dual_arm_coordinator)/share/dual_arm_coordinator/config"
ros2 run dual_arm_coordinator check_task_config "$share/sim/coordinator.yaml" > "$B/03_check_sim.txt" 2>&1
record check_sim_exit_expected_0 "$?"
ros2 run dual_arm_coordinator check_task_config "$share/hardware/coordinator.yaml" > "$B/04_check_hardware.txt" 2>&1
record check_hardware_exit_expected_1 "$?"
grep -o -E 'gripper\.[a-z0-9_.]+ is not measured' "$B/04_check_hardware.txt" | sort -u
exit "$rc"
