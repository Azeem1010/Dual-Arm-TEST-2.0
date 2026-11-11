# 實機測試紀錄（Orin 現場）

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
