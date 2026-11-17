階段：UPDATE（更新到 origin/main 最新版並重新建置、離線基準測試）
日期與時間：2026-11-12 約 13:05～13:20+08:00
操作者／記錄者：測試人員要求「更新系統並建置完整環境」／Claude Code 執行並記錄
程式版本（git rev-parse HEAD）：5d394ba（更新前 8ad9d47）；three-camera-vision-ros2 submodule 4a40f30 → 64f28a0，其餘 submodule 不變（logs/version.txt）
實際輸入的指令與完整輸出：run_update_checks.sh、run_console.txt、summary.tsv、logs/*.log
量測工具與解析度：無（軟體）
照片檔名：無
結果：建置、coordinator／HMI／CM530／Mock Serial、Mock 啟停 PASS；vision_pkg pytest 96/100（4 項失敗，判定為測試假設與 Orin 環境不符，見下方，待開發端確認）。未接觸硬體。

## 更新步驟（依 ORIN_DEPLOYMENT.md 第 3 節「從舊版更新」）
1. 本機未提交修改只有文件：docs/PROGRESS.md（11-11 現場摘要）、20261110_H1/record.md；無程式修改。上游 d2ddfae 已收錄兩者內容（record.md 差異相同；PROGRESS 有 11-11 現場狀態條目）。
2. 備份到 ~/projects/backup_20261112_1308/：git_status.txt、local_changes.patch、整個 docs/evidence/。
3. 移開 70 個「未追蹤、但上游已有」的證據檔到備份 moved/；`LC_ALL=C diff -rq --strip-trailing-cr` 比對 repo 版本無差異（只差 CRLF）。
4. git restore 證據與 PROGRESS.md 後 `git merge-base --is-ancestor` 成立 → `git pull --recurse-submodules --ff-only` → 5d394ba；`git submodule update --init --recursive`。
5. install_jazzy.sh、build.sh、package.xml 在 8ad9d47..5d394ba 無變更，未重跑安裝；`rosdep check --from-paths src --ignore-src`：All system dependencies have been satisfied。

## 結果（HANDOFF_PROMPT_HARDWARE_TESTER.md 第一步 4～7 的預期值）
| 項目 | 結果 | 預期 | 判定 |
|---|---|---|---|
| bash scripts/build.sh | exit 0，13 packages finished（20 s） | 成功 | PASS |
| coordinator pytest | 293 passed | 293 | PASS |
| HMI pytest（QT_QPA_PLATFORM=offscreen） | 293 passed | 293 | PASS |
| vision_pkg pytest | 96 passed, 4 failed | 100 | FAIL（環境，見下） |
| colcon test cm530_hardware | 42 tests, 0 errors, 0 failures, 0 skipped | 42 | PASS |
| scripts/test_cm530_mock.py | 7 階段 PASS | 7 | PASS |
| start_sim.sh mock（ROS_DOMAIN_ID=43） | 7 s 內 arm1/arm2_controller、joint_state_broadcaster active；/joint_states 8 關節；move_group「You can start planning now」；SIGINT 1 s 內結束、process group 清空（logs/mock_check.txt、mock_launch.log） | 能啟動與關閉 | PASS |

### vision_pkg 4 項失敗（未修改程式）
失敗：test_launch.py 的 test_no_devices_configured_skips_usb_cam_but_still_starts_vision_nodes、test_nonexistent_device_path_is_reported、test_intrinsics_file_is_passed_as_camera_info_url_when_present、test_vision_node_parameters_show_debug_calib_dir_and_undistort（logs/pytest_vision.log）。
- 這些測試假設 config/cameras.yaml 預設的 by-path 裝置不存在。Orin 上環境相機目前接在 USB 埠 4.3，`/dev/v4l/by-path/platform-3610000.usb-usb-0:4.3:1.0-video-index0` 存在，launch 因此多啟動 env_cam 的 usb_cam_node_exe，與測試預期不同。
- 推論：測試依賴執行機器的實體裝置，在開發端（無這些路徑）會通過；在 Orin 要拔掉環境相機或由測試改用臨時設定才能驗證。尚未拔線重跑，`NOT_RUN`。

## 其他觀察
- 目前 /dev/v4l/by-path 只有 4.3（→ video4）與 4.4（→ video2）兩個裝置；cameras.yaml 的手臂相機路徑 4.4.3、4.4.1 不存在。與 11-11 實測接法不同，實機跑視覺前要重查（ORIN_DEPLOYMENT 第 3 節「找到裝置路徑」）。
- build.sh 與 test_cm530_mock.py 覆寫的 tracked 證據（overwritten_tracked.txt）已複製到 outputs/ 後 git restore。
- Mock 日誌仍有 Octomap 未設定 3D sensor、結束時 pal_statistics「context cannot be slept with」訊息（關閉時序，非啟動錯誤）。
- 上游 11-12 新增：實機 config/hardware/coordinator.yaml 的 heights.cup_radius_m、motion.max_tool_tilt_deg 空白欄位，要現場量測後才能填，不可抄模擬值。
- Mock 通過 ≠ 實機驗收。
