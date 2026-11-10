# 雙機械手臂 ROS 2 系統：安裝與使用

兩支 PhantomX Pincher 手臂協作，把瓶蓋從 A 區經 B 區交接，放到 C 區的八個格位。系統使用 ROS 2 Jazzy、MoveIt 2、Gazebo Harmonic，實機由一片 CM-530 控制八顆 AX-12A。

**第一次使用，照著「2. 選擇你的電腦」往下做就可以。**

## 1. 目前能做到什麼

| 功能 | 狀態 | 說明 |
|---|---|---|
| 建置專案 | 可用 | Windows（WSL2）已實測 |
| Gazebo 模擬與 RViz | 可用 | |
| 模擬 A→B→C 搬運 | 可用 | 兩個物體已驗證，含故障停止與人工復歸。區域與格位用 Gazebo 的真實座標 |
| CM-530 驅動程式、安全監控 | 僅模擬測試 | 已用韌體原始碼的 Mock Serial 與 MoveIt mock 測試，**還沒接過實機** |
| 八個物體完整搬運 | 未完成 | 目前模型只搆得到 4 個瓶蓋、7 個 C 格 |
| 視覺自動定位 | 部分 | 模擬中 Arm 1 取料點可由視覺決定；區域與格位還沒接，實體相機尚未校正 |
| ESP32 吸盤 | 僅模擬測試 | 程式完成，只用替身節點測過。韌體沒有真空感測，吸取結果要人工確認 |
| Jetson Orin | 部分實測 | 2026-11-10 已在 AGX Orin 安裝、建置，離線測試、Mock 與 CM-530 唯讀連線都 PASS；實機動作仍未放行 |

**實機控制預設是關閉的。** 模擬成功不代表實機可以直接動作，詳見「6. 連接實機」。

完整進度在 [docs/PROGRESS.md](docs/PROGRESS.md)。

## 2. 選擇你的電腦

| 你的電腦 | 用途 | 看哪一節 |
|---|---|---|
| Windows 11 | 開發、跑模擬 | [3. Windows 安裝](#3-windows-11-安裝) |
| Jetson AGX Orin | 部署、接實機 | [4. Orin 安裝](#4-jetson-agx-orin-安裝) |

**換電腦時只複製原始碼**，不要帶 `build/`、`install/`、`log/`、`.cad-venv/`。這些是舊電腦產生的，尤其 Windows 的產物不能放到 Orin 上用。

專案在 [GitHub](https://github.com/xian1022/dual_arm_system)。`third_party/` 是 git submodule，**clone 時一定要加 `--recurse-submodules`**，否則 CM-530 的 Mock Serial 測試和 CAD 重新生成會缺檔案。上游的單臂或視覺 repo 都不能取代這份專案。

## 3. Windows 11 安裝

需要先確認 BIOS 已開啟虛擬化。專案透過 WSL2 在 Ubuntu 裡執行。下面的時間是在開發電腦上實測的參考值。

### 步驟 1：安裝 Ubuntu 24.04

用**系統管理員身分**開啟 PowerShell，執行：

```powershell
wsl --install -d Ubuntu-24.04
wsl --update
wsl --list --verbose
```

依提示重新開機並建立 Ubuntu 帳號。最後一行要看到 `VERSION` 是 **2**。如果你已經有名為 `Ubuntu` 的 24.04，可以直接用。

### 步驟 2：把專案放到 Linux 磁碟

開啟 **Ubuntu 終端**（開始功能表搜尋 Ubuntu），執行：

```bash
mkdir -p ~/projects
cd ~/projects
git clone --recurse-submodules https://github.com/xian1022/dual_arm_system.git
cd dual_arm_system/dual_arm_ws
```

> **為什麼放在 Linux 磁碟？** 直接在 `/mnt/e` 上也能跑，但讀取 Windows 磁碟很慢，模擬會慢很多。

如果你手上已經有完整資料夾，也可以複製過去（下面假設在 `E:\dual_arm_system`，約 7 分鐘）：

```bash
mkdir -p ~/projects/dual_arm_system/dual_arm_ws
cd /mnt/e/dual_arm_system/dual_arm_ws
tar --exclude='./build' --exclude='./install' --exclude='./log' --exclude='./.cad-venv' \
    -cf - . | tar -xf - -C ~/projects/dual_arm_system/dual_arm_ws
cd ~/projects/dual_arm_system/dual_arm_ws
```

### 步驟 3：安裝相依套件

```bash
sudo bash scripts/install_jazzy.sh
```

會安裝 ROS 2 Jazzy、MoveIt、Gazebo 和 Python 套件，下載量較大。腳本只接受 Ubuntu 24.04。

### 步驟 4：建置

```bash
bash scripts/build.sh
```

約 5 分鐘。最後看到 `Summary: ... packages finished`，而且沒有 `failed` 就成功了。

### 步驟 5：啟動模擬

```bash
bash scripts/start_sim.sh gui
```

等 Gazebo 畫面出現，再到「5. 確認安裝成功」檢查。Gazebo 視窗由 WSLg 顯示，如果打不開，在 Ubuntu 執行 `echo "$DISPLAY"`，應該要有內容。

## 4. Jetson AGX Orin 安裝

> 2026-11-10 已在 AGX Orin（Ubuntu 24.04.5）照本節建置成功。安裝時遇過 ROS 套件來源衝突、缺 `noble-updates`、缺 FFmpeg 開發套件，處理方式見 [ORIN_DEPLOYMENT.md](docs/ORIN_DEPLOYMENT.md) 第 3 節；完整的實機放行步驟也在該文件。

### 步驟 1：確認系統版本

```bash
uname -m
cat /etc/os-release
head -n 1 /etc/nv_tegra_release
```

要看到 **`aarch64`** 和 **Ubuntu 24.04**。

- **已是 24.04：** 直接到步驟 2。
- **還是 22.04（JetPack 6）：** **不要執行安裝腳本。** 需要先刷成 Ubuntu 24.04。[NVIDIA JetPack 下載頁](https://developer.nvidia.com/embedded/jetpack/downloads)的 JetPack 7.2.1 支援 Orin 系列，並以 Ubuntu 24.04 為基礎（2026-11-09 確認）。刷機前請備份，並選擇符合你的模組和載板的映像，不要直接做一般的 Ubuntu 版本升級。

### 步驟 2：安裝與建置

```bash
mkdir -p ~/projects
cd ~/projects
git clone --recurse-submodules https://github.com/xian1022/dual_arm_system.git
cd dual_arm_system/dual_arm_ws
sudo bash scripts/install_jazzy.sh
bash scripts/build.sh
```

### 步驟 3：先用不需要畫面的模式確認

```bash
bash scripts/start_sim.sh mock
```

| 使用方式 | 指令 |
|---|---|
| 接著螢幕 | `bash scripts/start_sim.sh gui` |
| 透過 SSH、沒有畫面 | `bash scripts/start_sim.sh headless` |

SSH 連線不會自動顯示圖形視窗。

### 步驟 4：要接 CM-530 時

讓帳號有序列埠權限，然後**登出再登入**：

```bash
sudo usermod -aG dialout $USER
```

接上後查裝置的固定路徑（重新插拔後 `/dev/ttyUSB0` 這類編號可能改變，指令裡一律用 `by-id` 路徑）：

```bash
ls -l /dev/serial/by-id/
```

接下來請看「6. 連接實機」。

## 5. 確認安裝成功

保持模擬在執行，**另開一個終端**，輸入：

```bash
cd ~/projects/dual_arm_system/dual_arm_ws
source /opt/ros/jazzy/setup.bash
source install/setup.bash
export ROS_DOMAIN_ID=43
ros2 control list_controllers
```

看到 `arm1_controller`、`arm2_controller`、`joint_state_broadcaster` 都是 **`active`** 就成功了。

> **每開一個新終端**，都要執行前面的 `cd`、兩行 `source` 和 `export`。

### 跑搬運展示

先開一個全新的模擬，然後在另一個終端執行：

```bash
bash scripts/run_pipeline.sh --count 2
```

Arm 1 把物體從 A 放到 B，Arm 2 再從 B 放到 C。`--count` 可以是 1、2、3，目前版本已驗證的是 2。跑完會自動結束，要重跑請重開模擬。這是較早的展示流程，沒有故障紀錄與復歸。

### 跑任務節點（coordinator）

這是目前的搬運流程，會自己啟動模擬，不要同時開著另一個模擬：

```bash
ros2 launch dual_arm_bringup demo_pick_place.launch.py journal_path:=/tmp/dual_arm_journal.json
```

等控制器都 active 後，在另一個終端操作：

```bash
ros2 run dual_arm_coordinator operator_console start
ros2 run dual_arm_coordinator operator_console status
```

故障後要先用手確認吸盤和 B 區都已淨空，才能復歸：`operator_console recover --cleared`。預設搬一個物體，可用 `cycles:=2` 調整。`journal_path` 檔案會保留狀態，要從頭開始請換一個路徑。服務清單見 [ROS_INTERFACES.md](docs/ROS_INTERFACES.md)。

### 停止模擬

在啟動模擬的終端按 `Ctrl+C`。Gazebo 有時關不乾淨（已知問題），可以這樣確認和處理：

```bash
pgrep -af 'gz sim'
pkill -f 'gz sim'
```

## 6. 連接實機

### 安全規則

1. **先裝好硬體急停。** 韌體沒有軟體 STOP，程式當掉時馬達會維持最後的目標。
2. **第一次動作前，先確認馬達的 Moving Speed。** 韌體不會設定速度，值為 0 時馬達會以最高速運動。
3. 扭力關閉時手臂會往下掉，要用手扶住。
4. 不要把模擬用的 HOME 假設值（`runtime.json`）抄到實機校正檔，模擬的速度比例也不能用在實機。
5. 啟動 `enable_motion:=true` 時會一起帶起 `safety_supervisor`。急停心跳遺失或 coordinator 失效時，它會停用手臂控制器並鎖定，要呼叫 `/safety/reset` 才能解除。這是軟體互鎖，不能取代實體急停，而且實機的心跳來源還沒做。

**要到現場測試，請照 [實機測試手冊](docs/HARDWARE_TEST_GUIDE.md) 的順序做。** 下面只是個別指令的說明。**2026-11-10 的 H1 已確認 A 區在手臂右方、Arm 1 的 j1 方向 +1；Arm 2 的方向、j2 的方向與各軸零點還沒確認，要先完成手冊的 H1。**

### 第一次連線：只讀不動

在 Windows 上可以先用韌體附的終端確認通訊，不需要 ROS。在 `third_party/CM530_ROS_BRIDGE/17 ROS to CM530 ver. dual arm/` 資料夾開 PowerShell，並把 `COM4` 換成實際的埠：

```powershell
python -m pip install -r requirements.txt
python manual_position_terminal.py --port COM4
```

依序輸入 `PING`、`VERSION`、`GET_HOME,arm1`、`READ,arm1`。**不要輸入 `demo`、`HOME` 或 `AX`，這些會讓手臂動作。**

> WSL 預設看不到 USB 序列埠，本專案也沒有驗證過轉接方式。要接 ROS 請用 Orin。

在 Orin 上可以用只允許唯讀指令的工具，同樣不會讓手臂動作：

```bash
ros2 run dual_arm_coordinator cm530_probe --port /dev/serial/by-id/<你的控制板>
```

### 量測校正值

照[實機測試手冊](docs/HARDWARE_TEST_GUIDE.md)的 H2 量測（只用直尺和手機照片；韌體附的 [HOME_CALIBRATION_TEST.md](third_party/CM530_ROS_BRIDGE/17%20ROS%20to%20CM530%20ver.%20dual%20arm/HOME_CALIBRATION_TEST.md) 是背景說明），通過檢查後才把結果填進 `src/cm530_hardware/config/calibration.yaml`。**任何欄位留空，驅動都會拒絕啟動**，這是刻意的設計。

量測前可以先填 `src/dual_arm_coordinator/config/hardware/calibration_worksheet.template.yaml` 的複本，再離線檢查。這個工具只回報候選值，不會寫入任何校正檔：

```bash
ros2 run dual_arm_coordinator check_calibration_sheet <你的工作表.yaml>
```

### 用 ROS 讀取實機（Orin）

`port` 請換成實際裝置：

```bash
ros2 launch dual_arm_bringup hardware.launch.py port:=/dev/serial/by-id/<你的控制板> calibration_file:=$PWD/src/cm530_hardware/config/calibration.yaml
```

這個模式只會讀位置，不會送出任何動作。用手扳動手臂，確認 `/joint_states` 的方向和角度都正確。

### 沒有實機時試跑驅動

```bash
ros2 launch dual_arm_bringup hardware.launch.py use_mock_serial:=true calibration_file:=$PWD/src/cm530_hardware/test/fixtures/calibration_mock.yaml
```

### 允許馬達動作

以下條件**全部**滿足才會放行：

| 條件 | 設定 |
|---|---|
| 校正通過 | `status: PASS`、`evidence_kind: physical`、`hardware_use_allowed: true` |
| 已確認速度 | `moving_speed_verified: true` |
| 單次最大步距 | 實測的 `max_step_raw` |
| 明確開啟 | `enable_motion:=true` |
| 到位判斷 | `controllers_file:=` 指向填好實測容差的控制器設定，範本是 `src/dual_arm_controllers/config/controllers_hardware.template.yaml`，留空的範本會被拒絕 |

啟動後扭力仍然關著。`/safety/estop` 要有心跳，然後依下面的順序，不能對調：

```bash
ros2 control set_hardware_component_state DualArmSystem active
ros2 service call /safety/reset std_srvs/srv/Trigger '{}'
```

`/safety/reset` 會自動啟動控制器。**不要手動執行 `switch_controllers --activate`**，鎖定時手動啟動的控制器會被安全監控再停掉。目前沒有實機心跳來源，這一步要先決定 D8。

`dual_arm_coordinator` 目前會拒絕實機模式，因為實機 TF、視覺的區域判斷與實測設定都還沒完成。ESP32 吸盤的接線與啟動順序見 [ORIN_DEPLOYMENT.md](docs/ORIN_DEPLOYMENT.md) 第 6.1 節。

## 7. 常用設定

| 想調整 | 位置 | 備註 |
|---|---|---|
| 模擬搬運速度 | `src/dual_arm_coordinator/config/sim/runtime.json`、`config/sim/coordinator.yaml` | 搬運 1.0、接觸 0.5、加速度 1.0，只限模擬，不可用在實機 |
| 模擬 HOME 姿態 | 同上，說明見 [HOME_POSES.md](docs/HOME_POSES.md) | 改完執行 `bash scripts/build.sh` |
| 實機校正 | `src/cm530_hardware/config/calibration.yaml` | 只能填實測值 |
| CAD 模型 | 見 [cad/README.md](cad/README.md) | 一般使用不需要 SolidWorks |

C 區是八個 25×25 mm 的白色齊平格位，表面高度 14 mm，10 mm 高的物體放穩後中心高度為 19 mm。

## 8. 資料夾說明

```text
dual_arm_system/
  README.md            專案入口
  dual_arm_ws/
    README.md          本文件
    AGENTS.md          給 AI 助手與接手開發者的規則
    src/               ROS 套件與 CAD 網格
    scripts/           安裝、建置、啟動、測試工具
    cad/               修正版 STEP 與 CAD 說明
    docs/              進度、測試報告、證據
    third_party/       上游原始碼（不要修改）
```

| 套件 | 用途 |
|---|---|
| `dual_arm_description` | 雙臂模型 |
| `dual_arm_gazebo` | 模擬世界 |
| `dual_arm_moveit_config` | 運動規劃 |
| `dual_arm_controllers` | 控制器設定 |
| `dual_arm_bringup` | 各種啟動檔 |
| `dual_arm_coordinator` | 搬運任務節點、工作流程、安全監控、操作工具 |
| `dual_arm_interfaces` | 操作用的服務定義 |
| `dual_arm_gripper` | Gazebo 吸盤（ESP32 後端在 coordinator 的 gripper gateway） |
| `vision_pkg`、`vision_interfaces` | 三相機視覺 |
| `dual_arm_vision_adapter` | 校正有效性狀態發布 |
| `cm530_hardware` | CM-530 實機驅動 |

## 9. 常見問題

| 現象 | 處理 |
|---|---|
| 找不到 `ros2` | 執行 `source /opt/ros/jazzy/setup.bash` |
| 找不到 dual_arm 套件 | 先建置，再 `source install/setup.bash`；每個新終端都要做 |
| 找不到控制器 | 等 Gazebo 載入完成；確認 `ROS_DOMAIN_ID` 都是 43 |
| `Switch controller timed out` | 偶發的啟動失敗，停掉模擬重開；載入期間先不要反覆查詢控制器 |
| 模擬非常慢 | 確認專案在 Linux 磁碟，不是 `/mnt/e`；沒畫面需求時改用 `headless` |
| 沒有 GUI | 檢查 `echo "$DISPLAY"`；沒有桌面就用 `headless` |
| 重開後場景異常 | 用 `pgrep -af 'gz sim'` 檢查有沒有上一輪的殘留 |
| 物體不在起始位置 | 流程會自動停止，重新開一個乾淨的模擬 |
| HOME 缺值 | 校正資料不完整，不是 ROS 安裝失敗；不要隨便填 512 |
| 網格遺失 | 重新建置，不要單獨搬動 `install/` |
| coordinator 回報 `Recovery is required` | 上一輪故障還沒復歸；確認吸盤和 B 區淨空後執行 `operator_console recover --cleared`，或換一個 `journal_path` |
| 序列埠權限不足 | 把帳號加入 `dialout` 群組，並重新登入 |
| `Configuration refused` | `calibration.yaml` 有欄位留空，或內容不正確 |
| `Motion refused` | 動作條件沒有全部滿足，看「允許馬達動作」 |
| `port already owned` | 序列埠被其他程式佔用，先關掉終端工具或 RoboPlus |

## 10. 驗證與接手開發

改完要跑哪些檢查，依 [TEST_PLAN.md](docs/TEST_PLAN.md) 第 4 節。`scripts/run_checks.sh` 把它們分成三層，每一步的退出碼、耗時和日誌記在 `OUT_DIR/summary.tsv`：

```bash
bash scripts/run_checks.sh t0 docs/evidence/<日期>_<主題>/t0   # 文件連結與區域描述，不到 1 分鐘，不需要 ROS
bash scripts/run_checks.sh t1 docs/evidence/<日期>_<主題>/t1   # 模型、建置、HOME、IK、可達性、單元測試、碰撞，約 5 分鐘
bash scripts/run_checks.sh t2 docs/evidence/<日期>_<主題>/t2   # Gazebo、MoveIt mock、視覺取料、README 截圖，約 40 分鐘
```

`t2` 時間長，可以放著讓它跑，結束後看 `summary.tsv`。只想重跑失敗的幾步時，把步驟名稱（`summary.tsv` 第一欄）放進 `STEPS`，例如 `STEPS="legacy_pipeline_two vision_pick" bash scripts/run_checks.sh t2 OUT_DIR`；`vision_pick` 需要一起列出 `generate_sim_vision_calibration probe_sim_vision`。任何一步失敗腳本都會退出 1，但會跑完整層；已知的失敗（例如 `test_ik.py` 16/18）也記為失敗，原因寫在該次的紀錄裡。CM-530 驅動另外用：

```bash
colcon test --base-paths src --packages-select cm530_hardware
colcon test-result --test-result-base build/cm530_hardware
python3 scripts/test_cm530_mock.py
```

`bash scripts/build.sh`、`run_pipeline.sh`、`scripts/test_cm530_mock.py` 等工具會覆寫 `docs/evidence/` 裡已追蹤的舊紀錄。`run_checks.sh` 會把被覆寫的新檔案存到 `OUT_DIR/outputs/`，再從 HEAD 還原；模型或配置改變、追蹤的證據本身要更新時，加 `KEEP_EVIDENCE=1`，新檔留在原處，HEAD 版本存到 `OUT_DIR/replaced/`。單獨執行這些工具時，要保留的結果請先另存，舊檔用 `git restore` 還原。

| 文件 | 內容 |
|---|---|
| [docs/PROGRESS.md](docs/PROGRESS.md) | 目前進度 |
| [docs/MODIFICATION_PLAN.md](docs/MODIFICATION_PLAN.md) | 工作包、衝突清單、待決定事項 |
| [docs/HARDWARE_TEST_GUIDE.md](docs/HARDWARE_TEST_GUIDE.md) | **實機測試手冊，現場照著做** |
| [docs/TEST_PLAN.md](docs/TEST_PLAN.md) | 測試計畫與實機放行階梯 |
| [docs/ORIN_DEPLOYMENT.md](docs/ORIN_DEPLOYMENT.md) | Orin 部署與實機步驟 |
| [docs/ROS_INTERFACES.md](docs/ROS_INTERFACES.md) | ROS 介面 |
| [docs/HANDOFF_PROMPT.md](docs/HANDOFF_PROMPT.md) | 交接給其他 AI 的 prompt |
| [docs/HANDOFF_PROMPT_NEXT_COMPUTER.md](docs/HANDOFF_PROMPT_NEXT_COMPUTER.md) | 換到另一台電腦時給 AI 的 prompt |
| [docs/COORDINATE_FRAMES.md](docs/COORDINATE_FRAMES.md) | 視覺與手臂的座標軸定義 |
| [docs/TEST_REPORT.md](docs/TEST_REPORT.md) | 測試結果 |
| [docs/RESUME.md](docs/RESUME.md) | 中斷後如何續接 |
| [docs/REQUIREMENTS.md](docs/REQUIREMENTS.md) | 完整需求 |
| [AGENTS.md](AGENTS.md) | 開發規則 |
