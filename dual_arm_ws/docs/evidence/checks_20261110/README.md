# 分層檢查（2026-11-10，A 區在手臂右方的配置）

這是第一次使用 `scripts/run_checks.sh` 的紀錄，起點是 commit `55196a5`，工作目錄裡還有這一階段未提交的文件與工具修改（各資料夾的 `commit.txt`、`git_status_before.txt`）。執行環境：WSL Ubuntu 24.04 + Jazzy。每個資料夾的 `summary.tsv` 記著各步驟的退出碼、耗時與日誌。

| 資料夾 | 指令 | 內容 |
|---|---|---|
| `t1/` | `KEEP_EVIDENCE=1 bash scripts/run_checks.sh t1 …` | 完整一次 t1 |
| `t2_aborted/` | `KEEP_EVIDENCE=1 … t2 …` | 使用者要求暫停，在 `regress_two` 中止，見其中的 ABORTED.md |
| `t2/` | `KEEP_EVIDENCE=1 … t2 …` | 完整一次 t2 |
| `t2_rerun/` | `KEEP_EVIDENCE=1 STEPS="smoke_runtime_sim legacy_pipeline_two operator_tools generate_sim_vision_calibration probe_sim_vision vision_pick" … t2 …` | 修正後重跑失敗的步驟 |
| `t2_operator_tools/` | `STEPS="operator_tools" … t2 …` | 第二次修正後重跑 operator_tools |

`outputs/` 是被覆寫的已追蹤證據的新版本，`replaced/` 是 HEAD 版本。因為加了 `KEEP_EVIDENCE=1`，新版本留在 `docs/evidence/` 原處，README 截圖也發布到 `docs/images/`。

## t1

除 `test_ik` 外全部 exit 0。

| 步驟 | 結果 |
|---|---|
| 產生模型與場景、`test_cad_pose`、`build` | PASS |
| `report_home_poses` | PASS |
| `test_ik` | FAIL，16/18，與舊配置是同兩點的鏡像（arm1 (-0.2, -0.085)、arm2 格位 1） |
| `report_reach` | 瓶蓋起始位置 4/8 可達（cap_3～6），格位 7/8（格位 1 搆不到），與舊配置相同。這是量測報告，退出碼 0 |
| coordinator／HMI／vision_pkg pytest | PASS，272／262／99 |
| HOME 碰撞 | PASS |
| `measure_slot_adjustment`、`verify_slot_proposals`、`slot_self_collision` | PASS；位移研究在新配置重跑，見 SLOT_ADJUSTMENT.md |

## t2

| 步驟 | `t2/` | 修正後 | 說明 |
|---|---|---|---|
| `smoke_runtime_sim` | FAIL | FAIL（`t2_rerun/`） | 功能項目全部 PASS，只有關閉檢查 FAIL（Gazebo 收到 SIGINT 後 5 秒內沒結束）。這個問題時有時無：`t2_aborted/` 那次是 PASS，其他兩次都是 FAIL。沒有修改 |
| `analyze_sim_images`、`validate_sim_coordinates` | PASS | — | |
| `regress_two` | PASS | — | |
| `legacy_pipeline_two` | FAIL | PASS（`t2_rerun/`） | 原因見下方 1 |
| `motion_gateway`、`safety_supervisor` | PASS | — | MoveIt mock |
| `operator_tools` | PASS | FAIL（`t2_rerun/`），再修正後 PASS（`t2_operator_tools/`） | 原因見下方 3 |
| `generate_sim_vision_calibration`、`probe_sim_vision` | PASS | PASS | |
| `vision_pick` | FAIL | PASS（`t2_rerun/`） | 原因見下方 2 |
| README 截圖（`readme_demo_start`、`readme_capture`、`readme_demo_status`、`readme_publish`） | PASS | — | coordinator 兩物體搬運，截圖已發布到 `docs/images/` |
| 殘留程序 | 1 行 | 0 行 | 原因見下方 3 |

### 失敗原因與修正

1. **`legacy_pipeline_two`：** `demo_transfer_pipeline.py` 在程式裡把 `ROS_DOMAIN_ID` 設成 43（README 的舊 demo 說明也是 43），但 t2 的模擬開在 47，demo 收不到任何訊息，90 秒後以 `Simulator not ready` 停止。修正：`run_checks.sh` 在這一步用 43 啟動模擬。demo 本身沒有修改。
2. **`vision_pick`：** `test_vision_pick_sim.py` 把搆不到的 cap_1、cap_2 停放在 (0.35, 0.30)。舊配置的 C 區在 −x，這個停放點不屬於任何區；新配置的 C 區是 x ≥ 0.10 的整側，兩個瓶蓋就被算進 C 區，C 區數量 4 和紀錄的 2 不符。無校正那一段和兩物體搬運都因此停在同一個錯誤，不是測試要確認的原因，四項檢查都是 FAIL。修正：停放點改成 (−0.35, 0.30)，在 A 區外緣（x −0.30）之外。這是配置改版時漏改的地方。
3. **`operator_tools` 與殘留程序：** 這個測試另外開了一個靜態 TF。原本用 `ros2 run … & kill $!` 只停掉外層的 `ros2 run`，`static_transform_publisher` 留下來（`t2/leftover_processes.txt`）。第一次修正改用 `setsid` 與 process group，結果 TF 沒有及時出現，`manual_execute` 查不到 `arm1_base`（`t2_rerun/operator_tools.json`）。第二次修正直接啟動 `static_transform_publisher` 程式本身，等待 3 秒，結束時 `kill` 並 `wait`，PASS，沒有殘留。

另外加了 `STEPS` 環境變數，只重跑指定的步驟，這次的重跑就是用這個方式。

## 範圍

t2 不含回歸 `faults`、`batch`、視覺取料連續 3 次，也不含 CM-530 的 gtest、Mock Serial 與 sanitizer（TEST_PLAN.md 第 4 節）。這幾項這次都是 NOT_RUN。實機全部 NOT_RUN。板寬與軸心到板緣的距離仍是 CAD 值。
