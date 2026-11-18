# 2026-11-18 arm2 B 區重新示教（Prototype）

狀態：NOT_RUN（只有讀值與模型換算，尚未在實機上執行）

## 做了什麼

1. 系統已停（序列埠沒有其他程式）。`manual_position_terminal.py --arm arm2` 送 `TORQUE,arm2,0`，回覆 `OK,TORQUE,arm2,0`；現場人員扶住 arm2。
2. `../20261111_H1/pose_guide.py --arm arm2 --target 95,707,757,700`（前一次示教值）每 0.3 s 送 `READ`，紀錄 `teach_arm2_B.csv`，畫面輸出 `pose_guide_output.txt`。
3. 現場人員把吸盤壓在 B 區中間的瓶蓋上；最後穩定讀值 `94, 704, 764, 689`（12:53:36–37 不變），已填入 `b_teach.raw.arm2`。

## 模型檢查（`teach_to_slots_from_config.txt`）

arm2 接觸點 (20.5, 1.8, 16.1) mm，傾角 2.1°（前一次 4.2°），離 arm1 接觸點 5.6 mm（前一次 5.0 mm）。

## 未確認

- 新姿勢還沒在實機上跑過。arm2 扭力在示教後仍是關的，啟動系統後要先上扭力。
