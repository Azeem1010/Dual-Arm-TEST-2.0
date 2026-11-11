#!/usr/bin/env python3
"""C 格中心座標換算與示教 j1 交叉檢查（2026-11-11）。
測試人員原始值（cm）：d_F2＝中心到 F2 膠帶水平距離（往 C 側）；d_edge＝中心到手臂側長邊距離。
示意圖定義：F = d_edge×10 mm；L = 200 + d_F2×10 mm（F1→F2 取 200 mm，未直接量）。
交叉檢查：arm2 軸心假設在 F = −5 mm、L = 205 mm（直尺目測：B|C 往 C 0.5 cm、長邊外 0.5 cm），
正對場地 j1 ≈ 519（線 F，±5°）；j1 往左（+L）增加，0.2933°/raw。
"""
import math
RAW = 300 / 1023
raw = {1: (3.5, 7.5), 3: (3.5, 11), 5: (3.5, 14.5), 7: (3.5, 18),
       2: (7.0, 7.5), 4: (7.0, 11), 6: (7.0, 14.5), 8: (7.0, 18)}
teach = {1: 572, 2: 635, 3: 560, 4: 608, 5: 549, 6: 587, 7: 540, 8: 576}
AX_F, AX_L, J1_F = -5.0, 205.0, 519
print('格  F(mm)  L(mm)  幾何角(°)  示教 j1  示教角(°)  差(°)  幾何預測 j1')
for k in sorted(raw):
    d_f2, d_edge = raw[k]
    F, L = d_edge * 10, 200 + d_f2 * 10
    geo = math.degrees(math.atan2(L - AX_L, F - AX_F))
    tch = (teach[k] - J1_F) * RAW
    print(f'{k}  {F:6.0f} {L:6.0f}   {geo:+7.1f}    {teach[k]:5d}   {tch:+7.1f}  {tch - geo:+6.1f}   {J1_F + geo / RAW:6.0f}')
