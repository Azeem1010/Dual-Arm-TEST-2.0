#!/usr/bin/env bash
# WP2 verification: rebuild the coordinator and run its unit tests.
cd /mnt/e/dual_arm_system/dual_arm_ws || exit 90
B=docs/evidence/wp2
export PYTHONDONTWRITEBYTECODE=1
record() { echo "$(date -Is) $1=$2" >> "$B/00_context.txt"; echo "$1=$2"; }
source /opt/ros/jazzy/setup.bash
source install/setup.bash
colcon build --base-paths src --packages-select dual_arm_coordinator --event-handlers console_direct+ > "$B/01_build.log" 2>&1
record build_exit "$?"
source install/setup.bash
( cd src/dual_arm_coordinator && python3 -m pytest -q -p no:cacheprovider test ) > "$B/02_coordinator_pytest.log" 2>&1
rc=$?
record coordinator_pytest_exit "$rc"
tail -25 "$B/02_coordinator_pytest.log" | cut -c1-170
share="$(ros2 pkg prefix dual_arm_coordinator)/share/dual_arm_coordinator/config"
ros2 run dual_arm_coordinator check_task_config "$share/sim/coordinator.yaml" > "$B/03_check_sim.txt" 2>&1
record check_sim_exit_expected_0 "$?"
ros2 run dual_arm_coordinator check_task_config "$share/hardware/coordinator.yaml" > "$B/04_check_hardware.txt" 2>&1
record check_hardware_exit_expected_1 "$?"
python3 - <<'EOF' > "$B/05_import_check.txt" 2>&1
import sys
import dual_arm_coordinator.workflow.transfer, dual_arm_coordinator.journal, dual_arm_coordinator.confirmation
print('installed package imported; rclpy loaded:', 'rclpy' in sys.modules)
EOF
cat "$B/05_import_check.txt"
exit "$rc"
