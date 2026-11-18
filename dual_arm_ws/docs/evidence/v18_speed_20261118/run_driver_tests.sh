#!/usr/bin/env bash
# Driver and coordinator checks for firmware v18 / protocol 6 (no hardware).
set -o pipefail
cd "$(dirname "$0")/../../.."
OUT=docs/evidence/v18_speed_20261118
source /opt/ros/jazzy/setup.bash
echo "== colcon build cm530_hardware dual_arm_coordinator"
colcon build --base-paths src --packages-select cm530_hardware dual_arm_coordinator \
  --event-handlers console_direct+ > "$OUT/colcon_build.log" 2>&1; echo "build exit=$?"
echo "== colcon test cm530_hardware"
colcon test --base-paths src --packages-select cm530_hardware --event-handlers console_direct+ \
  > "$OUT/colcon_test_cm530.log" 2>&1; echo "test exit=$?"
colcon test-result --test-result-base build/cm530_hardware --verbose > "$OUT/colcon_test_result_cm530.log" 2>&1; echo "test-result exit=$?"
tail -3 "$OUT/colcon_test_result_cm530.log"
echo "== sanitizer build of cm530_hardware (separate build base)"
colcon --log-base /tmp/v18_asan_log build --base-paths src --packages-select cm530_hardware \
  --build-base /tmp/v18_asan_build --install-base /tmp/v18_asan_install \
  --cmake-args -DCMAKE_BUILD_TYPE=Debug "-DCMAKE_CXX_FLAGS=-fsanitize=address,undefined -fno-omit-frame-pointer" \
  "-DCMAKE_C_FLAGS=-fsanitize=address,undefined -fno-omit-frame-pointer" \
  "-DCMAKE_EXE_LINKER_FLAGS=-fsanitize=address,undefined" "-DCMAKE_SHARED_LINKER_FLAGS=-fsanitize=address,undefined" \
  > "$OUT/asan_build.log" 2>&1; echo "asan build exit=$?"
for t in /tmp/v18_asan_build/cm530_hardware/cm530_*_test; do
  [ -x "$t" ] || continue
  echo "-- $t"; UBSAN_OPTIONS=halt_on_error=1:print_stacktrace=1 "$t" > "$OUT/asan_$(basename "$t").log" 2>&1; echo "exit=$?"
  tail -2 "$OUT/asan_$(basename "$t").log"
done
echo "== coordinator pytest"
source install/setup.bash
(cd src/dual_arm_coordinator && python3 -m pytest -q -p no:cacheprovider test) > "$OUT/coordinator_pytest.log" 2>&1; echo "pytest exit=$?"
tail -3 "$OUT/coordinator_pytest.log"
echo "== end-to-end mock (writes docs/evidence/cm530_mock_*; copied here, originals restored afterwards)"
timeout 600 python3 scripts/test_cm530_mock.py > "$OUT/test_cm530_mock_stdout.log" 2>&1; echo "mock exit=$?"
tail -3 "$OUT/test_cm530_mock_stdout.log"
echo "== operator tools (probe against the v18 mock)"
mkdir -p /tmp/v18_tools
timeout 600 python3 scripts/test_operator_tools.py /tmp/v18_tools "$OUT/operator_tools.json" > "$OUT/operator_tools_stdout.log" 2>&1; echo "tools exit=$?"
tail -2 "$OUT/operator_tools_stdout.log"
