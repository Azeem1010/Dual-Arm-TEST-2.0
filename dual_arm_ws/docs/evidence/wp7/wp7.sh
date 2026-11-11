#!/usr/bin/env bash
# WP7 verification. Usage: wp7.sh probe
cd /mnt/e/dual_arm_system/dual_arm_ws || exit 90
B=docs/evidence/wp7
export PYTHONDONTWRITEBYTECODE=1
CALIB=/tmp/dual_arm_wp7/calib
record() { echo "$(date -Is) $1=$2" >> "$B/00_context.txt"; echo "$1=$2"; }
source /opt/ros/jazzy/setup.bash
source install/setup.bash

stop_sim() {
  kill -INT -- "-$1" 2>/dev/null
  for i in $(seq 1 45); do kill -0 "$1" 2>/dev/null || break; sleep 1; done
  kill -TERM -- "-$1" 2>/dev/null
  sleep 5
  kill -KILL -- "-$1" 2>/dev/null
  sleep 3
}

wait_ready() {
  for i in $(seq 1 120); do
    out=$(timeout 15 ros2 control list_controllers 2>/dev/null)
    if [ "$(printf '%s\n' "$out" | grep -E 'arm[12]_controller|joint_state_broadcaster' | grep -c ' active')" -ge 3 ]; then return 0; fi
    sleep 5
  done
  return 1
}

case "$1" in
probe)
  pgrep -af 'gz sim|move_group' && { record probe_exit blocked_sim_running; exit 91; }
  export AMENT_PREFIX_PATH="/opt/ros/jazzy:${AMENT_PREFIX_PATH}"
  export ROS_DOMAIN_ID=48 GZ_PARTITION=dual_arm_wp7
  rm -rf "$CALIB"
  python3 scripts/generate_sim_vision_calibration.py "$CALIB" > "$B/01_generate_calibration.log" 2>&1
  record generate_exit "$?"
  mkdir -p "$B/calib"
  cp "$CALIB"/*.yaml "$B/calib/"
  setsid ros2 launch dual_arm_bringup vision_sim.launch.py calib_dir:="$CALIB" > "$B/02_probe_launch.log" 2>&1 &
  sim=$!
  ready=0
  wait_ready && ready=1
  record probe_sim_ready "$ready"
  rc=95
  if [ "$ready" -eq 1 ]; then
    sleep 15
    timeout 600 python3 scripts/probe_sim_vision.py "$B/04_probe.json" > "$B/03_probe.log" 2>&1
    rc=$?
  fi
  record probe_exit "$rc"
  cp "$CALIB"/zones.yaml "$B/calib/" 2>/dev/null
  stop_sim "$sim"
  pgrep -af 'gz sim|move_group|ros2_control_node' > "$B/05_leftover_processes.txt" || true
  record probe_leftover_lines "$(wc -l < "$B/05_leftover_processes.txt")"
  tail -5 "$B/03_probe.log" | cut -c1-200
  exit "$rc"
  ;;
unit)
  colcon build --base-paths src --packages-select dual_arm_coordinator dual_arm_bringup --event-handlers console_direct+ > "$B/10_build.log" 2>&1
  record build_exit "$?"
  source install/setup.bash
  ( cd src/dual_arm_coordinator && timeout 280 python3 -m pytest -q -p no:cacheprovider test ) > "$B/11_coordinator_pytest.log" 2>&1
  rc=$?
  record coordinator_pytest_exit "$rc"
  tail -15 "$B/11_coordinator_pytest.log" | cut -c1-170
  exit "$rc"
  ;;
pick)
  pgrep -af 'gz sim|move_group' && { record pick_exit blocked_sim_running; exit 91; }
  export AMENT_PREFIX_PATH="/opt/ros/jazzy:${AMENT_PREFIX_PATH}"
  export ROS_DOMAIN_ID=48 GZ_PARTITION=dual_arm_wp7
  REVISION=sim-fixed-overhead-camera
  rm -rf "$CALIB"
  python3 scripts/generate_sim_vision_calibration.py "$CALIB" > "$B/12_generate_calibration.log" 2>&1
  record generate_exit "$?"
  D="$B/pick"
  mkdir -p "$D"
  setsid ros2 launch dual_arm_bringup vision_sim.launch.py calib_dir:="$CALIB" > "$D/sim_launch.log" 2>&1 &
  sim=$!
  setsid ros2 launch dual_arm_bringup calibration.launch.py calib_dir:="$CALIB" mount_revision:="$REVISION" pose_signature:="$REVISION" > "$D/calibration_launch.log" 2>&1 &
  status=$!
  ready=0
  wait_ready && ready=1
  record pick_sim_ready "$ready"
  rc=95
  if [ "$ready" -eq 1 ]; then
    sleep 15
    ( cd scripts && true )
    PYTHONPATH="$PWD/scripts:$PYTHONPATH" timeout 2400 python3 scripts/test_vision_pick_sim.py /tmp/dual_arm_wp7/pick "$D/report.json" "$CALIB" "$B/04_probe.json" "$REVISION" > "$D/test.log" 2>&1
    rc=$?
  fi
  record pick_exit "$rc"
  cp /tmp/dual_arm_wp7/pick/coordinator_*.log /tmp/dual_arm_wp7/pick/*.json "$D/" 2>/dev/null
  mkdir -p "$D/calib"
  cp "$CALIB"/*.yaml "$CALIB"/*.json "$D/calib/" 2>/dev/null
  stop_sim "$status"
  stop_sim "$sim"
  pgrep -af 'gz sim|move_group|ros2_control_node|coordinator_node|calibration_status' > "$D/leftover_processes.txt" || true
  record pick_leftover_lines "$(wc -l < "$D/leftover_processes.txt")"
  tail -24 "$D/test.log" | cut -c1-230
  exit "$rc"
  ;;
repeat)
  for n in 1 2 3; do
    bash "$B/wp7.sh" pick | tail -6 | cut -c1-700
    record "repeat_${n}_exit" "${PIPESTATUS[0]}"
    mv "$B/pick" "$B/pick_repeat_$n"
  done
  ;;
regress)
  # Rerun the WP6 scenarios with the final speeds, tolerance and timeouts.
  overall=0
  for group in two faults; do
    pgrep -af 'gz sim|move_group' && { record "regress_${group}_exit" blocked_sim_running; exit 91; }
    export AMENT_PREFIX_PATH="/opt/ros/jazzy:${AMENT_PREFIX_PATH}"
    export ROS_DOMAIN_ID=48 GZ_PARTITION=dual_arm_wp7
    D="$B/regress_$group"
    mkdir -p "$D"
    setsid bash scripts/start_sim.sh headless > "$D/sim_launch.log" 2>&1 &
    sim=$!
    ready=0
    wait_ready && ready=1
    record "regress_${group}_sim_ready" "$ready"
    rc=95
    if [ "$ready" -eq 1 ]; then
      sleep 10
      PYTHONPATH="$PWD/scripts:$PYTHONPATH" timeout 2400 python3 scripts/test_transfer_regression.py "$group" "/tmp/dual_arm_wp7/regress_$group" "$D/report.json" > "$D/test.log" 2>&1
      rc=$?
    fi
    record "regress_${group}_exit" "$rc"
    cp /tmp/dual_arm_wp7/regress_$group/coordinator_*.log "$D/" 2>/dev/null
    stop_sim "$sim"
    pgrep -af 'gz sim|move_group|ros2_control_node|coordinator_node' > "$D/leftover_processes.txt" || true
    record "regress_${group}_leftover_lines" "$(wc -l < "$D/leftover_processes.txt")"
    tail -4 "$D/test.log" | cut -c1-220
    [ "$rc" -eq 0 ] || overall=$rc
  done
  exit "$overall"
  ;;
*) echo "usage: wp7.sh probe|unit|pick|repeat|regress"; exit 2 ;;
esac
