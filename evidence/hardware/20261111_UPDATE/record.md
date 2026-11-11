階段：UPDATE（更新到 origin/main 最新版並重新建置、離線基準測試）
日期與時間：2026-11-11 約 14:20～14:50+08:00
操作者／記錄者：測試人員（負責人）要求「更新建置新版本系統」／Claude Code 執行並記錄
程式版本（git rev-parse HEAD）：8ad9d47（更新前 3fd258c）；submodule 不變（three-camera-vision-ros2 4a40f30 等，見 logs/version.txt）
實際輸入的指令與完整輸出：run_update_checks.sh、run_console.txt、summary.tsv、logs/*.log
量測工具與解析度：無（軟體）
照片檔名：無
結果：PASS（建置、離線基準測試、Mock 啟停；未接觸硬體）

## 起因
- 測試人員要求依 Azeem1010/three-camera-vision-ros2 更新 OpenCV 端。查核：該 repo main = 4a40f30，與專案 submodule、sources.lock.json 相同；src/vision_pkg、src/vision_interfaces 與上游只差 CRLF 及專案自加的 publish_debug_image；桌面 ~/桌面/three-camera-vision-ros2-main（~/vision_ws 連結）也是 4a40f30 且與遠端一致 → 視覺端無需更新。
- 主專案本機停在 3fd258c，origin/main 已到 8ad9d47（9 個 commit，含 A 區在手臂右方的模擬配置、操作介面相機路徑、axis_circle 畫圓法工具、新版 HARDWARE_TEST_GUIDE／HANDOFF）。測試人員同意更新主專案。

## 更新步驟
1. 備份到 ~/projects/backup_20261111_before_update/：未提交修改的 patch（install_jazzy.sh、ORIN_DEPLOYMENT/PROGRESS/RESUME/TEST_REPORT）、git status、整個 evidence/hardware/、本機 PROGRESS.md。
2. 上游 bb126f3 已匯入 13 個與本機同路徑的 20261110 證據檔：12 個只差 CRLF（上游以 CRLF 儲存，.gitattributes `* -text`），內容相同；20261110_H1/record.md 多了本機 2026-11-11 加的註記。移開同路徑檔案、git restore 5 個修改檔後 `git pull --recurse-submodules --ff-only` → 8ad9d47。
3. 20261110_H1/record.md 以 CRLF 重寫回本機註記（diff 只 5+/3−）。
4. 上游 install_jazzy.sh 與現場修正版逐字相同 → 不需重新安裝；`rosdep check` 全部滿足（新增 exec_depend dual_arm_interfaces、std_srvs 已在系統）。

## 結果（新版 HANDOFF_PROMPT_HARDWARE_TESTER.md 第一步 4～7 的預期值）
| 項目 | 結果 | 預期 | 判定 |
|---|---|---|---|
| bash scripts/build.sh | exit 0，13 packages finished（增量建置 14 s） | 成功 | PASS |
| coordinator pytest | 285 passed | 285 | PASS |
| HMI pytest（QT_QPA_PLATFORM=offscreen） | 293 passed | 293 | PASS |
| colcon test cm530_hardware | 42 tests, 0 errors, 0 failures, 0 skipped | 42 | PASS |
| scripts/test_cm530_mock.py | 7 階段 PASS | 7 | PASS |
| start_sim.sh mock（ROS_DOMAIN_ID=43） | 4 s 內 arm1/arm2_controller、joint_state_broadcaster active；/joint_states 8 關節；move_group「You can start planning now」；SIGINT 1 s 內結束、process group 清空 | 能啟動與關閉 | PASS |
| fit_axis_circle 可執行檔 | 已安裝 | — | — |

- build.sh 與 test_cm530_mock.py 覆寫的 tracked 證據（overwritten_tracked.txt）已複製到 outputs/ 後 git restore。
- Mock 日誌仍有 FIFO RT 排程權限警告、Octomap 未設定 3D sensor 訊息（與 20261110_SETUP_retry 相同）。
- Mock 通過 ≠ 實機驗收。

## 對實機測試的影響
- 新版 HARDWARE_TEST_GUIDE「2026-11-10 之後還要補的項目」增加 H1 要求（j2 從前傾 30° 扳回、畫圓法求軸心、短邊 F1/F2 各量、C 區格位與示教、B 區示教）；20261111_H1 的判定依此修正，見該紀錄。
- 桌面參考改用 F1、F2、L 線（不再要求貼 world），解除 20261111_H1 的 world 軸向 BLOCKED。
