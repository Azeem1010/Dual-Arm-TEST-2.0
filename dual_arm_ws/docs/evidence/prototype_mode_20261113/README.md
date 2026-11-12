# 實機 Prototype 模式（2026-11-13）

設計：[prototype 設計](../../superpowers/specs/2026-11-13-hardware-prototype-mode-design.md)；計畫：[prototype 計畫](../../superpowers/plans/2026-11-13-hardware-prototype-mode.md)。全部在 Windows 的 WSL Ubuntu（Jazzy）執行，沒有接實機。

| 紀錄 | 內容 | 結果 |
|---|---|---|
| `hardware_show_args.log`、`prototype_show_args.log` | 兩個 launch 都能解析；`hardware.launch.py` 的 `require_estop` 預設 `true` | PASS |
| `build.log`、`launch.log`、`steps.log` | Mock Serial 跑 `hardware_prototype.launch.py`（驅動用 mock 校正檔，coordinator 用 `home_calibration_file:=calibration_prototype.yaml`）：coordinator 印出 PROTOTYPE 警告、沒有 BLOCKED；上扭力、啟動控制器；`/dual_arm/go_home` 接受，兩臂 `at_home` 變 true；`/dual_arm/start` 接受，任務 busy | PASS |
| 同上 | 沒有相機，任務停在等 env_scene 的場景結果，關閉時取消（`Task canceled`）。第一次執行 coordinator 因 mock 校正檔不是 `physical` 而退出（嚴格檢查，正確），因此加了 `home_calibration_file` | 預期限制 |
| `final_build.log` | colcon build coordinator、hmi、bringup、cm530_hardware、controllers | PASS |
| `test_coordinator.log` | coordinator 單元測試 | PASS，328 |
| `test_hmi.log` | 操作介面單元測試（含上扭力接通後重跑） | PASS，307 |
| `test_vision_adapter.log` | vision adapter | PASS，36 |
| `test_cm530.log` | cm530_hardware colcon test | PASS，43 |
| `test_cm530_mock.log`、`cm530_mock_rerun/` | `scripts/test_cm530_mock.py`（嚴格的 hardware.launch.py 路徑，含新的 `require_estop` 參數）；它覆寫的追蹤證據已還原，新輸出放在 `cm530_mock_rerun/` | PASS |

未完成：

- **實機 NOT_RUN。** 實機跑的結果記到 `docs/evidence/hardware/<日期>_PROTOTYPE/`，不算任何 H 階段 PASS。
- 介面「上扭力」只在 prototype 接通，Mock Serial 測試是用 `ros2 control` 指令做的，介面按鈕只有單元測試。
- 估計值可能讓手臂偏好幾公分；`esp32_modules` 是猜的（E0 未測）。
