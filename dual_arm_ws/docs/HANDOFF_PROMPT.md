# AI 接手 Prompt

額度用完或換手時，把下方整段貼給接手的 AI。內容不依賴先前的對話。

````text
你要接手一個 ROS 2 Jazzy 雙機械手臂專案的實作。請用繁體中文回報。

## 位置與環境

- Windows 路徑：E:\dual_arm_system\dual_arm_ws
- WSL2 路徑：/mnt/e/dual_arm_system/dual_arm_ws（Ubuntu 24.04、ROS 2 Jazzy、Gazebo Harmonic）
- ROS、colcon、Gazebo 指令都在 WSL 執行。從 Git Bash 呼叫 wsl.exe 時，先設定 MSYS_NO_PATHCONV=1。
- Windows 的 python、python3 可能是空殼指令，要用 py -3。

## 開始前依序閱讀

1. AGENTS.md（強制規則）
2. docs/MODIFICATION_PLAN.md（工作包、衝突清單、未決事項、進度表）
3. docs/RESUME.md 最上方、docs/PROGRESS.md 最上方
4. docs/FUTURE_ROADMAP.md 第 3、5 節（實機證據、節點設計）、docs/TEST_PLAN.md、docs/HARDWARE_TEST_GUIDE.md、docs/ORIN_DEPLOYMENT.md
5. docs/COORDINATE_FRAMES.md、docs/ROS_INTERFACES.md

文件可能過時。下結論前，以實際程式碼和 docs/evidence/ 的最新紀錄為準。兩份計畫不一致時，以 MODIFICATION_PLAN.md 為準。

## 目前狀態（2026-11-11）

- 不需實機的工作包 WP0～WP6、WP8～WP10、WP12、WP13 都是 PASS，細節以 MODIFICATION_PLAN.md 第 6 節為準。
- 模擬：coordinator 節點在 Gazebo 完成兩物體 A→B→C 與故障情境。觀測用 Gazebo 真值，取料點可由視覺決定。
- WP7 BLOCKED：模擬相機在 Home 被手臂遮擋，區域與格位仍用真值，等 D7。
- WP6S FAIL：最終時間只減少 48.6%，使用者選擇維持現況。
- cm530_hardware 與安全監控只驗證過 Mock，實機 NOT_RUN，config/calibration.yaml 刻意全為 null。Coordinator 會拒絕以實機設定啟動。
- 2026-11-10 H1（arm1）：A 區在手臂右方、j1 方向 +1，模擬已改成這個配置。arm2 的 j1 方向、j2 方向與零點仍 BLOCKED，需要現場手動確認（docs/HARDWARE_TEST_GUIDE.md 的 H1）。
- 模擬編號的格位 1 與 4 個瓶蓋位置在目前模型中搆不到，八件搬運是已知 FAIL，等 D3。實物格位編號已由使用者提供（和模擬差 180°），改編號併入階段 C。
- 操作介面 dual_arm_hmi 階段 0～3 在模擬可用（UI_PLAN.md），新增 `/safety/trigger_stop`、`/dual_arm/go_home`；實機模式只接通強制停止。
- 兩個專案都沒有完成實機取放。接下來幾乎都需要使用者決定或現場操作，不要自行繞過。

## 絕對禁止

- 開啟實體序列埠、驅動馬達、啟用扭力、燒錄韌體、操作相機或吸盤硬體。實機階段 H0～H8 只能由使用者在現場明確授權。
- 在 calibration.yaml、硬體 homography 或硬體 controllers 檔填入估計值、模擬值或對方的數值。
- 把 hardware_use_allowed、moving_speed_verified 等閘門設為可動作。驅動必須維持預設唯讀。
- 為了通過檢查而放寬關節限位、容差或碰撞規則，或修改測試使其通過。
- 序列逾時後自動重送。AX 命令一律不重送。
- 修改 third_party/、上游 vision_interfaces 的欄位或服務名稱。
- 執行 scripts/integrate_description.py。手改 dual_arm.srdf 的 HOME。
- 覆蓋失敗紀錄或把未驗證的項目寫成通過。
- 自行決定 D0～D8。未答覆時採 MODIFICATION_PLAN.md 第 2 節的預設。
- 未經使用者要求就 commit 或 push。使用者要求時，直接 commit 到 main 並 push origin main，不開 feature branch。

## 工作方式

1. 打開 MODIFICATION_PLAN.md 第 6 節，從第一個 NOT_RUN 的工作包接續，不要重做 PASS 的項目。如果已經沒有 NOT_RUN，剩下的都在等使用者決定或現場操作，要停下來詢問，不要自行解除 BLOCKED。若上一輪中斷，先檢查 git status、git diff 和 RESUME.md，確認殘留的修改。
2. 一次只做一個工作包。動手前讀該工作包列出的衝突編號，遵守處理方式。
3. 修改前先確認沒有模擬在執行：pgrep -af 'gz sim'。不要同時跑新舊流程。
4. 實際執行建置與測試，原始輸出存到 docs/evidence/。不能只憑閱讀程式判定通過。
5. 狀態只能用 PASS、FAIL、BLOCKED、NOT_RUN。以下都不算通過：合成影像、Mock Serial、Gazebo 座標、MoveIt 規劃成功、序列埠 ACK。
6. 改了模型、launch、world 或校正，要重跑受影響的檢查，用 scripts/run_checks.sh t0／t1／t2（哪種修改跑哪層見 docs/TEST_PLAN.md 第 4 節；t2 約 40 分鐘，放在背景跑，失敗的步驟修正後用 STEPS 只重跑那幾步）。修改 C/C++ 要跑 ASan/UBSan、TSan。AGENTS.md 指定的 Trail of Bits 技能不可用時，記為 NOT_RUN，不要跳過不提。
7. 每完成一個工作包，更新 MODIFICATION_PLAN.md 第 6 節、docs/PROGRESS.md、docs/TEST_REPORT.md、docs/RESUME.md，寫清楚未完成和未驗證的部分。額度快用完時，優先把目前進度、指令和下一步寫進 RESUME.md。

## 對方專案的參照方式

節點寫法參照 https://github.com/Azeem1010/Dual-Arm-TEST ，固定 commit 26d187f。

    git clone https://github.com/Azeem1010/Dual-Arm-TEST.git /tmp/dual-arm-test
    git -C /tmp/dual-arm-test checkout 26d187f

- clone 在專案目錄外，唯讀，不要加入 colcon 建置。
- 可參照：src/dual_arm_control/dual_arm_control/ 的 workflow.py、arm2_workflow.py、dual_workflow.py、dual_coordinator.py、moveit_client.py。
- 該 repo 沒有授權條款。D4 未核准前，只參照結構，自行撰寫，不要複製程式碼。
- 不可使用它的 URDF/SRDF（尺寸不符 CAD）、bridge_node.py（本地用 ros2_control）、manual_xy_legacy_confirmed.yaml。
- 它的實機 Y 值與 homography 符號未定，不可沿用。

## 最容易做錯的三件事

1. 本地 kinematics.yaml 是 position_only_ik: true，對方的 move_pose 與 GetCartesianPath 無法保證吸盤朝下。要沿用本地 CadKinematics 的朝下 IK，並用取樣的關節路徑點下降（衝突 C8）。
2. TCP 是 arm1_tcp、MoveIt 基座是 arm1_base_link；視覺輸出 arm1_base，必須經 TF 轉換（衝突 C9）。
3. 實機 coordinator 不可使用 SRDF 的 home named state，那是模擬值（衝突 C16）。

## 必須停下來詢問使用者的情況

- 下一步需要實機或現場量測。
- 需要 D0～D8 的決定才能繼續。
- 既有測試失敗且原因不是本次修改造成，或修正需要放寬規則。
- 發現計畫與程式碼有無法用既定處理方式解決的衝突。
- 需要刪除或大幅改寫舊 pipeline、模型或證據。

## 回報格式

每個工作包結束時回報：完成內容、實際執行的指令與結果（PASS／FAIL／BLOCKED／NOT_RUN）、證據路徑、未完成與未驗證的部分、下一個工作包。

現在開始：讀完上述文件後，先用三到五句話說明你判斷的目前進度，然後從第一個 NOT_RUN 的工作包接續；沒有的話，列出需要使用者決定的事項並等待答覆。
````
