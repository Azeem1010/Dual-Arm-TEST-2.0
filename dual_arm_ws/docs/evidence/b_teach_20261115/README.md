# 2026-11-15 Prototype：B 區交接改用示教關節值

使用者決定（2026-11-15）：實機 Prototype 的 B 區交接也改用 11-11 H1 的示教讀值，不再走「`b_place_xy_m` → IK」。Arm 1 放下、Arm 2 吸起都到各自的示教姿勢。A 區照舊；C 區照 11-13 的示教（`slot_teach_20261113/`）；模擬與嚴格實機不變。

## 示教讀值

| 手臂 | 檔案（最後一筆 READ） | raw j1,j2,j3,j4 | 備註 |
|---|---|---|---|
| arm1 | `teach_arm1_B_2.csv` | 350, 731, 702, 697 | 重做那筆，紀錄採用；第一筆 `teach_arm1_B.csv`（j1 634）不採用，也超出 arm1 j1 限位 0..486 |
| arm2 | `teach_arm2_B.csv` | 396, 703, 756, 700 | |

**示教時吸盤壓著瓶蓋**（示教紀錄沒寫，使用者 2026-11-15 確認），所以讀值就是接觸姿勢：Arm 1 在這裡放開，Arm 2 在這裡吸。兩臂示教點的模型高度 18.9／19.8 mm，和 C 格示教（16～20 mm）一致。

## 做法

- `config/prototype/coordinator.yaml` 新增 `b_teach`：兩臂 raw、`contact_lift_m` 0、`arrival_tolerance_raw` 4、`max_line_drift_m` 0.003。只有 `mode: prototype` 能用（`task_config.py`）。
- `homes.load_b_joints()`：和 C 格一樣，用 driver 同一份校正檔換算並檢查 `min_raw..max_raw`，所以馬達收到的就是示教值。
- `motion_math.prepare_b_poses()`：接觸姿勢 = 示教值；接近姿勢 = 模型 TCP 正上方 `approach_z`（52 mm，兩臂都解得到）。
- `MotionGateway.move_b()`：APPROACH_B 由 MoveIt 規劃到關節目標；DESCEND_B、LIFT_B 走關節直線，偏離超過 3 mm 就停；到位判定每軸 ≤ 4 raw。和 `move_slot` 共用 `_move_taught`。場景裡 B 區的瓶蓋放在 Arm 1 示教點的 FK xy。
- `arm1_workflow`、`arm2_workflow`：有 `b_teach` 時 B 區三段動作改呼叫 `move_b`，預檢改呼叫 `check_b`。`transfer` 在 Arm 1 取物前先檢查 Arm 2 的 B 姿勢，避免瓶蓋卡在 B 區。
- Arm 2 仍然先問 env_scene 的 B 區結果：B 區必須剛好一個物件、離 `b_place_xy_m` 在 `b_pick_tolerance_m`（50 mm）內，但移動不再用相機的 xy。

## 示教點的模型報告（`teach_report.txt`，`scripts/teach_to_slots.py --from-config`）

| 手臂 | 接觸 TCP（mm，模型） | 傾角 | 接近高度 | 關節直線偏離 | 離 `b_place_xy_m` |
|---|---|---|---|---|---|
| arm1 | 24.5, 5.8, 18.9 | 5.8° | 52 | 1.14 mm | 25.2 mm |
| arm2 | 17.0, 2.1, 19.8 | 2.7° | 52 | 0.86 mm | 17.2 mm |

兩臂的接觸點相距 8.4 mm（模型，含估計零點）。示教 raw 本身不經過模型。

## 檢查（WSL Ubuntu 24.04 + Jazzy，`bash docs/evidence/b_teach_20261115/run.sh`）

| 紀錄 | 內容 | 結果 |
|---|---|---|
| `build.log` | 重建 `dual_arm_coordinator` | PASS |
| `teach_report.txt`、`load_prototype.txt` | 示教報告；Prototype 設定載入 | PASS |
| `pytest_coordinator.log` | coordinator 單元測試（新增：設定驗證、raw 往返、arm1 用重做那筆、接近姿勢、直線偏離、兩臂 B 動作、取物前預檢、B 與 C 同時示教） | PASS，367 |
| `pytest_hmi.log` | 操作介面單元測試 | PASS，307 |
| `launch.log`、`steps.log` | Mock Serial 啟動 `hardware_prototype.launch.py`：coordinator 印出 `B hand-over uses taught joints of both arms` 和 `C slots use taught arm2 joints`，沒有例外，發布 `/dual_arm/status` | PASS |
| 同上 | 沒有相機，任務不會開始。SIGINT 後 launch 20 秒內沒結束（同 11-13），腳本送 SIGTERM，事後沒有殘留程序 | 預期限制 |
| `t0.log`、`t0/` | t0 文件檢查（`run.sh t0`，文件更新後） | PASS |

第一次跑單元測試有 1 項 FAIL：新測試用 j1 = 0 當超出限位的值，但 arm1 j1 限位是 0..486，0 在範圍內。改用 634（不採用的第一筆）後全部 PASS，程式沒改。

## 還沒做

- **`move_b` 沒有在 MoveIt + 控制器上實際執行過**（Mock 沒有相機，任務不會走到 B）。實機 NOT_RUN。
- 實機第一次建議：先讓 Arm 1 只到 B 區上方，從上方看是否在 B 區中央；再空手下到接觸姿勢看高度；Arm 2 同樣做一次。兩臂接觸點差 8 mm（模型），吸盤半徑 9 mm、瓶蓋半徑 10 mm，偏太多就 jog 後改 `b_teach.raw`。
- 扭力關閉時示教，上扭力後可能差 1～3 raw。
- Orin 要 `git pull` 後重建 `dual_arm_coordinator`。
