# 實機 Prototype 模式設計（2026-11-13）

## 目的

讓實機先**完整跑一次流程**：環境相機（env_scene）偵測瓶蓋座標與 C 格占用 → MoveIt 規劃 → Arm 1 到 A 區吸取 → 放到 B 區交接 → Arm 2 從 B 區吸起 → 放進空的 C 格。使用者 2026-11-13 決定：**不要求精準，吸不到也沒關係**，重點是整條流程會動；急停只有 CM-530 電源開關，沒有時間做其他硬體接線（D8 心跳節點暫不做）。

## 目標、非目標、反目標

- 目標：一個可切換的「實機 Prototype」模式，在操作介面選得到，也能用一條 launch 指令啟動；開了就能從頭跑到尾。
- 非目標：定位精度、成功率、D6 門檻、H2 正式校正、D8 急停節點、碰撞模型（WP11）。
- 反目標（就算能動也算失敗）：
  - 放寬到嚴格模式（現有「實機唯讀」「實機動作」）的檢查；嚴格模式的行為必須一模一樣。
  - prototype 的估計值寫進正式的 `calibration.yaml`、`config/hardware/coordinator.yaml`、`controllers_hardware.template.yaml`。
  - 看不出目前跑的是 prototype（介面、日誌、證據都要標明）。

## 做法（使用者選 A，並要求可切換）

| 做法 | 取捨 | 結果 |
|---|---|---|
| A. 另一套 prototype 設定 + 開關 | 嚴格路徑不動；估計值集中、標明；要多維護一套檔案 | **採用**，加上操作介面的模式切換 |
| B. 填滿正式設定、刪掉檢查 | 改最少；嚴格路徑消失，量測值與估計值混在一起 | 不採用 |
| C. 模擬 coordinator 設定接實機 | 綁 Gazebo 真值與模擬相機，要拆的更多 | 不採用 |

## 設計

### 1. 設定檔（全部新增，檔頭註明 PROTOTYPE、數值來源）

- `src/cm530_hardware/config/calibration_prototype.yaml`
  - `status: PASS`、`evidence_kind: physical`、`hardware_use_allowed: true`、`moving_speed_verified: true`：讓驅動的出力閘門通過（驅動 C++ 不改）。
  - 零點、方向：取 `config/sim/runtime.json` 的 `raw_at_cad_zero` 與 `direction`（H1 讀值支持的估計：j1 arm1 192.3、arm2 512；j2～j4 631.35／699.55／512；方向全 +1）。
  - 上下限：URDF 關節限位換算成 raw，再夾在 0～1023。
  - `max_step_raw`：取小值（建議 20），讓每個控制週期的目標變化受限，彌補 Moving Speed 上電可能是 0（最高速）。
- `src/dual_arm_controllers/config/controllers_prototype.yaml`：從 `controllers_hardware.template.yaml` 複製，容差放寬（例如 goal 0.15 rad、`goal_time` 10 s、`stopped_velocity_tolerance` 0.2），讓 `require_measured_tolerances` 通過、軌跡不會因誤差被中止。
- `src/dual_arm_coordinator/config/prototype/coordinator.yaml`
  - `mode: prototype`（第三種模式，與 simulation、hardware 並列；實作計畫的調整）、`evidence_kind: prototype_estimate`、`home_source: calibration`。
  - 速度、高度、區域、格位、動作參數：取模擬設定（`config/sim/coordinator.yaml`，場地已是 11-11 實測），速度可再降。
  - `b_pick_tolerance_m` 放寬（建議 0.05）。
  - `gripper.backend: esp32`、`auto_confirm: true`、`esp32_modules` 先猜 arm1: 1、arm2: 2（E0 未測，吸錯手臂改這兩個數字）。

### 2. 程式改動（只在 prototype 時生效）

- `task_config.py`：新增 `prototype` 模式規則；`auto_confirm: true` 只允許 simulation 與 prototype。hardware 規則不變。`create_gripper` 同步。
- `coordinator_node.py`：第 117 行的拒絕改成「mode 不是 simulation 或 prototype 時拒絕」。啟動時日誌明確印出 PROTOTYPE。
- `hardware.launch.py`：新增 `require_estop`（預設 true）傳給 `safety_supervisor`。嚴格模式預設值不變。
- 新增 `dual_arm_bringup/launch/hardware_prototype.launch.py`：一次啟動
  - `hardware.launch.py`（`enable_motion:=true`、prototype 校正檔與 controllers 檔、`require_estop:=false`）；
  - `vision_hardware.launch.py`；
  - `coordinator_node`（prototype 設定、`observation_source:=env_scene`）。
  - 參數：`port`、相機裝置、`cycles`（預設 1）、`journal_path`。
  - ESP32 的 micro-ROS agent 照 ORIN_DEPLOYMENT 6.1 另外開（不放進 launch）。
- 操作介面：`Mode` 新增 `HARDWARE_PROTOTYPE = '實機 Prototype'`（`is_hardware`、`has_torque_step` 都是 true；由 URDF 中的 `calibration_prototype` 檔名辨識），開放開始任務等按鈕，`build_plan` 對它用 `hardware_prototype.launch.py`。介面頂部要明顯標示 PROTOTYPE。上扭力、`/safety/reset`、開始任務的流程與實機動作相同。

### 3. 操作流程（寫進 HARDWARE_TEST_GUIDE 新的「Prototype 模式」一節）

1. 一人只守 CM-530 電源開關。手臂先扶到 HOME 附近（照「HOME 定位」）。
2. 開 ESP32 agent → 介面選「實機 Prototype」啟動（或 `ros2 launch dual_arm_bringup hardware_prototype.launch.py port:=...`）。
3. 上扭力 → `/safety/reset` → 開始任務。
4. 結果與異常寫進 `docs/evidence/hardware/<日期>_PROTOTYPE/`，標明是 prototype，**不算任何 H 階段 PASS**。

### 4. 與 AGENTS.md 規則的衝突

AGENTS.md 規定「不可填假的校正值」「不可把模擬 HOME（`runtime.json`）複製到實機設定」。prototype 校正檔正是用 `runtime.json` 的估計值，這是使用者 2026-11-13 的決定。處理：正式的 `calibration.yaml` 仍保持空白；AGENTS.md 加一條例外，只限 `*_prototype.yaml` 與 `config/prototype/`，且檔頭必須標明是估計值。

## 驗證

- 單元測試：`task_config` 的 prototype 規則（嚴格設定照樣拒絕 auto_confirm）、coordinator 接受 prototype／仍拒絕無 prototype 的 hardware、HMI `build_plan` 的新模式。
- `hardware_prototype.launch.py --show-args` 可解析；prototype 設定檔能被 loader 載入、驅動 `motion_blockers()` 回空。
- Mock Serial 跑一次 prototype 流程（用 mock 校正檔替換，因為 `evidence_kind: physical` 不接受虛擬序列埠）。
- 既有測試全過，證明嚴格模式沒變。
- 實機：NOT_RUN，交給現場。

## 留給實作者的決定

- `max_step_raw`、controllers 容差、速度比例的具體數字（照上面的建議，偏保守）。
- 介面上 PROTOTYPE 標示的樣式（沿用現有的警示色）。
