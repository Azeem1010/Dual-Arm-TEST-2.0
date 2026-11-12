# 實機 Prototype 模式 Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 新增可切換的「實機 Prototype」模式，用估計值讓實機跑完 A → B → C 整個流程，嚴格模式完全不變。

**Architecture:** coordinator 設定新增第三種 `mode: prototype`（與 simulation、hardware 並列），各處檢查把它當成「放寬的實機」；另外準備 prototype 的馬達校正、controllers、coordinator 三份設定，由新的 `hardware_prototype.launch.py` 一次啟動；操作介面新增 `Mode.HARDWARE_PROTOTYPE`，由 URDF 中的 prototype 校正檔名辨識，並開放任務按鈕。

**Tech Stack:** ROS 2 Jazzy、Python（rclpy、pytest／unittest）、ros2_control、PyQt5 介面。

**Spec:** `dual_arm_ws/docs/superpowers/specs/2026-11-13-hardware-prototype-mode-design.md`

**設計調整（實作者的決定，已寫回 spec）：** spec 寫的是 `mode: hardware` + `prototype: true` 欄位；改成獨立的 `mode: prototype`，因為 `task_config._RULES`、`create_gripper`、`coordinator_node` 都已經用 `mode` 分支，加一種值比加一個旗標少改、也不會讓 hardware 規則出現例外。

## Global Constraints

- 嚴格模式（`mode: hardware`、介面「實機唯讀」「實機動作」、`hardware.launch.py` 預設參數）行為一模一樣；既有測試不得修改預期值。
- 正式檔案不動：`cm530_hardware/config/calibration.yaml`、`dual_arm_coordinator/config/hardware/coordinator.yaml`、`dual_arm_controllers/config/controllers_hardware.template.yaml`。
- prototype 檔案檔頭第一行：`# PROTOTYPE ESTIMATE (2026-11-13): not measured, not calibration evidence.`，接著寫數值來源。
- prototype 的 `evidence_kind`：coordinator 設定用 `prototype_estimate`；馬達校正檔用 `physical`（驅動與 `homes.py` 只接受 physical，不改 C++）。
- 介面與 coordinator 日誌都要看得到 `PROTOTYPE`。
- 所有使用者可見文字用繁體中文。
- AGENTS.md 第 28～29 行加例外：只限 `*_prototype.yaml` 與 `config/prototype/`，檔頭必須標明是估計值。

## Review Focus

1. 選了「實機動作」卻載入 prototype 校正檔：介面應顯示 Prototype（以 URDF 判斷），不可顯示成嚴格的實機動作 → Task 5 測 `mode_from_urdf`。
2. `mode: hardware` 的設定加上 `auto_confirm: true` 仍要被拒絕（task_config 與 `create_gripper` 兩處）→ Task 1。
3. prototype 校正檔的 `min_raw`／`max_raw` 必須涵蓋 `expected_home`，否則上扭力時 HOME 換算超限 → Task 3 測試。
4. `hardware_prototype.launch.py` 接 Mock Serial 時要能換成 mock 校正檔（`evidence_kind: physical` 不接受虛擬序列埠）→ Task 4。
5. prototype 模式下 `/dual_arm/go_home` 的 `home_problem` 走實機分支（不是模擬分支）→ Task 2。

---

### Task 1: coordinator 設定接受 `mode: prototype`

**Files:**
- Modify: `src/dual_arm_coordinator/dual_arm_coordinator/task_config.py`（`_RULES`、`_check_rules`）
- Modify: `src/dual_arm_coordinator/dual_arm_coordinator/gateways/gripper.py:238-244`（`create_gripper`）
- Test: `src/dual_arm_coordinator/test/test_task_config.py`、`src/dual_arm_coordinator/test/test_gripper.py`

**Interfaces:**
- Produces: `task_config.AUTO_CONFIRM_MODES = ('simulation', 'prototype')`；`_RULES['prototype'] = {'evidence_kind': 'prototype_estimate', 'home_source': 'calibration', 'backends': ('manual_token', 'esp32')}`。

- [ ] **Step 1: 寫失敗測試**（test_task_config.py，用既有的 filled hardware 文件 helper 改欄位）
  - `test_prototype_document_is_accepted`：mode `prototype`、evidence_kind `prototype_estimate`、backend `esp32`、auto_confirm true → `validate` 不丟例外。
  - `test_prototype_requires_prototype_evidence`：prototype + evidence_kind `physical` → 錯誤訊息含 `prototype requires evidence_kind=prototype_estimate`。
  - `test_prototype_refuses_gazebo_gripper`、`test_prototype_cannot_use_runtime_json_home`。
  - 既有 `test_hardware_refuses_auto_confirm` 不改，仍要過。
  - test_gripper.py：`test_prototype_allows_auto_confirm`（esp32 backend 建得起來）；既有 `test_hardware_refuses_auto_confirm` 不改。
- [ ] **Step 2:** `cd src/dual_arm_coordinator && python3 -m pytest -q test/test_task_config.py test/test_gripper.py` → 新測試 FAIL。
- [ ] **Step 3:** 實作：`_RULES` 加 prototype；`_check_rules` 與 `create_gripper` 的 auto_confirm 判斷改成 `mode not in AUTO_CONFIRM_MODES`（gripper 從 task_config import）；錯誤字串維持 `gripper.auto_confirm is simulation only` 改為 `gripper.auto_confirm is only for simulation or prototype`，並同步既有測試若比對了完整字串（只改字串，不改預期行為）。
- [ ] **Step 4:** 同上指令 → 全部 PASS。
- [ ] **Step 5:** Commit `Accept a prototype coordinator config with automatic suction confirmation`.

### Task 2: coordinator 以 prototype 模式啟動

**Files:**
- Modify: `src/dual_arm_coordinator/dual_arm_coordinator/coordinator_node.py:116-117`
- Test: `src/dual_arm_coordinator/test/test_coordinator_node.py`

**Interfaces:**
- Consumes: Task 1 的 `mode: prototype`。
- Produces: `RUNNABLE_MODES = ('simulation', 'prototype')`；prototype 啟動時 `get_logger().warning('PROTOTYPE mode: estimated calibration, no e-stop heartbeat, suction auto-confirmed')`。

- [ ] **Step 1: 寫失敗測試**：`test_prototype_config_is_not_blocked`——用 Task 3 之前可用的臨時 prototype 文件（tmp_path 寫 YAML），建構節點時不得出現 `BLOCKED`（可能因缺 calibration_path 等其他原因失敗，斷言例外訊息不含 `BLOCKED`，或照既有 `test_complete_hardware_config_is_still_blocked` 的寫法）。既有兩個 hardware BLOCKED 測試不改。
- [ ] **Step 2:** 跑 `python3 -m pytest -q test/test_coordinator_node.py` → FAIL。
- [ ] **Step 3:** 實作 `if self.config['mode'] not in RUNNABLE_MODES: raise RuntimeError(...)`（訊息不變），prototype 印 warning。`home_problem(..., self.config['mode'] == 'simulation')` 不改（prototype 走實機分支，Review Focus 5）。
- [ ] **Step 4:** 同上 → PASS；再跑整個 coordinator 測試 `python3 -m pytest -q test` → 全過。
- [ ] **Step 5:** Commit `Let the coordinator run a prototype config on hardware`.

### Task 3: 三份 prototype 設定與 AGENTS.md 例外

**Files:**
- Create: `src/cm530_hardware/config/calibration_prototype.yaml`
- Create: `src/dual_arm_controllers/config/controllers_prototype.yaml`
- Create: `src/dual_arm_coordinator/config/prototype/coordinator.yaml`
- Modify: `src/dual_arm_coordinator/setup.py`（安裝 `config/prototype/*.yaml`，比照 `config/sim`）；確認 `cm530_hardware`、`dual_arm_controllers` 的 CMakeLists 會安裝整個 config 目錄，否則補上
- Modify: `AGENTS.md:28-29`
- Test: `src/dual_arm_coordinator/test/test_task_config.py`（新增）、`src/dual_arm_coordinator/test/test_home_pose.py` 或新檔 `test/test_prototype_files.py`

**Interfaces:**
- Produces: 三個檔案路徑（Task 4 用）；`share/dual_arm_coordinator/config/prototype/coordinator.yaml`。

數值（來源寫進檔頭）：
- 校正：`status: PASS`、`evidence_kind: physical`、`hardware_use_allowed: true`、`moving_speed_verified: true`、`max_step_raw: 20`；`expected_home` 照正式檔；`zero_raw` = `config/sim/runtime.json` 的 `raw_at_cad_zero`、`direction` = 其 `direction`；`min_raw`／`max_raw` = `zero_raw ± limit_rad / (300° 每 1024 tick 的弧度)`，limit 取 URDF（j1～j3 ±1.5、j4 −1.5～+1.65），四捨五入後夾在 0～1023。
- controllers：複製 template，`goal_time: 10.0`、`stopped_velocity_tolerance: 0.2`、每關節 `goal: 0.15`。
- coordinator：照 `config/sim/coordinator.yaml`，改 `mode: prototype`、`evidence_kind: prototype_estimate`、`home_source: calibration`、`journal_path: ~/.ros/dual_arm/prototype_journal.json`、`speeds` 0.3／0.2／0.3、`zones.b_pick_tolerance_m: 0.05`、`motion.tcp_error_limit_m: 0.01`、`gripper.backend: esp32`、`auto_confirm: true`、`vacuum_settle_s: 1.0`、`esp32_modules` arm1: 1、arm2: 2（註明 E0 未測）。

- [ ] **Step 1: 寫失敗測試**（`test/test_prototype_files.py`）
  - `test_prototype_coordinator_loads`：`task_config.load(<repo>/config/prototype/coordinator.yaml)['mode'] == 'prototype'`。
  - `test_prototype_calibration_gives_homes`：`homes.load_homes({'home_source': 'calibration', 'mode': 'prototype'}, calibration_path=<calibration_prototype.yaml>)` 回兩臂四關節，且每個 `expected_home` raw 落在該關節 `min_raw..max_raw`（Review Focus 3）。
  - `test_prototype_calibration_matches_runtime_json`：zero_raw、direction 與 runtime.json 相同。
  - `test_prototype_files_are_labelled`：三個檔案第一行都是 Global Constraints 的檔頭。
  - `test_strict_files_unchanged`：正式 `calibration.yaml` 仍 `status: NOT_RUN`、hardware coordinator 仍載入失敗。
- [ ] **Step 2:** 跑 → FAIL（檔案不存在）。
- [ ] **Step 3:** 建三個檔案、setup.py 安裝、AGENTS.md 加一行例外。
- [ ] **Step 4:** 跑 coordinator 全部測試 → PASS；WSL 跑 `colcon build --base-paths src --packages-select dual_arm_coordinator cm530_hardware dual_arm_controllers` → 成功，`install/` 內三檔都在。
- [ ] **Step 5:** Commit `Add the prototype calibration, controllers and coordinator settings`.

### Task 4: launch 檔

**Files:**
- Modify: `src/dual_arm_bringup/launch/hardware.launch.py`（新參數 `require_estop`，預設 `true`，傳給 `safety_supervisor` 的 `require_estop` 參數）
- Create: `src/dual_arm_bringup/launch/hardware_prototype.launch.py`

**Interfaces:**
- Consumes: Task 3 的三個檔案（用 `FindPackageShare` 找）。
- Produces: `hardware_prototype.launch.py` 參數：`port`（必填，預設 `/dev/ttyUSB0`）、`env_cam_device`、`arm1_cam_device`、`arm2_cam_device`、`calib_dir`、`cycles`（預設 `1`）、`journal_path`（預設空）、`use_mock_serial`（預設 `false`）、`calibration_file`（預設 prototype 校正檔）。內容：include `hardware.launch.py`（`enable_motion:=true`、`controllers_file`=prototype、`require_estop:=false`、轉傳 port／use_mock_serial／calibration_file）＋ include `vision_hardware.launch.py`（轉傳相機與 calib_dir）＋ `coordinator_node`（`config_path`=prototype、`calibration_path`=同一個 calibration_file、`observation_source: env_scene`、`cycles`、`journal_path`、`require_safety: true`）。檔頭 docstring 寫 PROTOTYPE 與「CM-530 電源開關是唯一急停」。

- [ ] **Step 1:** WSL：`ros2 launch dual_arm_bringup hardware.launch.py --show-args` 現在沒有 `require_estop`（確認起點）。
- [ ] **Step 2:** 實作兩個檔案。
- [ ] **Step 3:** WSL 重建 `dual_arm_bringup`；`--show-args` 兩個檔案都解析成功，hardware.launch.py 的 `require_estop` 預設 `true`；存 log 到 `docs/evidence/prototype_mode_20261113/`。
- [ ] **Step 4:** Commit `Add the prototype hardware launch and an optional e-stop heartbeat`.

### Task 5: 操作介面「實機 Prototype」

**Files:**
- Modify: `src/dual_arm_hmi/dual_arm_hmi/model/state.py`（`Mode`）
- Modify: `src/dual_arm_hmi/dual_arm_hmi/sources/ros_parse.py:65-79`（`mode_from_urdf`）
- Modify: `src/dual_arm_hmi/dual_arm_hmi/sources/live_source.py:124-126,152`（`_wired`）
- Modify: `src/dual_arm_hmi/dual_arm_hmi/launcher/profiles.py:88-117`（`build_plan`、`_hardware_plan`）
- Modify: 介面頂部狀態列（`state.py` 的 status cell，約 504 行）：prototype 顯示 `實機 Prototype`，用 `Level.HARDWARE` 色
- Test: `test/test_state.py`、`test/test_ros_parse.py`、`test/test_profiles.py`、`test/test_live_source.py`

**Interfaces:**
- Produces: `Mode.HARDWARE_PROTOTYPE = '實機 Prototype'`；`Mode.is_hardware`、`Mode.has_torque_step` 對它為 true；新屬性 `Mode.allows_hardware_tasks`（只有 prototype 為 true）；`PROTOTYPE_CALIBRATION_MARK = 'calibration_prototype'`（在 URDF 字串中出現即判定 prototype）。

- [ ] **Step 1: 寫失敗測試**
  - test_ros_parse：`mode_from_urdf` 的 URDF 含 `cm530_hardware/CM530SystemInterface` 與 `calibration_prototype.yaml` → `HARDWARE_PROTOTYPE`（有無 arm controllers 都是）；不含 → 原本結果（Review Focus 1）。
  - test_profiles：`build_plan(Mode.HARDWARE_PROTOTYPE, ...)` 指令含 `hardware_prototype.launch.py` 與 `port:=`，**不含** `vision_hardware.launch.py` 另開一份；沒 port 時同樣被拒；domain 用 hardware 的。
  - test_live_source：prototype 模式 `_wired` 含 `START_TASK`、`SAFETY_RESET`、`CANCEL_TASK`；`HARDWARE_MOTION` 仍只有 `STOP`。
  - test_state：prototype 的頂部狀態格文字是 `實機 Prototype`；prototype 且 `hardware_blocked_reason=''` 時開始任務不被擋。
- [ ] **Step 2:** `cd src/dual_arm_hmi && python3 -m pytest -q test` → 新測試 FAIL。
- [ ] **Step 3:** 實作。ros_source 產生 snapshot 時，prototype 模式的 `hardware_blocked_reason` 設 `''`；`profiles._hardware_plan` 對 prototype 改用 `hardware_prototype.launch.py`，把 `port`、`calibration_file`（若設定檔有）、相機裝置與 `vision_calib_dir`（作 `calib_dir`）傳進去。模式選單自動列出新 enum（確認 UI 沒有寫死清單；有的話加入）。
- [ ] **Step 4:** 同上 → 全部 PASS（既有 298 項不得改預期）。
- [ ] **Step 5:** Commit `Add the hardware prototype mode to the operator UI`.

### Task 6: Mock Serial 走完流程、全測試、文件

**Files:**
- Create: `docs/evidence/prototype_mode_20261113/README.md` 與 log
- Modify: `docs/HARDWARE_TEST_GUIDE.md`（新節「Prototype 模式」，放在 V1 之後；第 1 節表格加一列）、`docs/PROGRESS.md`、`docs/RESUME.md`、`docs/TEST_REPORT.md`、`docs/ROS_INTERFACES.md`（launch 表）、`docs/UI_PLAN.md`（第 9 節模式表）、`README.md`、`dual_arm_ws/README.md`、spec 的「設計調整」

- [ ] **Step 1:** WSL Mock Serial：`ros2 launch dual_arm_bringup hardware_prototype.launch.py use_mock_serial:=true calibration_file:=$PWD/src/cm530_hardware/test/fixtures/calibration_mock.yaml`（沒有相機時 env_scene 會報場地未定位，屬預期）。確認：coordinator 日誌有 `PROTOTYPE mode`、沒有 `BLOCKED`；`safety_supervisor` 不因心跳鎖定；`ros2 service call /safety/reset` 後 controllers active；`/dual_arm/go_home`（cleared true）能動。存 log。
- [ ] **Step 2:** 若 Step 1 因沒有 env_scene 結果無法開始任務，記錄為預期限制（任務要等實機環境相機），不為了測試加假資料。
- [ ] **Step 3:** WSL 全部單元測試：coordinator、hmi、cm530_hardware（colcon test）、vision_adapter → 全過，數字記入 TEST_REPORT。
- [ ] **Step 4:** 寫文件。HARDWARE_TEST_GUIDE 的 Prototype 節：前置（一人守 CM-530 電源開關、手臂扶到 HOME 附近、ESP32 agent 先開）、啟動（介面選「實機 Prototype」或 launch 指令）、上扭力 → `/safety/reset` → 開始任務、吸錯手臂改 `esp32_modules`、結果記到 `docs/evidence/hardware/<日期>_PROTOTYPE/`，**不算任何 H 階段 PASS**。
- [ ] **Step 5:** Commit `Record the prototype mode checks and document how to run it`，依使用者習慣推送到 origin main。
