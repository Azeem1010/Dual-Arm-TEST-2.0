#!/usr/bin/env python3
"""斜線（lineF_2）角度換算。輸入為測試人員 2026-11-11 回報的原始值，單位推定為 cm（待確認）。
θ：從線 F（正對場地）往 A 區（手臂自身右方）偏轉的角度。
H1 實測：往右（A 區）轉 j1 讀值變小 → j1_F = j1_diag + θ / (300/1023)。
"""
import math
RAW_DEG = 300 / 1023
reported = {'dx_reported_cm': 15.5, 'dy_cm': 11.0, 'e_cm': 1.5}   # e：舵盤中心在板外
j1_diag = 83   # lineF_2 最後讀值（測試人員貼回；CSV 檔未找到）
cases = {
    'A：回報的 dx 是 P 到板邊，dx = 15.5 + e': reported['dx_reported_cm'] + reported['e_cm'],
    'B：回報的 dx 已含 e': reported['dx_reported_cm'],
}
for name, dx in cases.items():
    dy = reported['dy_cm']
    th = math.degrees(math.atan2(dy, dx)); r = math.hypot(dx, dy)
    print(f'{name}: dx={dx:.1f} cm, dy={dy:.1f} cm, θ={th:.1f}°, |OP|={r:.1f} cm（應≈20）, '
          f'推得 j1_F = {j1_diag} + {th:.1f}/{RAW_DEG:.4f} = {j1_diag + th / RAW_DEG:.0f}')
# 誤差：各長度 ±0.5 cm（回報值為 0.5 cm 解析度）
dx, dy = 17.0, 11.0
ths = [math.degrees(math.atan2(dy + a, dx + b)) for a in (-.5, .5) for b in (-.5, .5)]
print(f'案例 A 在 ±0.5 cm 誤差下 θ 範圍 {min(ths):.1f}°～{max(ths):.1f}°'
      f' → j1_F {j1_diag + min(ths) / RAW_DEG:.0f}～{j1_diag + max(ths) / RAW_DEG:.0f}')
