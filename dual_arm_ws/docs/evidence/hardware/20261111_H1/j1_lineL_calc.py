#!/usr/bin/env python3
"""線 L 讀值的對齊偏移修正（2026-11-11 測試人員回報原始值）。
吸盤末端偏離尺邊 off_cm，偏向板內（使用者側＝線 F 側＝手臂右方）。
往右轉 j1 變小（H1 實測），所以真正對準線 L 時 j1 = 讀值 + atan2(off, r)/RAW_DEG。
r：末端沿尺距舵盤中心的距離，測試人員未量，假設 20 cm（另列 18、22 cm 敏感度）。
"""
import math, statistics as st
RAW_DEG = 300 / 1023
samples = [('lineL_1', 458, 5.0), ('lineL_2', 444, 5.5), ('lineL_3', 451, 5.0)]
F = [191, 176, 213]   # 線 F 三次獨立對齊（176 的 CSV 遺失）
for r in (18.0, 20.0, 22.0):
    corr = []
    for name, j1, off in samples:
        d = math.degrees(math.atan2(off, r)); c = j1 + d / RAW_DEG; corr.append(c)
        if r == 20.0:
            print(f'{name}: 讀值 {j1}，偏 {off} cm → 修正 +{d:.1f}° = +{d/RAW_DEG:.0f} raw → {c:.0f}')
    print(f'r={r:.0f} cm：修正後 L 平均 {st.mean(corr):.0f}（{", ".join(f"{c:.0f}" for c in corr)}）；'
          f'L−F = {st.mean(corr) - st.mean(F):.0f} raw = {(st.mean(corr) - st.mean(F)) * RAW_DEG:.1f}°（幾何上應為 90°）')
print(f'線 F 平均 {st.mean(F):.0f}（{F}）')
