# 續接工作紀錄 — 2026-11-09

## 使用者最新要求（取代先前保留錯誤 CAD 的限制）

1. 末端小方塊是鏡頭支架，依實機照片修正前後顛倒；同步修正相關 CAD、STEP、STL、URDF／Gazebo、碰撞及說明。
2. C 區八格以白色方塊填滿，表面齊平，取消凹洞；同步更新放置高度、視覺格位說明及驗證。
3. README 清楚列出 Windows／WSL 與 Jetson Orin 下載專案後的安裝、建置、啟動及現有限制。
4. 搬運速度再適度提高，接觸段保持較低速度。
5. 預備姿勢使用韌體 home_A、home_C 的關節數字計算，不再把 CAD q=0 當作 home。
6. 持續更新本檔，額度或對話中斷後可直接續接。

## 最新狀態（優先於以下全部內容）

- 2026-11-11：依使用者要求放寬實機交接的權限規則：團隊成員同等層級，現場成員做完安全檢查就能決定，決定寫進紀錄，不再需要「負責人」授權（HANDOFF_PROMPT_HARDWARE_TESTER、HARDWARE_TEST_GUIDE、AGENTS、MODIFICATION_PLAN 第 5 節、TEST_PLAN）。手冊新增「HOME 定位」：P0、H0 當天通過後可隨時用韌體 HOME 讓手臂回預設姿勢（例如調相機）；因 Moving Speed 上電通常是 0（最高速），先用唯讀的 `pose_guide.py` 扶到 HOME ±20 raw 內，再 HOME、上扭力，一次一支。H3 前置改為 H1。工程規則與程式閘門不變；H4 以後仍因 D8 未實作而 `BLOCKED`。
- 2026-11-11：匯入 Orin 現場 11-11 的實機紀錄（Azeem1010/Dual-Arm-TEST-2.0 `13a5b4f`，只複製文字，照片與大型日誌留在來源 repo），放在 `docs/evidence/hardware/`。現場已更新到 `8ad9d47` 並重跑離線測試 PASS；H1 兩臂資料取得但仍進行中（Moving Speed 未讀、畫圓法跳過），V0 用 by-path 完成相機對應。和模擬一致：arm2 j1 也是 +1、j1 正對場地約 193／519（模擬 192.3／512）、兩臂 j2 往使用者前傾讀值變大；arm2 C 格示教讀值的 FK 半徑與尺量差 3 mm 內。和模擬不同、併入階段 C：板寬 240 mm、軸心在板外約 5 mm、C 格 1、2 靠手臂且單號欄靠 B。模擬數值都沒改，只改了 MODIFICATION_PLAN（D0、D1、D3、WP11）、COORDINATE_FRAMES、HOME_POSES 與 `runtime.json` 的說明文字。下一步是階段 C。
- 2026-11-11：README 加上操作介面實際截圖（`docs/images/ui_working.png`、`ui_stopped.png`，由新的 `scripts/capture_hmi_images.py` 從模擬擷取）。擷取時發現：環境相機的區域在 A 在右的模擬中開機時偵測不到場地，會改讀 `~/.ros/dual_arm_calib/sim/zones.yaml`；這台 WSL 的檔案是 2026-11-08 舊配置（C 在左）存的，所以介面上 A 與 C 對調（框標「(saved)」，C 區顯示 7 個）。已把它改名為 `zones.yaml.old_layout_20261108`，之後顯示 `ZONES MISSING`。任務決策用真值不受影響；但存檔沒有記錄是哪個配置，換配置後會被默默沿用，實機換場地時同樣要先刪掉。
- 2026-11-11：依程式全面更新文件：兩份 README 加上操作介面的用法與狀態、UI_PLAN 的接通狀態與按鈕條件改成和 `state.py` 一致、ROS_INTERFACES 加入介面的兩個節點並更正 `hmi_sim` 與 ESP32 缺口、TEST_PLAN 加入介面測試與重跑規則、ORIN_DEPLOYMENT 的執行狀態、ARCHITECTURE、FUTURE_ROADMAP、AGENTS 與三份接手 prompt（預期 coordinator 285、HMI 293）。順帶修正介面事件紀錄：介面自己的事件原本一律排在 ROS 事件前面且沒有上限，改為依時間合併、最多 200 筆。
- 2026-11-11：操作介面階段 3 完成（UI_PLAN 第 13 節，evidence/hmi/stage3/）。新增 `/safety/trigger_stop`（軟體停止，鎖定並停用控制器）與 `/dual_arm/go_home`（不用 token，`success` 是人工確認；模擬中有持物時拒絕），`/dual_arm/status` 多了 `at_home`；`hmi_sim.launch.py` 加入 `safety_supervisor`（`require_estop:=false`）。介面以獨立的命令節點送出指令，`--monitor` 仍然只讀。WSL 模擬實測：一輪搬運、未持物停止後復歸再開始、持物停止後重置模擬都 `PASS`。實機只接通強制停止。發現：同一模擬第三次取料時手臂 1 肘關節到限位（C30），停在限位外時回 HOME 無法規劃。
- 2026-11-11：使用者以示意圖確認實物格位編號（使用者側視角）：1、2 最靠近手臂 2，往使用者依序到 7、8，單號在左。模擬、介面格位圖、`vision_pkg` 三處都不一致；使用者決定併入階段 C，和場地尺寸一起改，見 MODIFICATION_PLAN D3。另檢查介面與實機相容性，同日修正兩項：介面設定檔新增三顆相機路徑；實機改用專用的 `hardware.ros_domain_id`（預設 0），監看節點跟著模式換 domain，新增 `--monitor --hardware`（UI_PLAN 第 9 節，介面單元測試 276 項 `PASS`，監看節點加入指定 domain 已在 WSL 實測）。仍未解決：沒有急停心跳發布者，實機動作會一直鎖定。
- 2026-11-10：新增分層檢查 `scripts/run_checks.sh t0|t1|t2`（TEST_PLAN.md 第 4 節），只重跑部分步驟用 `STEPS`。在 A 在右的配置跑完 t1、t2（evidence/checks_20261110/）：除了已知的 IK 16/18 與冒煙測試的關閉檢查（Gazebo 結束逾時，時有時無）外全部 `PASS`，視覺取料、格位位移研究、README 截圖都已重跑。t2 抓到配置改版時漏改的停放點，已修正。新增 `fit_axis_circle` 畫圓找軸心工具與現場補量清單（HARDWARE_TEST_GUIDE.md）。板寬與軸心到板緣距離仍是 CAD 值，等現場量測。

- 2026-11-10：使用者依 H1 實測決定 D0，模擬改為 CAD 整組轉 180°：A 區在 -X（手臂右方）、兩臂 j1 方向 +1。單元測試、HOME、舊 pipeline 兩物體、coordinator 一輪都 `PASS`（evidence/a_right_layout_20261110/）。板寬與軸心到板緣距離仍是 CAD 值，待現場直接量測；視覺取料、格位位移研究、README 截圖未重跑。

- 2026-11-10：第一次 Orin 實機測試已匯入 evidence/hardware/（來源 Azeem1010/Dual-Arm-TEST-2.0 `fc4cd41`）。SETUP、P0、H0 `PASS`；H1 只做完 arm1：**A 區在手臂自身右方、j1 方向 +1**，與目前模擬（A 在左、−1）相反。軸心在板外約 10 mm、板寬約 235 mm，也與模型不同。只更新了文件與 `install_jazzy.sh`；模型、runtime.json、視覺設定未改，等使用者決定 D0。下方「A 區在手臂左邊」的敘述已被實測推翻。

- 2026-11-10：操作介面規劃與使用者決定在 [UI_PLAN.md](UI_PLAN.md)，階段 0 假資料畫面已實作（`src/dual_arm_hmi`，evidence/hmi/stage0/），等使用者確認視覺並在 Orin 執行一次才算結案。階段 1 唯讀監看 `PASS`（evidence/hmi/stage1/，205 項測試，WSL 模擬實測）：UI 不會送出任何指令，全部按鈕含強制停止都未接通。階段 2 啟停管理 `PASS`（evidence/hmi/stage2/，242 項測試，十次模擬啟停與當掉後接回都無殘留）：介面可啟動、關閉、重置模擬，強制停止與任務按鈕仍未接通。下一步是階段 3。WSL 系統沒有繁中字型，要先裝 `fonts-noto-cjk`。使用者要求實機運作時 Gazebo 同時動作，設計在 UI_PLAN.md 第 9.1 節，尚未實作；不可在同一個 ROS domain 同時跑 `sim.launch.py` 和實機。
- 2026-11-10：現場測試請照 [HARDWARE_TEST_GUIDE.md](HARDWARE_TEST_GUIDE.md)，換電腦用 [HANDOFF_PROMPT_NEXT_COMPUTER.md](HANDOFF_PROMPT_NEXT_COMPUTER.md)。安全監控鎖定可被手動 `switch_controllers` 繞過的問題（C32）已修正，只在 mock 驗證（evidence/c32/）。
- 2026-11-10：所有文件已對照現行程式更新（evidence/docs_audit/）；`demo_pick_place.launch.py` 預設一輪與舊 pipeline 兩物體都 `PASS`。README 截圖已於 2026-11-10 用 coordinator 重新擷取。
- 2026-11-09：接手請用 [HANDOFF_PROMPT.md](HANDOFF_PROMPT.md)，工作順序與進度在 [MODIFICATION_PLAN.md](MODIFICATION_PLAN.md) 第 6 節。WP0～WP6 都是 `PASS`（evidence/roadmap_baseline/、evidence/wp1/～wp6/）。WP6S 最終只減少 48.6%，未達 50%（`FAIL`）。WP7 取料點已由視覺決定，區域與格位仍用真值，等 D7（`BLOCKED`）。WP8 驅動強化 `PASS`（evidence/wp8/），READ 重試等 D2。WP9 安全監控 `PASS`（evidence/wp9/，只驗證 mock）。WP10 操作工具 `PASS`（evidence/wp10/）。WP13 文件 `PASS`。WP12 ESP32 後端 `PASS`（evidence/wp12/，只用替身節點），協定來源是 ray000518/micro-ros。WP7、WP11、實機階段在等使用者決定或現場操作，起點是 ORIN_DEPLOYMENT.md 第 4 節的手動確認。模擬速度比例 1.0／0.5／1.0、到位容差 0.5 mm，只限模擬。目前佈局只有 4 個瓶蓋可達（C30），八件搬運要等 D3 決定。Coordinator 被強制結束後，安全監控約 1.2 秒內停下手臂（C29，mock 量測），實體急停與實機心跳來源仍未完成。WP2 只用假 IO，WP3 只用 MoveIt mock，都還沒跑 Gazebo 物理。`build.sh` 和 pipeline 會覆寫 `docs/evidence/` 的舊紀錄，新結果要另存，舊檔用 `git restore` 還原。
- A 區左右與 arm1 的 j1 方向已由 2026-11-10 H1 確認（A 在右、+1）；arm2 的 j1、j2 方向與零點仍 `BLOCKED`（FUTURE_ROADMAP.md 第 3 節）。
- 從 Git Bash 呼叫 `wsl.exe bash -lc '...$VAR...'` 時變數會先被展開，指令會靜默出錯；複雜指令請寫成腳本再用 `wsl.exe bash <路徑>` 執行。
- 2026-11-09 的「A 區在手臂左邊」鏡像配置已在 2026-11-10 換成 CAD 整組轉 180°（A 在右），定義見 COORDINATE_FRAMES.md，證據在 evidence/a_right_layout_20261110/；更早的配置證據在 evidence/before_far_side_layout_20261109/。
- 待處理：格位 1 逆運動學 FAIL（見 SLOT_ADJUSTMENT.md）；需要實機俯視照片確認配置。
- ROS 介面規格已寫入 ROS_INTERFACES.md，並用 headless `vision_sim` 的實際 graph 核對（evidence/ros_graph_vision_sim/）。目前缺口列在該文件最後一節。
- 使用者提供實機零姿態：四顆馬達 raw 512、手臂伸直。已套用為模擬暫定值，換算與數字見 HOME_POSES.md。
- 兩物體搬運回歸 PASS（Gazebo 真值、無畫面），證據為 transfer_pipeline.json 與 zero512_pipeline.log。先前手動中斷的那一輪備份在 evidence/before_zero512/，不是搬運失敗。
- 待使用者提供：Arm 1 馬達 17 的三筆讀值（步驟見 HOME_POSES.md），用來取代 j1 暫定值 192.3；確認「伸直」是否指垂直朝上。
- `cm530_hardware` 與 `hardware.launch.py` 已完成並通過 Mock Serial 測試，尚未接實機。`config/calibration.yaml` 仍全為 null，故意讓驅動拒絕啟動，只能填實機量測值。
- 模擬已全部關閉，沒有進行中的工作階段。下方的 session 編號與「進行中」描述都已過時。

## 目前執行狀態

### 最新續接覆核（優先於下方歷史描述）

- 本輪新增 `cad/dual_arm_corrected_geometry.SLDPRT`：SolidWorks 已儲存並重新開啟，342 個 solid bodies、warnings=0。是多實體幾何，不是原特徵樹組合。
- PackAndGo 雖回覆 PASS files=267，實際只有組合檔與清單，沒有完整可攜引用；不把 native_portable 宣稱為完成。
- HOME named states 局部建置 PASS（home_named_states_build.log），README／HOME_POSES 已更新為模擬假設，不再要求使用者先提供實測值才能模擬。
- 新版 GUI 與兩物體測試已啟動，但 Windows 磁碟讀取導致載入很慢；本輪 exec GUI session=92015、pipeline session=39417。先看 revised_gui_launch.log / revised_pipeline.log，勿重複啟動。前一輪舊 domain43 遺留 Gazebo 2521/2522 已定點停止。

- 舊版三物體 `transfer_pipeline.json` 已 PASS，三物體落孔與雙臂同步取物有實際回饋。舊模擬已停止。
- 已完成 10 個末端零件翻向前方、STEP/STL/URDF 生成，八個白格填平至 z=14 mm；`model_revision_validation.json` PASS，TCP／軸保持不變。
- 8 個 coordinator 測試 PASS。新版全套 10 套件建置已完成；加入 HOME named states 後的局部重建正在本輪執行。
- 使用者已回覆：沒有零位方向量測，先建立模擬換算。設定已寫入 runtime.json；home_A=(-30,-10,40,60)°、home_C=(30,-10,40,60)°；是反算零位假設，hardware_use_allowed=false。
- 搬運／接觸速度改為 0.50／0.25，加速度 0.25。新白格中心高度 0.019 m。新版取放驗收尚未完成。
- README Windows／Orin 指南、啟動腳本已完成。需依本輪結果更新狀態。
- 本機 SolidWorks 2019 打不開較新版原始 SLDASM（8192）。已成功從修正版 STEP 匯入新 `cad/native_corrected/dual_arm_corrected_geometry.SLDASM`，但引用仍指向 SolidWorks 暫存目錄；**不可單獨交付此檔**。`scripts/package_native_cad.ps1` 正在處理 PackAndGo 引用封裝問題。
- 上次修正版 smoke_runtime 已記錄 FAIL：三相機、控制器、網格 PASS，部分 views 未收到，動作等待太短且 shutdown 未通過。已將 action 等待 15 秒改為 90 秒，尚待重驗，不可將更長等待當成通過。

- 舊版三物體管線在 ROS_DOMAIN_ID=43、GZ_PARTITION=dual_arm_pipeline_demo 執行中。啟動 exec session=48173，搬運 session=93915。
- 2026-11-09 接到新要求時，cap_5 已放 C 第3孔、cap_6 已完成 C 放置，cap_4 正在 B 交接流程。**先讀 docs/evidence/transfer_pipeline.json / .log 確認最終狀態，勿重跑或假設已完成。**
- 原單物體流程在 C 孔底姿態 TCP 誤差 >1 mm 停止；三物體版本改於孔口上方釋放，已驗證至少第一個實際落孔。新齊平白格需重新驗證，不可沿用凹洞高度。
- 舊版流程為模擬真值定位，非已校正的視覺自動取放；完整工作站與負載 PlanningScene 驗收仍未完成。

## 待辦與進度

- [ ] 鏡頭支架 CAD 零件辨識、方向修正及原生 SolidWorks / STEP 輸出。
- [ ] 重新生成並檢查 STL、URDF 視覺／碰撞與 Gazebo。
- [ ] C 八格白色齊平實體填塊與所有高度使用處更新。
- [ ] HOME 原始值換算設定、姿態計算與 named states，待零位方向確認。
- [ ] 速度集中設定與腳本整合。
- [ ] Windows、Orin 使用指南及根目錄 README。
- [ ] 建置、模型一致性、模擬啟動、實際取放重驗與結果紀錄。

## 已知來源與工具

- 照片：已複製為 [reference/physical_camera_mount.png](reference/physical_camera_mount.png)（2026-11-10 核對 MD5 與原暫存檔相同），cad/README.md 引用的是這份。
- 韌體來源：`third_party/CM530_ROS_BRIDGE/17 ROS to CM530 ver. dual arm/APP/inc/arm_config.h`。
- home_A=[90,567,712,825]、home_C=[590,567,712,825]；原始位置值不是 URDF rad。CAD 零位 raw offset / 方向尚缺，已透過非同步問題詢問使用者。
- SolidWorks COM `SldWorks.Application` 註冊存在，尚未驗證自動化能否啟動。沒有授權修改來源 checkout；工作副本應置於 `cad/`，匯出與生成器改指向工作副本。
- CAD 主組合：`third_party/dual_arm_3d/雙臂_交付/完成_雙臂總組合.sldasm`；STEP：同目錄 `雙臂總組合.STEP`。
- 末端主零件 arm1 component_010、011、019；arm2 component_231、232、240。尚不能僅憑名稱假定哪個是鏡頭支架，需檢視幾何。
- WSL Ubuntu 中 ROS Jazzy / Gazebo Harmonic 已安裝；OpenCascade / VTK 在 `.cad-venv`。
- 建置：`bash scripts/build.sh`。不可直接重跑早期 `integrate_description.py`，會覆寫後續設定。

完成每項後更新待辦、證據路徑、假設與未完成部分。不得將假設的 HOME 轉換標為實機校正通過。
