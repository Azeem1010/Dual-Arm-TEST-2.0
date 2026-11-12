# 鏡頭分工調整 實作計畫

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal：** 任務判斷全部改由環境相機（`env_scene`）提供，兩顆手臂鏡頭降為監控，並由切換節點保證任何時刻最多一顆在串流。

**Architecture：** 上游 `env_scene` 以 submodule 匯入並複製到 `src/`。coordinator 新增 `env_scene` 觀測來源與「Arm 2 的 B 區吸取點」介面。`dual_arm_vision_adapter` 新增兩個節點：手臂鏡頭切換節點（啟動／結束 usb_cam 程序），以及 env_scene 橋接節點（把場景轉成既有的 `/vision/env/zone_state` 與 env 標定狀態，讓操作介面沿用）。操作介面顯示鏡頭輪流狀態。

**Tech Stack：** ROS 2 Jazzy、Python（rclpy、unittest/pytest）、usb_cam、OpenCV（上游）。

**Spec：** `docs/superpowers/specs/2026-11-12-camera-roles-design.md`

所有路徑相對於 `dual_arm_ws/`。開發環境是 WSL2 Ubuntu 24.04 + Jazzy；指令在 WSL 內執行（`AGENTS.md`）。

## Global Constraints

- `third_party/` 不可修改；上游以 submodule 加入、鎖版本、記錄到 `docs/sources.lock.json`，整合時複製到 `src/`。
- 上游 `vision_interfaces`、`env_scene_interfaces` 的欄位與服務名稱不可改。
- 任何啟動檔、操作介面設定或程序重啟情境，都不可同時讓兩顆手臂鏡頭串流；切換一律「先確認舊的已釋放，再開新的」。
- 手臂鏡頭的狀況（沒畫面、切換失敗）不可影響任務；coordinator 不得依賴切換節點。
- 環境相機結果只在 `success`、`scene.valid`、對應 `armN_valid`／`c_slots_valid` 皆為真，且 `coords_source ∈ {standard, measured}` 時採用；`estimated` 一律拒絕。
- coordinator 的實機模式維持 BLOCKED，本計畫不解除。
- 不填假的量測值；`config/hardware/coordinator.yaml` 新增欄位一律為 `null`。
- 狀態只能用 `PASS`、`FAIL`、`BLOCKED`、`NOT_RUN`；指令原始輸出放 `docs/evidence/camera_roles_20261112/`，失敗紀錄也要保留。
- 依使用者記憶：commit 直接在 `main` 並推送 `origin main`。

## Review Focus

1. **切換節點自己被重啟（respawn）時，前一個實例留下的 usb_cam 還在跑** — 新實例不可再開另一顆；應回報裝置被佔用並等待。測試：Task 5 `test_refuses_to_start_when_other_device_busy`。
2. **舊 usb_cam 收到 SIGTERM 不退出** — 逾時後 SIGKILL，確認群組消失與裝置釋放後才開新的；整段期間 `phase == 'switching'`。測試：Task 5 `test_escalates_to_sigkill_before_starting_next`。
3. **`/dual_arm/status` 在 coordinator 當掉後停更或來回快速變動** — 停更時保持目前鏡頭；短時間內多次變動只切到最後一個值，不會同時開兩顆。測試：Task 5 `test_stale_status_keeps_current`、`test_rapid_changes_never_overlap`。
4. **B 區看到 0 顆或 2 顆以上瓶蓋（含 Arm 1 放歪、旁邊掉一顆）** — Arm 2 不得吸取，任務停止並說明數量。測試：Task 3 `test_b_target_requires_exactly_one`。
5. **env_scene 在回應中途標定失效（`arm2_valid=false` 但 `arm1_valid=true`）** — A 區取料可繼續，B/C 判斷必須拒絕。測試：Task 3 `test_validity_is_checked_per_use`。

---

## 檔案結構

| 檔案 | 責任 |
|---|---|
| `third_party/env_camera_vision`（submodule） | 上游原樣 |
| `src/env_scene/`、`src/env_scene_interfaces/` | 上游複製，未修改 |
| `src/dual_arm_coordinator/dual_arm_coordinator/workflow/ports.py` | 新增 `TaskIO.b_pick_target()`、`WorkflowSettings.b_pick_tolerance` |
| `src/dual_arm_coordinator/dual_arm_coordinator/workflow/arm2_workflow.py` | Arm 2 改用量到的 B 區座標 |
| `src/dual_arm_coordinator/dual_arm_coordinator/gateways/env_scene.py`（新） | `EnvSceneObserver`：EnvScene → 各 View |
| `src/dual_arm_coordinator/dual_arm_coordinator/gateways/truth.py`、`vision.py` | 實作 `b_pick_target()`（回傳固定 `b_place`） |
| `src/dual_arm_coordinator/dual_arm_coordinator/coordinator_node.py` | `observation_source=env_scene` 接線 |
| `src/dual_arm_vision_adapter/dual_arm_vision_adapter/arm_camera_switch.py`（新） | 純邏輯 `ArmCameraSwitch` + ROS 節點 |
| `src/dual_arm_vision_adapter/dual_arm_vision_adapter/processes.py`（新） | 程序群組啟動／結束、裝置佔用檢查 |
| `src/dual_arm_vision_adapter/dual_arm_vision_adapter/env_scene_bridge.py`（新） | EnvScene → `ZoneState` 與 env 標定狀態 |
| `src/vision_pkg/vision_pkg/camera_launch.py`（新）、`launch/vision.launch.py`、`launch/arm_camera.launch.py`（新） | 單顆相機的啟動動作共用；手臂鏡頭最多一顆 |
| `src/dual_arm_bringup/launch/vision_hardware.launch.py`（新） | 實機視覺：環境相機 + env_scene + 橋接 + 切換節點 |
| `src/dual_arm_hmi/...` | 手臂鏡頭輪流狀態顯示、啟動改用新 launch |

---

### Task 1：匯入上游 env_camera_vision

**Files:**
- Create: `third_party/env_camera_vision`（submodule）、`src/env_scene/`、`src/env_scene_interfaces/`
- Modify: `docs/sources.lock.json`、`../.gitmodules`

**Interfaces:**
- Produces: `env_scene_interfaces/srv/GetEnvScene`（`scene: EnvScene`）、`env_scene_interfaces/msg/EnvScene`、`SceneObject`；服務 `/vision/env_scene/get_scene`、`/vision/env_scene/calibrate`（`std_srvs/Trigger`）。

- [ ] **Step 1：確認要鎖定的上游 commit。** 執行 `git ls-remote https://github.com/Azeem1010/env_camera_vision.git HEAD`。如果仍是 `6b059eb`，代表現場版本（A 區座標以黑框左緣為原點，見 spec 第 5 節）還沒推上 GitHub：**停下來回報使用者**，請上游推送後再繼續。使用者明確同意先用 `6b059eb` 時才可繼續，並在 `sources.lock.json` 註記「待更新為現場版本」。
- [ ] **Step 2：加入 submodule 並鎖版本。** `git submodule add https://github.com/Azeem1010/env_camera_vision.git dual_arm_ws/third_party/env_camera_vision`，checkout 到 Step 1 的 commit；在 `docs/sources.lock.json` 依既有格式新增一筆（url、commit、日期 2026-11-12）。
- [ ] **Step 3：複製套件到 `src/`。** `cp -r third_party/env_camera_vision/env_scene third_party/env_camera_vision/env_scene_interfaces src/`。不修改內容。
- [ ] **Step 4：建置並跑上游測試。**
  Run: `colcon build --symlink-install --packages-select env_scene_interfaces env_scene && (cd src/env_scene && python3 -m pytest -q -p no:cacheprovider)`
  Expected：建置成功、測試全部 PASS。輸出存到 `docs/evidence/camera_roles_20261112/env_scene_import.log`。
- [ ] **Step 5：核對座標定義。** 讀新版 `EnvScene.msg`、`SceneObject.msg`，確認 `x_mm/y_mm` 仍是 world（原點場地中心、x 由 A 往 C、y 遠離使用者）。如果新版改了定義，停下來回報，因為 Task 3 依賴這個定義。
- [ ] **Step 6：Commit。** `git add` 上述檔案；訊息 `Import env_camera_vision <commit> as env_scene`。

---

### Task 2：Arm 2 的 B 區吸取點改成可由觀測提供

**Files:**
- Modify: `src/dual_arm_coordinator/dual_arm_coordinator/workflow/ports.py`、`workflow/arm2_workflow.py`、`gateways/truth.py`、`gateways/vision.py`（`VisionPickObserver`、`VisionObserver`）、`coordinator_node.py`（`CoordinatorIO`）、`task_config.py`（`_SHAPE['zones']` 加 `b_pick_tolerance_m`，`_check_numbers` 要求 > 0）、`config/sim/coordinator.yaml`（`b_pick_tolerance_m: 0.02`）、`config/hardware/coordinator.yaml`（`b_pick_tolerance_m: null`）
- Test: `src/dual_arm_coordinator/test/test_workflow.py`、`test_task_config.py`、`test_truth.py`

**Interfaces:**
- Produces: `TaskIO.b_pick_target(self) -> PickView`（target frame，z = 瓶蓋頂）；`WorkflowSettings.b_pick_tolerance: float`（取自 `zones.b_pick_tolerance_m`）。
- `TruthObserver.b_pick_target()` 與 `VisionPickObserver.b_pick_target()` 回傳 `PickView(True, '', b_place[0], b_place[1], cap_top_z)`，模擬行為不變。

- [ ] **Step 1：寫失敗測試**（`test_workflow.py`，`World` 新增 `b_pick_target()`，預設回傳 `b_place`，可被測試覆寫）：
  - `test_arm2_picks_at_observed_b_position`：`b_pick_target` 回傳 `(b_place.x + 0.01, b_place.y, cap_top_z)`，跑一個物件；斷言 Arm 2 的 `move_to` 有到 `(b_place.x + 0.01, b_place.y, contact_z)`，Arm 1 的 B 區放置仍是 `b_place`。
  - `test_arm2_refuses_b_target_beyond_tolerance`：偏移 `b_pick_tolerance + 0.001` → FAULT，訊息含 `B pick target`，且 Arm 2 沒有任何 `move_to`。
  - `test_arm2_refuses_invalid_b_target`：`PickView(False, 'x')` → FAULT 含 `x`。
  - `test_arm2_preflight_uses_observed_b`：`check_reachable` 呼叫中包含量到的 B 點（approach 與 contact 兩個高度）。
  - `test_task_config.py`：缺少 `b_pick_tolerance_m` 或 ≤ 0 時 `validate` 回報錯誤。
- [ ] **Step 2：執行確認失敗。** Run: `(cd src/dual_arm_coordinator && python3 -m pytest -q -p no:cacheprovider test/test_workflow.py test/test_task_config.py)` Expected：新測試 FAIL（`b_pick_target` 未定義）。
- [ ] **Step 3：實作。** `Arm2Workflow.run()` 在 `CHECK_ZONES` 之後新增 `ctx.step(ARM, 'QUERY_B_TARGET')`，呼叫 `io.b_pick_target()`；檢查 `success`、數值有限、與 `settings.b_place` 的平面距離 ≤ `b_pick_tolerance`；高度檢查同 `Arm1Workflow._validated_target` 的 `pick_z_tolerance`。用量到的 xy 計算 `above_b`/`at_b`。錯誤訊息以 `B pick target` 開頭。其餘 observer 與 `CoordinatorIO` 加上轉呼叫。
- [ ] **Step 4：執行確認通過。** Run: `(cd src/dual_arm_coordinator && python3 -m pytest -q -p no:cacheprovider test)` Expected：全部 PASS。
- [ ] **Step 5：Commit**：`Let arm 2 pick zone B at an observed position`。

---

### Task 3：EnvSceneObserver 與 `observation_source=env_scene`

**Files:**
- Create: `src/dual_arm_coordinator/dual_arm_coordinator/gateways/env_scene.py`
- Modify: `coordinator_node.py`（`observation_source` 允許 `env_scene`；`package.xml` 加 `env_scene_interfaces` 依賴）
- Test: `src/dual_arm_coordinator/test/test_env_scene.py`

**Interfaces:**
- Consumes: Task 1 的 `GetEnvScene`；Task 2 的 `b_pick_target`；`gateways/vision.py` 的 `ImageMonitor`。
- Produces:
  - `class EnvSceneObserver(scene_call, images, home_state, can_reach, home_tcp, settings, guard, settle_s, image_timeout_s, clock=time.monotonic, sleep=time.sleep)`。`scene_call() -> GetEnvScene.Response`；`home_state(arm) -> bool | None`；`can_reach(arm, xyz)` 在不可達時丟 `TaskFault`；`home_tcp(arm) -> (x, y, z)`；`settings` 是 `WorkflowSettings`。
  - 方法：`zone() -> ZoneView`、`pick_target() -> PickView`、`b_pick_target() -> PickView`、`grid() -> GridView`、`verify_place(slot) -> PlaceView`。
  - 座標一律用 world：`x_mm/1000, y_mm/1000`，z = `settings.cap_top_z`。只在 config `target_frame == 'world'` 時可建立，否則丟 `ValueError`。
  - `def wire_env_scene(node, config, settings, motion, guard, callback_group=None) -> EnvSceneObserver`。

- [ ] **Step 1：寫失敗測試**（`test_env_scene.py`，以 `SimpleNamespace` 偽造回應，仿照 `test_vision.py` 的 `Base`）。預設場景：`valid=True`、`coords_source='standard'`、`arm1_valid=arm2_valid=c_slots_valid=True`、A 兩顆、B 零顆、`c_occupied=[T,T,F,F,F,F,F,F]`、`c_occupied_count=2`。
  - `test_zone_maps_counts_and_uses_home_state_for_b_clear`：兩臂 `home_state=True` → `b_arm_clear=True`；任一為 `False` 或 `None` → `False`。
  - `test_estimated_coords_are_refused`：`coords_source='estimated'` → 所有方法 `success=False`，訊息含 `estimated`。
  - `test_validity_is_checked_per_use`：`arm2_valid=False` → `pick_target` 成功；`b_pick_target`、`grid`、`verify_place` 失敗。`c_slots_valid=False` → `grid`、`verify_place`、`zone` 失敗。
  - `test_pick_target_nearest_reachable`：A 區有三顆，最近的那顆 `can_reach` 丟 `TaskFault` → 回傳第二近的；全部不可達 → 失敗，訊息 `No reachable object in zone A`。距離以 `home_tcp('arm1')` 的 xy 計算。
  - `test_b_target_requires_exactly_one`：B 區 0 顆或 2 顆 → 失敗，訊息含數量；1 顆 → 回傳該顆 world 座標（m）與 `cap_top_z`。
  - `test_verify_place_order`：`c_occupied=[T,T,T,F...]`、slot=3 → `placed=True, order_ok=True`；`[T,F,T,F...]`、slot=3 → `order_ok=False`。
  - `test_waits_for_image_after_settle`：沿用 `test_vision.py` 的方式；`settle_s` 之後沒有新的 env 影像 → 失敗 `No new image from env after the arm settled`，而且沒有呼叫 `scene_call`。
  - `test_service_failure_and_invalid_scene`：`success=False` 或 `scene.valid=False` → 失敗並帶出 message。
  - `test_requires_world_target_frame`：`target_frame='arm1_base'` 時 `wire` 前的檢查丟 `ValueError`（測試直接呼叫負責檢查的小函式 `require_world_frame(config)`）。
- [ ] **Step 2：執行確認失敗。** Run: `(cd src/dual_arm_coordinator && python3 -m pytest -q -p no:cacheprovider test/test_env_scene.py)` Expected：ImportError。
- [ ] **Step 3：實作 `gateways/env_scene.py`。** 每個公開方法：先走影像閘門（與 `VisionObserver._problem` 相同的等待邏輯，但不查 `CalibrationMonitor`），再呼叫一次 `scene_call()`，最後檢查有效性。A 區挑選規則照 `TruthObserver.pick_target`（依離 arm1 HOME TCP 的距離排序，approach 與 contact 兩個高度都可達才選）。`wire_env_scene` 訂閱 `/env_cam/image_raw`，建立 `/vision/env_scene/get_scene` client，逾時沿用 `_Services._call` 的做法，`home_state` 取 `motion.home_state`。
- [ ] **Step 4：接線。** `coordinator_node.py`：`observation_source` 允許 `('truth', 'vision_pick', 'env_scene')`；`env_scene` 時以 `wire_env_scene(...)` 取代 observer（`TruthObserver` 仍建立，因為 gripper 的 `cap_under_tool` 需要它）。實機模式的 BLOCKED 檢查不動。
- [ ] **Step 5：執行確認通過。** Run: `(cd src/dual_arm_coordinator && python3 -m pytest -q -p no:cacheprovider test)` Expected：全部 PASS。
- [ ] **Step 6：Commit**：`Add the env_scene observation source`。

---

### Task 4：單顆相機啟動共用，vision.launch 最多開一顆手臂鏡頭

**Files:**
- Create: `src/vision_pkg/vision_pkg/camera_launch.py`、`src/vision_pkg/launch/arm_camera.launch.py`
- Modify: `src/vision_pkg/launch/vision.launch.py`、`src/vision_pkg/setup.py`（安裝新 launch）
- Test: `src/vision_pkg/tests/test_camera_launch.py`

**Interfaces:**
- Produces:
  - `camera_launch.camera_actions(cam: str, device: str, rotate: int, cfg_dir: Path, calib_dir: Path, respawn: bool) -> list`：回傳 usb_cam（與 rotate≠0 時的 `image_rotate_node`）的 launch actions，內容等同目前 `vision.launch.py` 迴圈中的那一段（含 realpath、`image_raw_unrotated` 的 remap）。
  - `camera_launch.resolve_device(cam, launch_value, cam_cfg) -> (device, rotate, problems)`。
  - `arm_camera.launch.py camera:=arm1|arm2`：只啟動該顆，`respawn` 固定 `false`（重啟由切換節點負責）。
  - `vision.launch.py` 新增參數 `arm_camera`（`none`|`arm1`|`arm2`，預設 `none`），**只**啟動指定的那一顆手臂鏡頭；手臂視覺節點只在指定的那顆啟動。

- [ ] **Step 1：寫失敗測試**：`test_camera_actions_rotate_adds_rotate_node`（rotate=180 → 兩個 Node，usb_cam 有 `image_raw→image_raw_unrotated` remap）；`test_camera_actions_plain`（rotate=0 → 一個 Node，無 remap）；`test_vision_launch_never_starts_two_arm_cameras`：以 `arm_camera` 各值呼叫 `vision.launch.py` 的 `_launch_setup`（用 `LaunchContext` 和暫存的 cameras.yaml，裝置指向暫存檔），計算 namespace 為 `arm1_cam`/`arm2_cam` 的 usb_cam 數量 ≤ 1。
- [ ] **Step 2：執行確認失敗。** Run: `(cd src/vision_pkg && python3 -m pytest -q -p no:cacheprovider tests/test_camera_launch.py)`
- [ ] **Step 3：實作**：把 `vision.launch.py` 中單顆相機的那段抽到 `camera_launch.py`，兩個 launch 都改用它。
- [ ] **Step 4：執行 vision_pkg 全部測試確認通過。** Run: `(cd src/vision_pkg && python3 -m pytest -q -p no:cacheprovider)`
- [ ] **Step 5：Commit**：`Start at most one arm camera from the vision launch`。

---

### Task 5：手臂鏡頭切換節點

**Files:**
- Create: `src/dual_arm_vision_adapter/dual_arm_vision_adapter/processes.py`、`arm_camera_switch.py`
- Modify: `src/dual_arm_vision_adapter/setup.py`（entry point `arm_camera_switch`）、`package.xml`
- Test: `src/dual_arm_vision_adapter/test/test_arm_camera_switch.py`

**Interfaces:**
- Consumes: Task 4 的 `arm_camera.launch.py`。
- Produces:
  - `processes.py`：`class GroupProcess`，包含 `start(argv) -> None`（`subprocess.Popen(..., start_new_session=True)`，並以 `preexec_fn` 設定 `prctl(PR_SET_PDEATHSIG, SIGTERM)`）、`running() -> bool`、`stop(term_timeout_s: float) -> bool`（SIGTERM 給整個群組，逾時改 SIGKILL，回傳群組是否已消失）；`device_in_use(path: str) -> bool`（掃描 `/proc/*/fd` 是否指向 `os.path.realpath(path)`）。
  - `arm_camera_switch.py`：`class ArmCameraSwitch(launcher_factory, device_of, device_in_use, clock, term_timeout_s=3.0, status_max_age_s=2.0)`，包含 `on_status(active_arm: str) -> None`、`tick() -> None`（狀態機每次前進一步，不阻塞）、`state() -> dict`（`{'want', 'streaming', 'phase', 'message'}`，`phase ∈ {'on', 'switching', 'error'}`）。
  - 節點：訂閱 `/dual_arm/status`（`std_msgs/String` JSON，讀 `active_arm`），每 0.2 s 執行一次 `tick()`；在 `/vision/arm_cameras/state` 以 transient_local 發布 `std_msgs/String` JSON（內容同 `state()`）。

規則（spec 7.3、7.8）：`active_arm` 為 `arm1`/`arm2` 時要開該顆；空字串或尚未收到時開 arm1。狀態超過 `status_max_age_s` 沒更新時保持目前那顆。要切換時：先 `stop()`，確認群組消失**而且**舊裝置 `device_in_use` 為 false 之後，才開新的；新裝置被佔用時 `phase='error'`，不啟動，下一次 tick 再檢查。該開的那顆意外結束時，只重啟那一顆。

- [ ] **Step 1：寫失敗測試**（假的 launcher 記錄事件順序、假的時鐘）：
  - `test_boot_starts_arm1`
  - `test_switch_stops_before_start`：事件順序必須是 `stop arm1` → `start arm2`，兩者之間沒有任何時刻兩顆同時 `running`。
  - `test_escalates_to_sigkill_before_starting_next`：假程序不理 SIGTERM，`stop` 回傳 false 直到逾時後 SIGKILL；這段期間 `phase=='switching'`，arm2 沒有啟動。
  - `test_refuses_to_start_when_other_device_busy`：剛開機時 arm2 裝置被佔用、要開 arm1 → 正常開 arm1；之後切換到 arm2 但 arm2 裝置被佔用 → `phase=='error'`、訊息含裝置路徑，不啟動。
  - `test_rapid_changes_never_overlap`：在一次切換尚未完成時連續送 `arm2`、`arm1`、`arm2` → 任何時刻最多一顆 running，最後停在 arm2。
  - `test_stale_status_keeps_current`
  - `test_crash_restarts_only_wanted`：arm1 意外結束 → 只重啟 arm1。
  - `test_device_in_use_detects_open_fd`：開一個暫存檔，`device_in_use` 為 true；關閉後為 false（只在 Linux 執行）。
- [ ] **Step 2：執行確認失敗。** Run: `(cd src/dual_arm_vision_adapter && python3 -m pytest -q -p no:cacheprovider test/test_arm_camera_switch.py)`
- [ ] **Step 3：實作** `processes.py` 與 `arm_camera_switch.py`。launcher 的 argv：`['ros2', 'launch', 'vision_pkg', 'arm_camera.launch.py', f'camera:={arm}']`；`device_of(arm)` 用 `camera_launch.resolve_device` 讀 `cameras.yaml`。
- [ ] **Step 4：執行確認通過**（adapter 全部測試）。
- [ ] **Step 5：Commit**：`Add the arm camera switch that streams one arm camera at a time`。

---

### Task 6：env_scene 橋接節點與實機視覺 launch

**Files:**
- Create: `src/dual_arm_vision_adapter/dual_arm_vision_adapter/env_scene_bridge.py`、`src/dual_arm_bringup/launch/vision_hardware.launch.py`
- Modify: `src/dual_arm_vision_adapter/setup.py`（entry point `env_scene_bridge`）、`package.xml`
- Test: `src/dual_arm_vision_adapter/test/test_env_scene_bridge.py`

**Interfaces:**
- Consumes: Task 1 的 `GetEnvScene`、Task 5 的節點、Task 4 的 `camera_launch`。
- Produces:
  - `env_scene_bridge.to_zone_fields(response, at_home: dict) -> dict`：回傳 `ZoneState` 各欄位（`valid, message, a_has_object, b_has_object, b_arm_clear, c_object_count`）；有效性規則同 Task 3。`b_arm_clear` = `/dual_arm/status` 的 `at_home` 兩臂都是 `true`；沒有狀態時為 false。
  - `env_scene_bridge.env_calibration(response) -> (passed: bool, reasons: list[str])`。
  - 節點：每 0.5 s 呼叫一次 `get_scene`（非同步，前一次未回應時跳過）；發布 `vision_interfaces/ZoneState` 到 `/vision/env/zone_state`，以及 `DiagnosticArray` 到 `/vision/calibration_status`（`hardware_id='env'`，`reasons` 用 JSON 字串，格式同 `status_node.py`）。
  - `vision_hardware.launch.py`：環境相機（`camera_actions('env_cam', ...)`）、`env_scene_node`（上游參數檔）、`env_scene_bridge`、`arm_camera_switch`。**不**啟動 `calibration_status`、`env_vision_node`、手臂視覺節點，也不直接啟動手臂 usb_cam。

- [ ] **Step 1：寫失敗測試**：`test_zone_fields_valid_scene`；`test_zone_fields_b_clear_needs_both_home`；`test_zone_fields_invalid_when_estimated`；`test_calibration_reasons`（`estimated`、`arm1_valid=False`、`c_slots_valid=False` 各自產生一條可讀的原因）。
- [ ] **Step 2：執行確認失敗。**
- [ ] **Step 3：實作**橋接節點與 launch。
- [ ] **Step 4：執行確認通過**；另外 `colcon build` 全部套件，並以 `ros2 launch dual_arm_bringup vision_hardware.launch.py --show-args` 確認 launch 可解析。輸出存到 evidence。
- [ ] **Step 5：Commit**：`Bridge env_scene to the zone topic and add the hardware vision launch`。

---

### Task 7：操作介面顯示鏡頭輪流狀態

**Files:**
- Modify: `src/dual_arm_hmi/dual_arm_hmi/model/state.py`（`CameraStatus` 加 `rotation: str = ''`；`camera_placeholder`；第 532 行附近失聯清單）、`sources/ros_source.py`（訂閱 `/vision/arm_cameras/state`）、`sources/ros_parse.py`（解析 JSON）、`sources/fake_source.py`（示範資料）、`launcher/profiles.py`（實機改啟動 `vision_hardware.launch.py`，不再啟動 `vision.launch.py`、`calibration.launch.py`）
- Test: `src/dual_arm_hmi/test/test_state.py`、`test_ros_parse.py`、`test_profiles.py`

**Interfaces:**
- Consumes: Task 5 的 `/vision/arm_cameras/state` JSON、Task 6 的 launch。
- Produces: `CameraStatus.rotation`：`''`（不受輪流管理）、`'on'`、`'off'`、`'switching'`、`'error'`。

- [ ] **Step 1：寫失敗測試**：
  - `test_placeholder_rotation_off`：`rotation='off'` → `('輪流中，鏡頭關閉', Level.NEUTRAL)`；`'switching'` → `('切換中', Level.NEUTRAL)`；`'error'` → `('鏡頭切換失敗', Level.WARN)`。
  - `test_rotated_off_camera_is_not_lost`：關閉中的手臂鏡頭不列入失聯警告。
  - `test_parse_arm_camera_state`：`{"streaming":"arm1","phase":"on",...}` → arm1 `on`、arm2 `off`；`phase='switching'` → 兩顆都 `switching`；JSON 錯誤 → 回傳 None。
  - `test_hardware_profile_uses_vision_hardware_launch`：實機 LaunchPlan 包含 `vision_hardware.launch.py`，不包含 `vision.launch.py`、`calibration.launch.py`；by-path 覆寫參數照樣傳入。
- [ ] **Step 2：執行確認失敗。** Run: `(cd src/dual_arm_hmi && QT_QPA_PLATFORM=offscreen python3 -m pytest -q -p no:cacheprovider test)`
- [ ] **Step 3：實作**。arm1/arm2 的 `calibration` 顯示改成 `僅監控`（輪流管理下手臂鏡頭不做標定）。
- [ ] **Step 4：執行確認通過**；再用 `tools/capture_screens.py` 的 fake 模式擷圖，確認關閉中的那格顯示正確，圖存到 evidence。
- [ ] **Step 5：Commit**：`Show the arm camera rotation in the operator UI`。

---

### Task 8：全量檢查、文件與現場驗證清單

**Files:**
- Modify: `docs/HARDWARE_TEST_GUIDE.md`（A 區黑框放置規則；`env_scene` 標定步驟；spec 第 8 節的四項現場驗證，每項有指令和 PASS 判準）、`docs/ORIN_DEPLOYMENT.md`（USB 頻寬段落改寫成輪流做法；新 launch）、`docs/ARCHITECTURE.md`（視覺段落）、`docs/PROGRESS.md`、`docs/TEST_REPORT.md`、`docs/RESUME.md`、`README.md` 狀態表的視覺列
- Create: `docs/evidence/camera_roles_20261112/README.md`

- [ ] **Step 1：全量檢查。** Run: `bash scripts/run_checks.sh t1 docs/evidence/camera_roles_20261112/t1`；如果改到的檔案在 `TEST_PLAN.md` 第 4 節要求 t2，就跑 t2。Expected：PASS；模擬兩物體搬運結果與改動前相同（模擬仍用 truth／vision_pick）。
- [ ] **Step 2：更新文件**。現場的四項驗證標為 `NOT_RUN`。
- [ ] **Step 3：Commit 並推送**：`Document the camera roles change and its on-site checks`，`git push origin main`。

---

## 自我檢查紀錄

- spec 覆蓋：7.1→T1；7.2→T4、T6、T7；7.3→T5；7.4→T3；7.5→T2；7.6→T7（env 標定改由橋接節點的 `/vision/calibration_status` 提供，介面沿用原本的顯示）；7.7→T3、T6；7.8→T4、T5；第 8 節→各 Task 測試與 T8；第 3 節非目標→T3 不解除 BLOCKED。
- 我做的決定（spec 留給建造者的部分）：切換節點放在 `dual_arm_vision_adapter`；用 `ros2 launch` 子程序開關鏡頭；座標用 world mm，不經手臂座標（避開 arm2 軸向待確認）；B 區容許距離模擬值 0.02 m、實機值 `null`；閒置時開 arm1；狀態 topic 用 JSON String。
