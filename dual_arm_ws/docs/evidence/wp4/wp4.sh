#!/usr/bin/env bash
# WP4 verification: rebuild the coordinator and run its unit tests.
cd /mnt/e/dual_arm_system/dual_arm_ws || exit 90
B=docs/evidence/wp4
export PYTHONDONTWRITEBYTECODE=1
record() { echo "$(date -Is) $1=$2" >> "$B/00_context.txt"; echo "$1=$2"; }
source /opt/ros/jazzy/setup.bash
source install/setup.bash
colcon build --base-paths src --packages-select dual_arm_coordinator --event-handlers console_direct+ > "$B/01_build.log" 2>&1
record build_exit "$?"
source install/setup.bash
( cd src/dual_arm_coordinator && timeout 240 python3 -m pytest -q -p no:cacheprovider test ) > "$B/02_coordinator_pytest.log" 2>&1
rc=$?
record coordinator_pytest_exit "$rc"
tail -25 "$B/02_coordinator_pytest.log" | cut -c1-170
exit "$rc"
