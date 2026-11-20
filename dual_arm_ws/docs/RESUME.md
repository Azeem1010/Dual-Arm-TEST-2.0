# 續接工作紀錄 — 2026-11-20

## 使用者最新要求（取代先前保留錯誤 CAD 的限制）

1. 末端小方塊是鏡頭支架，依實機照片修正前後顛倒；同步修正相關 CAD、STEP、STL、URDF／Gazebo、碰撞及說明。
2. C 區八格以白色方塊填滿，表面齊平，取消凹洞；同步更新放置高度、視覺格位說明及驗證。
3. README 清楚列出 Windows／WSL 與 Jetson Orin 下載專案後的安裝、建置、啟動及現有限制。
4. 搬運速度再適度提高，接觸段保持較低速度。
5. 預備姿勢使用韌體 home_A、home_C 的關節數字計算，不再把 CAD q=0 當作 home。
6. 持續更新本檔，額度或對話中斷後可直接續接。

## 最新狀態（優先於以下全部內容）

- 2026-11-20（開發電腦，無硬體）：
  - 分析：arm2 重力力矩（`docs/evidence/diag_20261119/README.md` 第 5 節）顯示所有路徑中途都不會經過重力為 0 的點；會晃的是從 HOME（lift 無負載）出發的移動，判斷改為「離開 HOME 時齒輪換邊，加上出廠 compliance 偏軟」，仍是推論。1f24a25 之後過時的 Homes 測試已修正（第 6 節）。
  - 韌體第 19 版（協定 7）：`READ` 帶 Present Load、新增 `COMP`／`GET_COMP`／`DIAG`；開機不寫 compliance。驅動只接受協定 7，發布 `raw_load`，有 `motor_settings_file` 時每次啟用在上扭力前寫入並讀回比對。Prototype 用 `cm530_hardware/config/motor_settings_prototype.yaml`，目前全部是出廠值。韌體建置、主機測試（含 sanitizer、突變測試）、驅動 gtest（一般、ASan/UBSan、TSan）、Mock Serial 端對端、t1 都 PASS。見 `docs/evidence/fw_v19_20261120/`。
  - **沒做**：燒錄第 19 版（現場決定）、實機驗收、Gazebo 回歸 `two`。**驅動已不接受板上的第 18 版，下次上實機前一定要先燒錄第 19 版**，再跑晃動第 1 輪（加速度 0.3、出廠 compliance），之後才改 lift／elbow 的 slope 為 16 比較。
  - 韌體 repo 的 commit／push、主 repo 的 submodule 指標與 `docs/sources.lock.json` 要一起更新（commit 時做）。

- 2026-11-19（Orin 現場，韌體第 18 版，Prototype）：診斷「手臂晃動變大」與「部分瓶蓋吸不起」，細節見 `docs/evidence/diag_20261119/README.md`。
  - FTDI latency timer 原本仍是 16 ms，已裝 `/etc/udev/rules.d/99-ftdi-latency.rules` 改成 1 ms，READ 往返 16.0 → 2.0 ms（PASS），但晃動沒有改善（使用者確認），規則保留。
  - 晃動（錄製檔分析）：馬達本身約 4 Hz 振盪，只在從 HOME 往外伸的路段（arm1 HOME→A 上方、arm2 HOME→B 上方），肩關節 p2p 20～26 count，其他路段 3～10；收回 HOME 同幅度卻很穩，所以和重力方向有關。判斷：重力順著移動方向把限速的馬達拉過頭，且第 18 版沒寫 compliance／punch（出廠預設）；11-18 提速可能讓它變大。尚未用修改驗證。
  - 吸不起：和 A 區位置有關（y < −40 mm 成功 5／失敗 8、x < −185 mm 3／6、其他約 31／6），相機重複性 0.7 mm 內，是估計校正的區域偏差；瓶蓋實際直徑 25 mm（16:02 已把 Prototype `cap_radius_m` 改 0.0125、env_scene 改 25 mm，模擬仍 20 mm；先前分析誤用 20 mm 說餘裕 1 mm，實際約 3.5 mm），失敗時光關節到位誤差就 2～3 mm，單一全域 `a_pick_offset_xy_m` 修不到。
  - **沒做（建議順序）**：(1) 速度改回 0.3／0.3（`transport_scale` 0.6、`acceleration_scale` 0.3）並錄一輪比較；(2) 第 19 版韌體在上扭力時寫 compliance slope／margin／punch（要現場決定燒錄）；(3) 現場對調失敗區瓶蓋、在 (−143, −50) mm 量吸盤偏差，再做分區偏移或重新校正。
  - 121 MB 錄製檔 mcap 不進 git（`.gitignore`），只留 `metadata.yaml`。新瓶蓋尺寸還沒實機跑過。

- 2026-11-18 晚（開發電腦，無硬體）：手臂卡頓與前後擺動的推定原因是第 17 版韌體從不寫 Moving Speed，每一小步可能用全速走完再停。新增韌體第 18 版（`third_party/CM530_ROS_BRIDGE/18 ROS to CM530 ver. dual arm/`，第 17 版不動）：位置和速度一起寫、AX 可帶四個速度（1～1023，0 拒絕）、HOME／HOLD 用預設速度 100、主機連線 1 Mbps、協定 6、HOME 改成板上實際值 256,512,512,512。驅動只接受協定 6，每筆 AX 依指令速度（×1.2）或剩餘誤差（0.25 秒追上）算速度，限制在 20～300。原型速度提高：搬運 0.3→0.5 rad/s、加速度 0.3→0.6 rad/s²。韌體建置與主機測試、驅動測試（含 ASan/UBSan）、coordinator 508、Mock Serial 端對端都 PASS。**還沒做：燒錄第 18 版（要現場人員決定）、Orin 上設 FTDI latency timer 1 ms、實機確認卡頓與擺動是否改善**。板子仍是第 17 版時，新驅動會連線失敗。見 `docs/evidence/v18_speed_20261118/`。

- 2026-11-18 下午（Orin 現場，`60b91ca`、`24e4c8f`）：arm1 持物到 B 上方時 j2 下垂 5.6 count 而故障，新增 `b_teach.above_arrival_tolerance_raw: 6`；arm2 到 C7 上方差 5.3 count，新增 `c_slot_teach.above_arrival_tolerance_raw: 6`（接觸姿勢仍 4）。下降補正的路徑在模型中會碰撞時跳過、保留已到高度，不再故障（使用者決定）。arm2 的 B 與 C1～C8 重新示教；C8 新值 j2 830 在模型中 link_2 撞底座（816 起），改回 11-11 值。ESP32 在 agent 啟動 3 秒後自動用 RTS 重開（`esp32_reset_delay_s`），agent 部分實機 PASS，從介面完整啟動未確認。介面名稱「實機 Prototype」改為「實機運作模式」，舊設定仍可讀。12:55 一輪 9 次取件成功 8 次；A 區一顆瓶蓋（x −125、y 0 mm）連續 3 次吸不起，懷疑瓶蓋或座位，未確認。arm1 匯流排偶發 DXL_CORRUPT/TIMEOUT，懷疑線材，未查。
- 2026-11-18 晚（開發電腦）：`prototype-field-20261118b` 快轉合入 `main` 並推送；WSL 上 coordinator 508、HMI 322 測試 PASS；兩份 README、HARDWARE_TEST_GUIDE、ORIN_DEPLOYMENT、UI_PLAN、ROS_INTERFACES、TEST_REPORT、交接 prompt 已對照程式更新。下一步：從介面完整啟動確認 ESP32 自動重開、查 arm1 線材、用 TIMING 分段表找最慢的步驟，穩定後再試 overlap。

- 2026-11-18（Orin）：`main` 快轉到 `47b9b5c` 並重建，`build.sh` 與模型檢查 PASS，coordinator 501、HMI 320 測試 PASS；Mock Serial 開 overlap（固定路徑）在 Orin 重跑也 PASS，但結束後殘留一個 `robot_state_publisher`（腳本的殘留檢查沒包含它，已手動關掉）。使用者選做法 2：不改 src/ 和 git，只暫時改 install 裡的副本讓模擬模式能開 overlap，跑 Gazebo 回歸 `two`，PASS：兩件放進格位 1、2，兩臂確實同時動作（arm1 去 A 取下一件時 arm2 去 B 拿上一件；arm1 放 B 時 arm2 送 C），B 區交接順序正確。跑完已把 src 原檔複製回 install（`colcon build` 沒蓋掉較新的檔案），`cmp` 一致。沒測到：互相等待 x 範圍（這次沒發生）、overlap 的 `faults`／`batch`、相機、原型的示教點與固定路徑、實機。overlap 在原型設定仍預設關，模擬模式仍不允許。見 `docs/evidence/orin_overlap_20261118/`。

- 2026-11-18：Mock Serial 開 overlap 跑兩種：固定路徑、MoveIt 只規劃。兩種都 PASS：軌跡都直接送 `follow_joint_trajectory`（move_group 執行請求 0 次），兩臂回 HOME，overlap 任務啟動後在第一次看相機時如預期停下，時間記錄正常。測試期間暫時改寫的原型設定已還原，overlap 仍預設關。沒測到：兩臂同時動與互相等待 x 範圍（需要相機）、吸盤、接觸段、實機。見 `docs/evidence/mock_overlap_20261118/`。

- 2026-11-18：在本機 WSL 用 Mock Serial 跑原型 launch。第一次 FAIL：碰撞檢查一次送出約 157 筆，超過服務佇列（約 10 筆）被丟掉，固定路徑逾時退回 MoveIt；接觸段用同一個檢查、沒有退回，上實機會故障。已修：同時最多 8 筆。第二次 PASS：兩臂回 HOME 都走固定路徑（各 157 點），任務在第一次看相機時如預期停下，TIMING 分段表與 CSV 正常。coordinator 501 測試 PASS。相機之後的流程（A/B/C、吸盤、接觸段）、overlap、實機仍 NOT_RUN。見 `docs/evidence/mock_run_20261118/`。

- 2026-11-17：加速計畫 (5) 已完成：合入 Dual-Arm-TEST-2.0 `prototype-overlap-20261117`（`770f960`）。`overlap` 與 `direct_transfer` 不能同時開；原型設定維持 `direct_transfer: true`，`overlap` 區塊註解掉（預設關，下面那條「連續搬運」描述的程式碼已在但沒開）。arm1 `run()` 把 direct 傳進分支的 `pick_a`/`place_b`；arm2 兩條釋放 B 的路徑都會通知 overlap；所有計時路徑（接觸、示教直線、固定路徑）都經過分支的 `_send`，開 overlap 時也會預約 x 範圍。測試 PASS（coordinator 499、HMI 320、overlap 重跑 5 次），overlap 經 MoveIt／控制器與實機 NOT_RUN。加速計畫 1–5 全部完成；下一步要等 Orin：先用預設跑 2 件看 TIMING 分段表，穩定後再試 overlap（先 Mock Serial `go_home`，再實機 `cycles:=2`）。見 `docs/evidence/merge_overlap_20261117/`。

- 2026-11-17：加速計畫 (4) 已完成：原型 `fixed_transits: true`，非接觸移動（HOME、A/B/C 上方）先走關節直線、以一般速度執行，不再每次 MoveIt 規劃；任一點碰撞檢查不過，或吸盤低於兩端較低者超過 5 mm（板子沒有碰撞幾何），就退回 MoveIt。取消或安全停止不會被當成退回。模型檢查原型流程 22 段路徑全部通過，每段 3.5–8.0 秒。測試 PASS（coordinator 472、HMI 320），move_group 碰撞檢查與實機 NOT_RUN；實機看 log 的 `fixed joint path refused`。見 `docs/evidence/fixed_transits_20261117/`。下一步：(5) 合入 overlap 分支、預設關。

- 2026-11-17：加速計畫 (2) 接觸區分兩段，使用者決定跳過（模型計算每件只省約 1.5 秒，因為接觸段加速度只有 0.3 rad/s²）。(3) 已完成：原型 `grasp_settle_s` 1.2 秒（放開仍等 2.0 秒）；等停穩先用已收到的讀值套用同一套判斷，過去兩個窗格已經停穩就不再多等；接觸路徑的逐點碰撞檢查改成一次全部送出再等結果（每點照樣檢查）。後兩項所有模式都生效、判斷標準不變。測試 PASS（coordinator 462、HMI 320），實機 NOT_RUN；實機若吸取後瓶蓋掉落，調高或刪掉 `grasp_settle_s`。見 `docs/evidence/shorter_waits_20261117/`。下一步：(4) 示教點之間走固定關節路徑。

- 2026-11-17：身邊沒有 Orin，使用者同意的加速順序：(1) 時間記錄 →(2) 接觸區分兩段 →(3) 縮短等待 →(4) 示教點之間走固定關節路徑 →(5) 合入 overlap 分支但預設關。每項都放在原型設定開關後面、分開提交；等待點取代 HOME、B 區雙格要等 overlap 實機跑過再做。(1) 已完成：新增 `timing.py`，每一步記錄耗時與細項（規劃、移動、到位、等停穩、驗證、等相機、相機、ESP32 回音、吸盤等待），每步一行 `TIMING`、任務結束一段 `TIMING SUMMARY`，CSV 寫在 journal 旁的 `timing/`（原型：`~/.ros/dual_arm/timing/`）。只記錄，不改動作。測試 PASS（coordinator 448、HMI 320），實機輸出 NOT_RUN。見 `docs/evidence/timing_20261117/`。下一步：(2)。

- 2026-11-17：使用者要求加快 Prototype 流程，先拿掉中途回 HOME。11-17 影片顯示一個物件約 153 秒，其中兩臂吸著瓶蓋回 HOME 再出發約多 25 秒。新增 `direct_transfer`（只限 prototype，已在 `config/prototype/coordinator.yaml` 開啟）：arm1 在 PREFLIGHT 就預約 B 區，A 上方直接到 B 上方；arm2 B 上方直接到 C 上方，回 HOME 後在 VERIFY_C 確認 B 區已清空才釋放 B。單元測試 PASS（coordinator 437、HMI 320），MoveIt 直接路徑與實機 NOT_RUN（Orin 要 pull 後重建）。同日使用者決定一般移動加快：`transport_scale` 0.3 → 0.6（0.15 → 0.3 rad/s），接觸段先不動（`contact_scale` 0.2、`acceleration_scale` 0.3 都不變，因為接觸軌跡也用加速度設定）；實機跑時注意 log 有沒有 `exceeds max_step_raw`。下一步候選：加快接觸區（兩段式下降、`settle_s`、吸盤等待）、量驅動每輪時間後再把 transport 拉到 1.0。見 `docs/evidence/direct_transfer_20261117/`。

- 2026-11-17：使用者決定做「連續搬運」：Prototype 的 `overlap` 區塊開啟時，Arm 2 把上一件送去 C 的同時，Arm 1 去 A 取下一件，到 HOME 拿著等 Arm 2 離開 B 再放；B 區仍然同時只有一個擁有者。兩臂同時動作時，MoveIt 只負責規劃，軌跡直接送給各臂控制器，送出前先在模型裡預約整段軌跡的 x 範圍（`clearance_m` 0.025），和另一臂重疊就等待（`wait_s` 240）。A 區取完就結束（SUCCEEDED）。模擬和嚴格實機不變。單元測試 PASS（coordinator 450、HMI 320）；**MoveIt 只規劃＋直接送控制器這條路徑還沒在 Mock Serial 或實機跑過**（當時 Orin 上實機系統在跑，沒啟動 Mock，也沒重建 install）。要回到一次一臂，刪掉 `overlap` 區塊後重建。見 `docs/evidence/overlap_20261117/`。

- 2026-11-17：使用者決定「強制停止」也讓 ESP32 吸盤全關（送 0，吸住的瓶蓋會掉），停止時先送一次，取消回覆後再送一次；coordinator 每次送 ESP32 命令前都會再檢查 guard。Prototype 的 micro-ROS agent 改由介面啟動（`hardware.esp32_port`、`hardware.microros_setup`，Orin 本機已填 CP2102）；「關閉系統」會先送 0 並等回音，再關掉 launch 和 agent，沒收到回音也會繼續關閉，但會記一筆 DANGER。coordinator 故障時吸盤仍維持原狀。單元測試、替身 ESP32、agent 啟停 PASS；實機 NOT_RUN（先關掉手動開的 agent）。見 `docs/evidence/esp32_stop_20261117/`。

- 2026-11-15：使用者決定 Prototype 的 B 區交接也改用 11-11 H1 示教關節值（arm1 用重做的 `teach_arm1_B_2.csv`，arm2 用 `teach_arm2_B.csv`）。`config/prototype/coordinator.yaml` 新增 `b_teach`；兩臂 B 區接近、下降、抬起都到示教姿勢（`move_b`），Arm 2 仍用相機確認 B 區有一個物件。示教時壓著瓶蓋（使用者 11-15 確認），讀值就是接觸姿勢。測試與 Mock 啟動 PASS，`move_b` 尚未在 MoveIt＋控制器上跑過，實機待測（Orin 要 pull 後重建）。見 `docs/evidence/b_teach_20261115/`。
- 2026-11-13：使用者決定 Prototype 的 C 格改用 11-11 H1 的 arm2 示教關節值（示教時壓著瓶蓋，等於放置姿勢），不用 B 區示教。`config/prototype/coordinator.yaml` 新增 `c_slot_teach`；接近姿勢在示教點正上方（C8 降到 50 mm，沒放寬 9° 傾角）；下降與抬起走關節直線。測試與 Mock 啟動 PASS，`move_slot` 尚未在 MoveIt＋控制器上跑過，實機待測（Orin 要 pull 後重建）。見 `docs/evidence/slot_teach_20261113/`。

- 2026-11-13：現場回報 Prototype 吸盤高約 2 mm、吸不到瓶蓋。Prototype 的 `heights` 整組降 2 mm（桌面 0.012、吸取 0.0223、放置 0.0233、接近 0.052），模擬與嚴格模式不變；測試通過，實機待重跑（Orin 要 pull 後重新建置）。見 `docs/evidence/prototype_z_20261113/`。
- 2026-11-13：使用者決定先以 Prototype 為主，並和兩個上游 repo 同步。合入 Dual-Arm-TEST-2.0 `e0-esp32-suction`（E0 吸盤實測：重燒韌體、腳位 12/13/25/26、模組 arm1 1／arm2 2、`vacuum_settle_s` 2.0；斷電後要重開 agent）。env_camera_vision 換到 `6b3d5c1`（C 格依尺量 y = 45／10／−25／−60 mm），Prototype 的 `c_slots_xy_m` 跟著改，模擬不變。其餘分支已在本機或已過時，見 PROGRESS。待辦：韌體腳位修改推回 ray000518/micro-ros；env_scene 尺量標定檔只在現場機器上。
- 2026-11-13：新增「實機 Prototype」模式（使用者決定：先讓實機跑完整流程，不要求精準、吸不到也可以；急停只有 CM-530 電源開關，D8 不做）。coordinator `mode: prototype`、三份標 `PROTOTYPE ESTIMATE` 的估計設定檔、`hardware_prototype.launch.py`、`hardware.launch.py` 的 `require_estop`、操作介面新模式。嚴格模式不變。操作步驟見 HARDWARE_TEST_GUIDE「Prototype 模式」；證據 `docs/evidence/prototype_mode_20261113/`。實機尚未跑。
- 2026-11-13：合入 Orin 上的修正 `52a6518`（Azeem1010/Dual-Arm-TEST-2.0 `env-scene-debug-image` 分支）：`env_scene_node` 發布框線影像 `/vision/env/debug_image`（`publish_debug_image` 預設開），實機操作介面的環境相機改顯示標註畫面；`vision_hardware.launch.py` 新增 `show_debug`（OpenCV 視窗，預設關）、`publish_debug_image`，vision_pkg 的 include 改成 scoped，不再蓋掉 env_scene 的 `show_debug`。這是對匯入的 `src/env_scene` 的本地修改，換上游版本時要帶過去。Windows 的 WSL 已重建、env_scene 10 項測試 PASS（`docs/evidence/env_debug_image_20261113/`）。
- 2026-11-12：鏡頭分工調整（USB 頻寬）。使用者決定：環境相機負責 A/B/C 判斷，手臂鏡頭只監控、跟著動作的手臂輪流開（開關 usb_cam 程序），不做端到端試跑模式，瓶蓋只放 A 區黑框內。已完成：Arm 2 用觀測到的 B 區座標吸取（容許 `b_pick_tolerance_m`）、coordinator 新來源 `env_scene`、`vision.launch.py` 最多一顆手臂鏡頭、`arm_camera_switch`、`env_scene_bridge`、`vision_hardware.launch.py`、操作介面輪流顯示。env_camera_vision 暫用 `6b059eb` 匯入（使用者 2026-11-12 同意）；現場版本（A 區座標以黑框左緣為原點）推送後要換版並重新核對座標。coordinator 在手臂停妥後多等 0.5 s（env_scene 的處理與格位防抖延遲）才查詢。現場驗證見 HARDWARE_TEST_GUIDE V1，全部 NOT_RUN。2026-11-12 全專案檢查通過（`docs/evidence/project_check_20261112/`），只剩已知的 Gazebo 關閉逾時與一次 operator_tools 偶發（重跑 PASS）。設計與計畫：`docs/superpowers/`。
- 2026-11-12：格位 8 改用傾斜吸盤，模擬八物體放滿 8 格（evidence/tilt_slot8_20261112/README.md）。使用者決定：放寬吸盤朝下（模擬上限 9°）、傾斜目標調高接觸高度、移動模擬 cap_8 到 (-0.24, 0.05)、軸心到板緣用 5 mm、模擬相機先不處理。IK 取「離目前關節最近」的傾斜解（傾斜最小的解會撞底座）；接觸高度依吸盤或持物瓶蓋的傾斜補償。實機設定新增 `cup_radius_m`、`max_tool_tilt_deg`，要現場量。手臂軸心、格位、瓶蓋起點集中到 `scripts/field_layout.py`。整體檢查（evidence/system_audit_20261112/）：live graph 無型別、QoS、缺伺服器問題；`run_checks.sh` 改為擋下並判定殘留的 coordinator 等節點。Orin 的 `orin-source` 分支與 `3fd258c` 相同，更新步驟在 ORIN_DEPLOYMENT「從舊版更新」。

- 2026-11-12：階段 C 完成（evidence/phase_c_20261111/README.md）。模擬改成 11-11 實測場地：板 600×240 mm、兩臂軸心 world (±0.10, 0.125)、C 格位依實物編號（1、2 靠手臂，單號欄靠 B，x 0.135／0.170），A 區瓶蓋起點是格位鏡像，B 放置點 (0, 0)，`prefilled_slots` 改 0，介面格位圖 1 號在左上，`vision_pkg` 新增 `slot_one_corner`（實機 `top_left`）。模擬手臂相機移到 x ±0.15，arm1 校正誤差 1.15 → 0.70 mm（預算 1 mm）；順便修正 `sim.launch.py` 相機 TF 仍是舊左右。幾個測試寫死舊座標，已改（舊 pipeline 改讀 coordinator.yaml、先拿離 HOME 最近的瓶蓋）。最終 t1、t2：只有已知的 IK 16/18（cap_8、格位 8 吸盤朝下不可達）與冒煙測試的 Gazebo 關閉逾時 `FAIL`，其餘 `PASS`；八物體從空 C 區放完 7 件、格位 8 FAULT。發現：arm1 拿最靠近底座的 cap_1 時偏 28 mm（推測撞相鄰瓶蓋）。仍未解決：碰撞模型（WP11）、格位 8（C30）、模擬相機遮擋（C31、D7）、軸心偏移 5 或 15 mm。
- 2026-11-12：視覺端更新到上游 `64f28a0`（commit `e38c6c1`）：`cameras.yaml` 填入 V0 實測的三條 by-path，arm2 改 YUYV。三顆同 hub 頻寬不足，要把一顆手臂相機改接其他 root port（未在此驗證）。

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
- 韌體來源：`third_party/CM530_ROS_BRIDGE/18 ROS to CM530 ver. dual arm/APP/inc/arm_config.h`（第 18 版，協定 6，1 Mbps）。
- home_A=home_C=[256,512,512,512]（2026-11-13 起；第 17 版原始碼原本是 [90,567,712,825]、[590,567,712,825]）；原始位置值不是 URDF rad。CAD 零位 raw offset / 方向尚缺，已透過非同步問題詢問使用者。
- SolidWorks COM `SldWorks.Application` 註冊存在，尚未驗證自動化能否啟動。沒有授權修改來源 checkout；工作副本應置於 `cad/`，匯出與生成器改指向工作副本。
- CAD 主組合：`third_party/dual_arm_3d/雙臂_交付/完成_雙臂總組合.sldasm`；STEP：同目錄 `雙臂總組合.STEP`。
- 末端主零件 arm1 component_010、011、019；arm2 component_231、232、240。尚不能僅憑名稱假定哪個是鏡頭支架，需檢視幾何。
- WSL Ubuntu 中 ROS Jazzy / Gazebo Harmonic 已安裝；OpenCascade / VTK 在 `.cad-venv`。
- 建置：`bash scripts/build.sh`。不可直接重跑早期 `integrate_description.py`，會覆寫後續設定。

完成每項後更新待辦、證據路徑、假設與未完成部分。不得將假設的 HOME 轉換標為實機校正通過。
