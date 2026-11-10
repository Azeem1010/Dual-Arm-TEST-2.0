# 座標軸定義（OpenCV 端與手臂端共用）

更新：2026-11-10。狀態只使用 `PASS`、`FAIL`、`BLOCKED`、`NOT_RUN`。

> **實機量測與本文件的模擬配置相反。** 2026-11-10 的 H1（[evidence/hardware/](evidence/hardware/README.md)）顯示 A 區在手臂**自身右方**。下方「模擬模型」一節描述的仍是 commit `c7dfba3` 的遠側配置（A 在手臂左邊），模型尚未修改；是否依實測改模型由使用者決定（D0，[MODIFICATION_PLAN.md](MODIFICATION_PLAN.md) 第 2 節）。

## 實機配置

### 2026-11-10 實測（arm1，H1）

- 手臂底座在**遠離使用者**的長邊，面向使用者（俯視照片）。
- 從手臂底座面向場地時，**A 區在右邊**，C 區在左邊。使用者由左到右看到 **A | B | C**。
- arm1 是靠 A 區那支，軸心在 A/B 分界；arm2 軸心在 B/C 分界，兩軸心相距 200 mm。
- 軸心在靠手臂那條長邊的**板外約 10 mm**（口頭回報「大約」，未註明哪支手臂）。
- 板子短邊推算約 235 mm，尚未直接量；文件與 `env_vision.yaml` 寫 300 mm。
- C 區 8 格為 2 × 4，靠 arm2；格位編號的實際位置尚未確認。

```text
        手臂底座（遠離使用者側）
         arm1    arm2
   ┌───────┬───────┬───────┐
   │   A   │   B   │   C   │
   └───────┴───────┴───────┘
              使用者
```

現場貼的參考線（F：垂直長邊朝使用者，0 在各自軸心；L：沿長邊朝 B/C，0 在 F1 交點）與 `armN_base` 的 +x、+y 同向，但原點不是 `world`。

### 2026-11-09 口述（已被實測推翻）

- 使用者由左到右看到 C | B | A；從手臂底座面向場地時 A 區在左邊；C 區格位 1、2 靠近使用者。模擬模型目前仍依此配置。

## 視覺端座標系

| 座標系 | 原點 | +X | +Y | +Z | 單位 |
|---|---|---|---|---|---|
| 影像像素 (u, v) | 影像左上角 | 向右 | 向下 | — | px |
| A 區平面 `x_mm`、`y_mm`、`plane_x_mm`、`plane_y_mm` | A 區在影像中的左上角 | 向右（0–200） | 向下（0–300） | — | mm |
| 手臂 1 基座 `arm1_base` | 底座旋轉軸與場地頂面的交點 | 朝場地內（朝使用者） | 手臂面向場地時的左邊（C→A 方向） | 朝上 | m |
| 手臂 2 基座 `arm2_base` | 底座旋轉軸與場地頂面的交點 | 待確認，建議同手臂 1 | 待確認，建議同手臂 1 | 朝上 | m |
| 場地 / URDF `world` | 模擬世界原點，場地中心 | 使用者看到的左到右，C→B→A | 遠離使用者 | 朝上 | m |

- 像素座標以旋轉、去畸變後實際用來標定的影像為準。
- 模擬：`arm1_base` 中 A 區位於 **y > 0** 側。實測：A 區在 **y < 0** 側（與 `calibrate_caps` 預設相同）。
- `arm2_base` 的軸向在程式中沒有定義，上表是建議值，要由 OpenCV 端確認。

## 模擬模型

launch 載入的是 `src/dual_arm_description/urdf/dual_arm_cad.urdf.xacro`，由 `scripts/generate_cad_robot.py` 產生。`dual_arm.urdf.xacro` 沒有被 launch 使用，不要拿它判斷方向。

| 項目 | 值 |
|---|---|
| 手臂 1 底座 | `world` (0.10, +0.08725, 0)，yaw 180° |
| 手臂 2 底座 | `world` (-0.10, +0.08725, 0)，yaw 180° |
| j1 = 0 朝向 | `world` -Y，朝使用者 |
| C 區格位 | x = -0.1675 / -0.1325，y = -0.090 + 列 × 0.035，格位 1、2 在 y = -0.090 |
| 平台 | 原始 CAD 不變，安裝時以 y = 0 鏡射（繞 X 軸翻面） |

`0.08725` 沿用 CAD 的數值，不是實機量測值。

## 換算

`armN_base` 到 `armN_base_link` 是固定的 +90° yaw：

```text
x_link = -y_vision
y_link =  x_vision
z_link =  z_vision + 0.014（模擬的場地頂面高度）
```

`arm1_base` 到 `world`：

```text
x_world = x_base_origin + y_vision
y_world = y_base_origin - x_vision
```

`sim.launch.py` 已發布 `armN_base_link` → `armN_base` 的 static TF。實機沒有這個 TF，也還沒有把視覺目標送進 MoveIt 的 adapter。

## `calibrate_caps` 的使用限制

程式預設 `OUTER_EDGE_Y_MM = -200`，代表 A 區在 y < 0。這和 2026-11-10 實測的方向一致，但**與目前的模擬配置相反**；D0 決定前仍不可直接使用預設值。預設的「旋轉軸在板緣外 20 mm」與實測約 10 mm 不同，使用時以實測值輸入。下表是配合目前模擬配置的輸入方式。程式的換算是 `y = outer_edge_y + side`，不改程式時用下列方式輸入：

| 輸入 | 內容 |
|---|---|
| `front` | 瓶蓋中心到手臂底座那條長邊（遠離使用者）的距離，mm |
| `side` | 先量瓶蓋中心到 A 區外側短邊的距離 d，填 `200 - d`，mm |
| `--front-edge-x-mm` | 旋轉軸到手臂底座那條長邊的實測距離，mm |
| `--outer-edge-y-mm` | A/B 分界在基座 y 的實測位置，旋轉軸對齊分界時為 0，mm |

`calibrate_homography` 以 TCP 碰點時，輸出軸向會跟著 TCP 讀值的座標系。兩種工具不可混用不同軸向。

## 驗證狀態

| 項目 | 狀態 | 說明 |
|---|---|---|
| 模型配置轉換 | `PASS` | `test_cad_pose.py`，264 個元件；只代表模型符合本文件，不代表符合實機 |
| 模擬 static TF | `PASS` | `tf2_echo` 讀到平移 (0, 0, 0.014)、yaw 90° |
| 模擬兩物體搬運 | `PASS` | Gazebo 真值，不是視覺驅動 |
| 實機配置 | `FAIL` | 2026-11-10 俯視照片與 H1：A 區在手臂右方，與模型相反（arm1）；arm2 `NOT_RUN` |
| 底座到板緣距離 | `FAIL` | 實測軸心在板外約 10 mm（未讀到 mm），模型約在板內 63 mm |
| A/B 分界與旋轉軸是否對齊 | `PASS` | 實測 arm1 在 A/B、arm2 在 B/C 分界，相距 200 mm，與模型 x = ±0.10 一致；直尺 1 mm，口頭回報 |
| 場地短邊 | `FAIL` | 推算約 235 mm，模型與 `env_vision.yaml` 為 300 mm；尚未直接量 |
| 上述 `calibrate_caps` 輸入方式 | `NOT_RUN` | 依程式公式推導，尚未實際執行 |
| 手臂 2 軸向 | `NOT_RUN` | 待 OpenCV 端確認 |
| 視覺目標轉換（模擬） | `PASS` | `gateways/vision.py` 以 TF 轉到 `world`，evidence/wp7/ |
| 實機 `armN_base` TF | `NOT_RUN` | 需要實測，尚未發布 |

## 待釐清

[HOME_POSES.md](HOME_POSES.md) 記錄「Arm 1 在 raw 512 時朝 +Y」。在目前的 `world` 中手臂面向 -Y，需要確認當時的 +Y 指的是哪個座標系。現場附的一份來源不明的分析截圖主張這是 `arm1_base` 的 +Y（手臂左邊），並估計 arm1 底座正對場地約為 raw 196；兩者都不是本次實測，待 H1 量「底座正對場地時的 READ」確認。
