# 2026-11-17 Prototype 連續搬運（兩臂重疊作業）

使用者決定（2026-11-17）：Arm 2 把上一件送去 C 時，Arm 1 去 A 取下一件；兩臂會同時動作；只在 Prototype 用設定區塊開啟，重疊時 Arm 1 只在 A／HOME 之間。模擬與嚴格實機不變。

## 做法

- `config/prototype/coordinator.yaml` 新增 `overlap: {clearance_m: 0.025, wait_s: 240}`。只限 Prototype，且要 `gripper.auto_confirm`。刪掉就回到一次一臂。
- `workflow/overlap.py`：兩臂各一個執行緒。Arm 1 取完在 HOME 拿著等，Arm 2 從 B 吸起並離開 B 後才放下一件；B 區仍然只有一個擁有者。B 姿勢與本次會用到的每一格在開始時一次檢查。A 區取完就結束（SUCCEEDED，訊息寫取了幾件）。一臂故障時另一臂把手上那段做完再停；取消或安全停止兩臂同時停。
- `gateways/motion.py`、`lanes.py`：重疊時 MoveIt 只規劃（一次一個），軌跡直接送 `/armN_controller/follow_joint_trajectory`。送出前用模型算整段軌跡所有關節座標的 x 範圍，兩邊各加 `clearance_m` 後預約；和另一臂（移動中的預約，或靜止時所在範圍）重疊就等，最多 `wait_s`。只看 x，看不到校正誤差。
- ESP32 指令加鎖依序送出（回音不分手臂）；journal 的 holding 更新加鎖。

## 檢查

| 紀錄 | 內容 | 結果 |
|---|---|---|
| `pytest_coordinator.log` | coordinator 單元測試（新增 25 項：重疊順序、故障、車道、設定、ESP32 回音、關節座標） | PASS，450 |
| （終端輸出） | `test_overlap.py` 連跑 10 次，檢查執行緒時序 | PASS，每次 17 |
| `pytest_hmi.log` | 操作介面單元測試（標籤改為「搬運件數（模擬／Prototype）」） | PASS，320 |
| `lanes_check.py`、`lanes_check.txt` | Prototype 姿勢的車道衝突（模型，路徑以關節直線近似 MoveIt 規劃） | 見下 |
| | MoveIt 只規劃＋直接送控制器（Mock Serial） | NOT_RUN：當時 Orin 上實機 Prototype 系統正在執行，沒有啟動 Mock，也沒重建 install |
| | 實機 | NOT_RUN |

車道（加上 0.025 m 餘裕後）：Arm 1 在 A 區 69 個可達點的取料段最右 x −0.040；Arm 2 HOME↔B 最左 −0.007，不衝突（差 33 mm）。Arm 1 HOME↔B 最右 0.064；Arm 2 HOME↔C 八格最左都是 0.075，不衝突（差 11 mm，較緊）。實際 MoveIt 路徑可能繞得比關節直線大，那時只會等待，不會放行。

## 還沒做

- 先在 Mock Serial 跑一次 `/dual_arm/go_home`，確認 plan-only 加 FollowJointTrajectory 能走完。
- 實機第一次建議 `cycles:=2`、慢速，現場人員手放在 CM-530 電源開關上。
- Orin 要重建 `dual_arm_coordinator`、`dual_arm_hmi` 才會生效。
