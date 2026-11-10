#!/usr/bin/env bash
# Tiered checks; which tier a change needs is in docs/TEST_PLAN.md section 4.
#
#   bash scripts/run_checks.sh t0 OUT_DIR   # Markdown links and layout statements, < 1 min, no ROS
#   bash scripts/run_checks.sh t1 OUT_DIR   # model, build, HOME, IK, unit tests, collision, about 5 min
#   bash scripts/run_checks.sh t2 OUT_DIR   # Gazebo and MoveIt mock runs, about 40 min; run in background
#
# Run in WSL Ubuntu 24.04 + Jazzy from anywhere; OUT_DIR is relative to dual_arm_ws.
# Every step's exit code, duration and log go to OUT_DIR/summary.tsv; the script exits 1
# if any step failed, but always runs every step of the tier. Known failures (for
# example test_ik.py at 16/18) still count as FAIL here; the reader records why.
# Tracked files under docs/evidence/ that the steps overwrite are copied to
# OUT_DIR/outputs/ and then restored from HEAD (AGENTS.md: new results go to their own
# folder, old ones are restored). After a model or layout change, when the tracked
# evidence itself must be renewed, run with KEEP_EVIDENCE=1: the new files stay in
# place and the HEAD versions are saved to OUT_DIR/replaced/.
# To rerun only some steps of a tier, list their names in STEPS, for example
#   STEPS="legacy_pipeline_two vision_pick" bash scripts/run_checks.sh t2 OUT_DIR
# Steps that need an earlier one must list it too: vision_pick needs
# generate_sim_vision_calibration and probe_sim_vision; the README steps all run under readme_capture.
# No `set -u`: the ROS setup scripts read unset variables.
cd "$(dirname "$0")/.." || exit 90
TIER=${1:-}
OUT=${2:-}
case "$TIER" in t0|t1|t2) ;; *) echo 'Usage: bash scripts/run_checks.sh t0|t1|t2 OUT_DIR' >&2; exit 2 ;; esac
[ -n "$OUT" ] || { echo 'OUT_DIR is required' >&2; exit 2; }
mkdir -p "$OUT"
SUMMARY=$OUT/summary.tsv
printf 'step\texit\tseconds\tlog\n' > "$SUMMARY"
export PYTHONDONTWRITEBYTECODE=1 QT_QPA_PLATFORM=offscreen
FAILED=0

# True when STEPS is empty or names this step.
want() { [ -z "${STEPS:-}" ] || [[ " $STEPS " == *" $1 "* ]]; }

# Record the exit code before anything else can overwrite $?.
step() {
  local name=$1; shift
  want "$name" || return 0
  local log=$OUT/$name.log start rc
  start=$(date +%s)
  { printf '$'; printf ' %q' "$@"; printf '\n'; } > "$log"
  "$@" >> "$log" 2>&1
  rc=$?
  printf '%s\t%s\t%s\t%s\n' "$name" "$rc" "$(( $(date +%s) - start ))" "$log" >> "$SUMMARY"
  [ "$rc" -eq 0 ] || FAILED=1
  echo "$name exit=$rc"
  return 0
}

note() { printf '%s\t-\t-\t%s\n' "$1" "$2" >> "$SUMMARY"; echo "$1: $2"; }

ros_env() {
  source /opt/ros/jazzy/setup.bash
  source install/setup.bash
  export AMENT_PREFIX_PATH="/opt/ros/jazzy:${AMENT_PREFIX_PATH}"
}

wait_ready() {
  local i out
  for i in $(seq 1 120); do
    out=$(timeout 15 ros2 control list_controllers 2>/dev/null)
    [ "$(printf '%s\n' "$out" | grep -E 'arm[12]_controller|joint_state_broadcaster' | grep -c ' active')" -ge 3 ] && return 0
    sleep 5
  done
  return 1
}

stop_group() {
  kill -INT -- "-$1" 2>/dev/null
  local i
  for i in $(seq 1 45); do kill -0 "$1" 2>/dev/null || break; sleep 1; done
  kill -TERM -- "-$1" 2>/dev/null; sleep 5
  kill -KILL -- "-$1" 2>/dev/null; sleep 3
}

no_sim_running() {
  if pgrep -af 'gz sim|move_group|ros2_control_node' > "$OUT/already_running.txt"; then
    note "$1" "BLOCKED: simulation processes already running, see already_running.txt"
    FAILED=1
    return 1
  fi
  return 0
}

# Start a launch in its own process group, wait for the controllers, run one step, stop it.
with_launch() {
  local name=$1 launch_log=$2; shift 2
  local sep=0 args=() group
  want "$name" || return 0
  no_sim_running "$name" || return 0
  while [ $# -gt 0 ]; do
    if [ "$1" = -- ]; then sep=1; shift; break; fi
    args+=("$1"); shift
  done
  setsid "${args[@]}" > "$OUT/$launch_log" 2>&1 &
  group=$!
  if wait_ready; then
    sleep 10
    step "$name" "$@"
  else
    note "$name" "FAIL: controllers not active, see $launch_log"
    FAILED=1
  fi
  stop_group "$group"
  pkill -KILL -f 'gz sim' 2>/dev/null
  sleep 2
}

settle_evidence() {
  local f
  git diff --name-only -- docs/evidence | while read -r f; do
    f=${f#dual_arm_ws/}
    case "$f" in "$OUT"/*) continue ;; esac
    grep -qxF "$f" "$OUT/.dirty_before" 2>/dev/null && continue
    mkdir -p "$OUT/outputs/$(dirname "$f")" "$OUT/replaced/$(dirname "$f")"
    cp "$f" "$OUT/outputs/$f"
    git show "HEAD:dual_arm_ws/$f" > "$OUT/replaced/$f" 2>/dev/null
    if [ "${KEEP_EVIDENCE:-0}" != 1 ]; then git restore -- "$f"; fi
  done
  [ "${KEEP_EVIDENCE:-0}" = 1 ] || rm -rf "$OUT/replaced"
}

git diff --name-only -- docs/evidence | sed 's#^dual_arm_ws/##' > "$OUT/.dirty_before"
git rev-parse HEAD > "$OUT/commit.txt"
git status --short > "$OUT/git_status_before.txt"

if [ "$TIER" = t0 ]; then
  step check_docs python3 scripts/check_docs.py "$OUT/check_docs.json"
fi

if [ "$TIER" = t1 ]; then
  ros_env
  export ROS_DOMAIN_ID=46
  step generate_cad_robot python3 scripts/generate_cad_robot.py
  step generate_world python3 scripts/generate_world.py
  step test_cad_pose python3 scripts/test_cad_pose.py
  step build bash scripts/build.sh
  source install/setup.bash
  step report_home_poses python3 scripts/report_home_poses.py
  step test_ik python3 scripts/test_ik.py
  step report_reach python3 scripts/report_reach.py "$OUT/reach.json"
  step pytest_coordinator bash -c 'cd src/dual_arm_coordinator && python3 -m pytest -q -p no:cacheprovider test'
  step pytest_hmi bash -c 'cd src/dual_arm_hmi && python3 -m pytest -q -p no:cacheprovider test'
  step pytest_vision bash -c 'cd src/vision_pkg && python3 -m pytest -q -p no:cacheprovider tests'
  if no_sim_running home_collision; then step home_collision python3 scripts/check_home_collision.py; fi
  # Slot proposal checks reuse joint solutions saved by the study, so rerun the study first.
  step measure_slot_adjustment python3 scripts/measure_slot_adjustment.py
  step verify_slot_proposals python3 scripts/verify_slot_proposals.py
  if no_sim_running slot_self_collision; then step slot_self_collision python3 scripts/check_slot_self_collision.py; fi
fi

if [ "$TIER" = t2 ]; then
  ros_env
  WORK=/tmp/dual_arm_checks_$$
  rm -rf "$WORK"; mkdir -p "$WORK"
  export ROS_DOMAIN_ID=47 GZ_PARTITION=dual_arm_checks
  if want smoke_runtime_sim && no_sim_running smoke_runtime_sim; then
    step smoke_runtime_sim python3 scripts/smoke_runtime.py sim --group both_arms
    pkill -KILL -f 'gz sim' 2>/dev/null; sleep 2
  fi
  step analyze_sim_images python3 scripts/analyze_sim_images.py
  step validate_sim_coordinates python3 scripts/validate_sim_coordinates.py
  with_launch regress_two regress_two_sim.log bash scripts/start_sim.sh headless -- \
    env PYTHONPATH="$PWD/scripts:${PYTHONPATH:-}" timeout 2400 python3 scripts/test_transfer_regression.py two "$WORK/regress_two" "$OUT/regress_two.json"
  # demo_transfer_pipeline.py sets ROS_DOMAIN_ID=43 itself (the old demo in README),
  # so its simulation has to run in 43 as well.
  if want legacy_pipeline_two; then
    ROS_DOMAIN_ID=43
    with_launch legacy_pipeline_two legacy_pipeline_sim.log bash scripts/start_sim.sh headless -- \
      timeout 1800 python3 scripts/demo_transfer_pipeline.py --count 2
    ROS_DOMAIN_ID=47
    [ -f docs/evidence/transfer_pipeline.json ] && cp docs/evidence/transfer_pipeline.json "$OUT/legacy_pipeline_two.json"
  fi
  for t in motion_gateway operator_tools safety_supervisor; do
    if [ "$t" = motion_gateway ]; then cmd=(timeout 900 python3 scripts/test_$t.py "$OUT/$t.json")
    else cmd=(timeout 900 python3 scripts/test_$t.py "$WORK/$t" "$OUT/$t.json"); fi
    if [ "$t" = operator_tools ]; then
      # Start the publisher binary itself, not `ros2 run`, so that killing $tf stops it.
      cmd=(bash -c '"$(ros2 pkg prefix tf2_ros)/lib/tf2_ros/static_transform_publisher" --z 0.014 --yaw 1.57079632679 --frame-id arm1_base_link --child-frame-id arm1_base > /dev/null 2>&1 & tf=$!; sleep 3; "$@"; rc=$?; kill $tf; wait $tf; exit $rc' _ "${cmd[@]}")
    fi
    with_launch "$t" "${t}_mock.log" bash scripts/start_sim.sh mock -- "${cmd[@]}"
  done
  # Vision-chosen picks: probe the simulated cameras, then pick through the coordinator.
  CALIB=$WORK/calib
  REVISION=sim-fixed-overhead-camera
  step generate_sim_vision_calibration python3 scripts/generate_sim_vision_calibration.py "$CALIB"
  with_launch probe_sim_vision probe_sim_vision_launch.log ros2 launch dual_arm_bringup vision_sim.launch.py calib_dir:="$CALIB" -- \
    timeout 600 python3 scripts/probe_sim_vision.py "$OUT/probe_sim_vision.json"
  if ! want vision_pick; then
    :
  elif [ -f "$OUT/probe_sim_vision.json" ] && no_sim_running vision_pick; then
    setsid ros2 launch dual_arm_bringup calibration.launch.py calib_dir:="$CALIB" mount_revision:="$REVISION" pose_signature:="$REVISION" > "$OUT/vision_pick_calibration.log" 2>&1 &
    status=$!
    with_launch vision_pick vision_pick_launch.log ros2 launch dual_arm_bringup vision_sim.launch.py calib_dir:="$CALIB" -- \
      env PYTHONPATH="$PWD/scripts:${PYTHONPATH:-}" timeout 2400 python3 scripts/test_vision_pick_sim.py "$WORK/pick" "$OUT/vision_pick.json" "$CALIB" "$OUT/probe_sim_vision.json" "$REVISION"
    stop_group "$status"
  else
    note vision_pick "NOT_RUN: probe report missing or simulation running"
  fi
  # README screenshots from a two-cycle coordinator demo; publish only after a full capture.
  JOURNAL=$WORK/readme_journal.json
  if want readme_capture && no_sim_running readme_capture; then
    setsid ros2 launch dual_arm_bringup demo_pick_place.launch.py cycles:=2 journal_path:="$JOURNAL" > "$OUT/readme_demo_launch.log" 2>&1 &
    demo=$!
    if wait_ready; then
      python3 scripts/capture_readme_images.py capture "$OUT/readme_raw" > "$OUT/readme_capture.log" 2>&1 &
      cap=$!
      sleep 8
      STEPS_SAVED=${STEPS:-}; STEPS=
      step readme_demo_start timeout 60 ros2 run dual_arm_coordinator operator_console start
      wait "$cap"; rc=$?
      printf 'readme_capture\t%s\t-\t%s\n' "$rc" "$OUT/readme_capture.log" >> "$SUMMARY"; [ "$rc" -eq 0 ] || FAILED=1
      step readme_demo_status timeout 30 ros2 run dual_arm_coordinator operator_console status
      [ "$rc" -eq 0 ] && step readme_publish python3 scripts/capture_readme_images.py publish "$OUT/readme_raw" docs/images
      STEPS=$STEPS_SAVED
    else
      note readme_capture "FAIL: controllers not active, see readme_demo_launch.log"; FAILED=1
    fi
    stop_group "$demo"
    pkill -KILL -f 'gz sim' 2>/dev/null
  fi
  pgrep -af 'gz sim|move_group|ros2_control_node|coordinator_node|static_transform' > "$OUT/leftover_processes.txt"
  note leftover_processes "$(wc -l < "$OUT/leftover_processes.txt") lines"
fi

settle_evidence
rm -f "$OUT/.dirty_before"
echo "summary: $SUMMARY"
column -t -s "$(printf '\t')" "$SUMMARY" 2>/dev/null || cat "$SUMMARY"
exit "$FAILED"
