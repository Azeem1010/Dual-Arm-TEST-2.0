# 2026-11-17 arm2 B 區重新示教（Prototype）

狀態：NOT_RUN（只有讀值與模型換算，尚未在實機上執行）

## 做了什麼

1. `manual_position_terminal.py` 送 `TORQUE,arm2,0`（回覆 `OK,TORQUE,arm2,0`），現場人員扶住 arm2。
2. `../20261111_H1/pose_guide.py --arm arm2` 每 0.3 s 送 `READ`，紀錄 `teach_arm2_B.csv`，畫面輸出 `pose_guide_output.txt`。
3. 現場人員把吸盤壓在 B 區（場地中間綠框）的瓶蓋上；最後穩定讀值 `90, 700, 779, 683`（14:20:15）。

## 發現

同樣是 B 區，2026-11-11 讀 `396, 703, 756, 700`。j2～j4 相近，j1 差 −306 count（約 90°）。
推測 arm2 底座讀值整體偏移（舵盤鬆脫或拆裝？），**未經實機確認**；現場人員要求不再測試，直接採用。

## 使用者決定（2026-11-17）：直接採用

為了讓模型和實機一致，同一個 −306 偏移套用到所有 arm2 j1（只改 Prototype 檔案）：

| 檔案 | 修改 |
|---|---|
| `src/cm530_hardware/config/calibration_prototype.yaml` | arm2 j1 `zero_raw` 512→206，`min_raw/max_raw` 219..805→0..499（URDF ±1.5 rad 跟著零點） |
| `src/dual_arm_coordinator/config/prototype/coordinator.yaml` | `b_teach.raw.arm2` → `90, 700, 779, 683`；`c_slot_teach.raw` 每格 j1 −306，j2～j4 不變 |

模型檢查（`teach_to_slots_from_config.txt`）：arm2 B 接觸點 (21.6, 8.8) mm，離 arm1 接觸點 4.2 mm（舊值 8.4 mm）；C 區 8 格位置與修改前完全相同。

## 未確認、風險

- 偏移只由一次 B 區讀值推得，C 區 8 格的 j1 是推算，不是重新示教；可能差幾 count。
- arm2 HOME（firmware 256）在模型中的方向因此改變（−75°→+15°），實際方向未確認。
- 新 B 接觸姿勢比 arm1 低約 5 mm（模型 13.8 vs 18.9 mm），下壓可能較用力；壓太深時加大 `b_teach.contact_lift_m`。

## 16:13 第二次示教（同日）

使用者要求重新設定 arm2 B 區示教值。停系統 → `TORQUE,arm2,0`（`OK,TORQUE,arm2,0`）→ `pose_guide.py` 讀值，紀錄 `teach_arm2_B_2.csv`、`pose_guide_output_2.txt`。
最後穩定讀值（16:13:36–39 不變）：`95, 707, 757, 700`，已填入 `b_teach.raw.arm2`。
模型（`teach_to_slots_from_config_2.txt`）：arm2 接觸點 (21.4, 1.9, 16.5) mm，傾角 4.2°，離 arm1 接觸點 5.0 mm。
j1 95 與 14:20 的 90 一致，支持 arm2 j1 偏移 −306 的推定。狀態：NOT_RUN。
