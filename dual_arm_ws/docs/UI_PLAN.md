# 操作介面（HMI）實作規劃

更新：2026-11-10。**階段 0 假資料畫面與階段 1 唯讀監看已實作，並在 WSL 模擬中驗證。階段 0 還差使用者視覺確認與 Orin 執行；階段 2 以後都是 `NOT_RUN`。** 接真實資料：`ros2 run dual_arm_hmi hmi`；假資料：加上 `--fake`。階段 1 全部按鈕（含強制停止）都未接通，畫面會明確標示。介面定義以 [ROS_INTERFACES.md](ROS_INTERFACES.md) 和實際程式碼為準，開發規則見 [AGENTS.md](../AGENTS.md)。

## 1. 已定案

| 項目 | 決定 |
|---|---|
| 技術 | PyQt5 Qt Widgets 自繪，不用 QML，不依賴 GPU |
| Windows | WSLg 完整版，和 Orin 同一套程式；實機操作以 Orin 為準 |
| 部署機 | Jetson AGX Orin Developer Kit，Ubuntu 24.04.5，L4T R39.2.1，32GB RAM，一般螢幕加鍵鼠 |
| 版面基準 | 1920×1080，最小視窗 1280×720 |
| 強制停止 | 新增 `/safety/trigger_stop`，同時呼叫 `/dual_arm/cancel`；標明是軟體停止，實體急停不可省略 |
| 回 HOME | 新增 `/dual_arm/go_home`，模擬先開放，實機等 H5 通過 |
| 急停心跳（D8） | 獨立節點接實體急停，UI 只顯示、不發送。節點與接線尚未完成 |
| 相機畫面 | Qt 內嵌，判定框來自視覺節點自己的標註圖，不用 `cv2.imshow` |
| Gazebo 畫面 | 使用 `/view_*` 影像，放大顯示並可切換四個視角，不嵌入 Gazebo 視窗 |
| 實機同步 Gazebo | 實機運作時 Gazebo 同時動作，跟隨實機回授，單向且和實機系統隔離（第 9.1 節） |

## 2. 範圍

**要做：** 啟動與關閉系統、開始工作、取消、強制停止、回 HOME、復歸、三格相機與判定框、馬達數值、工作狀態、安全狀態、事件紀錄。

**不做：**

- UI 不開序列埠，CM-530 只能由一個程序持有。
- UI 不提供單軸手動移動。H3～H5 照 [HARDWARE_TEST_GUIDE.md](HARDWARE_TEST_GUIDE.md) 用終端指令。
- UI 不能繞過實機 `BLOCKED`、校正閘門或限位，不發布 `/safety/estop`。
- 不改 `third_party/` 和 `vision_interfaces`。

## 3. 視覺規格

**禁止：** 漸層、陰影、半透明、卡片包卡片、裝飾圖示、深色主題。按鈕與區塊用直角，以 1px 分隔線和留白分區。

| 類別 | 用途 | 色彩 | 文字（對比） |
|---|---|---|---|
| 結構 | 頂部列、區塊標題條、一般操作按鈕 | `#17375E` | 白（12:1） |
| | 頁面底色／面板 | `#EAF1F8`／`#FFFFFF` | `#111827` |
| | 次要文字／分隔線 | `#4B5563`／`#C9CED6` | |
| 手臂識別 | arm1 | `#00838F` | 白（4.5:1） |
| | arm2 | `#6A3FA0` | 白（7.4:1） |
| 區域識別（只用於字母標籤） | A／B／C | `#0080FF`／`#00C800`／`#FFDC00` | 黑 |
| 狀態 | 正常 | `#0B7A3B` | 白（5.4:1） |
| | 進行中 | `#0B5FD9` | 白（5.7:1） |
| | 警告 | `#FFC400` | 黑（13:1） |
| | 危險、強制停止 | `#C8102E` | 白（5.9:1） |
| 模式 | 實機標籤 | `#000000` | `#FFC400` |

區域色取自 `env_vision_node.py` 的 `ZONE_BGR`，和相機畫面上的框一致。

**規則：**

- 大面積紅色只留給安全鎖定和故障橫幅。警告黃和危險紅不當裝飾。
- 狀態一定同時有文字，不單靠顏色。
- 字型統一 Noto Sans CJK TC，數值用等寬字。1080p 下欄位說明 12、內文 14、區塊標題 16 粗體、狀態 20、橫幅 24 粗體，最小 12。
- 顏色的實際感受在階段 0 對照畫面後再微調。

**重要程度：** 強制停止（固定位置、永遠可按、最大）、全寬橫幅（狀態＋原因＋下一步）、欄位警告、一般數值。

## 4. 版面

1920×1080（縮放 100%）的預估配置，單位 px：

```text
┌ 頂部狀態列 56：模式｜ROS｜系統｜安全｜任務｜決策來源 ────────────────┐
├ 狀態橫幅 48（固定保留，版面不跳動）────────────────────────────┤
├─────────────┬─────────────┬─────────────┬──────────┤
│ 環境相機     │ 手臂1相機    │ 手臂2相機    │ 控制欄 320 │
│ 533×400     │ 533×400     │ 533×400     │ 強制停止   │
├─────────────┴─────┬───────┴─────────────┤ 系統操作   │
│ 馬達表（arm1／arm2）│ 任務進度、持物、C 區八格 │ 任務操作   │
├──────────────────┴─────────────────────┤ 吸盤確認   │
│ 事件紀錄                                 │          │
└────────────────────────────────────────┴──────────┘
```

| 視窗寬度 | 版面 |
|---|---|
| 1600 以上 | 如上 |
| 1280～1599 | 控制欄 280，馬達表隱藏 rad 欄 |
| 高度 800 以下 | 事件紀錄收成最新一行，可展開 |

- 相機固定 4:3、不拉伸，判定框才不會變形；點擊放大單格。
- 主要按鈕高 40，要有 hover 和 focus 樣式。開啟 Qt 高 DPI 縮放。
- 強制停止綁 F12。開始工作不綁快捷鍵、不設預設焦點，避免按 Enter 誤啟動。

## 5. 架構

```text
src/dual_arm_hmi/
  dual_arm_hmi/
    app.py              進入點、單一實例鎖定
    model/state.py      彙整狀態、判斷按鈕（純 Python，可單元測試）
    model/steps.py      任務步驟對照
    model/joints.py     角度、raw、限位餘裕
    sources/base.py     資料來源介面
    sources/ros_source.py
    sources/fake_source.py
    launcher/profiles.py
    launcher/process.py
    ui/theme.py, main_window.py, camera_panel.py, motor_panel.py,
       task_panel.py, control_panel.py, event_log.py
  config/profiles.yaml
  test/
```

- ROS 在背景執行，Qt 主執行緒只繪製。影像只保留最新一張，轉換在背景完成。
- 強制停止用專屬的 client 和 callback group，不和一般資料共用。
- 資料過期用電腦收到的時間判斷，模擬時 `header.stamp` 是模擬時間。
- 用 apt 的 `python3-opencv` 和 `python3-pyqt5`，不用 pip 版 `opencv-python`（Qt plugin 會衝突）。
- 影像轉換沿用 `vision_pkg.node_common.image_msg_to_bgr`，不用 `cv_bridge`，避開 Jetson 上的 ABI 問題；只在顯示時轉換。
- 模式由載入的 `/robot_description` 硬體 plugin 判斷，不靠人工設定，避免實機被標成模擬。
- 模擬比真實時間慢，模擬時鐘驅動的資料（相機、區域、校正狀態）過期門檻放寬 4 倍，只限模擬；連線判斷與任務、安全狀態不放寬。

## 6. 操作狀態與按鈕

```text
未啟動 → 啟動中 → 就緒 → 工作中 → 完成
                    ↑        ↓
                  復歸 ←── 故障／已取消／C 區已滿

實機多兩步：唯讀就緒 → 已上扭力 → 解除鎖定 → 就緒
安全鎖定可在任何狀態發生，優先顯示
```

| 按鈕 | 可按條件 | 確認方式 | 實際動作 |
|---|---|---|---|
| 強制停止 | 永遠可按 | 不確認 | `/safety/trigger_stop` 加 `/dual_arm/cancel` |
| 啟動系統 | 未啟動，且沒有殘留的 Gazebo | 選擇模式 | 依模式執行 launch |
| 關閉系統 | 任務未執行 | 確認視窗 | SIGINT，逾時 SIGTERM，再檢查殘留 |
| 上扭力（實機） | 唯讀就緒、校正 `PASS` | 確認視窗，提醒急停 | `set_hardware_component_state active` |
| 解除鎖定 | 已鎖定且原因已排除 | 確認視窗 | `/safety/reset`，不直接切換 controller |
| 重置模擬（僅模擬） | 系統已啟動、任務未執行 | 確認視窗 | 重啟系統並使用新的 `journal_path` |
| 開始工作 | `state` 為 IDLE 或 SUCCEEDED、未忙碌、未鎖定、controller 啟用 | 不確認 | `/dual_arm/start` |
| 取消任務 | 任務執行中 | 不確認 | `/dual_arm/cancel` |
| 回 HOME | 任務未執行、未鎖定、人工確認吸盤已清空 | 勾選 | `/dual_arm/go_home` |
| 吸盤成功／失敗 | 有 `suction_token` | 按鈕本身 | `/dual_arm/confirm` |
| 復歸 | FAULT 或 FULL、任務未執行 | 勾選已清空 | `/dual_arm/recover` |

- 不能按時，原因直接顯示在按鈕旁。
- 動作回饋分三段：已送出、系統接受或拒絕、實際結果。實際結果以狀態 topic 為準。
- 上扭力與解除鎖定的順序不可對調（[HARDWARE_TEST_GUIDE.md](HARDWARE_TEST_GUIDE.md) H4）。

## 7. 停止與復歸

取消和強制停止都會進入 `FAULT`（`TaskCancelled` 是 `TaskFault` 的子類別）。

```text
強制停止 → controller 停用，手臂保持最後位置
→ 排除問題 → 解除鎖定 → 清空吸盤與 B 區 → 回 HOME → 復歸 → 可再開始
```

**不用 `/safety/estop=true` 當 UI 的停止手段：** coordinator 的 `estop_latched` 沒有解除路徑，只能重啟；另有心跳來源持續發 `false` 時，`true` 也可能被蓋掉。

**模擬的限制：** `recover` 會檢查 B 區沒有物件，但 Gazebo 裡沒有人能用手清空吸盤或 B 區，所以瓶蓋還在吸盤上或 B 區時，復歸會被拒絕。這種情況用「重置模擬」處理：重啟系統並使用新的 `journal_path`（舊 journal 會讓 coordinator 以 `FAULT` 開始）。

**`/dual_arm/go_home` 要求：** 任務未執行、未鎖定、人工確認吸盤已清空，動作前做碰撞檢查，兩臂依序移動。實機模式維持拒絕，等 H5 通過。Token 的設計在階段 3 定案。

## 8. 畫面內容

| 區域 | 內容 | 來源 |
|---|---|---|
| 頂部狀態列 | 模式、ROS、系統、安全、任務、決策來源 | 綜合 |
| 相機三格 | 判定框、FPS、影像延遲、校正結果、標註／原始切換 | `/vision/*/debug_image`、`/*_cam/image_raw`、`/vision/calibration_status` |
| Gazebo 視角 | 等角、俯視、正面、側面，2 Hz。模擬標「Gazebo 模擬」，實機標「跟隨實機回授，非實機影像」，同步中斷要明顯標示 | `/view_{isometric,top,front,side}/image_raw` |
| 馬達表 | deg、rad、raw、速度（估計）、命令誤差、限位位置條 | `/joint_states`、`/armN_controller/controller_state`、`/robot_description` |
| 任務 | 八段進度、目前步驟、持物、B 區擁有者、C 區八格、完成數 | `/dual_arm/status`、`/vision/arm2/grid_state` |
| B 區互鎖 | Arm1、B 區、Arm2 三格與兩道閘門 | `/dual_arm/status` 的 `b_owner`、`state`，`/vision/env/zone_state` |
| 安全 | 鎖定、原因、controller 實際是否停止 | `/safety/status`、`list_controllers` |
| 事件紀錄 | 時間、等級、訊息；故障置頂，可匯出 | UI 彙整 |

**任務八段**（`state` 格式為 `ARM1:APPROACH_A`）：回 HOME、Arm1 取料、Arm1 放到 B、確認 B 區、Arm2 取料、確認 B 清空、Arm2 放到 C、確認 C 區。未對應的步驟顯示原文。

**B 區互鎖**依 `resources.py` 的 `ZoneManager` 與兩支手臂的工作流程顯示：同時只有一個擁有者；擁有者以手臂色標示，另一臂「禁止進入」並關閉閘門（黑條）；未佔用時要手臂已離開才可預約，B 區沒物件時 Arm1 可進入，有物件時 Arm2 可進入；故障時若有擁有者則顯示「故障鎖定」直到復歸。模擬的實際決策用 Gazebo 真值，顯示的區域狀態來自視覺，接 ROS 時要依決策來源選擇資料，避免互鎖圖和實際判斷不一致。

**資料限制：**

- 韌體只回報位置，沒有溫度、電壓、負載。速度是位置差分，要標示為估計值。
- raw 換算要和 `cm530_hardware/src/calibration.cpp` 一致。`calibration.yaml` 還是 null，先顯示「—」；模擬不顯示 raw。
- 模擬預設 `observation_source=truth`，任務依 Gazebo 真值決策，畫面的區域判定只是視覺結果，兩者可能不同。要顯示決策來源。
- 校正不完整時判定框仍會畫，座標改顯示像素。有框不代表已校正。
- 相機超過 1 秒沒更新顯示「無訊號」；馬達表整張反灰標「資料過期」。

## 9. 啟動模式

| 模式 | 內容 | 能否開始工作 |
|---|---|---|
| Mock | `mock.launch.py rviz:=false` | 否，沒有任務節點 |
| 模擬 | 新增 `hmi_sim.launch.py`：模擬、視覺、校正狀態、coordinator、`safety_supervisor` | 可以 |
| Mock Serial | `hardware.launch.py use_mock_serial:=true` | 否，用來測啟動步驟 |
| 實機唯讀 | `hardware.launch.py` 加 `vision.launch.py` | 否 |
| 實機動作 | `enable_motion:=true`，選實測的 controllers 檔 | `BLOCKED` |

- `safety_supervisor` 在模擬要設 `require_estop:=false`，否則沒有心跳會一直鎖定。
- 各模式獨立於 UI 執行，UI 當掉時系統不跟著結束，重開可接回。
- `ROS_DOMAIN_ID`、`GZ_PARTITION` 和 `scripts/start_sim.sh` 一致。
- 就緒以 `list_controllers` 為準，spawner 可能誤報失敗（ROS_INTERFACES 缺口 10）。
- `cycles`、`prefilled_slots` 放在啟動選項，任務中不能改。

### 9.1 實機與 Gazebo 同步

**同步的是實機回授 `/joint_states`，不是把同一份指令送給兩邊。** 跟隨回授時，實機卡住或沒到位，Gazebo 也會顯示出來；同送指令只會看到「應該到的位置」。

**不能直接同時開 `sim.launch.py` 和實機。** 兩邊使用相同的 `/joint_states`、`/controller_manager/*`、`/armN_controller/*`、`/move_action`、`/tf`、`/robot_description`，模擬相機也發布 `/{env,arm1,arm2}_cam/image_raw`。同一個 ROS domain 下，假回授會混進到位判斷、視覺節點可能吃到模擬影像，`safety_supervisor` 也可能操作到錯的 controller manager。

| 設計 | 內容 |
|---|---|
| 隔離 | Gazebo 使用獨立的 `ROS_DOMAIN_ID` 和 `GZ_PARTITION`，實機系統完全看不到它 |
| 單向 | 新增 `twin_mirror` 節點：在實機 domain 只有一個 `/joint_states` 訂閱，沒有任何發布者或 service client；只在 Gazebo domain 發布 |
| 啟動內容 | 新增 `twin.launch.py`：Gazebo、`robot_state_publisher`、位置 controller、`/view_*`。沒有 `move_group`、coordinator、視覺節點、吸盤，也不發布三支相機 topic |
| 手臂驅動 | `forward_command_controller` 接收回授位置，頻率 20～30 Hz |
| UI 影像 | UI 用獨立的 context 只訂閱 Gazebo domain 的 `/view_*` |
| 啟停 | 獨立於系統啟動，可隨時開關。Gazebo 當掉不影響實機，UI 只顯示「同步中斷」 |
| 資料過期 | 回授超過 1 秒沒更新就停止送出，手臂停在最後位置並標示中斷 |
| 瓶蓋 | 第一版只同步手臂。實機沒有瓶蓋真值，孿生場景不顯示瓶蓋 |
| 系統負載 | Gazebo 以低優先權執行；開啟前後要量 `/joint_states` 頻率與相機 FPS，不能下降 |

**前提與限制：**

- 實機回授要先有正確的校正，H2 之前 `calibration.yaml` 是空的，驅動不會啟動。開發時先用 Mock 和 Mock Serial 驗證。
- H2 的唯讀核對可以開著同步，手扳時看 Gazebo 方向是否一致，幫助發現方向錯誤，但不取代手冊的量測。
- Gazebo 跟得上不代表實機安全或到位，不能當驗收依據。
- Gazebo 在 Orin 上的實際渲染與負載是 `NOT_RUN`，要先試跑。負載過高時可降低 `/view_*` 頻率。

## 10. 現有程式要改的地方

| 檔案 | 改動 | 階段 |
|---|---|---|
| `scripts/install_jazzy.sh` | 加 `fonts-noto-cjk`、`python3-pyqt5` | 0 |
| `src/vision_pkg` 三個節點 | 新增 `publish_debug_image`，發布 `/vision/*/debug_image`。`_render` 目前被 `show_debug` 擋住，要讓繪圖和 `imshow` 分開控制 | 1 |
| `src/dual_arm_bringup` | 新增 `hmi_sim.launch.py`（已提前於階段 1 完成，尚未含 `safety_supervisor`） | 2 |
| `safety_monitor.py`、`safety_supervisor.py` | 新增 `/safety/trigger_stop`，直接鎖定，由 `/safety/reset` 解除 | 3 |
| `coordinator_node.py` | 新增 `/dual_arm/go_home` | 3 |
| 新增 `twin_mirror`、`twin.launch.py`、孿生用 controller 設定與不含相機和瓶蓋的 world | 第 9.1 節，不改動現有 `sim.launch.py` | 同步階段 |
| 文件 | `ROS_INTERFACES`、`HARDWARE_TEST_GUIDE`、`PROGRESS`、`TEST_REPORT`、`RESUME` | 各階段 |

`vision_pkg` 位於 `src/`，可以修改；`third_party/` 裡的上游版本不動。

## 11. 階段與完成條件

| 階段 | 內容 | 完成條件 |
|---|---|---|
| 0 | 假資料完整畫面 | 第 12 節的情境都正確，使用者確認視覺，WSLg 與 Orin 都開得起來 |
| 1 | 唯讀監看、三格判定框、Gazebo 視角 | 模擬中三格、四視角與數值正確，斷線會顯示過期 |
| 2 | 啟動與關閉 | 連續十次啟動關閉無殘留，UI 重開能接回 |
| 3 | 任務控制、強制停止、回 HOME、復歸 | 模擬完成一輪；無持物時中途停止能復歸並再次開始；有持物時能重置模擬 |
| 4 | 事件匯出、截圖、版面細修 | 連續執行一小時記憶體穩定 |
| 同步 | 實機同步 Gazebo（第 9.1 節） | Mock 與 Mock Serial 下 Gazebo 跟隨回授；實機 domain 上確認 `twin_mirror` 只有一個訂閱；Gazebo 當掉時實機系統不受影響；Orin 上量測負載 |
| 5 | 實機分步啟動、吸盤確認 | Mock Serial 通過，再配合 H0 起的順序驗證 |

和實機測試的關係：H0、H1、V0、E0 可和階段 0、1 同時進行。H3～H5 不用 UI 下動作指令，只開唯讀監看。H6 以後的前置條件見 HARDWARE_TEST_GUIDE。

## 12. 階段 0 工作清單

開工前要在 WSL 和 Orin 各執行一次：

```bash
sudo apt-get install -y fonts-noto-cjk python3-pyqt5
```

| # | 工作 | 產出 |
|---|---|---|
| 1 | 建立 `dual_arm_hmi` 套件，加進 `install_jazzy.sh` 的相依 | 可建置的空套件 |
| 2 | `ui/theme.py`：第 3 節的色彩與字型 | 樣式集中一處 |
| 3 | `model/`：狀態彙整、按鈕規則、步驟對照 | 單元測試 |
| 4 | `sources/fake_source.py`：情境切換 | 不需要 ROS |
| 5 | 五個面板與主視窗，含版面切換 | 可操作畫面 |
| 6 | 截圖工具，輸出四種解析度 | `docs/evidence/hmi/stage0/` |
| 7 | Orin 上執行一次，確認桌面環境與顯示驅動 | 紀錄與照片 |

假資料情境：未啟動、啟動中、就緒、工作中、等待吸盤確認、取消後故障、安全鎖定、C 區已滿、實機唯讀、實機 `BLOCKED`、相機無訊號、資料過期。

## 13. 驗收

WSLg 與 Orin 各跑一次，結果放 `docs/evidence/hmi/`，狀態只用 `PASS`、`FAIL`、`BLOCKED`、`NOT_RUN`。UI 在模擬通過不等於實機驗收。

| 項目 | 內容 |
|---|---|
| 解析度 | 1280×720、1366×768、1920×1080、2560×1440 |
| 顯示 | 中文正常、高 DPI 不模糊、相機比例正確 |
| 效能 | 三相機同時顯示的 FPS、延遲、CPU。建議目標：相機至少 10 FPS，強制停止從點擊到送出低於 100 ms，實測後定案 |
| 異常 | 相機斷線、ROS 節點結束、UI 被強制關閉、操作被拒絕 |
| 單元測試 | 狀態模型、按鈕規則、步驟對照，不需要 ROS 和 Qt |

已做的環境檢查（2026-11-10）：

| 項目 | 狀態 | 說明 |
|---|---|---|
| PyQt5、rclpy、cv_bridge、OpenCV 同一程序 | `PASS` | WSL |
| arm64 套件存在 | `PASS` | 只確認套件庫有發布 |
| 階段 0 單元與版面測試 | `PASS` | 166 項，含十二種情境在四種解析度的離屏版面檢查，[evidence/hmi/stage0/](evidence/hmi/stage0/) |
| 階段 0 WSLg 實際視窗 | `PASS` | xcb，視窗可開啟、實按 F12 送出強制停止，假資料下每次刷新平均 7.0 ms；字型暫用私有資料夾 |
| 階段 1 離線測試 | `PASS` | 205 項，[evidence/hmi/stage1/](evidence/hmi/stage1/) |
| 階段 1 接模擬實測 | `PASS` | 實際視窗元件以離屏方式接 `hmi_sim.launch.py`：三格判定框、四個 Gazebo 視角、八軸、一輪搬運到 `SUCCEEDED`、斷線標示 |
| 階段 1 唯讀 | `PASS` | `ros2 node info` 只有 `/rosout`、`/parameter_events` 發布者，client 只有 `list_controllers`、`get_parameters`，沒有 action |
| UI 對系統的負載 | `PASS` | WSL 模擬速度：無 UI 0.182、有 UI 0.183 倍實時；刷新平均 1.0 ms。相機約 2 FPS 是 WSL 渲染限制，無法驗證 10 FPS 目標 |
| WSL 系統繁中字型 | `FAIL` | 確認時為 0 個，需用 sudo 安裝 `fonts-noto-cjk` |
| 高 DPI 150% | `NOT_RUN` | 目前只測 100% |
| 使用者視覺確認 | `NOT_RUN` | 等使用者看過畫面 |
| Orin 實際執行 | `NOT_RUN` | 還不確定 Orin 上是否已裝 ROS Jazzy |

## 14. 風險與未決

| 項目 | 對策 |
|---|---|
| Orin 桌面或顯示驅動不可用 | 階段 0 就到 Orin 開一次畫面 |
| Gazebo 加三路影像在 WSL 太重 | 顯示降頻，模擬用 headless |
| 軟體停止被誤認為實體急停 | 按鈕標明，實機模式持續提示 |
| 視覺與真值不一致造成誤解 | 顯示決策來源 |
| 舊資料被當成即時資料 | 三類資料都有過期判斷 |
| Gazebo 和實機系統互相干擾 | 獨立 domain，`twin_mirror` 對實機只訂閱 |
| Gazebo 拖慢 Orin 上的控制或視覺 | 低優先權，開啟前後量測，可隨時關閉 |
| 實體急停的接線方式未定 | D8 節點等接線決定，不影響階段 0～3 |
