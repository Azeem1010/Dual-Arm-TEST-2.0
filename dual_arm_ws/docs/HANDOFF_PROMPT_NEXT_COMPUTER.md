# 換到另一台電腦時給 AI 的 Prompt

把下方整段貼給另一台電腦上的 AI。內容不依賴先前的對話。

貼上之前要先確認：開發電腦上的修改已經 commit 並 push 到 `origin main`，否則另一台電腦拿不到這些檔案。

````text
你要在一台新的電腦上接手 ROS 2 Jazzy 雙機械手臂專案。請用繁體中文回報。使用者和組員會在現場操作實體手臂，你協助他們。

專案：https://github.com/xian1022/dual_arm_system （main 分支，工作區在 dual_arm_ws/）
硬體：兩支 PhantomX Pincher、一片 CM-530（韌體 v17，協定 5）、8 顆 AX-12A、ESP32 吸盤、三顆相機。目標是把瓶蓋 A→B→C 搬運。

## 第一步：確認環境（只讀，不動硬體）

1. 回報 `uname -m`、`cat /etc/os-release`、有沒有 ROS Jazzy，以及這台電腦有沒有接控制板（`ls -l /dev/serial/by-id/`，只列出，不要開啟）。需要 Ubuntu 24.04。Windows 只能跑模擬，要接 ROS 實機請用 Orin。
2. 取得程式碼：
   git clone --recurse-submodules https://github.com/xian1022/dual_arm_system.git
   已經有 clone 的話，先看 git status，沒有未保存的修改才 git pull。不要丟棄別人的修改。
3. 確認 dual_arm_ws/docs/HARDWARE_TEST_GUIDE.md 存在。不存在代表開發電腦的修改還沒推上來，停下來告訴使用者。
4. 只有在沒有 build/ 時才安裝與建置：sudo bash scripts/install_jazzy.sh（需要使用者同意）、bash scripts/build.sh。不要把別台電腦的 build/、install/、log/ 複製過來。
5. 建立基準，全部不需要硬體，結果回報給使用者：
   (cd src/dual_arm_coordinator && python3 -m pytest -q -p no:cacheprovider test)
   應為 272 passed。
   python3 scripts/test_cm530_mock.py
   這支會覆寫 docs/evidence/ 的舊紀錄，跑完先把結果另存，再用 git restore 還原舊檔。

## 開始前依序閱讀

1. dual_arm_ws/AGENTS.md（強制規則）
2. docs/HARDWARE_TEST_GUIDE.md（現場測試手冊，最重要）
3. docs/MODIFICATION_PLAN.md 第 2 節（D0～D8 待決定事項）、第 3 節（衝突 C1～C32）、第 6 節（進度）
4. docs/RESUME.md、docs/PROGRESS.md 最上方
5. docs/ORIN_DEPLOYMENT.md、docs/TEST_PLAN.md、docs/COORDINATE_FRAMES.md、docs/ROS_INTERFACES.md

文件可能過時。以程式碼和 docs/evidence/ 的最新紀錄為準。

## 目前狀態（2026-11-10）

- 模擬：coordinator 在 Gazebo 完成兩物體 A→B→C、故障停止與人工復歸。區域和格位用 Gazebo 真值，只有 arm1 取料點可由視覺決定。
- cm530_hardware、安全監控、ESP32 後端只用 Mock 或替身節點驗證。實機全部 NOT_RUN，所有實機步驟都還沒執行過。
- config/calibration.yaml 刻意全為 null，coordinator_node 會拒絕實機模式。
- 2026-11-10 H1（arm1）已確認 A 區在手臂右方、j1 方向 +1，模擬已依此修改。arm2 的 H1、j2 的方向與零點仍待手冊的 H1 解決（D1）。
- 模型只有 cap_3～6 與部分格位可達，格位 1 搆不到，八件搬運是已知 FAIL（D3）。
- safety_supervisor 鎖定時會把手動啟動的控制器再停掉（C32，只驗證 Mock），約有 0.3 秒空窗，所以手動切換依然禁止。

## 絕對禁止

下面任何一項，只有使用者在這次對話中明確要求該階段時才可以做，而且一次只限該階段：

- 開啟實體序列埠、啟用扭力、驅動馬達、燒錄韌體、操作相機或吸盤硬體。手冊的 H0 雖然唯讀，一樣要先得到同意。
- 跑 H3 以後的階段。必須有人在現場，手放在實體急停上。你看不到現場，不可以假設安全。

下面這些在任何情況都不可以：

- 在 calibration.yaml、homography 或實機 controllers 檔填入估計值、模擬值或別的專案的數值。量測值只能由現場量到的結果而來。
- 為了通過檢查而放寬關節限位、容差、碰撞規則，或修改測試使其通過。
- 把 hardware_use_allowed、moving_speed_verified 設為 true，除非使用者提供了對應的實測紀錄並要求你填。
- 序列逾時後自動重送。AX 命令一律不重送。
- 手動 switch_controllers 啟動實機控制器。一律走 /safety/reset。
- 修改 third_party/、上游 vision_interfaces 的欄位或服務名稱。執行 scripts/integrate_description.py。手改 dual_arm.srdf 的 HOME。
- 覆蓋失敗紀錄，或把未驗證的項目寫成通過。狀態只能用 PASS、FAIL、BLOCKED、NOT_RUN。Mock、模擬、ACK 都不算實機通過。
- 自行決定 D0～D8。把選項和影響告訴使用者，由使用者決定。
- 未經要求就 commit 或 push。使用者要求時，直接 commit 到 main 並 push origin main，不開 feature branch。

## 工作順序

先問使用者今天要做哪一種，不要自己猜：

A. 現場實機測試
   依 HARDWARE_TEST_GUIDE.md 的順序，一次帶一個階段：說明目的、要準備什麼、指令、該看到什麼、什麼情況要按急停。等使用者貼回結果，你判斷 PASS/FAIL，寫進 docs/evidence/hardware/<日期>_<階段>/，再問要不要進下一階段。
   H1 完成後要停下來分析：比對目前的模擬配置、COORDINATE_FRAMES.md、URDF 與 runtime.json，告訴使用者哪些要改，得到同意才改。改了模型或 HOME 要依 TEST_PLAN.md 第 4 節重跑檢查。

B. 不需要實機的開發，建議順序
   1. 使用者決定 D8 後，做急停心跳節點。
   2. 使用者決定 D7 後，做實機的區域與格位判斷，以及實機 TF。
   這些都完成後才討論移除 coordinator_node.py 的實機拒絕條件。

## 容易出錯的地方

- 實機啟動順序：心跳先有，然後 set_hardware_component_state active，最後 /safety/reset。先 reset 會被拒絕（Controller activation was refused）。
- kinematics.yaml 是 position_only_ik: true，要用本地 CadKinematics 的朝下 IK，不能用 MoveIt 的姿態目標。
- TCP 是 arm1_tcp，MoveIt 基座是 arm1_base_link，視覺輸出 arm1_base，必須經 TF。
- 實機不可使用 SRDF 的 home named state，那是模擬值。實機 HOME 由 calibration.yaml 換算。
- CM-530 開機時扭力是關的，重置會立刻關扭力，手臂會掉。韌體沒有 STOP 也沒有 watchdog。第 17 版韌體無法寫入或讀取 Moving Speed，值 0 代表最高速。
- ESP32 沒有真空感測，/suction_status 只是命令回音。發生故障時不要自動送 0，持有中的物件會掉落。
- 模擬速度 1.0／0.5／1.0 不能用在實機，實機由 0.05 起步。
- 改 C/C++ 要跑 ASan/UBSan、TSan（docs/evidence/wp8/wp8.sh sanitize）。

## 回報格式

每個階段或工作結束時回報：做了什麼、實際指令與結果（PASS／FAIL／BLOCKED／NOT_RUN）、證據路徑、未完成與未驗證的部分、下一步需要使用者做什麼。完成後更新 docs/PROGRESS.md、TEST_REPORT.md、RESUME.md。

現在開始：完成「第一步」，用三到五句話說明環境與目前進度，然後問使用者今天要做 A 還是 B。
````
