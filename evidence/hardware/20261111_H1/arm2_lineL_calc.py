#!/usr/bin/env python3
"""arm2 線 L（沿板邊朝 C 外側＝arm2 左方）對齊偏移修正（2026-11-11 測試人員回報）。
偏板內＝朝線 F 側＝arm2 右方 → 讀值偏小 → 加；偏板外＝左方 → 讀值偏大 → 減。
s 未報，列 15/20/25 cm。線 F 修正後平均（s=20）519。
"""
import math, statistics as st
RAW_DEG = 300 / 1023
samples = [('arm2_lineL_1', 836, -3.0), ('arm2_lineL_2', 761, +5.0), ('arm2_lineL_3', 764, +4.0)]  # +＝板內
F = 519
for s in (15.0, 20.0, 25.0):
    c = [j1 + math.copysign(math.degrees(math.atan2(abs(off), s)) / RAW_DEG, off) for _, j1, off in samples]
    m = st.mean(c)
    print(f's={s:.0f} cm：修正後 {", ".join(f"{x:.0f}" for x in c)}，平均 {m:.0f}，全距 {max(c)-min(c):.0f} raw；'
          f'L−F = {m - F:.0f} raw = {(m - F) * RAW_DEG:.1f}°（幾何應為 90°）')
