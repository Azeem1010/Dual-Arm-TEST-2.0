# 鏡頭分工調整（2026-11-12）

設計：[camera-roles 設計](../../superpowers/specs/2026-11-12-camera-roles-design.md)；計畫：[camera-roles 計畫](../../superpowers/plans/2026-11-12-camera-roles.md)。

| 紀錄 | 內容 | 結果 |
|---|---|---|
| `t6_build.log`、`t6_show_args.log` | `colcon build`（vision_pkg、dual_arm_vision_adapter、dual_arm_bringup、dual_arm_coordinator）與 `vision_hardware.launch.py --show-args` | PASS |
| `t7_hw_read_only.png` | 操作介面假資料「實機唯讀」：手臂 2 顯示「輪流中，鏡頭關閉」，兩顆手臂鏡頭標「僅監控」 | PASS |
| `t1/` | `run_checks.sh t1`：模型、建置、HOME、IK 18/18、可達性、單元測試 coordinator 311／HMI 298／vision 104、HOME 碰撞 | PASS |
| `t2/` | `run_checks.sh t2`：回歸 `two`、舊 pipeline 兩物體、運動 gateway、操作工具、安全監控、視覺取料、README 截圖 | PASS，只有 `smoke_runtime_sim` FAIL（規劃與控制器 PASS，`shutdown` FAIL：已知的 Gazebo 關閉逾時） |
| `regress_faults.*`、`regress_faults_rerun.*` | 回歸 `faults`，但呼叫時**沒有先起模擬**（我的指令錯誤） | FAIL：`arm1 home action server is unavailable`，`at_home` 為 null。保留作為紀錄，不代表程式問題 |
| `faults_with_sim/` | 同上，先用 `start_sim.sh headless` 起模擬（照 `run_checks.sh` 的 `with_launch`） | PASS，22 項 |
| 調整後單元測試 | 審查修正（鏡頭當掉時退避、橋接節點丟棄無回應請求）後 `dual_arm_vision_adapter` | PASS，33 項 |

未完成：

- **BLOCKED**：匯入上游 env_camera_vision。GitHub 只有 `6b059eb`，現場版本（A 區座標以黑框左緣為原點）尚未推送。`src/env_scene` 不存在，`env_scene_node` 與 coordinator 的 `env_scene` 來源都還不能實際執行。
- **NOT_RUN**：Orin 現場四項（HARDWARE_TEST_GUIDE V1）。
- 審查留下的小問題（未修）：`device_in_use` 讀不到其他使用者的 `/proc/<pid>/fd` 時當成沒占用，所以所有相機程序要用同一個使用者執行；SIGKILL 後仍不退出的程序群組會一直顯示 `switching`；`env_scene` 的格位陣列沒檢查長度；橋接節點的 `at_home` 不會過期；`scene_call` 等服務時不檢查取消。
- 待 env_scene 匯入後再確認：`GetEnvScene` 的結果是否保證來自手臂停妥後的影像（是否有時間戳可用）。
