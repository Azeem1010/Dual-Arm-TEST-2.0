#!/usr/bin/env bash
# Old README command, but keeping the ROS entries in PYTHONPATH instead of replacing them.
cd "$(dirname "$0")/../../.."
OUT=docs/evidence/docs_audit
source /opt/ros/jazzy/setup.bash
source install/setup.bash
PYTHONDONTWRITEBYTECODE=1 PYTHONPATH="src/dual_arm_coordinator:${PYTHONPATH:-}" python3 -m unittest discover -s src/dual_arm_coordinator/test > "$OUT/10_unittest_sourced.log" 2>&1
echo "unittest_sourced_exit=$?" | tee -a "$OUT/00_context.txt"
tail -4 "$OUT/10_unittest_sourced.log"
