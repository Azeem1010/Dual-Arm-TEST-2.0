# 實機測試紀錄（Orin 現場）

## 2026-11-11：UPDATE、P0 PASS，H1、V0 進行中

來源：[Azeem1010/Dual-Arm-TEST-2.0](https://github.com/Azeem1010/Dual-Arm-TEST-2.0) commit `13a5b4f5f047acec16e8bd25e294029d0b98fe60`（2026-11-11 17:02）。測試時的程式版本：上午 `3fd258c`，14:50 起 `8ad9d47`。

和 11-10 一樣只複製文字紀錄與原始 CSV；照片、相機截圖、建置與 Mock 啟動日誌、`20261111_UPDATE/outputs/` 留在來源 repo。

| 檔案 | 內容 |
|---|---|
| `20261111_tester_report.md` | 現場報告全文（來源 repo 的 README.md） |
| `20261111_SUMMARY.md` | 現場維護的總表（來源 `evidence/hardware/SUMMARY.md`） |
| `20261111_UPDATE/` | 更新到 `8ad9d47` 後重新建置、離線測試 PASS；只複製 record、腳本與小型日誌 |
| `20261111_P0/` | 每日複查 PASS（口頭回報） |
| `20261111_H1/` | 兩臂 j1、j2、伸直、HOME、線 F／L、板寬、C 格位與示教的紀錄、逐筆 READ 的 CSV、換算腳本、現場寫的唯讀工具 `pose_guide.py` |
| `20261111_V0/` | 三顆相機的 by-path 對應與 arm1_cam 方向；`snapshots_SHA256SUMS` 是截圖的雜湊（開發端產生） |
| `20261111_fk_crosscheck/` | 開發端的離線檢查：arm2 C 格示教讀值的 FK 半徑與尺量比對 |
| `20261110_H1/record.md` | 已更新為來源最新版（多了 2026-11-11 的註記） |

複製時的差異：
- 來源的 `20261111_H1/arm2_lineF_4.csv.`、`_5.csv.`、`_6.csv.` 檔名結尾有一個點，Windows 不能建立，這裡去掉結尾的點。`SHA256SUMS` 保留原樣（裡面仍是原檔名）。
- 依 `SHA256SUMS` 核對，`record.md` 與 `j1_measure_diagram.html` 的雜湊不符：現場在產生雜湊後又改過這兩個檔。這裡的檔案與來源 commit 的內容逐位元相同。

### 開發端的判讀（2026-11-11）

只整理事實，決定見 [MODIFICATION_PLAN.md](../../MODIFICATION_PLAN.md) 第 2 節。數值都是 H1 近似值（直尺 0.5 cm、目視、j1 ±5°），不可填入 `calibration.yaml`。

- **和模擬一致**：arm2 j1 方向 +1；j1 正對場地 arm1 約 193、arm2 約 519（模擬 192.3、512）；home_A、home_C 朝向；兩臂 j2 往使用者前傾讀值變大（模擬 +1）。11-10 的「j2 上抬讀值變小」是往底座後方倒，作廢。
- **和模擬不同（階段 C）**：板子短邊 240 mm（模型 300）；軸心在手臂側長邊外約 5 mm（arm1 另一次 15 mm；模型在板內 63 mm）；C 格 1、2 最靠手臂、單號欄靠 B（模型轉了 180°）。
- **相機**：兩顆手臂相機同型號、沒有序號，`/dev/v4l/by-id/` 只剩一條連結，現場改用 `/dev/v4l/by-path/`，是否採用待決定。
- **安全**：現場兩次要求用 HOME 指令讓手臂自己移動，都沒有執行（Moving Speed 未讀、H3 未授權），改為扭力關閉、讀值導引的人工擺位。兩臂目前扭力關閉。

## 2026-11-10：SETUP、P0、H0 PASS，H1 進行中

來源：[Azeem1010/Dual-Arm-TEST-2.0](https://github.com/Azeem1010/Dual-Arm-TEST-2.0) commit `fc4cd41be7766621551c5519a15ef5a52bb17f62`。測試時的程式版本是本專案 `3fd258c`。

這裡只複製文字紀錄，照片與大型日誌（建置、安裝、Mock 原始日誌，約 6.7 MB）留在來源 repo。紀錄內的相對連結指向來源 repo 的路徑；照片的雜湊值保留在 `*/photos_SHA256SUMS`，可用來核對來源 repo 的檔案沒有變動。

| 檔案 | 內容 |
|---|---|
| `20261110_tester_report.md` | 現場報告全文（來源 repo 的 README.md） |
| `20261110_SUMMARY.md` | 現場維護的總表 |
| `20261110_SETUP/` | 第一次安裝 FAIL（ROS 來源 Signed-By 衝突） |
| `20261110_SETUP_retry/` | 修正後 PASS；`uncommitted_vs_3fd258c.patch` 是現場對安裝腳本與文件的修改 |
| `20261110_P0/` | 開始前準備 PASS（急停為口頭回報） |
| `20261110_H0/` | 唯讀連線 PASS |
| `20261110_H1/` | 只完成 arm1；arm2 NOT_RUN |

### 開發端的判讀（2026-11-10）

只整理事實，D0、D1 的決定見 [MODIFICATION_PLAN.md](../../MODIFICATION_PLAN.md) 第 2 節。

- **D0**：arm1 底座往手臂自身右方轉，末端朝 A 區（口頭回報＋俯視照片）。即 A 在 `arm1_base` 的 y < 0，使用者由左到右看到 A | B | C，與 commit `c7dfba3` 的模擬遠側配置相反，與 `c7dfba3` 之前的 CAD 原始方向一致。
- **j1（arm1）**：右轉時 raw 變小，方向 +1；模擬假設 −1。arm2 未測，不可沿用。
- **j2（arm1）**：回報「上抬時讀值變小」（498 → 384）。起點 j2 = 498 已接近 raw 512 的垂直，從垂直往任一側轉都會讓末端變低，所以「上抬」指的是往場地側還是往底座後方，紀錄沒有寫，**方向結論待現場補充**。
- **伸直**：READ 200,505,498,513，照片為垂直朝上（人手扶持、目視），大致支持「j2～j4 raw 512 = 垂直伸直」，精確零點待 H2。
- **場地**：兩軸心相距 200 mm，各自對齊 A/B、B/C 分界（與模型 x = ±0.10 相符）；軸心在靠手臂的長邊外約 10 mm（模型為板內約 63 mm）；板子短邊推算約 235 mm（文件與 `env_vision.yaml` 寫 300 mm），尚未直接量。
- **安裝**：補裝的 FFmpeg 6.1 開發套件覆蓋了 NVIDIA `ffmpeg 7:8.0.1-nvidia1` 的部分檔案（安裝日誌 "Replaced by files in installed package ffmpeg"）。對 Jetson 硬體影像編解碼的影響 `NOT_RUN`，V0 時要留意。
- **硬體狀態**：arm1 在 H1 送了 `TORQUE,arm1,0` 後未恢復，重新上電前要扶住。
