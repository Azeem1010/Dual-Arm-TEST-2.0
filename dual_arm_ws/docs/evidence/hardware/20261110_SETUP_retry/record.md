階段：SETUP_retry（使用者授權修正來源並完成環境與建置）
日期與時間：2026-11-10T14:51:51.979797+08:00
操作者／記錄者：Codex
程式版本：3fd258c8e81c3bada92df92ef9a95e5749ca5178（main，加本地安裝腳本／文件修正）
實際輸入的指令與完整輸出：見 output.txt 與本目錄各原始輸出
量測工具與解析度：系統指令；無實體量測
照片檔名：無；無畫面 Mock，未做實機測試
結果：PASS（環境、建置與規定離線測試範圍）

## 修復與失敗歷史
- 舊來源衝突及初次安裝 FAIL 保留於 ../20261110_SETUP/。
- 安裝腳本先辨識已可用的 ROS 2 Noble APT 來源，沿用既有 Signed-By，避免覆寫 ros2-apt-source 的內嵌金鑰配置。
- 第一次重試仍 FAIL（exit 100）：系統缺 noble-updates，開發套件版本不能與既有函式庫匹配。見 install_output.txt。
- 新增 /etc/apt/sources.list.d/dual-arm-noble-updates.sources，使用既有官方 ports.ubuntu.com 站台與 Ubuntu archive keyring。
- 第二次安裝 PASS（exit 0），見 install_output_02.txt。APT 安裝 502 新套件、升級 13 個依賴，未移除套件。
- 首次建置 FAIL：dual_arm_gripper 缺 SWSCALE；見 build_output.txt、colcon_build_failed.log。
- 補齊 Gazebo 所需 FFmpeg 開發套件，安裝腳本同步加入 libswscale-dev、libavdevice-dev、libavformat-dev、libavcodec-dev、libavutil-dev。見 ffmpeg_install.txt。
- 第二次完整建置 PASS：13 packages finished，模型結構 PASS，MoveIt 設定重建 PASS。見 build_output_02.txt。

## 驗證
| 檢查 | 狀態 | 結果 |
|---|---|---|
| APT 依賴檢查 | PASS | apt-get check exit 0 |
| 安裝腳本語法 | PASS | bash -n exit 0 |
| Coordinator | PASS | 259 passed |
| HMI | PASS | 262 passed；QT_QPA_PLATFORM=offscreen |
| CM530 | PASS | 42 tests, 0 errors, 0 failures, 0 skipped |
| Mock Serial | PASS | 七階段全通過；既有腳本強制 use_mock_serial，測試自行選獨立 ROS domain |
| 基本 Mock | PASS | 三控制器 active、兩臂 joint_states、MoveIt ready；SIGINT 後 launch exit 0、process group 已消失 |
| dialout 群組設定 | PASS | id orin 包含 dialout；桌面工作階段仍需登出再登入 |
| 實機驗證 | NOT_RUN | 未接觸裝置、未送出實機命令 |

## 保留的訊息與範圍限制
- Mock 日誌有 FIFO RT 排程權限警告、field_platform 無碰撞幾何警告、Octomap 缺 3D sensor plugin 訊息，以及 SIGINT 關閉時 pal_statistics context invalid 訊息。控制器、關節回授與 MoveIt 均就緒；所有 launch 子程序正常結束。這不是 Gazebo 物理、影像串流或實機驗收。
- build.sh 第二次重建 MoveIt 設定有 colcon underlay override 警告；退出碼 0。
- 未修改第三方、控制程式、測試、限位或實機校正；未 commit/push。
- 本次生成證據已複製至本目錄，原有 tracked docs/evidence 已 git restore。前次失敗紀錄仍保留。
- 下一步先登出再登入，再由現場確認 P0 器材、人員、急停與照片；D6/H3 授權仍未填，H4～H8 BLOCKED。
