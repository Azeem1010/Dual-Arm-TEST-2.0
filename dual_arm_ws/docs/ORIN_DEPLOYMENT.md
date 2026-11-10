# Jetson AGX Orin 部署與實機放行

更新：2026-11-10。**本文件的所有步驟都還沒有在 Orin 或實機上執行過（`NOT_RUN`）。** 指令依目前的程式撰寫，實際操作時請記錄結果，放到 `docs/evidence/`。

**現場照順序操作請用 [HARDWARE_TEST_GUIDE.md](HARDWARE_TEST_GUIDE.md)。** 本文件是部署細節與 ESP32 的補充。安裝步驟與基本連線另見 [README.md](../README.md) 第 4、6 節，驗收標準見 [TEST_PLAN.md](TEST_PLAN.md) 第 6 節。

## 1. 動作前必須知道

- **實體急停要先裝好。** 韌體沒有 STOP 也沒有 watchdog，程式失效時馬達會維持最後的目標。軟體互鎖不能取代實體急停。
- **扭力關閉時手臂會往下掉**，操作前要用手扶住。
- **CM-530 重置會立刻關閉扭力**，手臂下方要保持淨空。
- **同一時間只有一個程式可以開序列埠。** 跑 `cm530_probe` 前先關掉 ROS 驅動。
- **不要把模擬值抄進實機設定。** `runtime.json`、`config/sim/` 和測試夾具都只限模擬。
- **第一次動作的速度比例由 0.05 起步。** 模擬的 1.0／0.5／1.0 不能用在實機。

## 2. 目前還不能在實機做的事

| 項目 | 狀態 | 需要什麼 |
|---|---|---|
| Coordinator 自動搬運 | `BLOCKED`，節點會拒絕以實機設定啟動 | 視覺 gateway 完成區域判斷（D7）、實機 TF、實機設定 |
| 手臂動作 | `BLOCKED` | 完成第 5 節的校正與全部放行條件 |
| 控制器長時間啟用 | `BLOCKED` | `/safety/estop` 的實機心跳來源。沒有心跳時 `safety_supervisor` 會保持控制器停用 |
| ESP32 吸盤 | `NOT_RUN` | 後端已完成並以替身節點驗證，尚未接真正的 ESP32，見第 6.1 節。韌體沒有真空感測，吸附結果仍要人工確認 |
| A 區左右、j1 與 j2 方向 | arm1：A 在右、j1 +1 `PASS`（2026-11-10，D0 已決定）；arm1 j2 與 arm2 全部 `BLOCKED` | 第 4 節的手動確認（D1），項目見 HARDWARE_TEST_GUIDE.md「2026-11-10 之後還要補的項目」 |

## 3. 安裝

要求 `aarch64` 與 Ubuntu 24.04。JetPack 6（Ubuntu 22.04）要先刷機，詳見 README 第 4 節。

```bash
mkdir -p ~/projects
cd ~/projects
git clone --recurse-submodules https://github.com/xian1022/dual_arm_system.git
cd dual_arm_system/dual_arm_ws
sudo bash scripts/install_jazzy.sh
bash scripts/build.sh
source install/setup.bash
sudo usermod -aG dialout $USER
```

執行 `usermod` 後要登出再登入。接著確認基本流程：

```bash
bash scripts/start_sim.sh mock
```

### 安裝失敗時（2026-11-10 Orin 實際遇到）

證據見 `docs/evidence/hardware/20261110_SETUP/`、`20261110_SETUP_retry/`。

| 症狀 | 原因 | 處理 |
|---|---|---|
| `Conflicting values set for option Signed-By`，exit 100 | 系統已裝 `ros2-apt-source`（`ros2.sources` 內嵌金鑰），舊版腳本又新增 `ros2.list` | 現在的腳本偵測到 APT 已能讀 ROS 2 Noble 來源就沿用，不再新增。舊腳本留下的 `ros2.list` 先備份再改名停用，例如 `sudo mv /etc/apt/sources.list.d/ros2.list /etc/apt/sources.list.d/ros2.list.disabled` |
| `unmet dependencies`，開發套件要求的版本比已安裝的函式庫舊，exit 100 | Ubuntu 來源缺 `noble-updates` | 新增 `/etc/apt/sources.list.d/dual-arm-noble-updates.sources`（內容如下），`sudo apt-get update` 後重跑腳本 |
| 建置 `dual_arm_gripper` 時 `Could NOT find SWSCALE` | 缺 FFmpeg 開發套件 | 腳本已加入 `libswscale-dev` 等五個套件 |

```text
Types: deb
URIs: http://ports.ubuntu.com/ubuntu-ports
Suites: noble-updates
Components: main universe restricted multiverse
Signed-By: /usr/share/keyrings/ubuntu-archive-keyring.gpg
```

**注意：** Ubuntu 的 FFmpeg 6.1 開發套件安裝時會覆蓋 NVIDIA `ffmpeg`（8.0.1-nvidia1）的部分檔案，安裝紀錄出現 "Replaced by files in installed package ffmpeg"。對 Jetson 硬體影像編解碼的影響 `NOT_RUN`；相機或影像串流異常時先檢查這點。

### 找到裝置路徑

使用固定路徑，不要用 `/dev/ttyUSB0`，重新插拔後編號可能改變。

```bash
ls -l /dev/serial/by-id/
ls -l /dev/v4l/by-id/
```

先前的紀錄中，控制板是 `/dev/serial/by-id/usb-FTDI_FT232R_USB_UART_AH01R3LJ-if00-port0`，請以實際結果為準。相機路徑填入 `src/vision_pkg/config/cameras.yaml`，手眼相機 1 的 `rotate: 180` 來自 2026-11-06 的實測，要重新確認。

## 4. H0、H1：只讀與手動確認

### H0 唯讀連線

只會送出 `VERSION`、`PING`、`GET_HOME`、`READ`，不會讓手臂動作。

```bash
ros2 run dual_arm_coordinator cm530_probe --port /dev/serial/by-id/<控制板>
```

確認 `home` 是 arm1 `[90,567,712,825]`、arm2 `[590,567,712,825]`。任何錯誤都會立刻停止，不要反覆重跑，先查原因。

### H1 手動確認方向

全程扭力關閉，不發任何動作命令。使用韌體附的 `manual_position_terminal.py`，步驟在 `third_party/CM530_ROS_BRIDGE/17 ROS to CM530 ver. dual arm/HOME_CALIBRATION_TEST.md` 第 3、4 節。不要輸入 `demo`、`HOME`、`AX`、`HOLD`。

1. 扶住手臂，送 `TORQUE,arm1,0`，用 `READ,arm1` 記下基準值。
2. 站在底座後方，面向手臂前方，把底座往**手臂自身右方**轉一小段，再 `READ,arm1`。
3. j1 變小代表方向 +1，變大代表方向 −1。
4. **記錄這個右轉是朝向 A 區還是 C 區**（arm1 已在 2026-11-10 確認朝 A 區，D0 依此決定；arm2 要確認是否一致）。
5. 用同樣方式確認 j2 上抬時讀值的增減（D1）。從 j2 往場地側前傾約 30° 的姿勢開始，並記錄是往場地側還是往底座後方轉；2026-11-10 那次起點太接近垂直，方向無法判斷。
6. arm2 重複相同步驟。

同時確認：實體急停可用、馬達 ID 15 的線材、Moving Speed。第 17 版韌體無法讀取 Moving Speed，要用其他工具，例如 RoboPlus 或 DYNAMIXEL Wizard，且使用時要先關閉其他占用序列埠的程式。

如果結果和目前的模擬配置（A 區在手臂右方、j1 方向 +1，見 COORDINATE_FRAMES.md）不符，要先修正模擬配置與 `runtime.json`，並依 [TEST_PLAN.md](TEST_PLAN.md) 第 4 節重跑檢查。

## 5. H2：校正

1. 複製 `src/dual_arm_coordinator/config/hardware/calibration_worksheet.template.yaml`，每軸填入至少三組「量測角度與同時的 READ」。
2. 另外量至少三個獨立姿態的 TCP 位置與傾角，不要抄 FK 的輸出。
3. 依 D6 填入 `acceptance` 的門檻，工具沒有預設值。
4. 執行：

```bash
ros2 run dual_arm_coordinator check_calibration_sheet worksheet.yaml
```

5. 通過後，**由人工**把候選值填入 `src/cm530_hardware/config/calibration.yaml`。工具不會寫入。
6. 用唯讀模式核對 `/joint_states` 的方向與角度：

```bash
ros2 launch dual_arm_bringup hardware.launch.py port:=/dev/serial/by-id/<控制板> calibration_file:=$PWD/src/cm530_hardware/config/calibration.yaml
```

### 動作前要全部完成的設定

| 檔案 | 內容 |
|---|---|
| `src/cm530_hardware/config/calibration.yaml` | 零點、方向、限位；`status: PASS`、`evidence_kind: physical`、`hardware_use_allowed: true`、`moving_speed_verified: true`、`max_step_raw` |
| `controllers_hardware.template.yaml` 的複本 | 實測的 `goal`、`goal_time`、`stopped_velocity_tolerance`。先前紀錄 j2 穩態誤差達 +7 raw（約 0.036 rad），夾具的 0.02 rad 不可用 |
| `src/dual_arm_coordinator/config/hardware/coordinator.yaml` 的複本 | 任務幾何、速度、逾時。`check_task_config` 通過才算完成 |

手臂的休息姿態要在 `calibration.yaml` 的限位內，否則啟用時會被拒絕。不可為此放寬限位，要先手動擺位。

## 6. H3 以後：第一次動作

只有在使用者現場授權、實體急停可用，且第 5 節全部完成時才能進行。

```bash
ros2 launch dual_arm_bringup hardware.launch.py port:=/dev/serial/by-id/<控制板> \
  calibration_file:=$PWD/src/cm530_hardware/config/calibration.yaml \
  enable_motion:=true controllers_file:=/絕對路徑/controllers_measured.yaml
```

這個指令會自動啟動 `safety_supervisor`。心跳到達後，先讓硬體 active，再解除鎖定。順序不能對調，硬體還沒 active 時 reset 會被拒絕（Mock Serial 實測，`docs/evidence/safety_order/`）：

```bash
ros2 control set_hardware_component_state DualArmSystem active
ros2 service call /safety/reset std_srvs/srv/Trigger '{}'
```

`/safety/reset` 成功時會自動啟動手臂控制器。不要手動執行 `switch_controllers --activate`，鎖定中手動啟動的控制器會被再停掉，中間約有 0.3 秒的空窗（C32）。

先用 `manual_xy` 只規劃，確認目標，再決定是否加 `--execute`：

```bash
ros2 run dual_arm_coordinator manual_xy --arm arm1 --x <X> --y <Y> --config /絕對路徑/coordinator_measured.yaml --calibration $PWD/src/cm530_hardware/config/calibration.yaml
```

接下來依 [TEST_PLAN.md](TEST_PLAN.md) 第 6 節的 H3～H8 逐級進行。

## 6.1 ESP32 吸盤

韌體來源是 [ray000518/micro-ros](https://github.com/ray000518/micro-ros)（commit `0c28c7f`），由那個專案維護與燒錄。本專案只透過 topic 使用它。

**韌體沒有真空感測。** `/suction_status` 只是命令回音，所以吸住或放開與否，每一步都要操作員確認：

```bash
ros2 run dual_arm_coordinator operator_console confirm --success
ros2 run dual_arm_coordinator operator_console confirm --failed --message "瓶蓋沒有吸住"
```

### 建置 agent

`micro_ros_agent` 要從原始碼建置，以下是 micro-ROS 官方流程，尚未在 Orin 上執行過：

```bash
mkdir -p ~/microros_ws/src
cd ~/microros_ws
git clone -b jazzy https://github.com/micro-ROS/micro_ros_setup.git src/micro_ros_setup
source /opt/ros/jazzy/setup.bash
sudo apt update && rosdep update
rosdep install --from-paths src --ignore-src -y
colcon build
source install/local_setup.bash
ros2 run micro_ros_setup create_agent_ws.sh
ros2 run micro_ros_setup build_agent.sh
source install/local_setup.bash
```

### 啟動順序

韌體不會檢查連線結果，也沒有重連機制，所以**一定要先開 agent，再按 ESP32 的 EN 鍵**。agent 或連線中斷後，也要重新按 EN。

```bash
ros2 run micro_ros_agent micro_ros_agent serial --dev /dev/serial/by-id/<ESP32>
```

### 第一次通電前要確認

手臂不要靠近工件，且不要啟動 Coordinator。

| 項目 | 確認方式 | 填入 |
|---|---|---|
| 繼電器觸發電位 | 韌體假設高電位觸發。ESP32 上電時泵和閥不應作動；若會作動，先修正接線或韌體 | — |
| GPIO5 開機訊號 | 觀察開機瞬間閥 1 是否誤動作 | — |
| 模組與手臂的對應 | 用下方指令逐一作動，看是哪支手臂的吸盤 | `gripper.esp32_modules` |
| 真空建立時間 | 實測吸取後要等多久才吸得穩 | `gripper.vacuum_settle_s` |
| 回音時間 | 釋放約 0.55 秒，逾時要留餘裕 | `gripper.esp32_echo_timeout_s` |

```bash
ros2 topic echo /suction_status
ros2 topic pub --once /suction_command std_msgs/msg/Int32 "{data: 1}"
ros2 topic pub --once /suction_command std_msgs/msg/Int32 "{data: 2}"
```

`1`、`2` 是模組 1 的吸取、釋放，`3`、`4` 是模組 2，`0` 是全部關閉。**`0` 會停泵，持有中的物件會掉落。** 發生故障時系統不會自動送 `0`，要由人現場處理。

## 7. 發生狀況時

| 狀況 | 處理 |
|---|---|
| 手臂動作異常 | 按實體急停 |
| 安全監控鎖定 | 查 `/safety/status`，排除原因後呼叫 `/safety/reset` |
| 任務進入 FAULT | 用 `operator_console status` 查原因，現場清空工具與 B 區、手臂回 HOME，再 `operator_console recover --cleared` |
| 序列埠錯誤或逾時 | 驅動會鎖定，不會重送。查線材後重啟驅動，先跑 H0 |
| `ERR,DXL_TIMEOUT` 指向某顆馬達 | 檢查該馬達的線材與供電 |

## 8. 要保存的紀錄

每次實機操作都要保存實際指令、輸出、照片或量測紀錄，放到 `docs/evidence/`，並標明 `evidence_kind: physical`。失敗的紀錄也要保留，完成後更新 `PROGRESS.md`、`TEST_REPORT.md`、`RESUME.md`。
