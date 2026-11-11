# 實機測試總表 — 2026-11-10

| 階段 | 狀態 | 實測值或缺漏原因 |
|---|---|---|
| SETUP 環境／下載 | PASS | aarch64、Ubuntu 24.04.5、837 GB 可用；main 與四個子模組下載完成 |
| SETUP 安裝 | PASS | 來源相容、noble-updates 與 FFmpeg 依賴已修復；原始失敗保留，最新證據見 20261110_SETUP_retry/ |
| 建置／離線測試／mock | PASS | 13 套件；259 coordinator、262 HMI、42 CM530、7 階段 Mock Serial；基本 Mock 啟停通過 |
| dialout | PASS | 已設定；使用者仍需登出再登入 |
| P0 | PASS | 急停按下斷電、放開恢復（口頭回報）；兩人以上（代號 A、B、C）；量具與 Moving Speed 軟體齊；已淨空；俯視照片 20261110_P0/photos/IMG_0891.webp。照片顯示 C 區在下方手臂側，與模擬配置可能相反，待 H1 |
| P0（11-11 複查） | PASS | 測試人員口頭確認急停、人員、淨空、扶持。見 20261111_P0/ |
| H0 | PASS | /dev/serial/by-id/usb-FTDI_FT232R_USB_UART_AH01R3LJ-if00-port0；VERSION,5、PONG；home arm1 [90,567,712,825]、arm2 [590,567,712,825] 相符；READ arm1 140,779,611,765→167,489,528,781，arm2 520,691,811,595→541,527,613,532（手推後 8 值皆變）。見 20261110_H0/ |
| H1 arm1/arm2 | PASS | 方向：兩臂 j1 往手臂自身右方轉讀值變小、右方＝A 區側；j2 上抬讀值變小；伸直 ≈ 512 垂直朝上。j1 正對場地 arm1≈193、arm2≈519；ID15 讀值連續；底座約在 A｜B、B｜C 分界外 0.5 cm、板外 0.5～1.5 cm；板寬實測 24 cm（文件 300 mm）。Moving Speed NOT_RUN（跳過）、world 軸向 BLOCKED。見 20261110_H1/、20261111_H1/ |
| H1 arm1 額外 | PASS（部分 BLOCKED） | GET_HOME 90,567,712,825；home_A 人工擺位 90,563,708,826，位於線 F 往 A 側約 30°；+Y 朝向 READ BLOCKED（軸向待負責人），以線 F≈193／線 L≈500 替代 |
| V0 | NOT_RUN | 缺三顆 by-id 對應、方向與 rotate:180 確認、三張截圖 |
| E0 | NOT_RUN | 缺 ESP32 by-id、上電泵閥/GPIO5 觀察、1～4 命令對應、至少三次吸穩時間原始錄影、status 回音時間 |
| H2 資料 | NOT_RUN | 缺每軸至少三組角度/READ、原始尺量或像素/照片/換算式、三個獨立姿態 TCP/傾角與 READ、工作表 |
| H2 驗收 | BLOCKED | D6 四項門檻空白；check、候選值填寫、唯讀十分鐘驗證未執行 |
| H3 | BLOCKED | 未填負責人授權且 H2 未通過；缺每顆 ±10 raw 方向、變化量、到位與穩態誤差、異音觀察 |
| H4～H8 | BLOCKED | 本次禁止，D8 急停心跳尚未實作 |
| D0/D1 | BLOCKED（待負責人） | 事實：A 區在手臂右方、使用者看到 A｜B｜C、兩臂 j1 方向 +1（模擬假設 A 在左、−1）；j2 上抬讀值變小、512 ≈ 垂直伸直；兩臂 j1 安裝角差約 90° |

安裝與建置已完成，前次失敗已保留。未進行實機操作，尚未提交或推送。Mock 的排程、Octomap 與關閉訊息詳見重試 record.md。
