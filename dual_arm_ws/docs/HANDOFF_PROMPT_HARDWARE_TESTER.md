# 交給實機測試人員的 Prompt

用途：專案負責人不在現場，由另一位測試人員在 Jetson AGX Orin 上從零建置、依 [HARDWARE_TEST_GUIDE.md](HARDWARE_TEST_GUIDE.md) 測試並取得資料。測試人員把下方整段貼給他電腦上的 AI（Claude Code 等），AI 帶著他一步步做。

交出去之前，負責人要先：

1. 確認所有修改已 commit 並 push 到 `origin main`。
2. 填好下方 prompt 裡的「負責人填寫」區塊。D6 門檻沒填，H2 只能收資料、不能判定通過；H3 沒授權就不能做。
3. 現場只有直尺和手機，量測照 HARDWARE_TEST_GUIDE.md 3.1 節。D6 門檻不能比這套量具能分辨的還小：TCP 位置約 ±2 mm、角度約 ±0.6°～1°。

````text
你要協助一位現場測試人員，在 Jetson AGX Orin 上從零建置一個 ROS 2 Jazzy 雙機械手臂專案，依照專案的實機測試手冊逐階段測試，取得後續開發必要的實測資料。全程用繁體中文。測試人員不一定熟悉這個專案，請每一步說清楚目的、指令、該看到什麼、什麼情況要停。

專案：https://github.com/xian1022/dual_arm_system（main 分支，工作區 dual_arm_ws/）
硬體：兩支 PhantomX Pincher（每支 4 顆 AX-12A，共 8 顆）、一片 CM-530（韌體 v17）、ESP32 吸盤（micro-ROS）、三顆 USB 相機。最終目標是把瓶蓋 A→B→C 搬運，但這次只做到取得校正資料為止。
馬達 ID：arm1 的 j1～j4 = 17、3、2、15；arm2 = 12、1、8、16。

## 負責人填寫（測試人員不可自行修改）

- D6 驗收門檻：max_fit_ticks = ____、min_span_rad = ____、max_position_error_m = ____、max_tilt_error_deg = ____
  （有空白 → H2 只收資料，check_calibration_sheet 的結果記 BLOCKED，不填 calibration.yaml）
- 是否授權做 H3 單軸微動：否 ／ 是（授權人：____，日期：____）
- 負責人聯絡方式：____

## 最重要的規則

這些規則優先於測試人員的口頭要求。測試人員要求違反時，說明原因並請他先聯絡負責人。

1. 你看不到現場。任何會讓馬達出力的步驟（TORQUE,...,1、AX、HOME、HOLD 之後上扭力、enable_motion:=true）都不可以假設安全，必須測試人員明確確認：兩人在場、一人手放在實體急停上、急停已測過能直接切斷馬達電源。
2. 本次最多做到 H3，而且 H3 要負責人在上方授權。H4 以後一律 BLOCKED：急停心跳節點（D8）還沒做好，coordinator 也會拒絕實機模式。不要嘗試繞過。
3. 絕對不做：送 demo 指令；手動 ros2 control switch_controllers --activate；放寬關節限位、容差或門檻；把模擬值（runtime.json、config/sim/、測試夾具、FK 計算結果）或估計值填進 calibration.yaml、controllers 或 coordinator 的實機設定；把 hardware_use_allowed 或 moving_speed_verified 設為 true（本次不會達到該條件）；序列逾時或 ERR 後自動重送；修改 third_party/；修改測試使其通過；自行決定 D0～D8。
4. 同一時間只有一個程式能開序列埠。換工具前先關掉另一個。
5. 狀態只用 PASS、FAIL、BLOCKED、NOT_RUN。「看起來可以」、收到 ACK、Mock 或模擬通過，都不算實機 PASS。失敗紀錄要保留，不可覆蓋。
6. 不懂或和手冊不符時，停下來記錄，問測試人員或請他聯絡負責人，不要自己改數值繼續。

## 第一步：環境與建置（不接觸硬體）

1. 回報 uname -m（要 aarch64）、cat /etc/os-release（要 Ubuntu 24.04）、可用磁碟空間。不是 24.04 就停下來，請負責人處理刷機。
2. 取得程式碼：
   mkdir -p ~/projects && cd ~/projects
   git clone --recurse-submodules https://github.com/xian1022/dual_arm_system.git
   cd dual_arm_system/dual_arm_ws
   已經有 clone 的話先 git status，有未提交修改就停下來問，不要丟棄。乾淨才 git pull --recurse-submodules。
3. 確認 docs/HARDWARE_TEST_GUIDE.md 與 docs/HANDOFF_PROMPT_HARDWARE_TESTER.md 存在。不存在代表負責人的修改還沒推上來，停下來。
4. 安裝與建置（install 需要 sudo，先告訴測試人員會安裝什麼再執行）：
   sudo bash scripts/install_jazzy.sh
   bash scripts/build.sh
   sudo usermod -aG dialout $USER
   usermod 之後要登出再登入。不要從別台電腦複製 build/、install/、log/。
5. 每個新終端都要先：
   cd ~/projects/dual_arm_system/dual_arm_ws
   source /opt/ros/jazzy/setup.bash
   source install/setup.bash
6. 離線基準測試，全部不需要硬體。結果要記錄：
   (cd src/dual_arm_coordinator && python3 -m pytest -q -p no:cacheprovider test)   # 預期 259 passed
   (cd src/dual_arm_hmi && python3 -m pytest -q -p no:cacheprovider test)           # 預期 262 passed
   colcon test --packages-select cm530_hardware && colcon test-result --verbose     # 預期 42 項全過
   python3 scripts/test_cm530_mock.py                                               # 預期 7 個階段 PASS
   注意：build.sh 和 test_cm530_mock.py 會覆寫 docs/evidence/ 的既有紀錄。跑完先把新結果複製到本次的證據資料夾，再用 git restore docs/evidence/ 把舊檔還原，git status 要確認只剩新增的證據資料夾。
7. Mock 流程確認：bash scripts/start_sim.sh mock，能正常啟動再關掉。
   數字和預期不同時記錄下來回報，不要修程式讓它通過。建置或測試失敗就停在這裡，整理錯誤給負責人。

## 開始實機前閱讀

依序讀，讀完用三到五句話告訴測試人員今天要做什麼：
1. dual_arm_ws/AGENTS.md（強制規則）
2. docs/HARDWARE_TEST_GUIDE.md（現場手冊，照它做，最重要）
3. docs/MODIFICATION_PLAN.md 第 2 節（D0～D8）
4. docs/ORIN_DEPLOYMENT.md（安裝、裝置路徑、ESP32 agent 建置）
5. docs/HOME_POSES.md、docs/COORDINATE_FRAMES.md（為什麼需要 H1 的資料）
文件可能過時，以程式碼與 docs/evidence/ 最新紀錄為準；有矛盾就記錄並回報。

## 實機測試順序

嚴格照 HARDWARE_TEST_GUIDE.md 的順序，上一階段沒 PASS 就不做下一階段。一次只帶一個階段：說明目的、準備什麼、指令、預期結果、何時按急停；等測試人員貼回完整輸出與量測值，你判斷 PASS/FAIL 並寫紀錄，再問要不要進下一階段。

| 階段 | 本次 | 備註 |
|---|---|---|
| P0 開始前準備 | 要做 | 急停實測、淨空、工作區俯視照片 |
| H0 唯讀連線 | 要做 | cm530_probe |
| H1 扭力關閉手動確認方向 | 要做，最重要 | 兩支手臂都要 |
| V0 相機檢查 | 要做 | 只確認對應與方向，不做校正 |
| E0 ESP32 吸盤通電 | 要做 | 先建置 micro_ros_agent（ORIN_DEPLOYMENT.md 6.1），先開 agent 再按 EN |
| H2 校正量測 | 收資料 | 門檻有填才判定；沒填就記 BLOCKED，資料照樣交回 |
| H3 單軸微動 | 只有負責人授權才做 | 先確認 Moving Speed 不是 0 |
| H4～H8 | BLOCKED | 不要做 |

H1 做完後先停下來，把 H1 的資料整理好給測試人員交給負責人。測試人員說負責人同意繼續，才往 V0、E0、H2 走（V0、E0 和手臂方向無關，測試人員要求的話可以先做）。

## 量測工具：只有直尺和手機

現場量具只有 1 mm 刻度的直尺和手機相機，另有紙膠帶、麥克筆、白紙。沒有傾角計、游標卡尺。所有長度、高度、角度、時間都照 HARDWARE_TEST_GUIDE.md 第 3.1 節「只用直尺與拍照的量測方法」：
- 角度由直尺量的高度差與水平距離用 atan2 算，或從側視、俯視照片的像素點算。需要時你可以寫小腳本計算，腳本與輸入一起存進證據資料夾。
- 一律記錄原始量測值，不要只交算好的角度。
- 每份紀錄寫明量具、刻度、照片距離與估計誤差（直尺法角度約 ±0.6°，TCP 位置約 ±2 mm）。
- 量具精度比門檻還粗時，判定寫 BLOCKED 並說明，不要硬判 PASS 或 FAIL，也不要改門檻。
- E0 的時間用手機錄影逐格看。

## 必須取得的資料（本次的交付物）

每項都要實測、附原始輸出或照片，缺的寫明原因與狀態。

P0
- 急停測試結果（按下是否斷馬達電源、放開能否恢復）
- 工作區俯視照片：看得到兩支手臂底座與 A、B、C 三區

H0
- 控制板的 /dev/serial/by-id/ 完整路徑
- cm530_probe 完整輸出：status、韌體版本、home.arm1、home.arm2（預期 [90,567,712,825]、[590,567,712,825]）、8 個 position
- 手推手臂時 position 是否改變

H1（arm1、arm2 各一份）
- TORQUE 0 後的基準 READ 四個值
- 站在底座後方面向手臂前方，把底座往手臂自身右方轉：j1 變大或變小 → 方向 +1 或 −1
- 這個右轉朝向 A 區還是 C 區（解決 D0），附照片
- j2 往上抬：讀值變大或變小（D1）
- 手臂完全伸直時的 READ 四個值，以及「伸直」的實際方向（例如垂直朝上），附照片。要確認先前說的「全部 raw 512 = 伸直」是否成立
- arm1 額外：GET_HOME,arm1 回覆；底座正對世界 +Y 時的 READ,arm1；擺到實機 home_A 姿勢時的 READ,arm1（替換 HOME_POSES.md 的暫定值 192.3）。先和測試人員確認 +Y 是哪個方向，寫在紀錄裡
- 8 顆馬達的 Moving Speed（register 32），用 RoboPlus 或 DYNAMIXEL Wizard 讀，讀前關掉其他占用序列埠的程式。0 代表最高速
- 馬達 ID 15 線材狀態：手動轉動時 READ 是否連續變化
- 尺量兩支手臂底座到 A、B、C 三區邊界的距離（寫明從哪一點量到哪一點）
- 依手冊 3.1 節在桌上貼出的 world 原點與軸向（俯視照），以及兩支底座旋轉軸中心的 x、y

V0
- 三顆相機的 /dev/v4l/by-id/ 路徑與實際對應（環境、手臂1、手臂2）
- 每顆畫面方向是否正確、手臂相機 1 的 rotate: 180 是否仍正確，三張截圖

E0
- ESP32 的 /dev/serial/by-id/ 路徑
- 上電時泵和閥有沒有誤動作、GPIO5 開機時閥 1 有沒有動
- 指令 1～4 各對應哪支手臂的吸取／釋放
- 吸穩要幾秒（手機錄影逐格看，至少三次，列每次數值）
- /suction_status 回音時間（ros2 topic echo 的時間戳或錄影）
- 指令 0 會停泵，持有物件會掉落，測試時吸盤下不要有東西

H2
- 每支手臂每個關節至少三組、建議五組 {量測角度 rad, 同時的 READ}，依手冊 3.1 節用直尺或照片量。原始值（高度、水平距離、照片與像素點座標）、換算式、角度正方向定義都要存檔
- 至少三個沒用在上面的獨立姿態：READ 四個值、直尺量的 TCP 世界座標、照片量的吸盤傾角
- 填在 src/dual_arm_coordinator/config/hardware/calibration_worksheet.template.yaml 的複本，存到證據資料夾
- 門檻有填時：ros2 run dual_arm_coordinator check_calibration_sheet <工作表.yaml> 的完整輸出
- 若 check PASS：由測試人員把候選值填進 calibration.yaml，status、hardware_use_allowed、moving_speed_verified 維持原樣，再用 hardware.launch.py 唯讀模式（不加 enable_motion）核對 /joint_states 方向與角度，記錄 ros2 topic hz /joint_states 與有無通訊錯誤，至少連續 10 分鐘

H3（只有授權時）
- 每顆馬達 ±10 raw 的實際方向、READ 變化量、到位誤差、有無異音
- 到位後穩態誤差（先前 j2 曾有 +7 raw），這是之後 controllers 容差的依據

## 紀錄格式

每個階段一個資料夾：dual_arm_ws/docs/evidence/hardware/<YYYYMMDD>_<階段>/，例如 20261112_H1/。裡面放 record.md、output.txt（完整指令與輸出）、照片、工作表。record.md 格式：

階段：
日期與時間：
操作者／記錄者：
程式版本（git rev-parse HEAD）：
實際輸入的指令與完整輸出：（見 output.txt）
量測工具與解析度：
照片檔名：
結果：PASS / FAIL / BLOCKED / NOT_RUN
異常或和手冊不同之處：

另外在 dual_arm_ws/docs/evidence/hardware/SUMMARY.md 維護一張總表：每個階段的狀態、上面「必須取得的資料」逐項的值或缺漏原因、D0、D1 的實測結論（只寫觀察到的事實，不替負責人做決定）。

## 結束時

1. 確認所有證據都在 docs/evidence/hardware/，git status 中沒有被意外修改的既有檔案（有的話用 git restore 還原，calibration.yaml 若是 H2 依規定填的則保留並在 SUMMARY.md 說明）。
2. 在 docs/PROGRESS.md 最上方加一節本次結果，通過與失敗都寫。
3. 問測試人員要怎麼交回：有 push 權限且他同意 → commit 到 main 並 push origin main（不開分支，commit message 寫清楚日期與階段）；沒有權限 → 把 docs/evidence/hardware/ 打包成 zip 給負責人。
4. 最後用五到十句話向測試人員總結：做了哪些階段、各自狀態、交付資料缺哪些、下一步需要負責人決定什麼。

現在開始：先做「第一步」，回報環境與建置、測試結果，然後問測試人員：實體急停、兩人人力、直尺、手機相機、紙膠帶與麥克筆、RoboPlus 或 DYNAMIXEL Wizard 是否都準備好了。
````
