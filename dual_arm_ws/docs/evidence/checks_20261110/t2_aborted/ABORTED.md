# T2 中止（2026-11-10）

使用者要求暫停，`run_checks.sh t2` 在 `regress_two` 執行中被停止。結果只有 `summary.tsv` 前三項：

| 步驟 | 結果 |
|---|---|
| `smoke_runtime_sim` | exit 0（這次關閉檢查也通過） |
| `analyze_sim_images` | exit 0 |
| `validate_sim_coordinates` | exit 0 |
| `regress_two` 之後全部 | `NOT_RUN`（中止） |

中止時腳本沒有執行最後的證據整理。這三項覆寫的已追蹤證據（模擬影像、`sim_runtime.json`、`sim_launch.log`、`sim_controllers.log`）已先複製到 `outputs/`，再用 `git restore` 還原。WSL 內的模擬程序已全部結束，沒有殘留。之後要完整重跑 T2。
