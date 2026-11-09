# 專案現況評估與未來修改方向

更新：2026-11-10。本文件是 2026-11-09 的評估，第 1、2、4、6、7、9 節已依現況更新。工作進度以 [MODIFICATION_PLAN.md](MODIFICATION_PLAN.md) 第 6 節為準。

比對對象：[Azeem1010/Dual-Arm-TEST](https://github.com/Azeem1010/Dual-Arm-TEST)，commit `26d187f`，以下簡稱「對方」。

狀態只使用 `PASS`、`FAIL`、`BLOCKED`、`NOT_RUN`。

**評估方式的限制：** 兩個專案都是靜態閱讀，沒有建置或執行。對方的實機資料照其 JSON 紀錄採信，尚未獨立驗證。FK 驗算是名義 CAD 幾何的手算，不是量測。標記「需在 Jazzy 確認」的項目來自對框架預設行為的理解，`NOT_RUN`。

## 1. 總結

| 問題 | 結論 |
|---|---|
| 離實機取放還差什麼 | 模擬的任務節點、驅動強化、安全監控、吸盤後端都已完成；還缺實機校正、視覺的區域判斷、實機 TF 與急停心跳來源 |
| 對方能補什麼 | 實機資料、任務節點寫法、故障復歸流程 |
| 本地要保留什麼 | CAD 模型、`ros2_control` 驅動、校正閘門、視覺工具、B 區與格位管理 |
| 最大阻礙 | A 區左右與 j1 方向證據矛盾；j2 方向與零點矛盾；格位 1 與 A 區可達範圍 |
| 建議策略 | 模型與驅動用本地，任務層參照對方重寫，實機依階梯逐步放行 |

兩邊都還沒有完成實機取放。對方的實機進度是：序列連線、單臂移動一次、四軸小幅方向測試、回 Home。

## 2. 與對方的差異

| 項目 | 本地 | 對方 | 採用 |
|---|---|---|---|
| 運動模型 | CAD：連桿 93.5 mm，腕到 TCP 71 mm | `arm1.urdf`：99.5 mm，108.5 mm | 本地 |
| 硬體控制 | C++ `ros2_control`，單一序列埠管理者 | Python action bridge，已實際驅動 arm1 | 本地架構，吸收對方到位判定 |
| 校正閘門 | 空值拒絕啟動，動作需多項明確授權 | NaN 拒絕，但曾以使用者確認繞過量測 | 本地 |
| 校正資料 | `calibration.yaml` 全為 null | 方向測試、尺量、READ 紀錄 | 對方資料，先確認座標方向 |
| 任務節點 | 已完成 `coordinator_node`（參照對方結構自行撰寫） | A→B→C、故障紀錄、token 復歸 | 本地 |
| PlanningScene | 已同步附掛、卸除、B 區與格位物件，復歸時會清理 | 附掛、卸除、B 區物件交接 | 本地 |
| B 區與格位 | `ZoneManager`、`SlotManager` 有 token 與連續性檢查 | `BReservation` 較簡單 | 本地 |
| 視覺 | 多 `image_rotate_node`、`calibrate_caps` | 較舊，`vision_interfaces` 相同 | 本地 |
| 吸盤 | Gazebo、人工 token、ESP32 三種後端（ESP32 只用替身驗證） | 人工操作 ESP32，再用 token 確認 | 本地 |
| 校正有效性與影像時效 | 取料點已接上閘門，區域與格位尚未 | coordinator 只檢查服務回覆成功與座標範圍 | 本地 |

**不要照搬：**

- `arm1.urdf`、`dual_arm_demo.urdf`：尺寸不符 CAD。
- `manual_xy_legacy_confirmed.yaml`：對方已自行鎖住。
- `bridge_node.py`：與 `ros2_control` 架構重複。
- `ArmIO` 借用其他類別方法與 `__getattr__` 動態轉發的寫法，型別不清楚，測試也難寫。

## 3. 實機事實整理

### 3.1 配置

**狀態：`BLOCKED`。A 區在手臂左邊或右邊，目前的證據互相矛盾。** 模擬的遠側配置（commit `c7dfba3`）要等實機確認。

| 證據 | 來源 | 指向 |
|---|---|---|
| 手臂底座遠離使用者，A 區在手臂左邊 | 使用者於 2026-11-09 確認 | A 在左，j1 方向 −1 |
| home_A 為 arm1 自身右轉 30°，home_C 為 arm2 自身左轉 30°；明定不以拍照者或畫面為準 | 第 17 版 `HOME_CALIBRATION_TEST.md` | A 在右 |
| Home_A 尺量 Y = −80 mm（+Y 朝左），約 −30.65° | 對方 `home_a_measured_xyz.json` | A 在右 |
| 相機目標 y = −0.083 m | 對方 `new_target_read`、`moveit_ik_only` 紀錄 | A 在右 |
| `OUTER_EDGE_Y_MM = -200` | `calibrate_caps` 預設值 | A 在右 |
| 從底座後方看，+raw 吸盤往左 | 對方 `joint_direction_observations` | j1 方向 +1 |
| 方向 +1 時，arm2 正前方約 raw 488，接近 512 | 由 home_C 自身左轉 30° 推算 | j1 方向 +1 |

這些無法同時成立。若底座遠離使用者，而視覺文件的「由左到右 C | B | A」也正確，手臂自身右轉會朝向 C 區，不是 A 區。可能的原因是文件的目標已過時，或文件裡的「使用者側」和目前使用者的站位不同。

**在確認前，對方紀錄的 Y 值和 homography 都不可沿用，也不可自行改號。** 實機俯視照片仍是 `NOT_RUN`，確認方法見階段 A。

### 3.2 關節方向與零點

| 軸 | 本地假設 | 實機線索 | 狀態 |
|---|---|---|---|
| j1 | 方向 −1，`raw_at_cad_zero` 192.3 | 方向未定（見 3.1）。A 在右且方向 +1 時，零點候選約 194.5；A 在左且方向 −1 時也約 194.5；A 在左且方向 +1 時 raw 561 幾乎朝後，不合理 | `BLOCKED`，需扭力關閉下手動確認 |
| j2 | 方向 +1 | +raw 時吸盤往上，模型預測往下 | `BLOCKED` |
| j3 | 方向 +1 | +raw 時吸盤往下，與模型一致 | `NOT_RUN`，零點未量 |
| j4 | 方向 +1 | +raw 時吸盤靠近底座，與模型一致 | `NOT_RUN`，零點未量 |

j2 的矛盾用「raw 512 垂直伸直」與 Home_A 尺量值（半徑 156.9 mm、高度 120 mm）驗算：

| j2/j3/j4 | 計算的半徑、高度 | 與尺量差距 | 符合運動方向 |
|---|---|---|---|
| +1/+1/+1 | 133.1、125.8 mm | 24.5 mm | 否 |
| −1/+1/+1 | 85.5、195.1 mm | 103.6 mm | 是 |

八種符號組合都無法同時符合兩者，所以 raw 512 的 j2 零點假設或該次 j2 觀察至少有一項有誤。

### 3.3 可直接參考的實機數據

| 項目 | 紀錄 | 用途 |
|---|---|---|
| 板上 HOME | arm1 `[90,567,712,825]`，arm2 `[590,567,712,825]` | 與本地 `expected_home` 一致 |
| 序列埠 | `/dev/serial/by-id/usb-FTDI_FT232R_USB_UART_AH01R3LJ-if00-port0` | Orin 部署參考 |
| READ 耗時 | 一臂約 16 ms（兩臂回覆時間差） | 估算迴圈率與 `max_step_raw` |
| 穩態誤差 | j2 +4 到 +7 raw，j3 +1 到 +4 raw，j1、j4 約 ±2 raw | 設定 goal tolerance |
| 誤差影響 | j2 5 raw 約等於吸盤端 3.4 mm | 判斷是否需要到位修正 |
| 通訊異常 | `VERSION` 回 `ERR,BAD_CMD` 兩次；`ERR,DXL_TIMEOUT,arm1,15` 一次 | 驅動強化、檢查 ID 15 線材 |
| 實機速度 | 比例 0.05，單段約 66 秒 | 第一次動作的上限參考 |
| 休息姿態 | `[213,524,517,486]`、`[229,490,514,500]`、`[537,505,536,662]` | 限位要涵蓋，或定義手動歸位 |
| 工具外形 | 末端有相機與支撐柱 | 工具碰撞包絡 |

韌體事實（第 17 版原始碼）：只寫 Goal Position 與 Torque Enable，不寫 Moving Speed；開機會關閉兩臂扭力；沒有 watchdog。

### 3.4 韌體版本比對

| 項目 | 第 16 版（協定 4） | 第 17 版（協定 5） |
|---|---|---|
| 四軸 raw 位置控制 `AX` | 有 | 有 |
| 讀取馬達位置 `READ` | 無 | 有 |
| `HOME`、`GET_HOME`、`HOLD` | 無 | 有，home_A `[90,567,712,825]` |
| XYZ、弧度、各軸零點與方向 | 不提供 | 不提供，規格要求由 ROS 換算 |

- **第 17 版足以收集校正資料，不需要換韌體。** 本地驅動也只接受 `VERSION,5`，不能使用第 16 版。
- 本地 submodule 與對方副本的第 17 版只有 `README.md` 不同。
- 例外：第 17 版不能讀寫 Moving Speed，確認 `moving_speed_verified` 需要另外的工具。
- 規格書中 HOME 全為 512 的段落已過時，以 `arm_config.h` 和板上 `GET_HOME` 為準。
- `HOME` 不保證路徑無碰撞，規格要求由 ROS 以 `GET_HOME` 為終點規劃路徑。
- `HOME_CALIBRATION_TEST.md` 只有步驟和空白紀錄表。對方 2026-11-09 的方向測試與尺量是部分資料，校正仍未完成。
- 馬達讀值對應到關節角度後，還需要 TCP 幾何、底座到場地的轉換與相機標定，才能定位到物體上方。目前模型在 Home_A 的最佳假設誤差為 24.5 mm，大於 2 cm 的懸停餘裕。

## 4. 整體缺口與評估

| 模組 | 狀態 | 主要缺口 |
|---|---|---|
| CAD 與 URDF | 模型 `PASS`，實機 `NOT_RUN` | 零點、方向、實機高度；肩高差異需釐清（模型距場地頂 81.5 mm，CAD 距平台頂 85.5 mm） |
| 碰撞模型 | `BLOCKED`（WP11） | 包圍盒過於保守，缺平台、泡棉、相機支架 |
| C 區與 A 區可達性 | `FAIL`（D3） | 格位 1 搆不到；A 區只有 4 個瓶蓋位置可達 |
| MoveIt | 模擬 `PASS` | 實機容差要實測 |
| `cm530_hardware` | Mock `PASS`，實機 `NOT_RUN` | READ 重試等 D2 |
| 任務協調 | 模擬 `PASS`，實機 `BLOCKED` | 節點會拒絕實機模式 |
| 視覺接線 | `BLOCKED`（D7） | 取料點完成；區域與格位被模擬相機遮擋 |
| 相機校正 | `NOT_RUN` | 三相機實體校正、硬體 `frame_id` 不一致（C20）、實機 TF |
| 吸盤 | 替身節點 `PASS`，實機 `NOT_RUN` | 韌體沒有真空感測，結果由人工確認 |
| 安全 | Mock `PASS`，實機 `NOT_RUN` | 實體急停與心跳來源 |
| 需求要求的交付物 | 大致完成 | `esp32_micro_ros` 套件未建立，ESP32 整合放在 coordinator 的吸盤 gateway |
| Gazebo 關閉 | `NOT_RUN` | 原本只對 launch 送 SIGINT 的 `FAIL` 未用相同方法重測 |

## 5. 節點架構：參照對方的寫法

### 5.1 值得沿用的模式

1. **流程與 ROS 分離。** `workflow.py` 不 import `rclpy`，動作、視覺、吸盤全由注入的 IO 物件提供，可用假 IO 做單元測試。
2. **長任務放工作執行緒。** `start` 只回覆「已接受」，最終結果看 status；搭配 `ReentrantCallbackGroup` 與 `MultiThreadedExecutor`。
3. **每次狀態轉移都先寫入紀錄。** 重啟後若上次未完成，或設定指紋不符，直接進 FAULT。
4. **故障不自動解除。** 持物狀態標記 `unknown`，B 區使用權保留，需現場清空並以一次性 token 復歸。
5. **每步前檢查。** `guard()` 同時檢查取消、急停心跳時效與控制器健康；watchdog 定時中止工作。
6. **放行前先預檢。** 進入 B 區前先對所有目標點做 IK 檢查，再保留使用權。
7. **取消要到底層。** 對方實測發現只取消 MoveIt action 時底層仍在動，本地要驗證 JTC 的取消行為。
8. **啟動一致性檢查。** 模型雜湊、兩臂 B 點一致性、ROS HOME 與板上 `GET_HOME` 比對。
9. **操作工具與主流程分開。** `operator_console`、唯讀 `cm530_probe`、預設只規劃的 `manual_xy`。

### 5.2 建議的本地結構

沿用需求書的套件名稱：

```text
dual_arm_coordinator/dual_arm_coordinator/
├── workflow/                 # 純 Python，無 rclpy
│   ├── arm1_workflow.py      # A→B
│   ├── arm2_workflow.py      # B→C
│   └── transfer.py           # 整批流程與 C 區檢查
├── resources.py              # 沿用本地 ZoneManager / SlotManager
├── gateways/                 # ROS 介面，各自可替換
│   ├── motion.py             # MoveIt 規劃、執行、PlanningScene、到位確認
│   ├── vision.py             # 視覺 client、時效、校正有效性、座標轉換
│   └── gripper.py            # gazebo / manual_token / esp32 三種後端
├── journal.py                # 紀錄、檔案鎖、設定與模型指紋
├── coordinator_node.py       # 服務、狀態、watchdog、工作執行緒
└── tools/
    ├── operator_console.py
    ├── manual_xy.py          # 預設只規劃
    └── cm530_probe.py        # 唯讀，且不可與驅動同時持有序列埠
```

### 5.3 節點與介面

| 節點 | 責任 | 來源 |
|---|---|---|
| `dual_arm_coordinator` | A→B→C、B 區與格位、紀錄、復歸 | 參照對方，資源管理用本地 |
| `move_group` | 規劃與碰撞檢查 | 本地 |
| `ros2_control_node` + `CM530SystemInterface` | 唯一序列埠持有者 | 本地 |
| `env`/`arm1`/`arm2_vision_node` | 視覺服務，介面不可更動 | 本地 |
| `calibration_status` | 校正有效性 | 本地，需接到 coordinator |
| `safety_supervisor`（新增） | 急停心跳、coordinator 存活，失效時停用控制器 | 參照對方 permit 概念 |
| 吸盤節點 | Gazebo 或 ESP32 | 本地 Gazebo，ESP32 待開發 |

| 介面 | 型別 | 用途 |
|---|---|---|
| `/dual_arm/start`、`/dual_arm/cancel` | `std_srvs/Trigger` | 接受工作、取消 |
| `/dual_arm/confirm`、`/dual_arm/recover` | `dual_arm_interfaces/ConfirmStep` | 人工確認、現場復歸 |
| `/dual_arm/status` | `std_msgs/String`（JSON，transient local） | 狀態、持物、B 區擁有者、格位 |
| `/handoff/b_state` | `std_msgs/String` | B 區使用權資訊 |
| `/dual_arm/permit`、`/safety/estop` | `std_msgs/Bool` | 軟體互鎖，不取代實體急停 |

本地不需要對方的 `/cm530/armN/enable`。扭力由 `set_hardware_component_state` 與 `switch_controllers` 明確啟用。

### 5.4 對方沒有、本地必須補上

| 需求 | 做法 |
|---|---|
| 校正無效時禁止自動抓取 | `start` 與每次視覺查詢前檢查 `/vision/calibration_status` |
| 目標時間戳驗證 | 服務回覆沒有時間戳，需以同時段影像證據對應 |
| 手臂靜止後才拍照 | Home 到位並穩定後才查詢，對方用 1.1 秒，需實測 |
| 座標轉換 | 由 `arm1_base` 經 TF 轉到 MoveIt 座標，不假設兩者相同 |
| 到位確認 | MoveIt 回報成功後，再取連續 3 筆新 READ 都在容差內 |
| 吸盤與場景一致 | 吸附回饋與 attached object 必須一致 |
| 格位提交 | `verify_place` 通過才提交，由 `SlotManager` 檢查連續性 |

## 6. `cm530_hardware` 強化項目

已於 WP8 完成，細節見 [MODIFICATION_PLAN.md](MODIFICATION_PLAN.md)。與本文件當初的建議不同之處：清除韌體緩衝改用 DEL 而不是空行（空行可能執行殘留命令）；速度抖動改用 `stopped_velocity_tolerance` 處理，沒有拿掉 velocity 狀態。READ 有限重試等 D2。

## 7. 執行順序

已併入 [MODIFICATION_PLAN.md](MODIFICATION_PLAN.md) 的工作包，實機放行階梯見 [TEST_PLAN.md](TEST_PLAN.md) 第 6 節，操作步驟見 [ORIN_DEPLOYMENT.md](ORIN_DEPLOYMENT.md)。

## 8. 風險

| 風險 | 影響 | 對策 |
|---|---|---|
| j2 零點錯誤 | 手臂朝錯誤方向，可能撞擊 | 階段 A 出口條件，不跳過 |
| A 區左右與 j1 方向未定 | 目標左右鏡像、底座轉錯方向 | 階段 A 手動確認，之後一律重新標定 |
| AX-12A 下垂與背隙 | 接觸高度偏差 | 到位修正、固定進給方向 |
| 序列埠或馬達偶發錯誤 | 流程頻繁中止 | 線材檢查、驅動強化 |
| CM-530 重置 | 扭力立即關閉，手臂失力 | 偵測 READY、機構下方淨空 |
| 模擬速度帶到實機 | 超速或振動 | 硬體設定分離，由 0.05 起步 |
| 格位 1 未解決 | 第一個放置就失敗 | 階段 C 先決策 |
| 人工吸盤確認 | 速度慢、依賴操作者 | 過渡方案，階段 F 取代 |

## 9. 需要使用者決定

清單與預設值見 [MODIFICATION_PLAN.md](MODIFICATION_PLAN.md) 第 2 節（D0～D7）。

## 10. 相關文件

- [COORDINATE_FRAMES.md](COORDINATE_FRAMES.md)：座標定義
- [HOME_POSES.md](HOME_POSES.md)：HOME 換算
- [ROS_INTERFACES.md](ROS_INTERFACES.md)：現有介面與已知缺口
- [SLOT_ADJUSTMENT.md](SLOT_ADJUSTMENT.md)：格位調整方案
- [PROGRESS.md](PROGRESS.md)：目前進度
