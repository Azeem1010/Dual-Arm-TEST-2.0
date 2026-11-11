# 階段 C：依 2026-11-11 實測更新場地幾何與格位編號

執行環境：WSL2 Ubuntu 24.04、ROS 2 Jazzy、Gazebo Harmonic。各資料夾的 `commit.txt` 是執行時的 HEAD，修改都還在工作目錄（未提交）。指令與每步結果在各資料夾的 `summary.tsv`。

## 改了什麼

量測來源：[../hardware/20261111_H1/](../hardware/20261111_H1/)。

| 項目 | 舊值 | 新值 |
|---|---|---|
| 板子 | 600×300 mm | 600×240 mm |
| 兩臂 j1 軸心（world） | (±0.10, 0.08725)，在板內 63 mm | (±0.10, 0.125)，在手臂側長邊外 5 mm |
| C 格位 | 轉 180°、兩欄對調 | 實物編號：1、2 最靠手臂，單號欄靠 B（x 0.135），雙號欄 x 0.170；列 y 0.050／0.015／-0.020／-0.055 |
| A 區瓶蓋起點 | 固定 8 點 | C 格位對 x = 0 的鏡像（模擬選擇） |
| B 放置點 | (0, -0.02) | (0, 0)，兩臂 11-11 示教的位置 |
| `prefilled_slots` | 2 | 0 |
| 介面格位圖 | 1 號在左下 | 1 號在左上（使用者視角） |
| `vision_pkg` | 1 號在左下 | 新增 `slot_one_corner`，實機 `arm2_vision.yaml` 設 `top_left` |
| 模擬手臂相機 | x ±0.20 | x ±0.15，在瓶蓋群與格位群上方 |
| `sim.launch.py` 相機 static TF | arm1 在 +0.2（舊左右） | 與 world 一致 |

## 各資料夾

| 資料夾 | 內容 | 結果 |
|---|---|---|
| `t1/` | 第一次 t1 | IK 16/18（已知：cap_8、格位 8）；coordinator、HMI 單元測試與格位位移研究失敗，原因是測試仍是舊座標 |
| `t1_rerun/` | 修正測試後重跑 t1；格位位移研究是舊配置工具，已從 t1 移除 | 除已知 IK 16/18 外 PASS |
| `t2_interrupted/` | 第一次 t2，使用者要求中止 | 冒煙測試只有 Gazebo 關閉逾時失敗（已知，HEAD 也有） |
| `t2_stopped/` | 第二次 t2，使用者要求中止 | 冒煙測試 `workspace_views` 失敗：2 Hz 視角相機在 0.2 倍實時下逾時，沒有程式修改 |
| `t2/` | 完整 t2 | 冒煙（關閉逾時）、舊 pipeline、運動 gateway、操作工具、視覺取料失敗；兩物體回歸、影像分析、座標驗證、安全監控、README 截圖 PASS |
| `t2_rerun/` | 改測試裡的舊座標後重跑失敗步驟 | 運動 gateway、操作工具 PASS；舊 pipeline 拿 cap_1 時 TCP 偏 28 mm；視覺取料 arm1 校正誤差 1.15 mm > 1 mm |
| `t2_rerun2/` | 舊 pipeline 改成和 coordinator 一樣先拿離 HOME 最近的瓶蓋 | PASS |
| `t2_camera/` | 手臂相機移到 x ±0.15，重新產生場景、建置後重跑冒煙、影像、座標、視覺校正與取料 | 全部 PASS；arm1 校正誤差 0.70 mm |
| `batch/` | 八物體回歸 `test_transfer_regression.py batch`，新啟動的模擬 | 見下方 |
| `t1_final/` | 最終程式完整 t1 | 除已知 IK 16/18 外 PASS；單元測試 coordinator 285、HMI 293、vision 100 |
| `t2_final/` | 最終程式完整 t2，含 README 截圖 | 除冒煙測試的關閉逾時外 PASS；視覺校正誤差 0.70 mm |
| `extra/` | t2 不含、但這次改動有關的兩項：回歸 `faults`（B 放置點改了）、Coordinator 節點（`test_coordinator_sim.py`，預設從空 C 區） | 見下方 |

## 測試修正（測試寫死舊配置，不是系統問題）

- `test_motion_gateway.py`：「已知不可達目標被拒絕」改用格位 8（格位 1 現在可達）。
- `test_operator_tools.py`：底座座標換算的測試點改為新軸心。
- `demo_transfer_one.py`、`demo_transfer_pipeline.py`：座標改由 `coordinator.yaml` 讀；依 coordinator 的規則先拿離 arm1 HOME 最近的瓶蓋（cap_4、cap_6、cap_3）。
- `test_vision_pick_sim.py`：只停放搆不到的 cap_8，預期放在格位 1、2。

## 發現

- 舊 pipeline 讓 arm1 拿 cap_1（-0.135, 0.050，離軸心 83 mm）時停在離目標 28 mm、比目標低 10 mm 處，推測撞到相鄰瓶蓋，未確認。Coordinator 不會先選它。實機若瓶蓋擺得很靠近手臂，要注意。
- 模擬手臂相機在 HOME 仍被手臂擋住：arm1 只看到 3 顆，arm2 找不到任何格位（C31、D7 未變）。
- 冒煙測試的 Gazebo 關閉逾時時有時無（`t2/` 失敗、`t2_camera/` 通過）。

## 八物體回歸

`batch/regress_batch.log`：從空 C 區開始，連續放完 7 件到格位 1～7（真值確認），第 8 件時 arm2 回報 `cannot reach (0.17, -0.055, 0.054)`，任務 FAULT。測試預期這個結果，所以判 `PASS`；以需求來看八件搬運仍是 `FAIL`（C30）。第一次執行時執行腳本沒設 `ROS_DOMAIN_ID`，一直等不到控制器，測試沒開始就被停止，紀錄已刪除後重跑。

## 額外情境

| 資料夾 | 測試 | 結果 |
|---|---|---|
| `extra/` | 回歸 `faults`（釋放失敗、急停心跳、持物取消；B 放置點已改 (0, 0)） | PASS，21 項 |
| `extra/` | Coordinator 節點 `test_coordinator_sim.py` | FAIL：coordinator 重啟後，用舊 token 呼叫 `/dual_arm/recover` 120 秒沒收到回覆。coordinator 日誌（`extra/coordinator_logs/`）有 `failed to send response (timeout)`，服務有處理但回覆沒送到客戶端；這一步與場地座標無關 |
| `extra_rerun/` | 同一測試，新啟動的模擬重跑一次 | PASS，22 項，包含從空 C 區放到格位 1 |

通過次數 1／2，失敗原因是 ROS 服務回覆遺失，沒有改程式。若再出現，要查新程序啟動後服務回覆的配對時間。

## 操作介面截圖

`hmi_images/capture.log`：`scripts/capture_hmi_images.py docs/images` 從實際模擬重拍 `ui_ready.png`、`ui_working.png`、`ui_stopped.png`，格位圖改為實物編號。
