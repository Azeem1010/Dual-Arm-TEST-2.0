# 2026-11-18 ESP32 自動重開（RTS = EN）

狀態：PASS（agent 部分，實機 ESP32；完整系統啟動尚未從 UI 跑過）

使用者要求：啟動系統時一起啟動 micro-ROS agent，且不用再手動按 EN。

## 改動

- `src/dual_arm_bringup/scripts/esp32_reset.py`：開序列埠前先把 DTR、RTS 設為 off，開啟後 RTS on 0.1 s 再 off（EN 拉低再放開），DTR 一直 off（IO0 高，正常開機，不進 bootloader）。
- `launch/hardware_prototype.launch.py`：agent 啟動後 `esp32_reset_delay_s`（預設 3 s）執行一次；設 0 則不自動重開。UI 的實機 Prototype 啟動本來就帶 `esp32_port`，所以 agent 與重開都隨 UI 的「啟動系統」執行。

## 實測（Orin，系統未啟動）

1. `agent_control_then_pulse.log`：只開 agent，15 s 內沒有 session；手動執行脈衝後 2.2 s `session established`。
2. `launch_agent_reset.log`：用 prototype launch 的 `micro_ros_agent()` 部分（agent + 自動重開），agent `running` 後約 4.7 s 建立 session，`/suction_status`、`/suction_command` 各 1 個發布／訂閱。
3. 送 `/suction_command 2`（arm1 release，繼電器關），`/suction_status` 回 `2`。

## 未驗證

- 從 UI 按「啟動系統」的完整流程。
- agent 已連線時重開 ESP32 會讓繼電器回到關閉；啟動時本來就沒有吸住東西，所以沒有影響。
