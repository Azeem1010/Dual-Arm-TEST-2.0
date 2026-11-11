# 系統修改計畫與衝突清單

更新：2026-11-11。本文件是 [FUTURE_ROADMAP.md](FUTURE_ROADMAP.md) 的執行版，兩者不一致時以本文件為準。各工作包的實際狀態見第 6 節。

接手實作請用 [HANDOFF_PROMPT.md](HANDOFF_PROMPT.md)。

狀態只使用 `PASS`、`FAIL`、`BLOCKED`、`NOT_RUN`。參照來源為 [Azeem1010/Dual-Arm-TEST](https://github.com/Azeem1010/Dual-Arm-TEST) commit `26d187f`，以下簡稱「對方」。

## 1. 原則

1. **模型與驅動用本地**，任務節點參照對方的結構重寫，不整包複製。
2. **會隨配置改變的數值只放設定檔**，程式不寫死左右或正負號，配置定案時才不必改程式。
3. **先模擬、後實機。** 實機階段一律由現場人員要求並操作，AI 不自行執行。
4. **舊流程保留到新流程通過。** `scripts/demo_transfer_pipeline.py` 是回歸基準。
5. **校正資料與模擬資料分開。** 不可互相複製。

## 2. 未決事項

未得到使用者答覆前，一律採用「預設」欄，不可自行判定。

| 編號 | 問題 | 預設 | 受影響的工作 |
|---|---|---|---|
| D0 | A 區在手臂左或右、j1 方向（[FUTURE_ROADMAP.md](FUTURE_ROADMAP.md) 3.1） | **2026-11-10 使用者決定：依 H1 實測（arm1）採用 A 在手臂右方、j1 方向 +1**，模擬已改（evidence/a_right_layout_20261110/）。2026-11-11 H1 實測 arm2 也是 +1，與模擬一致；j1 正對場地 arm1 約 193、arm2 約 519（±5°，非校正值），與模擬 `raw_at_cad_zero` 192.3、512 相符（evidence/hardware/20261111_H1/）。實機數值仍 `BLOCKED`，要等 H2 | H1、WP11 |
| D1 | j2 方向與零點 | 實機數值 `BLOCKED`。2026-11-11 H1（新版步驟 6）：兩臂往場地（使用者）側前傾時 j2 讀值變大（arm1 603→559、arm2 606→585 為扳回垂直），與模擬方向 +1 一致；11-10「上抬讀值變小」是往底座後方倒，作廢。伸直 READ arm1 200,505,498,513、arm2 507,516,523,511，大致支持 512 = 垂直。arm2 的 C 格示教讀值以模擬換算的 FK 半徑與尺量格位差 3 mm 以內（evidence/hardware/20261111_fk_crosscheck/，只是 H1 等級的旁證）。精確零點與 j3、j4 方向待 H2 | H1 |
| D2 | READ 收到完整 `ERR,DXL_*` 時可否有限重試 | **不重試**，維持現行鎖定 | WP8 第 4 項 |
| D3 | 格位 1 的處理方式，以及 A 區只有 4 個瓶蓋位置可達（C30） | 不套用位移，八件測試只記錄結果。**2026-11-11 使用者提供實物編號（使用者側視角）：格位 1、2 在最靠近手臂 2 的一排，往使用者依序 3、4 … 7、8，單號在使用者左側（靠 B 區）。** 模擬目前的編號是這個轉 180°，原本搆不到的「格位 1」位置在實物編號是格位 8；介面格位圖上下顛倒，`vision_pkg` 的 `order_slots` 是鏡像（`view_rotation_k` 無法表示）。**使用者決定併入階段 C（WP11）**：現場量測回來後和場地尺寸一起改模擬順序、`prefilled_slots`、介面格位圖與視覺鏡像選項，只跑一次 t2。**2026-11-11 H1 已量到格位與編號**（20261111_H1，直尺 0.5 cm）：靠 B 欄為 1、3、5、7，外側欄為 2、4、6、8；格中心距手臂軸心朝使用者 F = 75／110／145／180 mm，沿長邊距 arm1 軸心 L = 235（靠 B 欄）／270 mm（外側欄），即 world x 約 0.135／0.170（模擬為 0.1675 單號、0.1325 雙號，兩欄對調）。arm2 的 8 格與兩臂的 B 區都已示教（扭力關閉、手扶），實物 8 格都碰得到。**2026-11-12 階段 C 已套用**（evidence/phase_c_20261111/）：模擬板 600×240 mm、兩臂軸心 world (±0.10, +0.125)、格位依實物編號（單號欄 x 0.135、雙號欄 0.170，列 y 0.050／0.015／-0.020／-0.055），A 區瓶蓋起點是格位對 x = 0 的鏡像，B 放置點 (0, 0)。`prefilled_slots` 預設 0，介面格位圖 1 號在左上，`vision_pkg` 新增 `slot_one_corner`（實機 `top_left`）。模型中只剩格位 8 與 cap_8 在吸盤朝下時搆不到（實物示教時吸盤約傾斜 9°），不套用位移 | WP6、WP11 |
| D4 | 對方程式碼授權（repo 無授權條款） | **只參照結構，自行撰寫** | WP2～WP5 |
| D5 | 吸盤確認方式：ESP32 只回傳命令回音，沒有真空感測 | 命令走 ESP32，實際結果由人工 token 確認 | WP4、WP12 |
| D6 | 定位誤差與成功率的驗收門檻 | 未定，不可自訂數字後宣稱通過 | H2 以後 |
| D7 | 模擬相機遮擋（C31）：相機改裝到手臂上、改用不遮擋的觀測姿態，或接受模擬只驗證取料點 | 只驗證取料點，WP7 維持 `BLOCKED` | WP7 |
| D8 | 實機急停心跳 `/safety/estop` 的來源：接實體急停的節點，或暫時手動發布（只代表終端存活，不反映急停） | **2026-11-10 使用者決定：獨立節點接實體急停，UI 不發送。** 節點與接線尚未完成，H4 以後仍 `BLOCKED` | H4 |

## 3. 衝突清單

### 3.1 規則與現有測試

| 編號 | 衝突 | 處理 |
|---|---|---|
| C1 | `AGENTS.md` 禁止逾時後重送；測試 `TimeoutLatchesAndNeverResends`、`LostReplyFaultsWithoutRetry` 也鎖定此行為 | 這兩項測試不可修改。任何重試都不適用於序列逾時 |
| C2 | READ 重試會違反 `MotorFaultStopsAllTraffic` | D2 未核准前不做。核准後才調整此測試，且需保留「連續失敗仍鎖定」的情境 |
| C3 | 清除韌體緩衝：送空行可能**執行**殘留的完整命令（如 `HOME,arm1`），也會產生錯誤回覆 | 已處理：開埠時送 96 個 DEL，只清緩衝、不執行也不回覆；不改 `transact`。此修正是對 `BAD_CMD` 的推測，實機結果 `NOT_RUN` |
| C4 | `on_error` 想送 HOLD：排程執行緒可能仍持有序列連線；韌體的 HOLD 先 READ，馬達無回應時會失敗並清除 target 資格 | 先停排程，只在 `link_->healthy()` 時送一次，失敗僅記錄，不重試 |
| C5 | 不可放寬限位（`AGENTS.md`）；手臂休息姿態可能超出限位，`write()` 會立即故障 | 不放寬。啟動時檢查，超出就拒絕 activate 並提示人工擺位 |
| C6 | 上游 `vision_interfaces` 不可改；任務層需要時間戳，服務回覆沒有 | 不改介面，由 gateway 對應同時段 topic 或影像證據 |
| C7 | `third_party/` 不可修改 | 需要時複製到 `src/`，並記錄來源 |

### 3.2 對方與本地不相容

| 編號 | 對方 | 本地 | 處理 |
|---|---|---|---|
| C8 | `move_pose` 用姿態 IK 與 `GetCartesianPath`，假設可維持吸盤朝下 | `kinematics.yaml` 為 `position_only_ik: true`，不約束姿態 | **不可照搬。** 沿用 `CadKinematics` 的朝下 IK，轉成關節目標；直線下降用取樣的關節路徑點 |
| C9 | TCP 為 `arm1_suction_tcp`，基座為 `arm1_base` | TCP 為 `arm1_tcp`，MoveIt 基座為 `arm1_base_link`；`arm1_base` 只有模擬 static TF | 運動 gateway 的目標一律是 `world`，由 WP7 的視覺 gateway 用 TF 轉換；實機 launch 補同一組 static TF。換算見 [COORDINATE_FRAMES.md](COORDINATE_FRAMES.md) |
| C10 | `/cm530/armN/enable|read|hold`、`/cm530/status` | `ros2_control`，沒有這些服務 | 不新增。扭力由 hardware component 狀態控制，健康狀態看 controller 與 hardware 狀態 |
| C11 | `BReservation`、`occupied.index(False)` | `ZoneManager` 有 token，`SlotManager` 要求連續 | 用本地。`ZoneManager` 需要新增從 journal 還原的 API 並補測試 |
| C12 | `dual_arm_demo.yaml` 的扁平 `armN.*` 參數 | `runtime.json`（模擬）、`calibration.yaml`（實機） | 任務參數放新的 `config/{sim,hardware}/coordinator.yaml`，關節校正不重複存放 |
| C13 | 圓片 2 mm 厚、半徑 10 mm | `runtime.json` 瓶蓋高 10 mm | 用本地 |
| C14 | 雙臂輪流 | demo 有 `move_pair` 並行 | 新節點採輪流，較保守；需求不要求同時動作 |
| C15 | 取消時直接呼叫 bridge stop | MoveIt 取消由 JTC 處理 | 需實測 JTC 取消後確實停止，列入 WP5 的測試 |

### 3.3 本地內部

| 編號 | 衝突 | 處理 |
|---|---|---|
| C16 | `dual_arm.srdf` 的 home named state 由模擬 `runtime.json` 生成，實機 launch 也讀同一份 | 實機 coordinator **不可使用 named state**，HOME 由 `calibration.yaml` 與 `expected_home` 換算 |
| C17 | 修改 URDF 限位或 `<ros2_control>` 要同時改 `generate_cad_robot.py` 與 xacro；SRDF 由 `validate_model.py` 產生；`integrate_description.py` 不可執行 | 盡量不動模型。先前「拿掉 velocity 狀態」的建議**撤回**，改用下一項 |
| C18 | 速度差分抖動 | mock 夾具已用 `stopped_velocity_tolerance: 0.5`。實機 `controllers_file` 比照並依實測設定；`on_init` 維持要求 position + velocity |
| C19 | 夾具 goal tolerance 0.02 rad 小於 j2 實測誤差（最大約 0.036 rad） | 夾具不可當實機設定。實機值由量測決定 |
| C20 | 硬體 camera yaml 的 `frame_id` 與 `usb_cam` 不同，校正狀態會一直 `FAIL`；`reference_frame` 是 `arm1_base_link`，視覺輸出 `arm1_base` | 統一命名並補測試；只能在 WP7 改，實機校正欄位維持 null |
| C21 | Gazebo 吸盤命令要 `cap_N`，實機視覺不知道物件名稱；序號錯誤時無回覆 | gateway 內部在模擬時對應 cap 名稱，且一律有逾時 |
| C22 | `dual_arm_coordinator` 的 `package.xml` 依賴不足，`entry_points` 為空，`config/hardware` 不存在 | WP1 補齊 |
| C23 | `calibrate_caps` 預設 A 區 y<0，與目前模擬相反 | D0 定案前不使用預設值 |
| C24 | 新 coordinator 與舊 pipeline 都會使用 Gazebo 與相同 domain | 不同時執行，啟動前用 `pgrep -af 'gz sim'` 確認 |
| C25 | `SlotManager` 要求從格位 1 連續填放，但格位 1 在模型中搆不到；舊 pipeline 的 `PASS` 放的是格位 3、4 | WP6 不可放寬連續性。兩物體回歸以「格位 1、2 已占用」的起始紀錄放到 3、4，並在證據中註明；從空 C 區開始的流程在 D3 前照實記為 `FAIL`。**2026-11-12 階段 C 後已解決**：格位 1 可達，兩物體回歸與視覺取料都從空 C 區放到格位 1、2，連續性不變 |
| C26 | `Transfer` 每個循環都要求環境相機的 C 區計數等於紀錄，但模擬中環境相機因手臂遮擋只看到 4 顆（`sim_detection.json`） | WP7 需先確認 Home 姿態下計數是否正確。不可為了通過而移除這項檢查 |
| C27 | B 區已有物件時略過 arm1，`scene_remove_b_object` 會移除場景中不存在的物件 | WP3 已處理：沒有登錄過就不送移除 |
| C31 | 模擬相機固定在頭頂，兩臂在 Home 時擋住 C 區與部分 A 區（arm2 只找到 1 格，arm1 少看到 2 顆）；實機相機在手臂上，遮擋情況不同。環境相機也因 Gazebo 0.2 倍實時，取不滿定位場地所需的影像。2026-11-12 階段 C：arm1、arm2 模擬相機移到瓶蓋與格位群上方（x ±0.15，原 ±0.20），arm1 偵測誤差 1.15 mm → 0.70 mm（預算 1 mm），仍只看到 3 顆；arm2 找到 0 格 | 需使用者決定（D7）。在此之前區域與格位狀態用真值，取料點用視覺 |
| C32 | `safety_supervisor` 鎖定且控制器已停用後，手動 `switch_controllers --activate` 仍能啟動控制器，`/safety/status` 繼續回報 `controllers_stopped: true`（修正前的紀錄：`docs/evidence/safety_order/`） | 已修正（`docs/evidence/c32/`，只驗證 mock）。鎖定期間每 0.2 秒檢查控制器，發現啟動就再停用，約 0.3 秒內停下；狀態改為實際結果。這段空窗仍在，手動切換依然禁止 |
| C30 | 模擬中 8 個瓶蓋起始位置只有 cap_3～6 在 arm1 朝下 IK 範圍內（`docs/evidence/wp6/03_analysis.txt`），目前佈局無法搬完八件。2026-11-11 介面階段 3 實測又遇到一次：同一模擬第三次取料，手臂 1 下降到 (-0.14, 0.035) 的瓶蓋時肘關節到 1.5 rad 限位，停在 16.6 mm 外，之後回 HOME 因起始狀態超出限位無法規劃（evidence/hmi/stage3/）。**2026-11-12 階段 C 後**：瓶蓋起點改為格位鏡像，8 個中 7 個可達（cap_8 不可達）；八物體回歸從空 C 區連續放完格位 1～7，第 8 件因格位 8 不可達而 FAULT（evidence/phase_c_20261111/batch/） | 不可靠放寬限位來通過。格位 8 實物示教時吸盤約傾斜 9°；要讓模擬放滿 8 格需要放寬「吸盤朝下」的容差或改姿態，由使用者決定 |
| C29 | Coordinator 被強制結束後，已送出的軌跡不會停止。Gazebo 實測手臂又動了約 22 秒、0.26 rad，期間 MoveIt 拒絕新軌跡 | WP9 要在 coordinator 失效時停用 arm controllers。實機放行前必須完成 |
| C28 | Gazebo 吸盤要求橫向誤差 1 mm 以內，但模擬視覺的 arm1 最大誤差紀錄為 1.09 mm（`sim_coordinate_validation.json`） | 已處理：到位容差收緊為 0.5 mm 後，視覺取料連續 3 次通過。外掛的容許值沒有放寬 |

## 4. 工作包

依序執行。每項完成才進下一項，進度寫在第 6 節。

### WP0 基準線

重建後重跑既有檢查，取得修改前的基準，失敗也要保留紀錄。內容：`bash scripts/build.sh`、coordinator 單元測試、`cm530_hardware` 單元測試、`scripts/test_cm530_mock.py`、兩物體 pipeline。

**完成條件：** 結果存到 `docs/evidence/roadmap_baseline/`。與 `PROGRESS.md` 不符的項目要列出，例如 `cm530_hardware` 紀錄為 33 項測試，原始碼靜態計得 29 個 `TEST` 巨集，要以實際執行數為準。

### WP1 介面與套件骨架

新增 `src/dual_arm_interfaces`（`ConfirmStep.srv`、`ManualXY.srv`）。補 `dual_arm_coordinator` 的依賴、`entry_points`、`config/sim/coordinator.yaml`。硬體設定用空值模板，載入時拒絕。

**處理衝突：** C12、C22。**完成條件：** 全部建置通過，舊 pipeline 不受影響。

### WP2 流程層（不含 ROS）

建立 `workflow/arm1_workflow.py`、`arm2_workflow.py`、`transfer.py` 與 `journal.py`，IO 用注入。擴充 `ZoneManager` 的還原功能。

測試至少涵蓋：取消、吸取或釋放失敗、視覺無效、B 區被占用、C 區計數不符、重啟後未完成、設定指紋不符、token 過期、格位不連續。

**處理衝突：** C11、C13、C14。**完成條件：** 假 IO 測試全部通過，且不 import `rclpy`。

### WP3 運動 gateway

建立 `gateways/motion.py`：朝下 IK、關節目標規劃、取樣下降、`/check_state_validity`、PlanningScene 附掛與卸除、到位確認（連續 N 筆新 joint state 在容差內）。

**處理衝突：** C8、C9、C16。**完成條件：** mock 或 Gazebo 中到達指定點，TCP 姿態與位置誤差都有紀錄。

### WP4 吸盤 gateway

`gateways/gripper.py` 提供 `gazebo` 與 `manual_token` 兩種後端，`auto_confirm` 在實機模式必須拒絕。

**處理衝突：** C21。**完成條件：** 單元測試涵蓋逾時、錯誤回覆、實機拒絕 auto_confirm。

### WP5 Coordinator 節點

建立 `coordinator_node.py`：`/dual_arm/start|cancel|confirm|recover`、`/dual_arm/status`（transient local）、`/handoff/b_state`、`/dual_arm/permit`、背景工作執行緒、watchdog、啟動一致性檢查。新增 `demo_pick_place.launch.py`。

**處理衝突：** C10、C15。**完成條件：** 模擬中驗證取消後手臂確實停止；重啟後要求復歸。

### WP6 模擬回歸

用真值目標提供者（不經視覺）跑兩物體，再跑八物體；故障情境：取消、釋放失敗、急停心跳中斷。

**處理衝突：** C24、C25。格位 1 依 D3，失敗就照實記錄為 `FAIL`。**完成條件：** 兩物體 `PASS`；八物體有結果和證據。通過後才可討論退役舊 pipeline。

### WP6S 加快模擬速度（使用者要求）

WP6 完成後、WP7 之前執行。目標是單件搬運時間至少減少 50%，以兩物體回歸（WP6，約 12.5 分鐘）為比較基準。

先量測各階段耗時，再調整模擬用的 `speeds`、`runtime.json` 與接觸段參數，兩者要保持一致。只改模擬設定，實機模板維持空值，第一次實機動作仍由比例 0.05 起步。放寬 URDF 或 `joint_limits.yaml` 的限位需要使用者同意。

**完成條件：** 兩物體回歸 `PASS`，且總時間與基準比較減少至少 50%；達不到時照實記錄並說明瓶頸。

### WP7 視覺 gateway

建立 `gateways/vision.py`：呼叫 `vision_interfaces` 服務、校正有效性閘門、影像時效、座標範圍檢查、TF 轉換；Home 穩定後才查詢。修正 `frame_id`。

**處理衝突：** C6、C9、C20、C23。**完成條件：** 模擬中視覺驅動搬運，並和 Gazebo 真值比較誤差；模擬校正無效時會被拒絕。

### WP8 驅動強化

依序：

1. 啟動時檢查休息姿態是否在限位內（C5）。
2. 開埠後的輸入清除（C3）。
3. `on_error` 的單次 HOLD（C4）。
4. READ 有限重試：**D2 核准後才做**（C2）。

硬體用 `controllers_file` 範本維持 null 或 NaN，載入時拒絕（C18、C19）。

**完成條件：** WP0 基準線的全部既有測試（除 D2 明確核准的變更外）與新增測試通過，`test_cm530_mock.py` 通過，ASan/UBSan、TSan 通過。`AGENTS.md` 指定的 Trail of Bits 技能不可用時，記為 `NOT_RUN`。

### WP9 安全監控

新增 `safety_supervisor`：`/safety/estop` 心跳、coordinator permit 時效，失效時停用 arm controllers。這是軟體互鎖，不取代實體急停。

**完成條件：** mock 中驗證心跳中斷會停止動作，且需要明確復歸。

### WP10 操作工具

新增 `operator_console`、`manual_xy`（預設只規劃）、`cm530_probe`（唯讀）、校正工作表檢查（離線，不開序列埠，輸出候選值但不寫入 `calibration.yaml`）。

**完成條件：** 單元測試涵蓋拒絕情境；確認 probe 只送唯讀命令。

### WP11 幾何與碰撞（依 D0、D3）

建立經驗證的碰撞模型，納入平台、泡棉、相機支架；依決策處理格位 1。會變動模型，**改完要重跑全部模型檢查**（C17）。

### WP12 ESP32（依 D5）

協定來源：[ray000518/micro-ros](https://github.com/ray000518/micro-ros) commit `0c28c7f`，只參照介面，不複製韌體。經 micro-ROS agent（序列埠）連線，與 CM-530 分開。

| Topic | 型別 | 內容 |
|---|---|---|
| `/suction_command` | `std_msgs/Int32` | 0 全關；1／2 模組 1 吸取／釋放；3／4 模組 2 吸取／釋放；其他值視同全關 |
| `/suction_status` | `std_msgs/Int32` | 動作後回傳收到的命令值，未知命令回 0 |

**`/suction_status` 只是命令回音，不是真空感測**，不能當作吸附確認（同 ACK ≠ 到位）。需求書要求的吸附確認與故障回報，韌體都沒有提供。

新增 `Esp32Suction` 後端：依手臂與動作發布命令，等待相符的回音（有逾時），再由人工 token 或感測確認實際結果。任務進入 FAULT 時不可自動送 0，關泵會讓持有的物件掉落。

**完成條件：** 單元測試涵蓋回音相符、回音為 0、無回音逾時、實機模式組態；以替身節點驗證 topic 接線。真正的 ESP32 `NOT_RUN`。

**需現場確認：** 模組 1 對應哪支手臂、繼電器是否高電位觸發（低電位觸發時開機就會作動）、吸取後要等多久才建立真空、GPIO5 開機時的訊號是否讓閥誤動作。

### WP13 文件

補 `TEST_PLAN.md`、`ORIN_DEPLOYMENT.md`，並更新 `ROS_INTERFACES.md`。

## 5. 實機階段（由現場人員執行）

AI 不可自行執行，要由現場人員明確要求並完成出力前檢查（[HARDWARE_TEST_GUIDE.md](HARDWARE_TEST_GUIDE.md)）。團隊成員都是同等層級，現場任何成員都可以要求，不需要另外找人授權。H4 以後目前做不了，是因為程式還沒完成（D8、coordinator 拒絕實機模式），不是權限問題。

另有「HOME 定位」：P0、H0 當天通過後，現場可隨時用韌體 `HOME` 讓手臂回預設姿勢（例如調整相機），步驟見手冊。

| 階段 | 內容 | 前置 |
|---|---|---|
| H0 | 唯讀連線，量測迴圈率 | WP8 |
| H1 | 扭力關閉下手動確認 j1、j2，解決 D0、D1；確認急停、ID 15 線材、Moving Speed | H0 |
| H2 | 三組校正樣本、獨立姿態尺量，填入 `calibration.yaml` | H1、D6 |
| H3 | 單軸 ±10 raw，確認方向與穩態誤差，和 H2 互相驗證 | H1 |
| H4 | arm1 關節空間，比例 0.05 | H3 |
| H5 | 懸停目標上方、尺量；下降不接觸 | H4 |
| H6 | 相機實體校正，單件 A→B（人工吸盤） | H5、WP7 |
| H7 | arm2 單件 B→C、雙臂 A→B→C | H6 |
| H8 | 連續八件，逐步提速 | H7 |

## 6. 進度表

接手者完成每項工作後更新此表，並同步 `PROGRESS.md`、`TEST_REPORT.md`、`RESUME.md`。

| 工作 | 狀態 | 證據 | 備註 |
|---|---|---|---|
| WP0 基準線 | `PASS` | `docs/evidence/roadmap_baseline/` | 2026-11-09，commit `c7dfba3`。cm530 實際 29 個 gtest；Gazebo 關閉未用相同方法重測 |
| WP1 介面骨架 | `PASS` | `docs/evidence/wp1/` | `entry_points` 目前只有 `check_task_config`，節點於 WP5、WP10 再加。硬體模板載入時被拒絕 |
| WP2 流程層 | `PASS` | `docs/evidence/wp2/` | 假 IO 測試，尚未接 ROS。流程不做等待輪詢，觀測不符即 FAULT；若 WP7 需要等待，參數要另行取得依據 |
| WP3 運動 gateway | `PASS` | `docs/evidence/wp3/` | 只驗證 MoveIt mock，沒有物理與實機。接觸段必須從目標正上方開始。`mock_components` 的微米級誤差不代表定位精度 |
| WP4 吸盤 gateway | `PASS` | `docs/evidence/wp4/` | 用假回覆和替身節點驗證，尚未對接真正的 Gazebo 外掛（WP6）。`locator` 由 WP5、WP6 提供 |
| WP5 Coordinator | `PASS` | `docs/evidence/wp5/` | Gazebo 真值。階段 C 後從空 C 區開始（`prefilled_slots` 0）；之前起始格位 1、2 視為已占用（C25）。實機模式刻意拒絕啟動，待 WP7、WP9。`demo_pick_place.launch.py` 已實跑一輪與兩輪 `PASS`（`docs/evidence/docs_audit/`、`readme_images/`） |
| WP6 模擬回歸 | `PASS` | `docs/evidence/wp6/` | 兩物體與故障情境 `PASS`。階段 C 後八物體從空 C 區放完 7 件，第 8 件因格位 8 不可達而 FAULT（`FAIL`，C30）；之前是格位 1 不可達。舊 pipeline 暫不退役 |
| WP6S 加快模擬速度 | `FAIL` | `docs/evidence/wp6s/`、`docs/evidence/wp7/15_timing_compare.txt` | 目標 −50%。最終參數（到位容差 0.5 mm）為 727.6 s → 373.9 s（−48.6%）；收緊前單次 −51.6%。移動比例已達 URDF 上限，接觸比例還能調高。兩物體與故障情境已用最終參數重跑 `PASS`；舊 pipeline 兩物體也在此速度 `PASS`（`docs/evidence/docs_audit/`） |
| WP7 視覺 gateway | `BLOCKED` | `docs/evidence/wp7/` | 取料點由視覺決定 `PASS`（修正後連續 3 次，校正無效會被拒絕）。區域與格位仍用真值，等 D7。實機 `frame_id` 不一致（C20）尚未處理 |
| WP8 驅動強化 | `PASS` | `docs/evidence/wp8/` | 第 1～3 項與 controllers 模板完成，Mock Serial 驗證。第 4 項（READ 重試）等 D2。`c-review` 需要此環境沒有的 Workflow 工具，`NOT_RUN`。實機 `NOT_RUN` |
| WP9 安全監控 | `PASS` | `docs/evidence/wp9/` | MoveIt mock 驗證，C29 由 22 秒縮短到約 1.2 秒。這是軟體互鎖，不取代實體急停。`hardware.launch.py` 在 `enable_motion` 時自動帶上；啟動時若心跳尚未到達會先鎖定，需 `/safety/reset`。實機與 Gazebo 物理 `NOT_RUN`，實機急停心跳來源尚未存在 |
| WP10 操作工具 | `PASS` | `docs/evidence/wp10/` | Mock Serial 與 MoveIt mock。`manual_xy` 是命令列工具，WP1 定義的 `ManualXY.srv` 目前沒有使用者。實機校正工作表的門檻等 D6。2026-11-10 新增 `fit_axis_circle`（畫圓找 j1 軸心，只產生報告），單元測試 PASS，實際量測 `NOT_RUN` |
| WP11 幾何碰撞 | `NOT_RUN` | `docs/evidence/phase_c_20261111/` | 場地幾何已依 2026-11-11 實測更新（階段 C，D3）：板 600×240 mm、軸心在板外 5 mm（另一次量到 15 mm，未定）、格位與編號；模型檢查、t1、t2 已重跑。驗證過的碰撞模型（平台、泡棉、相機支架）尚未建立。格位位移研究是舊配置的工具，已從 t1 移除 |
| WP12 ESP32 | `PASS` | `docs/evidence/wp12/` | 後端以替身節點驗證。真正的 ESP32 `NOT_RUN`，模組對應、真空時間等現場確認項目見 `ORIN_DEPLOYMENT.md` 第 6.1 節 |
| WP13 文件 | `PASS` | `docs/evidence/wp13/` | `TEST_PLAN.md`、`ORIN_DEPLOYMENT.md`、`ROS_INTERFACES.md`；部署步驟尚未實際執行 |
| H0～H8 | 見 `evidence/hardware/` | `docs/evidence/hardware/` | 由現場人員執行。2026-11-11：P0、H0 `PASS`，H1、V0 進行中，E0、H2、H3 `NOT_RUN`，H4 以後 `BLOCKED`（D8 未實作） |
