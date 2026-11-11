# WP0 基準線

執行於 2026-11-09，commit `c7dfba3`，WSL Ubuntu、ROS 2 Jazzy。沒有修改任何程式、模型或校正檔。指令見 `wp0.sh`，時間與結束碼見 `00_context.txt`。

| 檢查 | 結果 | 內容 | 證據 |
|---|---|---|---|
| `scripts/build.sh` | PASS | 11 個套件，再重建 moveit_config | `01_build.log` |
| coordinator pytest | PASS | 8 項 | `02_coordinator_pytest.log` |
| vision adapter pytest | PASS | 10 項 | `03_vision_adapter_pytest.log` |
| vision_pkg pytest | PASS | 99 項 | `04_vision_pkg_pytest.log` |
| `cm530_hardware` colcon test | PASS | 29 個 gtest | `05`、`06` |
| `dual_arm_gripper` colcon test | PASS | 1 個 CTest 項目 | `05`、`07` |
| `test_cm530_mock.py` | PASS | 5 個階段 | `08_cm530_mock.log`、`cm530_mock/` |
| `run_pipeline.sh --count 2` | PASS | 74 個事件，兩物體經 B 放到 C | `11_pipeline.log`、`12_transfer_pipeline.json` |

以上都不代表實機驗收。pipeline 使用 Gazebo 真值，不是視覺驅動。

## 與既有紀錄的差異

1. **`cm530_hardware` 的「33 項」是重複計數。** `colcon test-result` 的 33 是 29 個 gtest 加上 4 個 CTest 包裝項目，實際測試案例是 29 個。
2. **Gazebo 關閉 `NOT_RUN`（本次方法不同）。** 本次把 SIGINT 送給整個 process group，launch 約 1 秒內結束，沒有殘留程序。`PROGRESS.md` 的 `FAIL` 是只對 launch 送 SIGINT，方法不同，不能據此改判通過。
3. **`12_transfer_pipeline.json` 的 `mode` 欄位寫 three-object**，但本次是 `--count 2`。這是腳本寫死的標籤。
4. **`arm1_controller` 的 spawner 記錄 `process has died`**（`09_sim_launch.log` 第 244 行），controller 實際為 active（`10_controllers.txt`）。與 `ROS_INTERFACES.md` 已知缺口第 10 項相同。

## 失敗的嘗試

第一次用 `wsl.exe bash -lc '...'` 執行，`wsl.exe` 先展開了 `$B`、`$rc`，輸出路徑變成 `/00_context.txt`，**建置實際沒有執行**，結束碼 0 不具意義，當時的測試輸出也沒有存檔。改用獨立腳本 `wp0.sh` 後重跑，上表都是重跑的結果。

## 舊證據的處理

這些腳本會覆寫 `docs/evidence/` 的 8 個受版本控制的舊檔（`colcon_build.log`、`moveit_rebuild.log`、`transfer_pipeline.json`、`cm530_mock_*.log`）。本次結果已存在此目錄，舊檔用 `git restore` 還原。`dual_arm.srdf` 重新產生後內容未變。

`wp0.sh` 的 sanitizer 檢查不在 WP0 範圍，`NOT_RUN`。
