# 座標軸定義（OpenCV 端與手臂端共用）

更新：2026-11-09。實機配置來自使用者口述，尚未以照片或量測確認。狀態只使用 `PASS`、`FAIL`、`BLOCKED`、`NOT_RUN`。

## 實機配置

- 使用者站在場地長邊前，由左到右看到 C | B | A。
- 手臂底座在**遠離使用者**的長邊，面向使用者。
- 從手臂底座面向場地時，**A 區在左邊**。
- C 區格位 1、2 靠近使用者，也就是離手臂底座最遠。

```text
        手臂底座（遠離使用者側）
   ┌───────┬───────┬───────┐      +Y（遠離使用者）
   │   C   │   B   │   A   │       ↑
   └───────┴───────┴───────┘       └→ +X（C→B→A）
              使用者
```

## 視覺端座標系

| 座標系 | 原點 | +X | +Y | +Z | 單位 |
|---|---|---|---|---|---|
| 影像像素 (u, v) | 影像左上角 | 向右 | 向下 | — | px |
| A 區平面 `x_mm`、`y_mm`、`plane_x_mm`、`plane_y_mm` | A 區在影像中的左上角 | 向右（0–200） | 向下（0–300） | — | mm |
| 手臂 1 基座 `arm1_base` | 底座旋轉軸與場地頂面的交點 | 朝場地內（朝使用者） | 手臂面向場地時的左邊（C→A 方向） | 朝上 | m |
| 手臂 2 基座 `arm2_base` | 底座旋轉軸與場地頂面的交點 | 待確認，建議同手臂 1 | 待確認，建議同手臂 1 | 朝上 | m |
| 場地 / URDF `world` | 模擬世界原點，場地中心 | 使用者看到的左到右，C→B→A | 遠離使用者 | 朝上 | m |

- 像素座標以旋轉、去畸變後實際用來標定的影像為準。
- `arm1_base` 中 A 區位於 **y > 0** 側。
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

程式預設 `OUTER_EDGE_Y_MM = -200`，代表 A 區在 y < 0，**與實機相反，不可直接使用預設值**。程式的換算是 `y = outer_edge_y + side`，不改程式時用下列方式輸入：

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
| 實機配置 | `NOT_RUN` | 口述，尚無俯視照片或量測 |
| 底座到板緣距離 | `NOT_RUN` | `calibrate_caps` 預設旋轉軸在板緣外 20 mm，模擬中約在板內 63 mm，以實測為準 |
| A/B 分界與旋轉軸是否對齊 | `NOT_RUN` | 模型中 x = 0.10，與分界一致；實機未量 |
| 上述 `calibrate_caps` 輸入方式 | `NOT_RUN` | 依程式公式推導，尚未實際執行 |
| 手臂 2 軸向 | `NOT_RUN` | 待 OpenCV 端確認 |
| 實機 TF 與視覺目標 adapter | `NOT_RUN` | 尚未實作 |

## 待釐清

[HOME_POSES.md](HOME_POSES.md) 記錄「Arm 1 在 raw 512 時朝 +Y」。在目前的 `world` 中手臂面向 -Y，需要確認當時的 +Y 指的是哪個座標系。
