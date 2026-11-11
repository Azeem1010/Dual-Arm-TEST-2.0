#!/usr/bin/env python3
"""arm2 線 F 對齊偏移修正（2026-11-11 測試人員回報）。
末端偏向 C（arm2 自身左方）→ 讀值偏大 → 修正 j1 = 讀值 − atan2(off, s)/RAW_DEG。
s（末端沿尺距舵盤中心）未報，假設 20 cm，另列 15、25 cm 敏感度。
"""
import math, statistics as st
RAW_DEG = 300 / 1023
samples = [('arm2_lineF_4', 532, 1.5), ('arm2_lineF_5', 564, 4.3), ('arm2_lineF_6', 558, 4.3)]
for s in (15.0, 20.0, 25.0):
    c = [j1 - math.degrees(math.atan2(off, s)) / RAW_DEG for _, j1, off in samples]
    print(f's={s:.0f} cm：修正後 {", ".join(f"{x:.0f}" for x in c)}，平均 {st.mean(c):.0f}，全距 {max(c)-min(c):.0f} raw')
s = 20.0
for name, j1, off in samples:
    d = math.degrees(math.atan2(off, s))
    print(f'{name}: {j1} − {d:.1f}° ({d/RAW_DEG:.0f} raw) = {j1 - d/RAW_DEG:.0f}')
c = st.mean(j1 - math.degrees(math.atan2(off, s)) / RAW_DEG for _, j1, off in samples)
print(f'home_C 590 相對線 F：({590} − {c:.0f}) × {RAW_DEG:.4f} = {(590 - c) * RAW_DEG:+.1f}°（正值＝往 arm2 左方／C 外側）')
