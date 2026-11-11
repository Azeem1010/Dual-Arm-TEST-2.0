# Dual-Arm-TEST-2.0：雙機械手臂實機測試紀錄

- 專案：[xian1022/dual_arm_system](https://github.com/xian1022/dual_arm_system)（main；11-10 與 11-11 上午用 `3fd258c`，11-11 14:50 起更新為 `8ad9d47`）
- 測試日期：2026-11-10、2026-11-11（台灣時間）
- 平台：Jetson AGX Orin，Ubuntu 24.04.5 LTS（aarch64），ROS 2 Jazzy
- 硬體：PhantomX Pincher ×2（AX-12A ×8）、CM-530（韌體 v17／協定 5）、ESP32 吸盤（micro-ROS）、USB 相機 ×3
- 馬達 ID：arm1 j1～j4 = 17、3、2、15；arm2 j1～j4 = 12、1、8、16
- 狀態只用 `PASS`、`FAIL`、`BLOCKED`、`NOT_RUN`。

這個 repo 只放測試證據與報告，不含專案原始碼。原始碼以上游的 commit `3fd258c` 為準，本機未提交的修改放在 [local_changes/](local_changes/)。

---

## 1. 一句話結論

環境與建置全部通過，11-11 下午已更新到上游最新 `8ad9d47` 並重新通過全部離線測試。實機做到 **H1 進行中**：兩支手臂的 j1 方向（+1，右方＝A 區，與上游 A-right 模擬一致）、j2 方向（新版方法：前傾讀值變大）、伸直讀值、HOME 實際朝向、C 區 8 格尺量與編號、C 格與 B 區示教都已取得。H1 只剩 **Moving Speed**（H3 前必做）；畫圓法依測試人員決定跳過。泡棉板短邊直接量為 **24 cm**（文件 300 mm）。C 格編號 1、2 靠手臂，與模擬假設相反。D6 門檻、H3 授權待負責人。

## 2. 各階段狀態

| 階段 | 狀態 | 重點 | 證據 |
|---|---|---|---|
| SETUP 第一次 | FAIL（保留） | `install_jazzy.sh` 退出碼 100：既有 `ros2-apt-source` 和新增的 `ros2.list` 的 Signed-By 衝突 | [20261110_SETUP](evidence/hardware/20261110_SETUP/record.md) |
| SETUP 重試 | PASS | 修正來源、補 noble-updates 與 FFmpeg 開發套件後，安裝、建置、離線測試、Mock 全部通過 | [20261110_SETUP_retry](evidence/hardware/20261110_SETUP_retry/record.md) |
| P0 開始前準備 | PASS | 急停、人員、量具、淨空、俯視照片（急停為口頭回報） | [20261110_P0](evidence/hardware/20261110_P0/record.md) |
| H0 唯讀連線 | PASS | 控制板路徑、VERSION／PING、home 值相符，手推後 8 個讀值都會變 | [20261110_H0](evidence/hardware/20261110_H0/record.md) |
| UPDATE（11-11） | PASS | 更新至 8ad9d47；build、coordinator 285、HMI 293、CM530 42、Mock Serial 7 階段、Mock 啟停 | [20261111_UPDATE](evidence/hardware/20261111_UPDATE/record.md) |
| P0 每日複查（11-11） | PASS | 口頭確認急停、人員、淨空 | [20261111_P0](evidence/hardware/20261111_P0/record.md) |
| H1 扭力關閉確認方向 | NOT_RUN（進行中） | 已做：兩臂 j1/j2 方向（j2 依新版重做）、短邊、C 格位與編號、C 格／B 區示教；跳過：畫圓法；未做：Moving Speed | [20261110_H1](evidence/hardware/20261110_H1/record.md)、[20261111_H1](evidence/hardware/20261111_H1/record.md) |
| V0 相機檢查 | NOT_RUN（進行中） | 三顆已接齊；遮蓋測試完成 by-path 對應；arm1_cam 方向 rotate 180 正確（暫定定義） | [20261111_V0/mapping.md](evidence/hardware/20261111_V0/mapping.md) |
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

### 3.4 H1 第一天（2026-11-10，arm1 部分）

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

### 3.5 H1 第二天（2026-11-11）：方向資料取得，依新版手冊仍進行中

開工前 P0 複查 PASS（控制板 11:57 重新上電）。全程扭力關閉，只送 `TORQUE,armN,0` 與唯讀指令。測試人員以負責人身分要求用 `HOME` 讓手臂自行到 home_A，**未執行**：Moving Speed 未讀（韌體 v17 不設定 register 32，可能為 0＝不限速）、超出本次 H3「單軸 ±10 raw」範圍、message.txt 授權欄未填。改用新寫的唯讀工具 [`pose_guide.py`](evidence/hardware/20261111_H1/pose_guide.py)（只經 `cm530_probe` 白名單送 READ）依讀值導引人工擺位。

| 項目 | arm1 | arm2 |
|---|---|---|
| 實體位置 | 靠 A 區 | 靠 C 區 |
| j1 往手臂自身右方轉 | 讀值變小（+1），右方＝A 區 | 499→461，讀值變小（+1），右方＝A/B 側 |
| j2 上抬 | 讀值變小 | 505→468，讀值變小 |
| 伸直（垂直朝上） | 200,505,498,513 | 507,516,523,511 |
| HOME（GET_HOME）人工擺位 | 90,563,708,826（差 ≤ 4 raw） | 595,571,709,826（差 ≤ 5 raw） |
| j1 正對場地（線 F） | 約 **193**（直接 191/176/213；斜線尺量推算 195） | 約 **519**（偏移修正後 517/523/517） |
| j1 沿板邊朝手臂左方（線 L） | 約 500（L−F = 90.0°） | 約 806（L−F ≈ 84°） |
| HOME 朝向 | 正對場地往 A 側約 30° | 正對場地往 C 外側約 21° |

- 角度誤差約 ±5°（直尺 0.5 cm 解析度、目視對齊、偏移量的 s 假設 20 cm），只是 H1 近似值，**不是校正值**，不填 `calibration.yaml`。
- 兩臂 j1 安裝角差約 90°：arm1 的 512 ≈ 沿板邊朝 B/C，arm2 的 512 ≈ 正對場地。
- 馬達 ID 15（arm1 j4）：手動轉動時讀值連續，相鄰最大變化 23 raw，無跳值。7 分半連續 1387 次 READ 無通訊錯誤。
- 底座：arm1 舵盤中心距 B｜C 膠帶 20.5 cm（A 側），arm2 距 A｜B 膠帶 20.5 cm（C 側）；兩支到使用者側長邊 24.5 cm，**板寬 24 cm** → 軸心在手臂側長邊外約 0.5 cm（arm1 斜線量測時為 1.5 cm）。
- 資料問題（已記錄，未覆寫）：arm1 一次線 F 的 CSV 被同檔名覆寫（工具已改為拒絕覆寫）；arm2 線 F 前三次缺偏移量不採用；arm2 部分 CSV 檔名尾端多一個點，保留原名。
- 量測示意圖：[`j1_measure_diagram.html`](evidence/hardware/20261111_H1/j1_measure_diagram.html)；換算腳本與輸出：`j1_diagonal_calc.py`、`j1_lineL_calc.py`、`arm2_lineF_calc.py`、`arm2_lineL_calc.py` 及對應 `_output.txt`。

#### 11-11 下午補做（依新版手冊）

- **j2 重做**：從前傾約 30° 扳回垂直約 15°，兩臂都是**扳回時讀值變小**（arm1 603→559、arm2 606→585），即前傾（朝使用者）讀值變大；垂直 ≈ 511。上午「上抬變小」的結論不採用。過程中一個誤建檔改名 `j2_arm1_fwd30_ABORTED_1.csv`；一次因目標值誤導擺成垂直，改名 `j2_arm1_vertical_facing_field.csv`，皆保留。
- **短邊**：F1、F2 兩處直接量都是 **24 cm**。
- **畫圓法**：測試人員決定跳過（NOT_RUN）。
- **C 區格位**（尺量，2 欄 × 4 列，間距 35 mm）：靠 B 欄由手臂側往使用者為 1、3、5、7，外側欄為 2、4、6、8。格中心 F = 75／110／145／180 mm，L = 235（靠 B 欄）／270 mm（外側欄）。白紙編號今天貼，但編號原本就已定義；**1、2 最靠手臂，與模擬假設（靠使用者）相反**。
- **示教**（扭力關閉、手扶到格中心的 READ，只是資料，未填任何設定）：

| 位置 | j1 | j2 | j3 | j4 |
|---|---:|---:|---:|---:|
| arm2 C1 | 572 | 630 | 926 | 602 |
| arm2 C2 | 635 | 636 | 906 | 600 |
| arm2 C3 | 560 | 645 | 885 | 596 |
| arm2 C4 | 608 | 666 | 838 | 629 |
| arm2 C5 | 549 | 701 | 767 | 664 |
| arm2 C6 | 587 | 721 | 724 | 694 |
| arm2 C7 | 540 | 779 | 602 | 758 |
| arm2 C8 | 576 | 803 | 557 | 760 |
| arm2 B | 396 | 703 | 756 | 700 |
| arm1 B（重做） | 350 | 731 | 702 | 697 |

- arm1 B 第一次 j1 = 634，幾何上不可能，保留檔案；重做為 350（正對場地往 B 側約 +46°）並採用。
- **交叉比對**：以尺量格位推算的 arm2 j1 角度，與示教讀值的大小順序 8 格完全一致，但示教值一致小約 3.5°（2.5～5.1°）。可能來自 arm2「正對場地 j1 ≈ 519」的 ±5° 誤差或軸心目測位置；未做畫圓法，無法區分。換算見 `c_slots_calc.py`／`c_slots_calc_output.txt`（F1–F2 距離以 200 mm 計算，未直接量）。
- C 格俯視照片（標格中心點）未拍。

### 3.6 UPDATE：更新到上游 8ad9d47（2026-11-11 14:20～14:50）

- 起因：要求依 `Azeem1010/three-camera-vision-ros2` 更新 OpenCV 端。查核後該 repo main 仍是 `4a40f30`，與專案 submodule 和 `src/vision_pkg` 相同，**視覺端不需更新**；落後的是主專案（本機 `3fd258c`，上游 `8ad9d47`，9 個 commit）。
- 先備份本機修改與證據，再快轉更新。上游已收錄現場的 `install_jazzy.sh` 修正（逐字相同）與 11-10 證據（只差 CRLF）。
- 結果全部 PASS：build、coordinator **285**、HMI **293**、CM530 **42**、Mock Serial **7 階段**、Mock 啟停（4 s ready、SIGINT 1 s 結束）。詳見 [20261111_UPDATE/record.md](evidence/hardware/20261111_UPDATE/record.md)。
- 新版手冊把桌面參考改為 F1、F2、L 線，原本「world 軸向 BLOCKED」解除；H1 補做清單見 [20261111_H1/record.md](evidence/hardware/20261111_H1/record.md) 文末。

---

## 4. 卡住的地方與待負責人決定的事項

### 4.1 D0：A 區在手臂哪一側和文件相反（最大的問題）

- `docs/COORDINATE_FRAMES.md` 寫的是：使用者由左到右看到 C | B | A；從手臂面向場地時 **A 在左邊**；`arm1_base` 中 A 在 y > 0。
- 實測（arm1）：手臂自身右方 = **A 區**，所以 **C 區在手臂左邊**，A 在 `arm1_base` 的 y < 0。從使用者的位置看，左到右是 **A | B | C**。
- 和實測一致的線索：`calibrate_caps` 的預設 `OUTER_EDGE_Y_MM = -200`（A 在 y < 0）；測試人員提供的另一份分析截圖也寫「A 區在 arm1_base −Y」。
- 影響：手冊說結果和遠側配置不同時，**要先修模型與 `runtime.json` 並重跑模擬，才能往下**。`env_vision.yaml`、`env_vision_node.py` 的「由左至右 C | B | A」註解與設定也可能要跟著改。
- 我們沒有修改任何文件、模型或設定，等負責人決定。

### 4.2 D1：j1 方向與零點

- 模擬假設兩臂的 j1 方向是 −1；兩臂實測都是 **+1**（右轉時讀值變小）。
- j2 上抬時讀值變小。
- 伸直時 j2/j3/j4 ≈ 505/498/513，大致符合「raw 512 = 垂直朝上」，但只是目視判斷。精確零點要靠 H2 的量測。
- arm2（11-11）：j1 同為 +1、j2 上抬同為變小；但兩臂 j1 安裝角差約 90°，零點不能共用。

### 4.3 泡棉板尺寸和文件不符

- `REQUIREMENTS.md`、`README.md`、`vision_pkg/config/env_vision.yaml`（`size_mm: [600.0, 300.0]`）寫的都是 600 × **300** mm。
- 11-11 下午在 F1、F2 直接量短邊都是 **240 mm**。P0 俯視照片按比例估算約 230～240 mm，方向一致。
- 會影響環境相機的區域換算和 C 區格位座標（實測格位見 3.5）。

### 4.3.1 C 區格位編號與模擬相反

- 實機格 1、2 最靠手臂，7、8 最靠使用者；模擬假設相反。是否改模擬或改貼紙由負責人決定。

### 4.4 底座位置和模型不同

- 模型中旋轉軸在**板內約 63 mm**（`world` y = +0.08725，沿用 CAD 數值，不是量測值）；實測在**板外約 10 mm**。
- 兩臂軸心各自對齊 A/B、B/C 分界（相距 20 cm）。這點和模型的 world x = ±0.10 相同，但 A、C 的左右相反（見 D0）。

### 4.5 負責人欄位全部空白

- **D6 驗收門檻**（`max_fit_ticks`、`min_span_rad`、`max_position_error_m`、`max_tilt_error_deg`）空白 → H2 只能收資料，`check_calibration_sheet` 記 BLOCKED，不能填 `calibration.yaml`。
- **H3 授權**空白 → 不做單軸微動。
- **負責人聯絡方式**空白。

### 4.6 硬體與量具限制

- 三顆相機已接齊：env_cam 為 AONI（有序號，by-id 可用）；arm1_cam、arm2_cam 為同型 Alcor 無序號，by-id 只剩一條連結 → 需改用 `/dev/v4l/by-path/`（綁定實體插孔，線不可互換），待負責人決定。
- 量具只有 1 mm 直尺和手機。直尺量角度約 ±0.6°，比馬達一格（0.29°）粗；TCP 位置約 ±2 mm。D6 門檻要考慮這個極限。
- 急停測試只有口頭回報，沒有錄影；斷電範圍未記錄。
- H4 以後 BLOCKED：急停心跳節點（D8）還沒做，coordinator 也會拒絕實機模式。

### 4.7 目前的硬體狀態

- 11-11 對 arm1、arm2 都送了 `TORQUE,armN,0`，**兩臂扭力目前是關的**，重新上電或操作前要扶好。
- 桌面參考：新版手冊改用 F1、F2、L 線，原本的 world 軸向 BLOCKED 已解除。

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

1. **H1 收尾**：用 RoboPlus／DYNAMIXEL Wizard 讀 8 顆馬達 Moving Speed（register 32），H3 前必做；畫圓法跳過，若要區分示教的 3.5° 差需補做；補拍 C 格俯視照片。
2. **V0**：三顆相機同型號無序號，`/dev/v4l/by-id/` 無法區分，需改用 `/dev/v4l/by-path/` 並固定插孔；只支援 YUYV，三顆共用一個 USB 2.0 hub 可能頻寬不足。
3. **E0**：`micro_ros_agent` 已在 `~/microros_ws` 建好。
4. **負責人**：D6 門檻、H3 授權；確認板寬 24 cm。H4～H8 BLOCKED（D8）。

## 7. 目錄

```text
README.md                         本報告
evidence/hardware/SUMMARY.md      總表
evidence/hardware/2026111*_*/     各階段 record.md、output.txt、照片、原始日誌、換算腳本
local_changes/                    對上游 3fd258c 的未提交修改
reference/test_instructions.md    本次測試依據的指示（含規則與交付清單）
```
