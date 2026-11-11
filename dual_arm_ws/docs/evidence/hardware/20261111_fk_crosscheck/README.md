# arm2 C 格示教讀值的 FK 交叉檢查（開發端，離線）

日期：2026-11-11。結果：只是旁證，不是校正，不可據此填 `calibration.yaml`。

## 做法

- 輸入：`20261111_H1` 的 arm2 示教最後讀值（j2～j4，扭力關閉、手扶到格中心），以及同一份紀錄裡直尺量的 C 格位置。
- 換算用模擬的對應：`sim/runtime.json` 的 `raw_at_cad_zero` j2～j4 = 631.35／699.55／512、方向 +1、每格 0.005118 rad；關節軸與樞軸位置取自 `docs/evidence/cad_joint_mapping.json`（CAD 原始座標）。
- 只比較末端到 j1 旋轉軸的水平距離 r，不用 j1，所以不受 j1 零點誤差影響。
- 尺量 r：以紀錄裡交叉比對採用的 arm2 軸心 (F −5, L 205) mm 計算，即 r = hypot(F + 5, (L − 200) − 5)。
- 指令：`python3 fk_check.py docs/evidence/cad_joint_mapping.json`（在 WSL Ubuntu、`dual_arm_ws/` 下執行），輸出見 `output.txt`。

## 結果

8 格的 FK 半徑與尺量半徑差 −2.7～+2.3 mm；FK 高度 16～20 mm，8 格彼此接近。表示 j2～j4 的方向 +1、raw 512 = 垂直伸直、以及 CAD 連桿長度，與實機大致相符。

## 限制

- 示教是人手扶持、目視對準格中心，直尺解析度 0.5 cm，軸心位置是目測。
- j3、j4 的方向是由這個一致性間接支持，沒有單獨量測。
- 高度的絕對值沒有和實機比對（CAD 的 z 原點不是桌面）。
