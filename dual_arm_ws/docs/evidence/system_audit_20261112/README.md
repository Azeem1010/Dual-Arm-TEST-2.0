# 整體系統檢查（2026-11-12）

範圍依使用者要求「只做必要」：實際執行中的節點對接、程序殘留與重啟問題、設定重複。執行環境 WSL2 Ubuntu 24.04、ROS 2 Jazzy。

## 節點對接（live graph）

指令見 `graph_hmi_sim.log`：以 `ROS_DOMAIN_ID=47` 啟動 `hmi_sim.launch.py`（Gazebo、MoveIt、coordinator、安全監控、三個視覺節點、校正狀態），控制器 active 後再等 20 秒，由 `scripts/audit_ros_graph.py --with-hmi` 同時建立操作介面的監看與指令節點，讀取整個 graph（`graph_hmi_sim.json`）。結束後沒有殘留程序（`leftover_processes.txt` 空白）。

| 檢查 | 結果 |
|---|---|
| 同一 topic 多種型別 | 0 |
| QoS 不相容（reliable 訂閱 best-effort、transient-local 訂閱 volatile） | 0 |
| 服務或 action 呼叫找不到伺服器 | 0。操作介面指令節點 → `/dual_arm/{start,cancel,go_home,recover}`、`/safety/{reset,trigger_stop}`；coordinator → `/apply_planning_scene`、`/check_state_validity`、`/get_planning_scene`、`/move_action`、`/execute_trajectory`；MoveIt → 兩個 `follow_joint_trajectory`，型別一致 |
| 重複的節點名稱 | 0（28 個節點） |
| 有訂閱沒有發布者 | 10，全部是設計上的可選輸入，已列入 `scripts/audit_expect_sim.json` 並註明原因：控制器的直接指令 topic（系統只用 action）、MoveIt 的場景 topic（coordinator 用服務）、`/safety/estop`（實體急停節點 D8 未實作，`hmi_sim` 設 `require_estop:=false`） |
| 有發布沒人讀 | 23，都是診斷、統計、給 RViz 的 topic，或 `camera_info`、`/vision/arm1/detections` 等目前沒有使用者的輸出 |

原始判定是 `FAIL`（10 項）；逐項審查後都是設計如此，結論 `PASS`。以後用 `--expect scripts/audit_expect_sim.json` 執行，新增的未接 topic 才會被報出來。Graph 只證明端點相符，不證明資料內容正確；資料與流程由回歸測試涵蓋。

## 程序殘留與重啟

| 問題 | 處理 |
|---|---|
| 停止測試時留下的 coordinator 仍在同一 domain 回應服務，下一輪測試拿到舊狀態，整輪白跑（evidence/tilt_slot8_20261112/sim_stale_coordinator/） | 已修：`run_checks.sh` 啟動前檢查加入 coordinator、安全監控、視覺節點、校正狀態、static TF；結束時有任何殘留就判 `FAIL`（原本只記錄行數） |
| coordinator 剛重啟時第一次服務呼叫的回覆可能遺失（DDS 尚未配對回覆通道，evidence/phase_c_20261111/extra/） | 記為已知問題（ROS_INTERFACES 第 11 項），測試腳本未加等待；操作介面是人按按鈕，影響小 |

## 設定重複

| 問題 | 處理 |
|---|---|
| 手臂軸心位置在 6 個腳本各寫一份，C 格位與瓶蓋起點也分散 | 已修：集中到 `scripts/field_layout.py`，`generate_cad_robot.py`、`generate_world.py`、`test_cad_pose.py`、`test_ik.py`、`runtime_settings.py`、三個模擬視覺腳本改為引用；重新產生的模型、場景與原本逐位元組相同 |

## 未做（依「只做必要」）

- MoveIt mock、實機（`hardware.launch.py`）模式的 live graph。
- 測試腳本在 coordinator 重啟後的等待修正。
