# 實機測試手冊

更新：2026-11-11。給現場操作的人照順序做。團隊成員都是同等層級：本手冊裡要「決定」的事，由現場做完安全檢查的成員決定，決定和理由寫進當天的紀錄，不需要另外找人授權。P0、H0、H1 已在 2026-11-10～11 實機執行過（[evidence/hardware/](evidence/hardware/README.md)），**其餘步驟都還沒有在實機上執行過（`NOT_RUN`）**，指令依目前的程式撰寫，遇到和手冊不符的情況要停下來記錄，不要自己改數值繼續。

Orin 的安裝與 ESP32 agent 的建置見 [ORIN_DEPLOYMENT.md](ORIN_DEPLOYMENT.md)，各級的驗收定位見 [TEST_PLAN.md](TEST_PLAN.md) 第 6 節。

## 1. 先看這張表

依序往下做，上一列沒通過就不要做下一列。

| 階段 | 做什麼 | 手臂會動嗎 | 目前能做嗎 |
|---|---|---|---|
| [P0](#p0-開始前準備) | 器材、人員、環境 | 否 | 可以 |
| [H0](#h0-唯讀連線) | 確認能和控制板通訊 | 否 | 可以 |
| [H1](#h1-扭力關閉手動確認方向) | 手扳確認方向，解決配置矛盾 | 由人手扳 | 可以 |
| [HOME 定位](#home-定位) | 讓手臂回 HOME，例如調整相機或 OpenCV | **會** | P0、H0 當天通過後隨時可以 |
| [V0](#v0-相機檢查) | 三顆相機接線與畫面方向 | 否 | 可以 |
| [E0](#e0-esp32-吸盤通電檢查) | 吸盤命令與時間 | 否，吸盤會作動 | 可以 |
| [H2](#h2-校正量測) | 量測校正值 | 由人手扳 | 要先訂門檻（D6） |
| [H3](#h3-單軸微動) | 單軸 ±10 raw，確認方向與穩態誤差 | **會** | H1 完成後；和 H2 互相驗證 |
| [H4](#h4-ros-關節空間小幅運動) | 透過 ROS 小幅動作 | **會** | 要先決定心跳來源（D8） |
| [H5](#h5-懸停與下降不接觸) | 移到目標上方，尺量誤差 | **會** | H4 通過後 |
| [H6～H8](#h6h8-取放與連續搬運) | 取放與連續搬運 | **會** | `BLOCKED`，程式還不允許 |

完成 H1 就先停下來，把結果交給開發者或 AI：模型與設定可能要先修正，後面的量測才有意義。

## 2. 絕對不能做的事

- 沒有實體急停，或急停沒有測過，不要讓馬達上扭力。
- 不要把模擬的數值（`runtime.json`、`config/sim/`、測試夾具）或估計值抄進實機校正檔。
- 不要用 `demo` 指令。`HOME`、`AX`、`TORQUE,...,1` 可以用，但要照 [HOME 定位](#home-定位) 或 [H3](#h3-單軸微動) 的步驟，急停手要在按鈕上。
- **不要手動執行 `ros2 control switch_controllers --activate`。** 一律用 `/safety/reset`。`safety_supervisor` 鎖定時會把手動啟動的控制器再停掉，但中間約有 0.3 秒的空窗（Mock 量測，C32）。
- 不要為了通過檢查而放寬限位、容差或門檻。
- 同一時間只有一個程式能開序列埠。換工具前先關掉另一個。
- 通訊逾時或出現 `ERR` 時不要反覆重送，先查原因。

## 3. 每個階段怎麼記錄

每個階段建一個資料夾 `docs/evidence/hardware/<日期>_<階段>/`，例如 `20261112_H1/`，放入下列內容。失敗的紀錄也要留，不要覆蓋。

```text
階段：
日期與時間：
操作者／記錄者：
程式版本（git rev-parse HEAD）：
實際輸入的指令與完整輸出：（可另存 output.txt）
量測工具與解析度：
照片檔名：
結果：PASS / FAIL / BLOCKED / NOT_RUN
異常或和手冊不同之處：
```

狀態只用這四個字。「看起來可以」不算 `PASS`。收到 ACK 也不代表手臂真的到位。

## 3.1 只用直尺與拍照的量測方法

現場只有直尺和手機時照這節做。原則：**記錄原始量測值**（長度、高度、照片上的點），角度由原始值計算，計算方式一併存檔，讓別人能重算。不要只寫算好的角度。

### 桌面座標

`world` 原點在場地中心，桌上不好直接標，所以用現場貼的兩組參考線量，換算交給開發者。2026-11-10 已經貼好，照用：

| 線 | 方向 | 0 點 |
|---|---|---|
| F1、F2 | 垂直泡棉板長邊，指向使用者 | 各自手臂的旋轉軸（F1 = Arm 1，F2 = Arm 2） |
| L | 沿靠手臂那條長邊，指向 B/C 側 | 和 F1 的交點 |

1. 膠帶被撕掉或移動過時，照上表重貼，拍俯視照說明怎麼貼的。F、L 和朝上構成右手座標系，軸向和 `armN_base` 的 +x、+y 相同。
2. 在膠帶上每 1 cm 做記號，量 TCP、底座、格位時直接讀。
3. 每筆讀值寫明是在 F1 還是 F2 上讀的。

### 讓直尺垂直

很多量測要把直尺立在桌面上。直尺底端貼桌面，靠著一個直角物（盒子、書本的角）立起，從兩個互相垂直的方向各看一次是否歪。把垂直立尺的照片留下一張當範例。

### 俯仰關節角（j2、j3、j4）：直尺法

1. 在連桿上選兩個點，最好是兩個關節的轉軸中心（螺絲或舵盤中心）。
2. 立尺量兩點到桌面的高度 `h1`、`h2`，再量兩點投影到桌面的水平距離 `d`。
3. 這段連桿相對桌面的仰角是 `atan2(h2 − h1, d)`。
4. 關節角是**相鄰兩段連桿的仰角差**，正負號依 URDF 的轉軸方向，由 AI 或開發者換算，換算式存檔。
5. 每段至少量兩次，差超過 2 mm 就重量。

連桿兩點相距約 10 cm 時，1 mm 誤差約等於 0.6°，比馬達一格 0.29° 粗。這是這套量具的極限，D6 門檻要考慮它。

### 俯仰關節角：拍照法（和直尺法擇一或互相驗證）

1. 手機放在手臂的側面，距離至少 50 cm，鏡頭正對手臂運動的平面。用 1× 鏡頭，**不要用 0.5× 廣角**，變形太大。
2. 桌面邊緣或桌面上的膠帶要在畫面中，作為水平參考；直尺貼著連桿放在畫面中，作為比例尺。
3. 在電腦上讀出照片中各點的像素座標（關節中心、桌面線上兩點），用 `atan2` 算角度。點的座標和計算腳本一起存檔。
4. 鏡頭沒有正對時角度會偏。同一姿態從反方向再拍一張，兩邊結果差超過 1° 就重拍。

### 底座轉角（j1）與旋轉軸：畫圓法

旋轉軸在馬達下方看不到，用眼睛對很難準。改成量「繞著軸轉的點」，由程式算出圓心：

1. 在底座會跟著 j1 轉動的支架上，用膠帶固定一根水平的細桿（吸管、竹籤），尖端伸出底座外，離軸心越遠越好（10 cm 以上）。**細桿要和手臂的正前方同方向**（從上方看，和上臂、吸盤在同一條線上），從上方拍一張照片確認。只轉 j1，j2～j4 不會影響這根桿子。
2. 在尖端下方的桌面貼白紙。扭力關閉，用手把 j1 轉到一個角度，在紙上點出尖端正下方的位置，同時輸入 `READ,armN` 記下 j1。
3. 換角度重複，至少 5 點，總共分布 90° 以上（例如 −60°、−30°、0°、30°、60°）。
4. 用直尺量每一點在 F、L 線上的讀值，填進 `src/dual_arm_coordinator/config/hardware/axis_circle_sheet.template.yaml` 的複本，一支手臂一份。
5. 執行：

   ```bash
   ros2 run dual_arm_coordinator fit_axis_circle <工作表.yaml> <報告.json>
   ```

   報告給出軸心的 F、L 座標與標準誤差、點的離散程度，有 READ 時還有 j1 方向和「尖端正對 +F（場地）時的 raw」。細桿和手臂正前方同方向時，這個 raw 就是手臂正對場地時的 j1；沒對齊時方向仍然正確，但這個 raw 會差一個固定角度。這份報告只是量測結果，不判定通過，也不會寫入任何校正檔。
6. 拍一張俯視照，看得到紙上的點和膠帶。

要量某個姿勢的 j1 角度時，用同一根桿子：尖端點的 `atan2(L − L軸心, F − F軸心)` 就是角度，正方向朝 +L（手臂的左邊）。

### TCP 位置與吸盤傾角

1. 吸盤末端正下方立尺，在桌面膠帶上讀 `x`、`y`，在尺上讀高度 `z`。兩個方向各看一次尺是否垂直。
2. 吸盤是否垂直朝下：從兩個互相垂直的方向各拍一張側視照，用拍照法量吸盤軸線和桌面的夾角。
3. 這種方法位置的誤差大約 ±2 mm，傾角約 ±1°，紀錄要寫明。

### E0 計時

用手機錄影，畫面同時拍到終端機（送出指令的時刻）和吸盤。逐格看影片，記下送出指令到吸穩、到釋放的時間。一般手機影片每格約 0.033 秒。每項至少量三次。

### 量具精度寫進紀錄

每個階段的紀錄要寫：直尺最小刻度、照片解析度與拍攝距離、估計誤差。**D6 門檻不能比量具能分辨的還小**，否則結果沒有意義；訂門檻時要考慮這點。門檻在量測前訂好，量完之後不要為了結果去調整。

## P0 開始前準備

**人員：** 至少兩人。一人只負責急停，手放在按鈕上；一人操作並記錄。

**器材：**

| 項目 | 用途 |
|---|---|
| 實體急停，能直接切斷馬達電源 | 必要，韌體沒有 STOP 也沒有 watchdog。不是量測工具，不能省 |
| 直尺（1 mm 刻度），最好 30 cm 以上 | H1、H2、H5 的長度、高度與角度，方法見 [3.1 節](#31-只用直尺與拍照的量測方法) |
| 手機相機 | 照片、量角度用的側視與俯視照、E0 計時錄影 |
| 紙膠帶、麥克筆、白紙 | 在桌上畫出原點與 X、Y 軸，標記點位 |
| 測試用瓶蓋 | H5 以後 |
| 工具軟體 RoboPlus 或 DYNAMIXEL Wizard | 讀取 Moving Speed。這是軟體，和量具無關；沒有的話 H3 `BLOCKED` |

傾角計、游標卡尺都不需要。有的話可以用，但紀錄要寫明用了什麼。

**每次開工前檢查：**

- [ ] 急停按下去，馬達電源確實斷開。放開後要能恢復。
- [ ] 手臂活動範圍內沒有人、線材和工具。
- [ ] 工作區的俯視照片，要看得到手臂底座、A、B、C 三區。第一次要拍。
- [ ] 手臂下方淨空。**CM-530 重置會立刻關閉扭力，手臂會往下掉。**
- [ ] 安裝完成（[ORIN_DEPLOYMENT.md](ORIN_DEPLOYMENT.md) 第 3 節）。Mock 確認能跑：`bash scripts/start_sim.sh mock`。

每個新終端都要先執行：

```bash
cd ~/projects/dual_arm_system/dual_arm_ws
source /opt/ros/jazzy/setup.bash
source install/setup.bash
unset ROS_DOMAIN_ID
```

實機一律用 ROS 預設的 domain 0（操作介面的 `hardware.ros_domain_id` 也是 0）。模擬用 43，終端機若曾 `export ROS_DOMAIN_ID=43` 或其他值，`unset` 後才看得到實機，也不會收到模擬的資料。

想用操作介面在旁邊看數值，另開終端執行 `ros2 run dual_arm_hmi hmi --monitor --hardware`。這個視窗只讀，不會下任何指令，也不開序列埠；H3～H5 的動作一律照本手冊用終端指令。

找到控制板的固定路徑，下面用 `<控制板>` 表示：

```bash
ls -l /dev/serial/by-id/
```

## H0 唯讀連線

**目的：** 確認電腦能和 CM-530 通訊，韌體是 v17。只會送 `VERSION`、`PING`、`GET_HOME`、`READ`。

```bash
ros2 run dual_arm_coordinator cm530_probe --port /dev/serial/by-id/<控制板>
```

| 看什麼 | 應該是 |
|---|---|
| `status` | `PASS` |
| `home.arm1` | `[90,567,712,825]` |
| `home.arm2` | `[590,567,712,825]` |
| `position` | 8 個數字都有，用手輕推手臂時會改變 |

**通過：** 上表都符合。把輸出存檔。

**停止：** 任何錯誤或逾時。不要反覆重跑。工具會回報 `error`，先檢查線材、供電、埠是否被占用。

## H1 扭力關閉手動確認方向

**目的：** 確認每支手臂的 j1、j2 方向與零點，以及 A 區在手臂哪一側（D0、D1）。2026-11-10 已做完 Arm 1：A 區在手臂右方、j1 方向 +1，模擬已依此修改；Arm 2 和 j2 的方向還沒確認。沒有這份結果，後面的校正和模型都可能是反的。

全程不發動作命令，並用韌體附的終端：

```bash
cd "third_party/CM530_ROS_BRIDGE/17 ROS to CM530 ver. dual arm"
python3 -m pip install -r requirements.txt
python3 manual_position_terminal.py --port /dev/serial/by-id/<控制板> --baud 57600
```

指令打在程式的提示符號後面，每次一筆，等回覆再送下一筆。Windows 也可以做，步驟相同，埠改成 `COM4` 這類名稱。

### 步驟

先對 arm1 做完，再對 arm2 做一次。

1. **用手扶住手臂。**輸入 `TORQUE,arm1,0`，等回覆 `OK,TORQUE,arm1,0`。
2. 輸入 `READ,arm1`，記下基準值。
3. 站在底座後方，面向手臂的前方。把底座往**手臂自身的右方**轉一小段，其他關節不動。
4. 輸入 `READ,arm1`，比較 j1：

   | 結果 | 記錄 |
   |---|---|
   | j1 變小 | 方向 +1 |
   | j1 變大 | 方向 −1 |
   | 沒變或不穩 | 無法確認，停下來檢查馬達 ID 對應 |

5. **記錄這個右轉是朝向 A 區還是 C 區，並拍照。**這一項解決 D0。
6. 轉回基準。先把 j2 扶到**往場地側前傾約 30°**（末端朝使用者），`READ,arm1`；再往後扳回垂直方向約 15°，`READ,arm1`。記錄讀值變大或變小，並寫明是「從前傾往垂直扳」（D1）。不要從接近垂直的姿勢開始：從垂直往前或往後轉，末端都會變低，看不出方向。
7. 扶到手臂完全伸直，`READ,arm1`，拍照並記錄「伸直」的實際方向，比如垂直朝上。先前的說法是全部 raw 512，要確認（D1）。

馬達 ID：arm1 的 j1～j4 是 17、3、2、15；arm2 是 12、1、8、16。

### 同時確認

| 項目 | 方法 | 記錄 |
|---|---|---|
| Moving Speed | 關掉終端，用 RoboPlus 或 DYNAMIXEL Wizard 讀 8 顆馬達的 register 32。**值為 0 代表最高速** | 8 個數值 |
| 馬達 ID 15 的線材 | 目視，手動轉動時 READ 要連續變化 | 正常／異常 |
| 底座實際位置 | 畫圓法（3.1 節）求軸心，再讀到 A、B、C 三區邊界的距離 | 工作表、`fit_axis_circle` 報告與照片 |

輸入 `q` 離開終端。**離開不會改變扭力狀態。**

### 2026-11-10 之後還要補的項目

第一次現場已做完 Arm 1 的方向（[evidence/hardware/](evidence/hardware/README.md)）。下次到現場，H1 要補下列項目，每項都附原始值與照片：

| 項目 | 方法 | 用途 |
|---|---|---|
| Arm 2 的 H1 全部步驟 | 上面的步驟 1～7，`arm1` 換成 `arm2` | Arm 2 的 j1 方向目前只是假設 |
| Arm 1 的 j2 方向重做 | 步驟 6 的新做法 | 上次從接近垂直開始，方向無法判定 |
| 兩支手臂的旋轉軸位置 | 3.1 節畫圓法，一支手臂一份工作表 | 取代「板外約 1 cm」的目測值 |
| 兩支手臂底座正對場地時的 j1 | 畫圓法報告的 `raw_facing_field`；或尖端對準 F 線時 `READ` | 取代 HOME_POSES.md 的暫定值 192.3 |
| 泡棉板短邊 | 直尺直接量，在 F1、F2 各量一次 | 目前只是推算的 235 mm，文件寫 300 mm |
| C 區 8 個格位 | 每格中心在 F2、L 上的讀值；格位上若有編號標記拍照，沒有就記錄「離使用者最近、靠 B 區」的是哪一格 | 模擬假設格位 1、2 最靠近使用者，要確認 |
| C 區格位示教 | Arm 2 扭力關閉，用手把吸盤對準每格中心、離表面約 5 mm，`READ,arm2` | 直接得到關節目標，不受軸心量測誤差影響 |
| B 區交接點示教 | 兩支手臂各一次，吸盤對準 B 區中央 | 同上 |
| Moving Speed、馬達 ID 15 線材 | 上表 | 上次未做 |

示教時手臂扭力是關的，要一直扶著。示教的 READ 只是量測資料，**不可以直接填進 `calibration.yaml` 或任何實機設定**，由開發端換算、和校正結果核對後才使用。

**通過：** 兩支手臂的方向都有明確結論，並有照片。

**接下來：** 把紀錄交給開發者或 AI，由他們比對模擬配置。2026-11-10 起模擬是「A 區在手臂右方、j1 方向 +1」（arm1 實測）。如果 arm2 或重測的結果和這個配置不同，要先修模型與 `runtime.json` 並重跑模擬，才能往下。

## HOME 定位

**目的：** 讓手臂用韌體的 `HOME` 回到預設姿勢並保持住，例如兩支手臂都回 HOME 之後調整相機、OpenCV 或場地。這不是驗收階段，現場需要時就可以做，不需要另外授權。

**出力前檢查（每次上扭力前都要）：**

- [ ] 當天 P0 做過，急停按下能直接切斷馬達電源。
- [ ] 一人手放在急停上，只負責急停。
- [ ] 手臂活動範圍淨空，另一支手臂不在這支的路徑上。
- [ ] 當天 H0 通過，序列埠只有一個程式開著。

**為什麼要先扶到 HOME 附近：** 韌體的 `HOME` 只寫入目標位置，不設定速度；第 17 版也不設定 Moving Speed（register 32）。AX-12A 上電後這個值通常是 0，代表最高速。手臂離 HOME 很遠時，上扭力那一下會用最高速衝過去。先用手扶到附近，移動量小，就算是最高速也沒有危險。

若已經用 RoboPlus 或 DYNAMIXEL Wizard 把 8 顆的 Moving Speed 設成較低的值（例如 100），可以跳過步驟 2。這個暫存器在斷電後會恢復，重新上電要再設，並記錄設了多少。

**步驟（一次一支手臂，先 arm1 再 arm2）：**

1. 用手扶住手臂。扭力是開的話，先輸入 `TORQUE,arm1,0`。
2. 關掉韌體終端，用唯讀的擺位輔助把手臂扶到 HOME 附近（只送 `READ`，不會讓馬達出力）：

   ```bash
   python3 docs/evidence/hardware/20261111_H1/pose_guide.py --port /dev/serial/by-id/<控制板> \
     --arm arm1 --target 90,567,712,825 --tol 20 --log home_arm1_<時間>.csv
   ```

   四軸都顯示 `OK` 後保持姿勢，按 Ctrl+C。arm2 的目標是 `590,567,712,825`。也可以在韌體終端反覆 `READ,arm1` 對照。
3. 繼續扶著，重新開韌體終端（H1 的指令），輸入 `HOME,arm1`，等 `OK` 回覆。扭力是關的，這一步只寫入目標，手臂不會動。
4. 輸入 `TORQUE,arm1,1`。手臂會小幅移到 HOME 並保持住，手可以慢慢放開。**突然大幅跳動、抖個不停或有異音，立刻按急停。**
5. `READ,arm1`，記錄讀值和 HOME 的差（到位誤差）。
6. arm2 照做一次。兩支都到 HOME 後，就可以開始調整相機等工作。
7. 做完後，手扶住手臂，`TORQUE,arm1,0`、`TORQUE,arm2,0`。

**注意：**

- HOME 是預設的姿勢，不是避碰路徑。兩支手臂在 HOME 的碰撞只在模擬檢查過，實機沒有驗證，所以一次動一支並看著。
- 保持扭力時，馬達會持續出力發熱。不要長時間放著不管，摸起來很燙就先關扭力。
- CM-530 重置或斷電會立刻關閉扭力，手臂會往下掉。調整時手不要伸到手臂正下方。
- 紀錄放在 `docs/evidence/hardware/<日期>_HOME/`：出力前檢查、指令與回覆、到位讀值、有無異常。

## V0 相機檢查

**目的：** 確認三顆相機對應正確、畫面方向正確。這裡不做校正。

```bash
ls -l /dev/v4l/by-id/
ros2 launch vision_pkg vision.launch.py env_cam_device:=/dev/v4l/by-id/<環境> arm1_cam_device:=/dev/v4l/by-id/<手臂1> arm2_cam_device:=/dev/v4l/by-id/<手臂2>
```

把路徑填到 `src/vision_pkg/config/cameras.yaml`，以後就不用每次打。用操作介面啟動實機時，也可以填在 `~/.ros/dual_arm_hmi/profiles.yaml` 的 `hardware.env_cam_device` 等欄位（優先於 cameras.yaml）。

| 看什麼 | 應該是 |
|---|---|
| 三個畫面都有影像 | 名稱和實際相機對得上 |
| 畫面方向 | 上下左右正確。手臂相機 1 的 `rotate: 180` 來自 2026-11-06，要重新確認 |
| 物件偵測 | 只是參考，偵測到不代表已校正 |

**通過：** 三顆都正確，存截圖。改過 `rotate` 的話，該相機的校正都要重做。

實體相機的內參與平面校正，在相機固定好之後依 [VISION_CALIBRATION.md](VISION_CALIBRATION.md) 進行，**校正工具 `calibrate_caps` 的預設邊界值和實際配置不符**，先看 [COORDINATE_FRAMES.md](COORDINATE_FRAMES.md)。

## E0 ESP32 吸盤通電檢查

**目的：** 確認吸盤命令對應哪支手臂、吸取要等多久。手臂不要靠近工件，不要啟動 Coordinator。

依 [ORIN_DEPLOYMENT.md](ORIN_DEPLOYMENT.md) 第 6.1 節：先開 agent，再按 ESP32 的 EN 鍵，然後逐一作動。

| 要記錄 | 填到 |
|---|---|
| ESP32 上電時泵和閥有沒有誤動作 | 紀錄，異常時先修接線或韌體 |
| 指令 1～4 分別對應哪支手臂、吸取或釋放 | `gripper.esp32_modules` |
| 實測吸穩要幾秒（手機錄影計時，見 3.1 節） | `gripper.vacuum_settle_s` |
| 回音時間 | `gripper.esp32_echo_timeout_s` |

指令 `0` 會全部關閉，持有中的物件會掉落。韌體沒有真空感測，吸住與否都靠人確認。

## H2 校正量測

**開始前：** 先訂好驗收門檻（D6）：定位誤差、傾角誤差。現場成員可以訂，寫進紀錄。工具沒有預設值，也不能量完才訂。

1. 複製 `src/dual_arm_coordinator/config/hardware/calibration_worksheet.template.yaml` 成自己的工作表，填入門檻。
2. 扭力關閉，每個關節擺至少三個姿態（只有直尺時建議五個，涵蓋活動範圍兩端與中間），依 [3.1 節](#31-只用直尺與拍照的量測方法)用直尺或照片量角度，同時 `READ`，填入 `samples`。原始量測值與換算過程另外存檔。
3. 另外量至少三個**沒用在上一步**的姿態，依 3.1 節用直尺量 TCP 位置、用照片量吸盤傾角，填入 `verification`。不要抄 FK 的計算結果。
4. 檢查：

   ```bash
   ros2 run dual_arm_coordinator check_calibration_sheet <工作表.yaml>
   ```

5. 通過後，**由人工**把候選值填進 `src/cm530_hardware/config/calibration.yaml`。工具不會寫入。`status`、`hardware_use_allowed`、`moving_speed_verified` 先維持原樣。
6. 用唯讀模式核對，這個模式不會送動作：

   ```bash
   ros2 launch dual_arm_bringup hardware.launch.py port:=/dev/serial/by-id/<控制板> calibration_file:=$PWD/src/cm530_hardware/config/calibration.yaml
   ros2 topic echo /joint_states
   ros2 topic hz /joint_states
   ```

   用手扳動，確認每個關節的方向和角度都對。讓它連續運作一段時間，記錄 `/joint_states` 的頻率和有無通訊錯誤。

**通過：** 工具回報 `PASS`，`/joint_states` 方向全對，沒有通訊錯誤。

**接著填寫，全部要是實測值：**

| 檔案 | 內容 |
|---|---|
| `src/cm530_hardware/config/calibration.yaml` | `status: PASS`、`evidence_kind: physical`、`hardware_use_allowed: true`、`moving_speed_verified: true`（H1 確認過才能填）、`max_step_raw` |
| `controllers_hardware.template.yaml` 的複本，例如 `controllers_measured.yaml` | `goal`、`goal_time`、`stopped_velocity_tolerance`。先前紀錄 j2 穩態誤差達 +7 raw，不能用夾具的 0.02 rad |
| `src/dual_arm_coordinator/config/hardware/coordinator.yaml` 的複本，例如 `coordinator_measured.yaml` | 幾何、速度、逾時 |

速度比例從 `0.05` 開始。檢查任務設定（不會動作）：

```bash
ros2 run dual_arm_coordinator check_task_config coordinator_measured.yaml
```

手臂休息的姿態要在限位內，否則啟用時會被拒絕。不要放寬限位，用手擺回去。

## H3 單軸微動

**馬達會出力。** 現場成員做完 [HOME 定位](#home-定位) 的出力前檢查就可以做，急停手要在按鈕上。HOLD 以目前位置為目標，所以上扭力時不會大幅移動；之後每次只改 10 raw，Moving Speed 是 0（最高速）時移動量也很小。Moving Speed 有讀的話一起記錄。

用韌體終端，一次只動一顆馬達，10 raw 約 2.9°。

1. 手扶住手臂，`READ,arm1`，記下四個值當基準，例如 `a,b,c,d`。
2. `HOLD,arm1`。這會把目前位置寫成目標，不會上扭力。
3. `TORQUE,arm1,1`。手臂應該維持原姿態，手可以慢慢放開。**如果突然跳動，立刻按急停。**
4. `AX,arm1,<a+10>,b,c,d`，觀察方向，`READ,arm1` 記錄。
5. `AX,arm1,a,b,c,d` 回基準。
6. `AX,arm1,<a-10>,b,c,d`，再回基準。
7. 對 j2、j3、j4 重複，每次只改一個數字。
8. 手扶住手臂，`TORQUE,arm1,0`。
9. arm2 重複相同步驟，用 `arm2`。

**通過：** 每顆馬達的運動方向都和 H1（有校正時也和校正）一致，READ 的變化量合理，沒有異常聲響。

**立即按急停：** 方向相反、持續抖動、異常聲音、手臂往下掉。

## H4 ROS 關節空間小幅運動

**前提：** 要先決定急停心跳來源（D8）。`safety_supervisor` 收不到 `/safety/estop` 時會鎖定，目前沒有實體心跳節點。團隊如果決定先用手動發布，要清楚它**只代表終端還活著，不會反映急停是否被按下**，實體急停必須能直接斷電，而且要記錄這個決定。

**順序很重要**，以下順序已在 Mock Serial 驗證（evidence/safety_order/），不能對調：

```bash
# 終端 1
ros2 launch dual_arm_bringup hardware.launch.py port:=/dev/serial/by-id/<控制板> \
  calibration_file:=$PWD/src/cm530_hardware/config/calibration.yaml \
  enable_motion:=true controllers_file:=/絕對路徑/controllers_measured.yaml
```

```bash
# 終端 2：心跳來源要持續發布，data false 代表沒有急停
```

```bash
# 終端 3：先讓硬體 active（此時上扭力），再解除鎖定（會啟動控制器）
ros2 topic echo --once /safety/status
ros2 control set_hardware_component_state DualArmSystem active
ros2 service call /safety/reset std_srvs/srv/Trigger '{}'
ros2 control list_controllers
```

`arm1_controller`、`arm2_controller` 要是 `active`，`/safety/status` 的 `latched` 要是 `false`。

只做目前姿態附近的小幅運動，先從 arm1 開始。`/joint_states` 讀目前值後，只改一個關節，加減不超過 0.05 rad。`time_from_start` 依 0.05 倍速計算，移動 0.05 rad 至少 2 秒，第一次建議再放慢：

```bash
ros2 action send_goal /arm1_controller/follow_joint_trajectory control_msgs/action/FollowJointTrajectory \
  "{trajectory: {joint_names: [arm1_arm_shoulder_pan_joint, arm1_arm_shoulder_lift_joint, arm1_arm_elbow_flex_joint, arm1_arm_wrist_flex_joint], points: [{positions: [<j1>, <j2>, <j3>, <j4>], time_from_start: {sec: 10}}]}}"
```

**通過：** 動作方向正確，`/joint_states` 到位，誤差在實測容差內。

**再測一次安全監控：** 停掉心跳，確認控制器變成 `inactive`、手臂停住。Mock 量到約 2.7 秒。這一項要在手臂靜止時測。

## H5 懸停與下降不接觸

**目的：** 確認 TCP 真的到達算出來的位置。移動目標用 `--frame world`，因為實機的 `arm1_base` TF 還不存在。

先只規劃，不會動作：

```bash
ros2 run dual_arm_coordinator manual_xy --arm arm1 --frame world --x <X> --y <Y> \
  --config /絕對路徑/coordinator_measured.yaml \
  --calibration $PWD/src/cm530_hardware/config/calibration.yaml
```

看輸出的 `target_world_m` 是不是你預期的位置，再加上 `--execute`。

1. 到達後用尺量 TCP 實際位置，和 `target_world_m` 比較。
2. 確認吸盤垂直朝下。
3. 下降測試：複製一份設定，只把 `heights.approach_z_m` 調低一點，再執行。每次降一小段，每次都尺量剩餘高度。必須維持 `contact < release < approach`。**不要接觸工件或桌面。**
4. 對 A、B 區和不同位置重複，arm2 也要做。

**通過：** 誤差達到 D6 的門檻，高度餘裕足夠。

## H6～H8 取放與連續搬運

**目前 `BLOCKED`，`coordinator_node` 會拒絕以實機模式啟動。** 需要開發者先完成：

| 需要什麼 | 說明 |
|---|---|
| 急停心跳節點（D8） | 接上實體急停 |
| 實機 TF 與硬體 `frame_id`（C20） | 視覺座標要轉到 `world` |
| 實機的區域與格位判斷（D7） | 目前模擬只驗證到取料點 |
| 三相機實體校正 | [VISION_CALIBRATION.md](VISION_CALIBRATION.md) |
| 移除 `coordinator_node.py` 的拒絕條件 | 上面都完成才可以 |

完成後的流程，每級都要通過才能下一級，每一步吸盤結果都由操作員確認：

| 級 | 內容 | 通過條件 |
|---|---|---|
| H6 | 單件 A→B，人工確認吸盤 | 吸放成功，場景一致 |
| H7 | arm2 單件 B→C，然後雙臂 A→B→C | `verify_place` 通過，互鎖與復歸正常 |
| H8 | 連續八件，逐步提速 | 達到 D6 的成功率門檻，並先處理 D3 的可達性 |

```bash
ros2 run dual_arm_coordinator operator_console start
ros2 run dual_arm_coordinator operator_console status
ros2 run dual_arm_coordinator operator_console confirm --success
ros2 run dual_arm_coordinator operator_console confirm --failed --message "瓶蓋沒有吸住"
```

目前模型只有 cap_3～6 可達、格位 1 搆不到，八件搬運要等 D3。

## 4. 發生狀況時

| 狀況 | 處理 |
|---|---|
| 手臂動作異常 | **按實體急停**，不要先去打指令 |
| 安全監控鎖定 | `ros2 topic echo --once /safety/status` 查原因，排除後 `/safety/reset` |
| 任務 FAULT | `operator_console status` 查原因，手動清空吸盤與 B 區、手臂回 HOME，再 `operator_console recover --cleared` |
| 序列埠錯誤或逾時 | 驅動會鎖定，不會重送。查線材，重啟驅動，從 H0 開始 |
| `ERR,DXL_TIMEOUT` | 檢查該馬達的線材與供電 |
| `Configuration refused` | `calibration.yaml` 有欄位留空或內容不正確 |
| `Motion refused` | 放行欄位沒有全部滿足，見 H2 的表 |
| 找不到 `/dev/serial/by-id/` | 重新插拔，帳號要在 `dialout` 群組並重新登入 |

## 5. 做完之後

1. 紀錄放進 `docs/evidence/hardware/`。
2. 在 [PROGRESS.md](PROGRESS.md)、[TEST_REPORT.md](TEST_REPORT.md)、[RESUME.md](RESUME.md) 寫上結果，通過或失敗都要。
3. 待決定事項（D0～D8）的答案，更新到 [MODIFICATION_PLAN.md](MODIFICATION_PLAN.md) 第 2 節。
