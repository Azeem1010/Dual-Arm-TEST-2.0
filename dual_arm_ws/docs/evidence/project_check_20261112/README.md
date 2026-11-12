# 全專案檢查（2026-11-12）

範圍：commit `b78065e`（鏡頭分工調整與審查小問題修正）之上，加上未提交的文件一致性修正。指令：`run_checks.sh t0|t1|t2`，各套件 pytest／colcon test，cm530 mock，以及先用 `start_sim.sh headless` 起模擬再跑回歸 `faults`、`batch` 與 `coordinator_node`。各步驟結束碼見 `results.txt`。

| 項目 | 結果 |
|---|---|
| t0 文件檢查 | PASS |
| t1：模型、建置、HOME、IK、可達性、HOME 碰撞；單元測試 coordinator 316／HMI 298／vision 104 | PASS |
| pytest `dual_arm_vision_adapter` 36、`env_scene` 10 | PASS |
| pytest `dual_arm_gripper` | 不適用：C++ 套件沒有 pytest 測試（exit 5 是我腳本選錯）；由 colcon test 覆蓋 |
| colcon test `cm530_hardware`、`dual_arm_gripper` | PASS，43 項 |
| cm530 mock serial | PASS |
| 回歸 `faults` 22、`batch` 5、`coordinator_node` 23 | PASS |
| t2：回歸 `two`、舊 pipeline、motion gateway、safety、視覺取料、README 截圖 | PASS |
| t2：`smoke_runtime_sim` | FAIL，只有 `shutdown`（已知 Gazebo 關閉逾時，與先前相同） |
| t2：`operator_tools` | 全套執行時 FAIL 1 項：`unreachable_target_is_refused` 回報 `No fresh joint state for arm1`（工具 20 s 內沒收到 `/joint_states`，還沒走到可達性判斷）。mock 啟動紀錄沒有錯誤；該工具與 motion gateway 本次未修改。單獨重跑 PASS（`operator_tools_rerun/`，正確回報 `cannot reach`）。判定為高負載下的偶發，未改程式 |

處理：

- t1／t2 會覆寫追蹤中的 `docs/evidence/*.png|*.log` 與 `docs/images/`，依 AGENTS 規則已 `git restore`；這次的截圖原始檔在 `t2/readme_raw/`。
- 文件一致性修正（同一 commit）：ROS_INTERFACES 補 `env_scene_node`、`env_scene_bridge`、`arm_camera_switch` 與兩個 service、launch 表；UI_PLAN 與 ORIN_DEPLOYMENT 改用 `vision_hardware.launch.py`；工作區 README 套件表；根 README 架構圖。
