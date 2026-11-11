#!/usr/bin/env bash
# 2026-11-11 更新到 origin/main 8ad9d47 後的建置與離線基準測試（依 HANDOFF_PROMPT_HARDWARE_TESTER.md 第一步 4～6）。
# 不接觸硬體。每步記錄指令、退出碼、秒數與完整日誌到 OUT；失敗不中斷，全部跑完。
cd "$(dirname "$0")/../../../.." || exit 90      # → dual_arm_ws
OUT=docs/evidence/hardware/20261111_UPDATE
mkdir -p "$OUT/logs"
SUMMARY=$OUT/summary.tsv
printf 'step\texit\tseconds\tstart\n' > "$SUMMARY"
export PYTHONDONTWRITEBYTECODE=1 QT_QPA_PLATFORM=offscreen

step() {
  local name=$1; shift
  local log=$OUT/logs/$name.log start rc t0
  t0=$(date --iso-8601=seconds); start=$(date +%s)
  { printf '$'; printf ' %q' "$@"; printf '\n'; } > "$log"
  "$@" >> "$log" 2>&1
  rc=$?
  printf '%s\t%s\t%s\t%s\n' "$name" "$rc" "$(( $(date +%s) - start ))" "$t0" >> "$SUMMARY"
  echo "$name exit=$rc"
}

{ echo "HEAD $(git rev-parse HEAD)"; git submodule status; uname -a; } > "$OUT/logs/version.txt"
step build bash scripts/build.sh
source /opt/ros/jazzy/setup.bash
source install/setup.bash
step pytest_coordinator bash -c 'cd src/dual_arm_coordinator && python3 -m pytest -q -p no:cacheprovider test'
step pytest_hmi bash -c 'cd src/dual_arm_hmi && python3 -m pytest -q -p no:cacheprovider test'
step colcon_test_cm530 bash -c 'colcon test --packages-select cm530_hardware && colcon test-result --verbose'
step test_cm530_mock python3 scripts/test_cm530_mock.py

# build.sh 與 test_cm530_mock.py 會覆寫 docs/evidence/ 的 tracked 檔：新結果另存，舊檔還原
git status --porcelain -- docs/evidence | grep -v '^??' | awk '{print $2}' | sed 's#^dual_arm_ws/##' > "$OUT/overwritten_tracked.txt"
mkdir -p "$OUT/outputs"
while read -r f; do [ -n "$f" ] && mkdir -p "$OUT/outputs/$(dirname "$f")" && cp -p "$f" "$OUT/outputs/$f"; done < "$OUT/overwritten_tracked.txt"
while read -r f; do [ -n "$f" ] && [ "$f" != "docs/evidence/hardware/20261110_H1/record.md" ] && git restore -- "$f"; done < "$OUT/overwritten_tracked.txt"
git status --short > "$OUT/git_status_after.txt"
echo DONE
