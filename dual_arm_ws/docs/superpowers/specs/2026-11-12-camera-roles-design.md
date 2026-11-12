# 鏡頭分工調整設計：環境相機負責 A/B/C，手臂鏡頭輪流監控

日期：2026-11-12　狀態：待使用者核准

## 1. 為什麼要改

三顆 USB 相機接在 Orin 同一個 USB 2.0 hub（root port 4：環境 4.3、手臂1 4.4.3、手臂2 4.4.1）。兩顆 Alcor 手臂鏡頭只支援未壓縮 YUYV，640×480@30 每顆約 147 Mbit/s；文件已記錄三顆同時開時第三顆無法啟動串流（`docs/ORIN_DEPLOYMENT.md`、`docs/PROGRESS.md`）。

解法是改變鏡頭分工，讓任務決策只依賴一顆 MJPG 環境相機，兩顆手臂鏡頭降為純監控並且輪流開。新版環境相機程式是上游 [env_camera_vision](https://github.com/Azeem1010/env_camera_vision)（commit `6b059eb`），相機已移到使用者這側，一次看到 A/B/C 三區。

## 2. 目標

1. **環境相機**負責所有任務判斷：
   - A 區：要吸取的瓶蓋座標（取代手臂 1 鏡頭的 `get_pick_target`）。
   - B 區：瓶蓋被放下後的實際座標，Arm 2 依此座標吸取（取代固定的 `b_place` 給 Arm 2 吸取用）。
   - C 區：8 格佔用狀態與放置驗證（取代手臂 2 鏡頭的 `get_grid_state`、`verify_place`）。
   - A/B 有無物件、C 區數量（取代 `get_zone_state` 的對應欄位）。
2. **手臂鏡頭**只做監控（操作介面顯示），不參與任何決策。
3. **任何時刻最多只有一顆手臂鏡頭在串流**，跟著 coordinator 目前動作的手臂切換。

## 3. 非目標

- 不開啟實機動作。coordinator 仍拒絕實機模式（還缺硬體 TF 與校正），本次只讓視覺這一塊到位。
- 不讓 Gazebo 模擬跑 `env_scene`。模擬的環境相機是正上方俯視、場地不是粉紅泡棉，`env_scene` 的場地偵測不適用；模擬維持現有的 Gazebo 真值與 `vision_pick` 來源。
- 不修改上游 `vision_interfaces`、`env_scene_interfaces` 的欄位與服務名稱。
- 不刪除 `vision_pkg` 的手臂視覺節點程式，只是實機啟動時不再啟動它們。
- 不做端到端試跑模式（使用者 2026-11-12 選定）。新的觀測來源只用單元測試驗證；Orin 上分項驗證環境相機判斷、手臂鏡頭切換（用手動發布的 `/dual_arm/status` 觸發）與頻寬。等實機模式開放時再接上 coordinator，屆時再處理 `b_arm_clear` 的實機關節回授。

## 4. 反目標（技術上能動但算失敗）

- 兩顆手臂鏡頭在任何時刻同時串流，包括開機、切換中、程式當掉重啟。
- 手臂鏡頭沒畫面、切換慢或失敗而讓任務停下或卡住。監控鏡頭的問題只能在介面上顯示，不能影響任務。
- 環境相機結果無效、過期或標定未通過時，任務仍拿它的座標去動作。

## 5. 限制

- `third_party/` 不可修改；新上游以 git submodule 加入並鎖版本，需要整合時複製到 `src/`（`AGENTS.md`）。
- 服務沒有時間戳，查詢前要確認有手臂停妥後才到的新影像（沿用 `gateways/vision.py` 的 `_problem` 閘門）。
- B 區釋放仍要以手臂確實離開為依據，不能只靠逾時（`ARCHITECTURE.md`）。
- 環境相機看不到 A 區最左端約 25%（上游 README，`a_visible_ratio`）。**處理方式定為現場規則**（使用者 2026-11-12 選定）：A 區用黑色膠帶框出可見的放置範圍，瓶蓋只能放在框內，寫進操作手冊（`HARDWARE_TEST_GUIDE.md`）。程式不因 `a_visible_ratio < 1` 拒絕執行。2026-11-12 現場畫面已有這個黑框，6 顆瓶蓋都在框內。
- **上游版本要先確認**：2026-11-12 現場畫面的標示是 `coords: x0=black frame left (visible range)`，A 區座標原點改以黑框左緣為準，這和 GitHub 上的 `6b059eb` 不同（該版本以場地接縫為 x=0），表示現場跑的是還沒推上 GitHub 的新版。實作前要請上游作者推送現場版本，鎖定那個 commit，並依新版的 A 區座標定義核對 7.4 節的欄位對應。
- 上游 `arm2_base` 軸向是建議值、標為待確認；`env_scene` 的 armN_base 定義（x 朝使用者、y 由 A 往 C）必須和本專案 `COORDINATE_FRAMES.md` 的 `arm1_base`／`arm2_base` 一致才能直接用。

## 6. 考慮過的做法（手臂鏡頭切換）

| 做法 | 內容 | 取捨 |
|---|---|---|
| **A. 開關 usb_cam 程序（採用）** | 新節點依 coordinator 的 `active_arm` 啟動／結束手臂鏡頭的 `usb_cam` 程序 | 程序結束裝置一定釋放，從開機起就不會同時開；切換約 1–2 秒才有畫面 |
| B. usb_cam 的 `set_capture` | 程序常駐，以 STREAMOFF/STREAMON 切換 | 較快；但 usb_cam 啟動時自動開串流，兩顆同時開機仍會撞，且 STREAMOFF 是否真的釋放頻寬要實測 |
| C. 自寫 OpenCV 手臂鏡頭節點 | 一個節點輪流開兩個裝置 | 完全可控，但多一個要維護的驅動 |

使用者選 **A**（2026-11-12）。理由：這次的重點是保證不撞頻寬，A 最可靠也最好驗證；切換延遲只影響監控畫面。

使用者決定的事：
- 環境相機負責 A/B/C 三區判斷，手臂鏡頭只監控、不可同時開。
- 輪流規則：**跟著動作的手臂**。
- 切換機制：做法 A。

## 7. 設計

### 7.1 上游整合

- 新增 submodule `third_party/env_camera_vision`，鎖在 `6b059eb`，記錄到 `docs/sources.lock.json`。
- 複製 `env_scene`、`env_scene_interfaces` 到 `src/`，保留上游測試與測試圖片。

### 7.2 實機視覺啟動（取代目前三相機都啟動的做法）

常駐：
- 環境相機 `usb_cam`（MJPG，`/env_cam/image_raw`）與 `env_scene_node`。
- `dual_arm_vision_adapter` 對環境相機的狀態回報。

不再常駐：
- `arm1_vision_node`、`arm2_vision_node`、`env_vision_node`（舊環境節點的功能被 `env_scene` 取代）。
- 兩顆手臂鏡頭的 `usb_cam`，改由 7.3 的切換節點管理。

`vision.launch.py` 的 by-path 裝置設定、`rotate`（手臂 1 鏡頭 180°，經 `image_rotate_node`）沿用 `cameras.yaml`，由切換節點讀取同一份設定。操作介面的實機啟動（`launcher/profiles.py`）改用新的啟動方式。

### 7.3 手臂鏡頭切換節點

位置：`dual_arm_vision_adapter` 內新增一個節點（建造者的決定，見第 9 節）。

- 訂閱 `/dual_arm/status`（JSON，已含 `active_arm`），決定要開哪一顆：`active_arm` 為 `arm1`／`arm2` 時開該顆；空字串（閒置、剛開機）時開 arm1。
- **切換順序**：先結束目前的 usb_cam 程序（含 rotate 節點），確認程序已退出（SIGTERM，逾時再 SIGKILL），**之後**才啟動另一顆。任何情況下都不能先開再關。
- 程序異常結束：只重啟「應該開的那一顆」，不碰另一顆。
- coordinator 狀態消失或過期：維持目前那一顆，不切換。
- 發布一個狀態 topic（目前開的是哪顆、正在切換、失敗原因），給操作介面顯示。
- 不提供、也不呼叫任何會影響任務的服務；coordinator 不知道這個節點存在。

### 7.4 coordinator 觀測來源

新增 `observation_source` 值 `env_scene`（實機用），由新的 `EnvSceneObserver` 實作 `zone()`、`pick_target()`、`grid()`、`verify_place()`，另加 Arm 2 的 B 區吸取點。每次查詢都呼叫 `/vision/env_scene/get_scene`，並套用：

- 影像閘門：手臂停妥後要有新的 `/env_cam/image_raw`（沿用 `ImageMonitor`／`_problem`）。
- 有效性：`success`、`scene.valid` 為真；用到 arm1 座標時 `arm1_valid`，arm2 座標時 `arm2_valid`，用到 C 區時 `c_slots_valid`；否則回報失敗，任務停止。

欄位對應：

| 現有介面 | 來自 `EnvScene` |
|---|---|
| `zone().a_has_object` | `len(a_objects) > 0` |
| `zone().b_has_object` | `len(b_objects) > 0` |
| `zone().b_arm_clear` | 不由相機判斷：兩支手臂的關節回授都在 HOME（`motion.home_state`）。回授缺失或過期時為 false |
| `zone().c_object_count` | `c_occupied_count` |
| `pick_target()` | 從 `a_objects` 挑一顆（規則見下），用 `arm1_x/arm1_y`，z = 場地高度 + 瓶蓋高度（設定值） |
| `grid().occupied` | `c_occupied` |
| `verify_place(slot)` | `placed = c_occupied[slot-1]`；`order_ok` = 已佔用格位是否為 1..n 連續 |
| **新增** Arm 2 的 B 區吸取點 | `b_objects` 必須剛好 1 顆，用 `arm2_x/arm2_y` |

A 區挑選規則沿用舊 `get_pick_target` 的意思：可達範圍內、周圍淨空、離 arm1 基座最近的一顆；結果仍要通過 `Arm1Workflow._validated_target` 的 A 區範圍檢查。

### 7.5 工作流程改動

- Arm 1 放到 B 區仍用固定的 `b_place`。
- Arm 2 在 `RESERVE_SLOT` 前查詢 B 區瓶蓋座標，用它算 `above_b`／`at_b` 並納入 `PREFLIGHT` 可達檢查。座標必須落在 B 區範圍內，且離 `b_place` 不超過設定的容許距離，否則停止。
- 其他狀態機流程、B 區互鎖、journal 不變。

### 7.6 操作介面

- 相機區：目前開著的手臂鏡頭照常顯示；關閉的那一格顯示「輪流中，鏡頭關閉」而不是「無影像／故障」，切換中顯示「切換中」。
- 環境相機格顯示 `env_scene` 的標定結果（`coords_source`、`calib_check_mm`）。

### 7.7 標定閘門（設計者的決定）

- 環境相機不再經過 `dual_arm_vision_adapter` 的 `CalibrationMonitor`（它要求的 `env_camera.yaml` 紀錄格式不適用於 `env_scene` 的自我標定）。改以 `env_scene` 自身的結果把關：`scene.valid`、對應的 `armN_valid`、`c_slots_valid`，且 `coords_source` 必須是 `standard` 或 `measured`；`estimated` 一律拒絕。`armN_valid` 已包含 C 區 8 格比對誤差 ≤ 10 mm 的檢查。
- `env_scene_node` 開機時自動標定（上游行為）；需要重標時由人手動呼叫 `/vision/env_scene/calibrate`（C 格旁不可有瓶蓋，格內可以）。本次不在操作介面加標定按鈕，只顯示結果。

### 7.8 單鏡頭規則的範圍（設計者的決定）

- 適用全系統：任何啟動檔或操作介面設定都不會同時開兩顆手臂鏡頭。手臂鏡頭只做監控，不再需要 homography 標定，`vision_pkg` 的手臂鏡頭標定流程不再列入實機步驟。
- 切換節點啟動的子程序綁在自己的程序群組並設 parent-death signal；切換節點啟動時，若發現手臂鏡頭裝置仍被其他程序佔用，先回報並拒絕開另一顆，不自動殺不明程序。

## 8. 驗證

- 單元測試：`EnvSceneObserver` 的欄位對應與各種無效情況（假的 service 回應）；切換節點的「先關後開」順序、異常重啟只重啟該開的那顆（假的程序啟動器）。
- 上游 `env_scene` 測試在 `src/` 裡照樣通過（含四張實拍測試圖）。
- coordinator 與操作介面既有單元測試、`run_checks.sh` 對應層級通過；模擬兩物體搬運結果不變（模擬不走新來源）。
- Orin 現場（記錄到 `docs/evidence/`）：
  1. 環境相機 + 一顆手臂鏡頭同時串流，持續 10 分鐘不掉幀中斷。
  2. 手動改變 `active_arm` 來回切換 50 次，沒有任何一次出現 STREAMON 失敗（`No space left on device`）。
  3. `env_scene` 的 `calibrate` 與 `get_scene`：手臂在 HOME 時不遮擋 A/B/C 判斷。
  4. 用尺量瓶蓋位置，比對 A、B 區座標誤差。

## 9. 留給建造者決定

- 切換節點放在 `dual_arm_vision_adapter` 或另開小套件；程序啟動方式（`subprocess` 包 `ros2 run`，或其他）。
- `EnvSceneObserver` 是用 `env_scene` 的 armN 座標，還是用 world mm 再經 TF 轉換；前提是先核對 5. 的座標軸一致性並寫進文件。
- B 區吸取點離 `b_place` 的容許距離、HOME 判斷的回授新鮮度門檻，依量測或既有設定訂定並記錄來源。
- 閒置時預設開哪顆（本文件先定 arm1）與狀態 topic 的格式。
