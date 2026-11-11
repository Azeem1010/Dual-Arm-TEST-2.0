# Dual-Arm-TEST-2.0：雙機械手臂實機測試紀錄

- 專案：[xian1022/dual_arm_system](https://github.com/xian1022/dual_arm_system)（main，測試時的 commit `3fd258c8e81c3bada92df92ef9a95e5749ca5178`）
- 測試日期：2026-11-10（台灣時間）
- 平台：Jetson AGX Orin，Ubuntu 24.04.5 LTS（aarch64），ROS 2 Jazzy
- 硬體：PhantomX Pincher ×2（AX-12A ×8）、CM-530（韌體 v17／協定 5）、ESP32 吸盤（micro-ROS）、USB 相機 ×3
- 馬達 ID：arm1 j1～j4 = 17、3、2、15；arm2 j1～j4 = 12、1、8、16
- 狀態只用 `PASS`、`FAIL`、`BLOCKED`、`NOT_RUN`。

這個 repo 只放測試證據與報告，不含專案原始碼。原始碼以上游的 commit `3fd258c` 為準，本機未提交的修改放在 [local_changes/](local_changes/)。

---

## 1. 一句話結論

環境與建置全部通過，實機做到 **H1 進行中**：arm1 的方向檢查已完成，arm2 還沒做。目前卡在 **D0（A 區在手臂哪一側）與文件相反**、**泡棉板實際寬度和文件不符**，以及**負責人欄位（D6 門檻、H3 授權）全部空白**。

## 2. 各階段狀態

| 階段 | 狀態 | 重點 | 證據 |
|---|---|---|---|
| SETUP 第一次 | FAIL（保留） | `install_jazzy.sh` 退出碼 100：既有 `ros2-apt-source` 和新增的 `ros2.list` 的 Signed-By 衝突 | [20261110_SETUP](evidence/hardware/20261110_SETUP/record.md) |
| SETUP 重試 | PASS | 修正來源、補 noble-updates 與 FFmpeg 開發套件後，安裝、建置、離線測試、Mock 全部通過 | [20261110_SETUP_retry](evidence/hardware/20261110_SETUP_retry/record.md) |
| P0 開始前準備 | PASS | 急停、人員、量具、淨空、俯視照片（急停為口頭回報） | [20261110_P0](evidence/hardware/20261110_P0/record.md) |
| H0 唯讀連線 | PASS | 控制板路徑、VERSION／PING、home 值相符，手推後 8 個讀值都會變 | [20261110_H0](evidence/hardware/20261110_H0/record.md) |
| H1 扭力關閉確認方向 | NOT_RUN（進行中） | arm1 完成大部分項目；arm2 全部未做 | [20261110_H1](evidence/hardware/20261110_H1/record.md) |
| V0 相機檢查 | NOT_RUN | 目前只接上 1 顆相機 | — |
| E0 ESP32 吸盤 | NOT_RUN | — | — |
| H2 校正量測 | 資料 NOT_RUN；驗收 BLOCKED | D6 門檻空白 | — |
| H3 單軸微動 | BLOCKED | 負責人未授權 | — |
| H4～H8 | BLOCKED | 本次禁止；急停心跳節點（D8）尚未實作 | — |

總表：[evidence/hardware/SUMMARY.md](evidence/hardware/SUMMARY.md)

---

## 3. 各階段詳細結果

### 3.1 SETUP：環境與建置

**環境**：aarch64、Ubuntu 24.04.5 LTS，可用磁碟 837 GB。main 與 4 個子模組都下載完成，兩份必要手冊（`HARDWARE_TEST_GUIDE.md`、`HANDOFF_PROMPT_HARDWARE_TESTER.md`）都在。

**失敗與修正過程**（失敗紀錄都保留）：

1. 第一次執行 `install_jazzy.sh` 失敗，退出碼 100。原因是系統已裝 `ros2-apt-source`，它的 `ros2.sources` 內嵌金鑰，腳本又另外新增一份 `ros2.list`，兩者的 Signed-By 衝突。處理方式：備份並停用新增的 `ros2.list`。
2. 使用者授權修改腳本：如果 APT 已經能讀到 ROS 2 Noble 來源，就沿用既有來源，不再新增（見 [patch](local_changes/uncommitted_vs_3fd258c.patch)）。
3. 第一次重試仍然失敗（exit 100）：系統缺 `noble-updates`，開發套件版本和已更新的函式庫對不上。新增 `/etc/apt/sources.list.d/dual-arm-noble-updates.sources` 後，第二次安裝 PASS（新增 502 個套件、升級 13 個，沒有移除）。
4. 第一次建置失敗：`dual_arm_gripper` 找不到 SWSCALE。補上 `libswscale-dev`、`libavdevice-dev`、`libavformat-dev`、`libavcodec-dev`、`libavutil-dev`（腳本也同步加入）後，第二次建置 PASS，13 個套件全部完成。

**離線測試**（都符合手冊預期數字）：

| 測試 | 預期 | 結果 |
|---|---|---|
| dual_arm_coordinator pytest | 259 passed | 259 passed，PASS |
| dual_arm_hmi pytest | 262 passed | 262 passed（`QT_QPA_PLATFORM=offscreen`），PASS |
| cm530_hardware colcon test | 42 項 | 42 tests, 0 errors, 0 failures, 0 skipped，PASS |
| test_cm530_mock.py | 7 階段 PASS | 7 階段 PASS |
| start_sim.sh mock | 能啟動並關閉 | 3 個控制器 active、兩臂 joint_states、MoveIt ready；SIGINT 後 exit 0 |
| dialout 群組 | — | 已加入，需要登出再登入 |

Mock 日誌裡有幾則訊息，不影響判定，原文保留：FIFO 即時排程權限警告、`field_platform` 沒有碰撞幾何、Octomap 缺 3D sensor plugin，以及關閉時 `pal_statistics context invalid`。

### 3.2 P0：開始前準備，PASS

| 項目 | 結果 | 備註 |
|---|---|---|
| 急停按下 → 馬達斷電 | PASS | 口頭回報，沒有錄影；斷電範圍（只斷馬達，還是整片 CM-530）未填 |
| 急停放開 → 恢復 | PASS | 口頭回報 |
| 兩人以上在場 | PASS | 人員代號 A、B、C，角色分配未填 |
| 直尺、手機、紙膠帶、麥克筆、白紙 | PASS | 直尺長度未填 |
| RoboPlus／DYNAMIXEL Wizard | PASS | 哪一套、裝在哪台電腦未填 |
| 淨空 | PASS | — |
| 俯視照片 | PASS | `IMG_0891.webp` |

當時 `/dev/v4l/by-id/` 只看得到 1 顆相機（Alcor，video2/3），而且正被 `~/vision_ws` 的程式占用。

### 3.3 H0：唯讀連線，PASS

- 控制板：`/dev/serial/by-id/usb-FTDI_FT232R_USB_UART_AH01R3LJ-if00-port0`（→ ttyUSB0），執行前已確認沒有其他程式占用。
- 只送 VERSION、PING、GET_HOME、READ，沒有任何動作或扭力指令。
- `VERSION,5`、`PONG`。這個「5」是協定版本；韌體資料夾名稱是 v17，兩者編號不同，沒有另外用韌體檔比對。
- home.arm1 = [90,567,712,825]、home.arm2 = [590,567,712,825]，和預期相符。

| READ | j1 | j2 | j3 | j4 |
|---|---:|---:|---:|---:|
| arm1 第 1 次 | 140 | 779 | 611 | 765 |
| arm1 第 2 次 | 167 | 489 | 528 | 781 |
| arm2 第 1 次 | 520 | 691 | 811 | 595 |
| arm2 第 2 次 | 541 | 527 | 613 | 532 |

兩次之間用手推動手臂，8 個值都有改變，表示回授是即時的。j2～j4 的變化很大，推測是扶手臂時其他關節也被帶動。H0 不判定方向。

### 3.4 H1：扭力關閉、手動確認方向（進行中）

使用韌體附的 `manual_position_terminal.py`，只送 VERSION、PING、`TORQUE,arm1,0`、READ、GET_HOME。

**arm1 = 俯視照片上方、靠 A 區那支**（測試人員轉動時確認是 arm1 的 j1 在變）。

| 項目 | 實測 | 結論 |
|---|---|---|
| TORQUE,arm1,0 | `OK,TORQUE,arm1,0` | — |
| 基準 READ | 167,499,570,787 | — |
| j1 往手臂自身右方轉 | 166,511,583,758 → 52,579,634,760（j1 −114 raw ≈ −33.4°） | j1 **變小** → 方向 **+1** |
| 右轉朝向 | 末端朝 **A 區**（口頭回報＋照片） | 手臂自身右方 = A 區 |
| j2 上抬 | 192,498,510,829 → 193,384,507,827（j2 −114 raw） | j2 上抬時讀值**變小** |
| 完全伸直 | 200,505,498,513，照片顯示垂直朝上 | j2/j3/j4 和 512 差 −7/−14/+1 raw（≈ −2.1°/−4.1°/+0.3°）。目視大致符合「512 = 垂直朝上」，但手扶加目視分辨不出幾度內的誤差，精確零點留到 H2 |
| GET_HOME,arm1 | `HOME,arm1,90,567,712,825` | 和 H0、預期相符 |
| 底座正對世界 +Y 時的 READ | NOT_RUN | +Y 的定義因 D0 還沒確定 |
| 實機 home_A 姿勢 READ | NOT_RUN | — |

j1 右轉時 j2 +68、j3 +51 也被帶動，是扶持造成的，不影響 j1 的判斷。

**桌面量測參考線 F、L**（依手冊 3.1 節「桌面座標」用紙膠帶貼出）：

| 線 | 方向 | 0 cm |
|---|---|---|
| F1（arm1）、F2（arm2） | 垂直於泡棉板長邊，指向場地，也就是朝使用者 | 各自底座的旋轉軸中心（測試人員回報有對準） |
| L | 沿靠手臂那條長邊，指向 B/C 側，也就是手臂面向場地時的左邊 | 和 F1 的交點 |

F、L 加上朝上方向構成右手座標系，軸向和文件裡 `armN_base` 的 +x、+y 定義一致。但它**不是**文件的 `world`（文件的 world 原點在場地中心），換算交給開發者。

**底座位置與區界**（1 mm 直尺，測試人員回報）：

| 位置 | L |
|---|---|
| A 端板邊 | −20 cm |
| arm1 軸心（A/B 分界，F1 貼在這條線上） | 0 |
| arm2 軸心（B/C 分界，F2 貼在這條線上） | 20 cm（實測） |
| C 端板邊 | 40 cm |

- 三區各 20 cm（實測）。
- 軸心在靠手臂那條長邊的**板外約 1 cm**，使用者那條長邊在 F = 24.5 cm。由此推得板子短邊**約 23.5 cm**。

**H1 還缺的項目**：
- arm2 的全部項目：TORQUE 0、基準 READ、j1 右轉、j2 上抬、伸直、照片。
- 8 顆馬達的 Moving Speed（register 32）。
- 馬達 ID 15 的線材觀察（手動慢轉時 READ 是否連續變化）。
- 泡棉板短邊直接量測、兩臂各自軸心到板緣的 mm 值、24.5 cm 是在 F1 還是 F2 上讀的、找軸心過程的照片。
- arm1：底座正對 +Y 時的 READ、home_A 姿勢的 READ。

**照片**（[photos/](evidence/hardware/20261110_H1/photos/)）：`H1_arm1_photo1.png`（arm1 右轉朝 A 區）、`H1_arm1_straight_front.png`（伸直）、`H1_FL_tape_overview.png`、`H1_FL_tape_closeup.png`、`H1_FL_tape_user_side_end.png`。[annotations/](evidence/hardware/20261110_H1/annotations/) 裡的是 AI 依照片畫的示意圖，不是量測資料。[provided/](evidence/hardware/20261110_H1/provided/) 是測試人員另外提供、來源未說明的截圖與照片，只存檔參考，不當作實測數據。

---

## 4. 卡住的地方與待負責人決定的事項

### 4.1 D0：A 區在手臂哪一側和文件相反（最大的問題）

- `docs/COORDINATE_FRAMES.md` 寫的是：使用者由左到右看到 C | B | A；從手臂面向場地時 **A 在左邊**；`arm1_base` 中 A 在 y > 0。
- 實測（arm1）：手臂自身右方 = **A 區**，所以 **C 區在手臂左邊**，A 在 `arm1_base` 的 y < 0。從使用者的位置看，左到右是 **A | B | C**。
- 和實測一致的線索：`calibrate_caps` 的預設 `OUTER_EDGE_Y_MM = -200`（A 在 y < 0）；測試人員提供的另一份分析截圖也寫「A 區在 arm1_base −Y」。
- 影響：手冊說結果和遠側配置不同時，**要先修模型與 `runtime.json` 並重跑模擬，才能往下**。`env_vision.yaml`、`env_vision_node.py` 的「由左至右 C | B | A」註解與設定也可能要跟著改。
- 我們沒有修改任何文件、模型或設定，等負責人決定。

### 4.2 D1：j1 方向與零點

- 模擬假設兩臂的 j1 方向是 −1；arm1 實測是 **+1**（右轉時讀值變小）。
- j2 上抬時讀值變小。
- 伸直時 j2/j3/j4 ≈ 505/498/513，大致符合「raw 512 = 垂直朝上」，但只是目視判斷。精確零點要靠 H2 的量測。
- arm2 還沒測，不能假設和 arm1 相同（arm2 的 home j1 是 590，arm1 是 90）。

### 4.3 泡棉板尺寸和文件不符

- `REQUIREMENTS.md`、`README.md`、`vision_pkg/config/env_vision.yaml`（`size_mm: [600.0, 300.0]`）寫的都是 600 × **300** mm。
- 實測推算短邊約 **235 mm**（24.5 cm − 1 cm）。用 P0 俯視照片按長邊 600 mm 比例估算，短邊也約 230～240 mm，方向一致。
- 還需要直接用尺量短邊確認。如果屬實，會影響環境相機的區域換算和 C 區格位座標。

### 4.4 底座位置和模型不同

- 模型中旋轉軸在**板內約 63 mm**（`world` y = +0.08725，沿用 CAD 數值，不是量測值）；實測在**板外約 10 mm**。
- 兩臂軸心各自對齊 A/B、B/C 分界（相距 20 cm）。這點和模型的 world x = ±0.10 相同，但 A、C 的左右相反（見 D0）。

### 4.5 負責人欄位全部空白

- **D6 驗收門檻**（`max_fit_ticks`、`min_span_rad`、`max_position_error_m`、`max_tilt_error_deg`）空白 → H2 只能收資料，`check_calibration_sheet` 記 BLOCKED，不能填 `calibration.yaml`。
- **H3 授權**空白 → 不做單軸微動。
- **負責人聯絡方式**空白。

### 4.6 硬體與量具限制

- 目前只偵測到 1 顆 USB 相機（Alcor），V0 需要接齊 3 顆，並先關掉占用相機的 `~/vision_ws` 程式。
- 量具只有 1 mm 直尺和手機。直尺量角度約 ±0.6°，比馬達一格（0.29°）粗；TCP 位置約 ±2 mm。D6 門檻要考慮這個極限。
- 急停測試只有口頭回報，沒有錄影；斷電範圍未記錄。
- H4 以後 BLOCKED：急停心跳節點（D8）還沒做，coordinator 也會拒絕實機模式。

### 4.7 目前的硬體狀態

- arm1 在 H1 中執行了 `TORQUE,arm1,0`，終端離開不會改變扭力狀態，所以 **arm1 扭力目前是關的**，重新上電前要扶好。
- arm2 本次沒有送任何扭力指令。

---

## 5. 本機修改（未提交到上游）

見 [local_changes/uncommitted_vs_3fd258c.patch](local_changes/uncommitted_vs_3fd258c.patch)，可以用 `git apply` 套用到上游 `3fd258c`：

| 檔案 | 修改 |
|---|---|
| `dual_arm_ws/scripts/install_jazzy.sh` | 沿用既有 ROS 2 Noble APT 來源，避免 Signed-By 衝突；加入 FFmpeg 開發套件 |
| `dual_arm_ws/docs/ORIN_DEPLOYMENT.md` | 補充來源衝突與 noble-updates 的說明 |
| `dual_arm_ws/docs/PROGRESS.md`、`RESUME.md`、`TEST_REPORT.md` | 最上方新增 2026-11-10 SETUP 的結果（三份內容相同） |

另外，Orin 系統層新增了 `/etc/apt/sources.list.d/dual-arm-noble-updates.sources`，停用了 `ros2.list`（改名為 `ros2.list.disabled-20261110`）。

沒有修改：third_party、測試、關節限位、容差、`calibration.yaml`、controllers、coordinator 的實機設定。`hardware_use_allowed` 與 `moving_speed_verified` 維持原值。

---

## 6. 下一步

1. **負責人**：決定 D0、D1，填寫 D6 門檻、H3 授權與聯絡方式；確認泡棉板尺寸，以及文件和 `env_vision.yaml` 是否要改。
2. **現場**：
   - 完成 arm2 的 H1。
   - 讀 8 顆馬達的 Moving Speed（先關掉其他占用序列埠的程式）。
   - 觀察 ID 15 的線材。
   - 補量泡棉板短邊和兩臂軸心到板緣的 mm 值，拍找軸心的照片。
3. H1 PASS 且負責人同意後，依序做 V0（接齊 3 顆相機）→ E0 → H2（只收資料）。

## 7. 目錄

```text
README.md                         本報告
evidence/hardware/SUMMARY.md      總表
evidence/hardware/20261110_*/     各階段 record.md、output.txt、照片、原始日誌
local_changes/                    對上游 3fd258c 的未提交修改
reference/test_instructions.md    本次測試依據的指示（含規則與交付清單）
```
