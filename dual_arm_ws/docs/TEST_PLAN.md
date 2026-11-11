# 測試計畫

更新：2026-11-10。狀態只使用 `PASS`、`FAIL`、`BLOCKED`、`NOT_RUN`。實際結果以 [TEST_REPORT.md](TEST_REPORT.md) 與 `docs/evidence/` 為準，本文件說明要測什麼、怎麼測，以及結果代表什麼。

## 1. 測試層級

每一層都不能代替下一層。

| 層級 | 工具 | 能證明 | 不能證明 |
|---|---|---|---|
| 單元測試 | pytest、gtest、假 IO | 邏輯、拒絕條件、狀態轉移 | ROS 接線、任何物理行為 |
| 韌體迴路 | 原版 v17 `bridge.c` + 模擬 AX-12 匯流排 | 協定解析與序列行為 | 實際 UART 時序、馬達電氣 |
| MoveIt mock | `mock_components` | 規劃、場景、動作介面、控制器切換 | 動力學與定位精度（關節完全照命令動） |
| Gazebo | 真值位置與吸盤外掛 | 完整流程、接觸條件 | 相機校正、實機精度 |
| 實機階梯 | 第 6 節 | 真正的驗收 | — |

Gazebo 只有約 0.2 倍實時，逾時以真實時間計算的設定要考慮這一點。

## 2. 執行方式

環境是 WSL2 Ubuntu 24.04。指令都在 `dual_arm_ws` 目錄下，先 `source install/setup.bash`。

| 項目 | 指令 |
|---|---|
| 分層檢查（見第 4 節） | `bash scripts/run_checks.sh t0\|t1\|t2 OUT_DIR`，結果在 `OUT_DIR/summary.tsv` |
| 完整建置 | `bash scripts/build.sh` |
| Coordinator 單元測試 | `cd src/dual_arm_coordinator && python3 -m pytest -q -p no:cacheprovider test` |
| 驅動單元測試 | `colcon test --base-paths src --packages-select cm530_hardware` |
| Mock Serial 整合 | `python3 scripts/test_cm530_mock.py` |
| Sanitizer | `docs/evidence/wp8/wp8.sh sanitize` |
| 運動 gateway（mock） | `start_sim.sh mock` 後 `python3 scripts/test_motion_gateway.py REPORT.json` |
| Coordinator 節點（Gazebo） | `start_sim.sh headless` 後 `python3 scripts/test_coordinator_sim.py WORK REPORT.json` |
| 回歸情境（Gazebo） | `python3 scripts/test_transfer_regression.py two\|faults\|batch WORK REPORT.json` |
| 視覺取料（Gazebo） | `docs/evidence/wp7/wp7.sh pick` |
| 安全監控（mock） | `start_sim.sh mock` 後 `python3 scripts/test_safety_supervisor.py WORK REPORT.json` |
| 操作工具（mock） | `docs/evidence/wp10/wp10.sh mock` |
| 操作介面單元測試 | `cd src/dual_arm_hmi && QT_QPA_PLATFORM=offscreen python3 -m pytest -q -p no:cacheprovider test` |
| 操作介面啟停（Gazebo） | `docs/evidence/hmi/stage2/stage2_live.sh`（十次啟停與接回） |
| 操作介面任務控制（Gazebo） | `docs/evidence/hmi/stage3/stage3_live.sh`，只跑持物停止加 `holding` |

- 每個 Gazebo 情境群組都要用剛啟動的模擬，因為瓶蓋會被移動。
- 啟動前用 `pgrep -af 'gz sim'` 確認沒有其他模擬。
- `build.sh`、舊 pipeline、`test_cm530_mock.py` 會覆寫 `docs/evidence/` 的舊紀錄。新結果另存，舊檔用 `git restore` 還原。
- 從 Git Bash 呼叫 WSL 時，不要用 `wsl.exe bash -lc '...$VAR...'`，變數會先被展開。

## 3. 涵蓋範圍與目前狀態

| 需求 | 測試 | 狀態 |
|---|---|---|
| 校正值未量測時拒絕 | `test_calibration`、`test_task_config`、mock 階段 | `PASS` |
| 未校正的相機不得驅動抓取 | `test_vision`、視覺取料 | `PASS`（只涵蓋 arm1 取料） |
| 影像時效 | `test_vision` | `PASS`（假時脈）；服務端影像時間戳不存在 |
| 吸盤朝下、接觸段直線 | `test_motion_math`、運動 gateway | `PASS` |
| 碰撞與不可達目標拒絕 | 運動 gateway | `PASS`（保守方塊模型） |
| B 區互斥、持物狀態保留 | `test_workflow`、故障情境 | `PASS` |
| 格位連續、驗證後才提交 | `test_workflow`、`test_resources` | `PASS` |
| 取消、釋放失敗、急停心跳 | 故障情境 | `PASS` |
| 重啟後要求復歸 | `test_workflow`、Coordinator 節點 | `PASS` |
| Coordinator 失效時停止手臂 | 安全監控 | `PASS`（mock） |
| 鎖定中手動啟動控制器會被再停用 | `test_safety_ros`、安全監控情境 | `PASS`（mock） |
| 軟體停止鎖定、解除鎖定後恢復 | `test_safety`、`test_safety_ros`、介面任務控制 | `PASS`（模擬） |
| 回 HOME 順序、拒絕條件、失敗進入故障 | `test_workflow`、介面任務控制 | `PASS`（模擬）；停在關節限位外時無法規劃 HOME，`FAIL`（已知缺口） |
| 介面指令的送出、接受與結果 | `test_live_source`、介面任務控制 | `PASS`（模擬）；實機只接通強制停止 |
| 序列逾時不重送 | `test_link`、`test_scheduler` | `PASS` |
| 兩物體搬運 | 回歸 `two` | `PASS` |
| 八物體搬運 | 回歸 `batch` | `FAIL`（格位 1 與 A 區可達範圍，C30、D3） |
| 視覺判斷區域與格位 | — | `BLOCKED`（模擬相機遮擋，C31、D7） |
| 搬運時間減少 50% | WP6S | `FAIL`（−48.6%） |
| 完整工作站碰撞 | — | `BLOCKED`（WP11） |
| ESP32 吸盤命令與回音 | `test_gripper`、`test_esp32_ros` | `PASS`（替身節點） |
| 真正的 ESP32、實際吸附 | — | `NOT_RUN`（韌體沒有真空感測，結果由人工確認） |
| 實機 | 第 6 節 | `NOT_RUN` |

## 4. 變更時要重跑什麼

| 變更 | 必須重跑 |
|---|---|
| `workflow/`、`journal.py`、`resources.py` | Coordinator 單元測試、回歸 `two`、`faults` |
| `gateways/motion.py` | 運動 gateway、回歸 `two` |
| `gateways/vision.py` | 單元測試、視覺取料 |
| 速度、容差、逾時設定 | 回歸 `two`、`faults`、視覺取料至少 3 次 |
| `cm530_hardware` | gtest、Mock Serial、ASan/UBSan、TSan |
| 安全監控 | 單元測試、安全監控情境、介面任務控制 |
| `dual_arm_hmi` | 介面單元測試；改到啟停或指令時加對應的 Gazebo 實測（stage2／stage3） |
| `/dual_arm/*` 服務或狀態欄位 | Coordinator 單元測試、Coordinator 節點、介面單元測試與任務控制 |
| URDF、SRDF、world、`runtime.json` 的 HOME | `build.sh`、模型檢查（`validate_model.py`、`test_cad_pose.py`、`check_home_collision.py`）、回歸 `two` |
| 場地座標、區域或格位設定 | 上一列全部，加上可達性（`report_reach.py`）、舊 pipeline 兩物體、視覺取料 |
| 只改文件 | `run_checks.sh t0`：連結全部有效，並逐條看過列出的區域順序描述 |

`scripts/run_checks.sh` 的三層對應：

| 層 | 內容 | 約略時間 |
|---|---|---|
| `t0` | 文件連結、區域順序描述清單 | < 1 分鐘 |
| `t1` | 產生模型與場景、`test_cad_pose.py`、`build.sh`（含 `validate_model.py`）、HOME、IK、可達性、coordinator／HMI／vision 單元測試、HOME 碰撞、格位候選與自碰撞 | 約 5 分鐘 |
| `t2` | 冒煙測試、模擬影像與座標驗證、回歸 `two`、舊 pipeline 兩物體、運動 gateway／操作工具／安全監控（mock）、視覺取料一次、README 截圖 | 約 40 分鐘 |

`t2` **不含**回歸 `faults`、`batch`、視覺取料連續 3 次與 CM-530 的 gtest／Mock Serial／sanitizer；上表要求這些時要另外跑。所有層都會跑完每一步，再以退出碼 1 表示有失敗；已知失敗也算失敗，由紀錄說明原因。修正後只重跑失敗的步驟時，用環境變數 `STEPS` 列出步驟名稱（`vision_pick` 要連同 `generate_sim_vision_calibration`、`probe_sim_vision`），結果放到新的 `OUT_DIR`，原來那次的紀錄保留不動。

## 5. 可靠度的計法

單次通過不算穩定。WP7 曾單次通過，連續測試卻只有 5 次過 1 次。

- 改動時序、容差或速度後，同一情境至少連續跑 3 次，並回報通過次數與次數總數。
- 失敗要保留紀錄與原因，不要只重跑到通過為止。
- 3 次全過只是小樣本。實機成功率的門檻由使用者訂定（D6）。

## 6. 實機放行階梯

每一級通過才能進下一級，全程要有實體急停與人員在場，由現場人員明確要求後執行（團隊成員同等層級，不需另外授權）。逐步操作見 [HARDWARE_TEST_GUIDE.md](HARDWARE_TEST_GUIDE.md)。

| 級 | 內容 | 通過條件 | 立即停止 |
|---|---|---|---|
| H0 | 唯讀連線，量測迴圈率 | `cm530_probe` PASS，HOME 與 `expected_home` 相符，長時間無通訊錯誤 | 任何 ERR 或逾時 |
| H1 | 扭力關閉下手動確認 j1、j2 方向；確認急停、ID 15 線材、Moving Speed | 方向與 A 區左右矛盾（D0、D1）解決並有紀錄 | 讀值與轉動不對應 |
| H2 | 校正樣本與獨立姿態尺量 | `check_calibration_sheet` PASS，門檻由 D6 訂定 | 誤差超過門檻 |
| H3 | 單軸 ±10 raw | 運動方向與校正一致 | 方向相反或異常聲響 |
| H4 | arm1 關節空間，速度比例 0.05 | READ 到位，誤差在實測容差內 | 追蹤誤差異常 |
| H5 | 懸停目標上方並尺量，再下降但不接觸 | TCP 誤差達 D6 門檻，高度餘裕足夠 | 高度不足 |
| H6 | 相機實體校正，單件 A→B，人工吸盤 | 吸放成功，場景一致 | 任何 FAULT 先查明 |
| H7 | arm2 單件 B→C、雙臂 A→B→C | `verify_place` 通過，互鎖與復歸正常 | 同上 |
| H8 | 連續八件，逐步提速 | 達到 D6 的成功率門檻 | 同上 |

## 7. 目前無法測試

| 項目 | 原因 |
|---|---|
| 真實 UART 時序、馬達負載與背隙 | 需要實機 |
| Moving Speed 的實際值 | 第 17 版韌體無法讀取 |
| Coordinator 實機模式 | 刻意拒絕啟動，等視覺 gateway 完成與實機 TF |
| 實機急停心跳 | 尚無實體裝置與發布節點 |
| `c-review` | 需要此環境沒有的 Workflow 工具 |
