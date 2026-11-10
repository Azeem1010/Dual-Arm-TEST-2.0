# 操作介面階段 3：任務控制、強制停止、回 HOME、復歸

2026-11-11，WSL Ubuntu 24.04 + Jazzy。以 ROS_DOMAIN_ID=78、GZ_PARTITION=hmi_stage3 和暫存的狀態目錄隔離，不碰操作者自己的工作階段與 journal。介面視窗以離屏方式執行，按鈕用程式按下，確認視窗一律回答「確定」（確認視窗本身由單元測試涵蓋）。

## 檔案

| 檔案 | 內容 |
|---|---|
| `stage3_build_test.sh` | 建置三個套件、跑兩套單元測試、對新改的檔案做 pyflakes 檢查 |
| `01_build.log`、`02_pytest.log`、`02_lint.log` | 上面的輸出 |
| `stage3_live.sh`、`stage3_live_check.py` | Gazebo 實測。不加參數跑三個部分；加 `holding` 只跑第三部分 |
| `03_live_check.log`、`04_live_check.json`、`screens/`、`launch_logs/` | 第一次實測（三個部分） |
| `03_live_check_holding.log`、`04_live_check_holding.json`、`screens_holding/`、`launch_logs_holding/` | 第三部分重跑 |

## 結果

| 項目 | 結果 | 說明 |
|---|---|---|
| 建置 | `PASS` | 01_build.log |
| 單元測試 | `PASS` | HMI 291、coordinator 285 |
| pyflakes | `PASS` | 新改的檔案沒有 F 類問題 |
| 一輪搬運 | `PASS` | 「開始工作」到 `SUCCEEDED`，245.6 秒 |
| 未持物時強制停止，再復歸並重新開始 | `PASS` | 停在 `ARM1:APPROACH_A`（手臂移動中）。按下後 0.3 秒鎖定並停用控制器，任務 `FAULT`。鎖定時「開始工作」與「復歸」都不能按；解除鎖定 0.3 秒；未勾選時不能按回 HOME；回 HOME 4.4 秒、兩臂在 HOME；復歸後 `IDLE`；再開始到 `SUCCEEDED`，190.8 秒 |
| 持物時強制停止，改用重置模擬 | 第一次 `FAIL`，重跑 `PASS` | 見下 |
| 關閉後殘留 | `PASS` | 兩次都沒有 Gazebo、帶標記程序或 ROS 節點 |

### 第三部分第一次為何失敗

第一次實測的第三部分是同一個模擬裡的第三次取料。手臂 1 下降到 (-0.14, 0.035) 的瓶蓋時，`arm1_arm_elbow_flex_joint` 到了 1.5 rad 的限位，停在離目標 16.6 mm 處，任務自己進入 `FAULT`（`did not settle within 0.0005 m, last error 0.01664 m`），手臂從頭到尾沒有吸到東西，所以「持物時停止」沒有測到。之後按回 HOME，MoveIt 因起始狀態超出關節範圍拒絕規劃（`CheckStartStateBounds`，code -26），見 launch_logs/ 第一個檔案第 1434 行。

這是 A 區可達性的既有限制（MODIFICATION_PLAN C30），不是階段 3 的程式問題；04_live_check.json 的 `stop_holding_reset_simulation: false` 照原樣保留。

### 重跑

用新的模擬只跑第三部分，在第一次取料時停止：任務在 `ARM1:LIFT_A`、手臂 1 `held` 時按下強制停止，1.0 秒鎖定並停用控制器。解除鎖定後，復歸因「兩臂需先回 HOME」不能按；勾選後按回 HOME，coordinator 拒絕（`An arm may still hold an object, which cannot be removed in simulation; reset the simulation instead`）。按重置模擬，46.1 秒後就緒、任務 `IDLE`、格位為預填的 1、2。

## 這次發現、尚未處理

- 手臂停在關節限位外時，回 HOME 無法規劃，介面除了重置模擬沒有其他恢復方式。實機上要人工處理，這個情況在 H5 前要定出程序。
- 第三部分的橫幅原本仍提示「勾選後按回 HOME」，已改為模擬中有持物時提示「重置模擬」（單元測試 `test_simulated_fault_while_holding_points_to_reset_simulation`）。重跑時用的是改之前的版本，只有橫幅文字不同。
- 介面上的「控制器啟用」由每秒一次的 `list_controllers` 更新，鎖定後約 1 秒才會變；是否已停用以 `/safety/status` 的 `controllers_stopped` 為準。

## 沒有涵蓋

吸盤確認、上扭力（階段 5）、Mock 與 Mock Serial 下的強制停止、實機。
