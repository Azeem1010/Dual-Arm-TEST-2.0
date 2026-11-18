#!/usr/bin/env bash
# The calibration test reads CM530_TEMPLATE, which ctest sets; set it when running directly.
cd "$(dirname "$0")/../../.."
CM530_TEMPLATE="$PWD/src/cm530_hardware/config/calibration.yaml" /tmp/v18_asan_build/cm530_hardware/cm530_calibration_test \
  > docs/evidence/v18_speed_20261118/asan_cm530_calibration_test.log 2>&1; echo "exit=$?"
tail -2 docs/evidence/v18_speed_20261118/asan_cm530_calibration_test.log
