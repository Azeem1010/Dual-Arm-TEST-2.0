# ROS 2 介面規格（Topic／Service／Action）

最後確認：2026-11-10。視覺與模擬端點來自 commit `b48eee8` 的擷取；coordinator 與安全監控來自 [wp13/04_node_info.txt](evidence/wp13/04_node_info.txt)。

本文件記錄**目前實際存在**的介面，不是目標設計。需求見 [REQUIREMENTS.md](REQUIREMENTS.md)。文件與程式不一致時，以程式碼和 `evidence/` 的最新紀錄為準。

## 驗證範圍

| 項目 | 狀態 | 依據 |
|---|---|---|
| `vision_sim` 節點、Topic、Service、Action 端點與型別 | PASS | [live_graph.json](evidence/ros_graph_vision_sim/live_graph.json)、[live_actions.txt](evidence/ros_graph_vision_sim/live_actions.txt) |
| `joint_state_broadcaster`、`arm1_controller`、`arm2_controller` 為 active | PASS | [live_controllers.txt](evidence/ros_graph_vision_sim/live_controllers.txt) |
| `/vision/calibration_status` 訊息內容 | NOT_RUN | 端點存在，但 15 秒內沒抓到訊息（`live_calibration_status.txt` 是空的） |
| `mock`、`hardware`、`vision.launch.py` 的實際 graph | NOT_RUN | 僅比對原始碼與 launch |
| `dual_arm_coordinator`、`safety_supervisor` 端點與型別 | PASS | [wp13/04_node_info.txt](evidence/wp13/04_node_info.txt)，MoveIt mock 上擷取 |
| 實機介面 | NOT_RUN | 未接硬體 |

Live graph 只證明端點存在且型別相符，不代表資料內容正確，也不代表任務流程可用。

擷取方式：以 `ROS_DOMAIN_ID=77`、`GZ_PARTITION=graph_capture_probe` 啟動 headless `vision_sim.launch.py` 與 `calibration.launch.py`，再用 rclpy graph API 傾印。腳本存於 [evidence/ros_graph_vision_sim/](evidence/ros_graph_vision_sim/)，裡面的輸出路徑是當次的暫存目錄，重跑前要修改 `OUT`。

## 節點

| 節點 | 來源 | 發布 | 訂閱 | Service／Action Server |
|---|---|---|---|---|
| `env_vision_node` | `vision_pkg` | `/vision/env/zone_state`、`/vision/env/ranking` | `/env_cam/image_raw` | `/vision/env/*` |
| `arm1_vision_node` | `vision_pkg` | `/vision/arm1/pick_target`、`/vision/arm1/detections` | `/arm1_cam/image_raw` | `/vision/arm1/get_pick_target` |
| `arm2_vision_node` | `vision_pkg` | `/vision/arm2/grid_state` | `/arm2_cam/image_raw` | `/vision/arm2/get_grid_state`、`/vision/arm2/verify_place` |
| `calibration_status` | `dual_arm_vision_adapter` | `/vision/calibration_status` | 三支相機 `image_raw` | 無 |
| `ros_gz_bridge` | `ros_gz_bridge` + [bridge.yaml](../src/dual_arm_gazebo/config/bridge.yaml) | 相機影像與 `camera_info`、`/clock`、`/gripper/armN/state`、`/ground_truth/*`、`/gazebo/ground_truth` | `/gripper/armN/command` | 無 |
| `robot_state_publisher` | ROS | `/robot_description`、`/tf`、`/tf_static` | `/joint_states` | 無 |
| `static_transform_publisher` × 3 | `sim.launch.py` | `/tf_static`：`world` → `{env,arm1,arm2}_camera_optical_frame` | 無 | 無 |
| `controller_manager` | `gz_ros2_control`（模擬）／`ros2_control_node`（mock、實機） | `/diagnostics`、statistics | `/robot_description` | `/controller_manager/*` |
| `joint_state_broadcaster` | `ros2_control` | `/joint_states`、`/dynamic_joint_states` | 無 | 無 |
| `arm1_controller`、`arm2_controller` | `JointTrajectoryController` | `/armN_controller/controller_state` | `/armN_controller/joint_trajectory`、`/armN_controller/speed_scaling_input` | Action：`/armN_controller/follow_joint_trajectory`；`/armN_controller/query_state` |
| `move_group` | `dual_arm_bringup/move_group_lifetime` | `/monitored_planning_scene`、`/display_planned_path`、`/display_contacts`、`/pipeline_state` | `/joint_states`、`/planning_scene`、`/planning_scene_world`、`/collision_object`、`/attached_collision_object`、`/trajectory_execution_event` | 見 Action 與 MoveIt Service |

| 任務與安全節點 | 來源 | 發布 | 訂閱 | Service／Action |
|---|---|---|---|---|
| `dual_arm_coordinator` | `dual_arm_coordinator` | `/dual_arm/status`、`/dual_arm/permit`、`/handoff/b_state`、`/gripper/armN/command` | `/joint_states`、`/safety/estop`、`/gripper/armN/state`、`/ground_truth/cap_{1..8}` | Server：`/dual_arm/{start,cancel,confirm,recover,go_home}`。Client：`/move_action`、`/execute_trajectory`、`/apply_planning_scene`、`/check_state_validity`、`/get_planning_scene` |
| `dual_arm_hmi_monitor` | `dual_arm_hmi`（操作介面，監看） | 無 | 三支相機 `image_raw`、`/vision/*/debug_image`、`/view_*/image_raw`、`/joint_states`、`/dynamic_joint_states`、`/armN_controller/controller_state`、`/dual_arm/status`、`/safety/status`、`/robot_description`、`/vision/env/zone_state`、`/vision/arm2/grid_state`、`/vision/calibration_status` | Client：`/controller_manager/list_controllers`、`/dual_arm_coordinator/get_parameters` |
| `dual_arm_hmi_command` | `dual_arm_hmi`（操作介面，指令；`--monitor` 不建立） | 無 | 無 | Client：`/safety/{trigger_stop,reset}`、`/dual_arm/{start,cancel,go_home,recover}` |
| `safety_supervisor` | `dual_arm_coordinator` | `/safety/status` | `/safety/estop`、`/dual_arm/permit` | Server：`/safety/reset`、`/safety/trigger_stop`。Client：`/controller_manager/switch_controller`、`/controller_manager/list_controllers` |

參數 `observation_source:=vision_pick` 時，`dual_arm_coordinator` 另外使用 `/vision/arm1/get_pick_target`、`/vision/calibration_status`、三支相機 `image_raw` 與 TF。實機設定目前會被 coordinator 拒絕啟動。

`SuctionSystem` 是 Gazebo system plugin，不是 ROS 節點，透過 gz-transport 與 `ros_gz_bridge` 連接。

## Topic

| Topic | 型別 | 方向／內容 | QoS／頻率 |
|---|---|---|---|
| `/{env,arm1,arm2}_cam/image_raw` | `sensor_msgs/msg/Image` | Gazebo→ROS（模擬）；`usb_cam`（實機） | Pub reliable，Sub best-effort（相容）；模擬 640×480、15 Hz |
| `/{env,arm1,arm2}_cam/camera_info` | `sensor_msgs/msg/CameraInfo` | 同上；目前無訂閱者 | |
| `/view_{isometric,top,front,side}/image_raw` | `sensor_msgs/msg/Image` | 僅模擬，觀察用 | 960×720、2 Hz |
| `/clock` | `rosgraph_msgs/msg/Clock` | 僅模擬 | |
| `/joint_states` | `sensor_msgs/msg/JointState` | 八軸回授 | |
| `/dynamic_joint_states` | `control_msgs/msg/DynamicJointState` | `joint_state_broadcaster` 發出所有狀態介面；實機 CM-530 另有 `raw_position`（最近一次成功 `READ` 的 Present Position，0–1023）與 `raw_target`（最近一次回 `OK,AX` 的目標；未確認前為 NaN）。訂閱者：`dual_arm_hmi` | 只有實機與 Mock Serial 有計數；模擬與 mock 沒有這兩個介面 |
| `/gripper/arm{1,2}/command` | `std_msgs/msg/String` | ROS→Gazebo，僅模擬 | reliable |
| `/gripper/arm{1,2}/state` | `std_msgs/msg/String` | Gazebo→ROS，僅模擬 | reliable |
| `/ground_truth/cap_{1..8}` | `tf2_msgs/msg/TFMessage` | 僅模擬，瓶蓋真值 | |
| `/gazebo/ground_truth` | `tf2_msgs/msg/TFMessage` | 僅模擬，整個場景的 pose | |
| `/vision/env/zone_state` | `vision_interfaces/msg/ZoneState` | A/B/C 區狀態 | reliable、depth 10；約 10 Hz |
| `/vision/env/ranking` | `vision_interfaces/msg/RankingSnapshot` | 固定發布一次 `valid=false`（不排序） | reliable、transient_local、depth 1 |
| `/vision/arm1/pick_target` | `vision_interfaces/msg/PickTarget` | 目前會選中的瓶蓋，`frame_id=arm1_base_link`（數值仍是 `arm1_base` 軸向，見已知缺口 4） | reliable、depth 10 |
| `/vision/arm1/detections` | `vision_interfaces/msg/PickDetections` | 所有偵測到的瓶蓋 | reliable、depth 10 |
| `/vision/arm2/grid_state` | `vision_interfaces/msg/GridState` | C 區八格，`frame_id=arm2_base_link`（數值仍是 `arm2_base` 軸向，見已知缺口 4） | reliable、depth 10 |
| `/vision/calibration_status` | `diagnostic_msgs/msg/DiagnosticArray` | 三支相機 PASS／FAIL 與原因 | reliable、depth 10；每 0.5 秒 |
| `/vision/{env,arm1,arm2}/debug_image` | `sensor_msgs/msg/Image` | 視覺節點的標註影像（`bgr8`），給操作介面顯示。需 `publish_debug_image:=true`，預設不發布 | best-effort；隨視覺處理頻率 |

| `/dual_arm/status` | `std_msgs/msg/String`（JSON） | 狀態、持物、B 區擁有者、格位、token、`at_home`（每臂 true／false，關節狀態過期時為 null） | transient_local、depth 1；5 Hz |
| `/dual_arm/permit` | `std_msgs/msg/Bool` | Coordinator 存活與是否允許；停止發布代表失效 | 10 Hz |
| `/handoff/b_state` | `std_msgs/msg/String`（JSON） | B 區擁有者 | transient_local、depth 1 |
| `/safety/estop` | `std_msgs/msg/Bool` | 急停心跳，`true` 為觸發；實機來源尚不存在 | 需持續發布 |
| `/safety/status` | `std_msgs/msg/String`（JSON） | 安全鎖定狀態、原因，以及實際查證的 `controllers_stopped` | transient_local、depth 1；5 Hz |

| `/suction_command` | `std_msgs/msg/Int32` | ROS→ESP32，僅實機。`0` 全關，`1`／`2` 模組 1 吸取／釋放，`3`／`4` 模組 2 | 尚未接真正的 ESP32 |
| `/suction_status` | `std_msgs/msg/Int32` | ESP32→ROS，命令回音，不是真空感測 | 尚未接真正的 ESP32 |

depth 取自程式碼；DDS graph 查詢回報的 depth 都是 0。訊息欄位以 [vision_interfaces/msg](../src/vision_interfaces/msg) 為準，依 `AGENTS.md` 不可改動。

## Service

### 視覺

| Service | 型別 | Request | Response |
|---|---|---|---|
| `/vision/arm1/get_pick_target` | `vision_interfaces/srv/GetPickTarget` | `int32 target_rank`、`bool peek_only`（保留，無作用） | `success, message, rank, x, y, z`（arm1 基座，公尺） |
| `/vision/arm2/get_grid_state` | `vision_interfaces/srv/GetGridState` | 無 | `occupied[8], place_x[8], place_y[8], place_z[8], all_full, success, message` |
| `/vision/arm2/verify_place` | `vision_interfaces/srv/VerifyPlace` | `int32 slot`（1..8） | `placed, order_ok, wrong_slots[], success, message` |
| `/vision/env/get_zone_state` | `vision_interfaces/srv/GetZoneState` | 無 | `a_has_object, b_has_object, b_arm_clear, c_object_count, success, message` |
| `/vision/env/recalibrate_zones` | `vision_interfaces/srv/RecalibrateZones` | 無（需場地淨空） | `success, message` |
| `/vision/env/capture_ranking` | `vision_interfaces/srv/CaptureRanking` | 無 | `success, message, count, low_confidence`（固定 false） |
| `/vision/env/get_rank` | `vision_interfaces/srv/GetRank` | `x_mm, y_mm, peek_only` | `success, message, rank, distance_mm`（固定 0） |
| `/vision/env/clear_taken` | `std_srvs/srv/Trigger` | 無 | `success, message` |

這些 response 都沒有影像時間戳，單憑回應不足以授權動作（見 [ARCHITECTURE.md](ARCHITECTURE.md)）。

### 任務與安全

| Service | 型別 | 用途 |
|---|---|---|
| `/dual_arm/start`、`/dual_arm/cancel` | `std_srvs/srv/Trigger` | 開始、取消；開始只代表已接受，結果看 `/dual_arm/status` |
| `/dual_arm/confirm` | `dual_arm_interfaces/srv/ConfirmStep` | 人工吸盤步驟的一次性確認 |
| `/dual_arm/recover` | `dual_arm_interfaces/srv/ConfirmStep` | 現場清空後復歸 |
| `/dual_arm/go_home` | `dual_arm_interfaces/srv/ConfirmStep` | 兩臂依序回 HOME，佔用 B 區的手臂先走；`success` 是人工確認吸盤與 B 區已清空，`token` 不使用。任務未執行、未鎖定才接受；模擬中有持物時拒絕（改用重置模擬）。結果看 `at_home`，移動失敗或被停止時任務進入 `FAULT` |
| `/safety/reset` | `std_srvs/srv/Trigger` | 輸入恢復正常後解除鎖定並重新啟用 controller |
| `/safety/trigger_stop` | `std_srvs/srv/Trigger` | 軟體停止：以 `Operator software stop` 鎖定並停用手臂 controller，用 `/safety/reset` 解除。不切斷馬達電源，不能取代實體急停 |

`dual_arm_interfaces/srv/ManualXY` 已定義，但目前沒有服務端，`manual_xy` 是命令列工具。

### MoveIt

`/check_state_validity`、`/compute_ik`、`/compute_fk`、`/compute_cartesian_path`、`/plan_kinematic_path`、`/get_planning_scene`、`/apply_planning_scene`、`/query_planner_interface`、`/get_planner_params`、`/set_planner_params`、`/clear_octomap`。

目前專案實際用到的有 `/check_state_validity`、`/apply_planning_scene`、`/get_planning_scene`。

### ros2_control

`/controller_manager/{list_controllers, list_controller_types, list_hardware_components, list_hardware_interfaces, load_controller, configure_controller, switch_controller, unload_controller, cleanup_controller, reload_controller_libraries, set_hardware_component_state}`。

實機的馬達上力矩由操作者透過 `set_hardware_component_state` 明確啟用，見 [hardware.launch.py](../src/dual_arm_bringup/launch/hardware.launch.py)。

## Action

| Action | 型別 | Server | Client |
|---|---|---|---|
| `/move_action` | `moveit_msgs/action/MoveGroup` | `move_group` | `dual_arm_coordinator`、`manual_xy`、`scripts/demo_transfer_*.py`、`smoke_runtime.py`、`show_gazebo_motion.py` |
| `/execute_trajectory` | `moveit_msgs/action/ExecuteTrajectory` | `move_group` | `dual_arm_coordinator`（接觸段） |
| `/arm1_controller/follow_joint_trajectory` | `control_msgs/action/FollowJointTrajectory` | `arm1_controller` | `moveit_simple_controller_manager`、`demo_transfer_pipeline.py`、`test_cm530_mock.py` |
| `/arm2_controller/follow_joint_trajectory` | `control_msgs/action/FollowJointTrajectory` | `arm2_controller` | `moveit_simple_controller_manager`、`demo_transfer_pipeline.py` |

兩個 controller 各控制四軸，關節不重疊，只有 `position` 指令介面。

## 吸盤字串協定（僅 Gazebo）

定義在 [policy.hpp](../src/dual_arm_gripper/include/dual_arm_gripper/policy.hpp) 與 [suction_system.cpp](../src/dual_arm_gripper/src/suction_system.cpp)。

| 方向 | 格式 |
|---|---|
| 指令 | `<seq>,attach,cap_<1-8>` 或 `<seq>,release` |
| 成功回覆 | `<seq>,attached:cap_N` 或 `<seq>,released` |
| 失敗回覆 | `<seq>,fault:already_attached`、`<seq>,fault:missing_entity`、`<seq>,fault:no_contact` |

- `seq` 必須 ≥1 且嚴格遞增，整段長度上限 64 字元。
- 格式錯誤、序號未遞增，或前一個指令還沒處理時，指令會被直接丟棄，**不會有回覆**。呼叫端必須有逾時處理。

## 各啟動模式

| Launch | 啟動內容 | 不包含 |
|---|---|---|
| `mock.launch.py` | RSP、`ros2_control_node`（`mock_components`）、`move_group`、RViz、三個 spawner | Gazebo、相機、吸盤、視覺 |
| `sim.launch.py` | Gazebo、bridge、RSP、`move_group`、三個 spawner、相機 static TF | 視覺節點 |
| `vision_sim.launch.py` | `sim.launch.py` + 三個視覺節點 | `calibration_status` |
| `demo_pick_place.launch.py` | `sim.launch.py` + `dual_arm_coordinator`（Gazebo 真值） | 視覺節點；預設一輪已實跑通過（evidence/docs_audit/） |
| `calibration.launch.py` | `calibration_status` | 校正工具 |
| `hmi_sim.launch.py` | `demo_pick_place.launch.py` + 三個視覺節點（發布標註影像）+ `calibration_status` + `safety_supervisor`（`require_estop:=false`） | 急停心跳 |
| `hardware.launch.py`（預設） | RSP、`ros2_control_node`、`joint_state_broadcaster`，唯讀 | arm controller、`move_group`、相機、吸盤 |
| `hardware.launch.py enable_motion:=true` | 上述 + inactive 的 arm controller；`use_moveit` 預設時加 `move_group`；非 Mock 時加 `safety_supervisor`。`controllers_file` 的容差必須是實測值 | 相機、吸盤、相機 TF |
| `vision.launch.py` | `usb_cam` × 3、視覺節點 × 3，需要時加 `image_rotate_node` | 手臂與 MoveIt |

## 已知缺口

| # | 問題 | 影響 |
|---|---|---|
| 1 | 區域與格位狀態仍用 Gazebo 真值，只有取料點可由視覺決定；模擬相機在 Home 被手臂遮擋（C31、D7） | 視覺驅動的完整搬運 `BLOCKED` |
| 2 | Coordinator 只有在 `observation_source:=vision_pick` 時才檢查 `/vision/calibration_status`，且只檢查 arm1 | 區域與格位的校正閘門還沒有實際使用 |
| 3 | 已解決（上游 4a40f30）：`usb_cam` 的 `frame_id` 改為 `*_camera_optical_frame`，與 `dual_arm_vision_adapter/config/hardware/*.yaml` 一致 | — |
| 4 | 上游 4a40f30 只把 `header.frame_id` 改成 `armN_base_link`，座標數值的計算沒變，仍是 `armN_base` 軸向（與 `armN_base_link` 差 +90° yaw 與 z 0.014）。`vision` gateway 不看 `header.frame_id`，用 `coordinator.yaml` 的 `vision_base_frame: armN_base` 經 TF 轉換；模擬有 static TF，實機 TF 尚未發布，需要量測值 | 不可依 `header.frame_id` 直接當 `armN_base_link` 使用；需與上游確認座標是否要真的改成 `armN_base_link` 軸向。軸向見 [COORDINATE_FRAMES.md](COORDINATE_FRAMES.md) |
| 5 | 已部分解決（WP12）：`gripper` gateway 有 `esp32` 後端，協定依 ray000518/micro-ros（`/suction_command`、`/suction_status`），只用替身節點驗證；ESP32 只回命令回音，沒有真空感測（D5） | 吸取結果仍要人工 token 確認；`/gripper/*` 只存在於模擬 |
| 6 | Coordinator 會同步 PlanningScene，但場景沒有平台、泡棉、相機支架，碰撞模型仍是保守方塊（WP11） | 路徑碰撞驗證不完整 |
| 7 | 相機 static TF 只在 `sim.launch.py` 發布 | 實機沒有相機 TF |
| 8 | `demo_pick_place.launch.py` 不含視覺節點；`calibration.launch.py` 只有狀態監看 | 含視覺的流程目前由測試腳本分開啟動 |
| 9 | `calibration.launch.py` 的 `use_sim_time` 預設 `true`，實機模式需明確設為 `false` | 否則節點等不到 `/clock` |
| 10 | 2026-11-09 擷取時 `arm1_controller` spawner 的第一次 switch 呼叫 10 秒逾時，重試時 controller 已切換，spawner 以 exit 1 結束，controller 實際為 active | launch log 出現 `process has died`，可能誤判；啟動後要以 `list_controllers` 為準 |
