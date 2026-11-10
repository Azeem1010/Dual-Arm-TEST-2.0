# 開發規則（AI 助手與接手開發者）

## 開始前先讀

1. `docs/REQUIREMENTS.md`：完整需求
2. `docs/PROGRESS.md`：目前進度，最上面的段落最新；工作包與衝突清單在 `docs/MODIFICATION_PLAN.md`
3. `docs/SOURCE_AUDIT.md`：上游來源與韌體查核
4. `docs/RESUME.md`：中斷時的續接資訊

文件可能過時。下結論前，以 `docs/evidence/` 的最新紀錄和實際程式碼為準。

## 必須遵守

**狀態只能用** `PASS`、`FAIL`、`BLOCKED`、`NOT_RUN`。

**以下都不算通過：**

- 合成影像測試 ≠ 實體相機校正
- 序列埠 ACK ≠ 馬達到位，到位要用 `READ` 的實際回授判斷
- Gazebo 座標正確 ≠ 真實相機座標正確
- MoveIt 規劃成功 ≠ 實機可以安全執行
- Mock Serial 通過 ≠ 實機驗收
- 只檢查 XML ≠ Gazebo 驗收

**實機安全：**

- 校正、關節限位和回授都實測驗證前，實機維持停用。
- 不可填假的校正值，`calibration.yaml` 的空欄位是刻意的。
- 不可把模擬 HOME（`runtime.json`）複製到實機設定。
- 不可為了通過檢查而放寬限位；確實需要時要經使用者同意，並記錄原因。
- 驅動預設唯讀，不可改成預設可動作。
- 通訊逾時後不可自動重送，因為協定沒有指令編號。
- 沒有使用者明確授權，不可燒錄韌體或驅動馬達。

**來源與紀錄：**

- `third_party/` 不可修改，需要整合時複製到 `src/`。四個上游是 git submodule，版本鎖定在 `docs/sources.lock.json`；`moveit2` 只是本機除錯用，沒有納入版本控制。
- 指令的原始輸出放在 `docs/evidence/`，保留失敗紀錄，不要覆蓋成成功。
- 改了模型、launch、world 或校正，要重跑受影響的檢查。
- 修改 C/C++ 時，套用 `C:/Users/39165/.codex/skills` 的 Trail of Bits 技能，並跑 sanitizer。

## 環境與常用指令

開發環境是 WSL2 Ubuntu 24.04 + ROS 2 Jazzy。

```bash
bash scripts/run_checks.sh t0|t1|t2 OUT   # 分層檢查，哪種變更跑哪層見 docs/TEST_PLAN.md 第 4 節
bash scripts/build.sh                     # 完整建置，也會重新產生 named states
bash scripts/start_sim.sh gui             # 或 headless、mock
bash scripts/run_pipeline.sh --count 2    # 需要另開終端和乾淨的場景
python3 scripts/check_home_collision.py   # HOME 碰撞檢查，需先 source install/setup.bash
python3 scripts/test_cm530_mock.py        # CM-530 整合測試，不需硬體
(cd src/dual_arm_coordinator && python3 -m pytest -q -p no:cacheprovider test)   # coordinator 單元測試
(cd src/dual_arm_hmi && QT_QPA_PLATFORM=offscreen python3 -m pytest -q -p no:cacheprovider test)   # 操作介面單元測試
```

## 容易踩到的地方

| 情況 | 正確做法 |
|---|---|
| 想重跑 `scripts/integrate_description.py` | **不要跑**，它會覆寫後來的設定 |
| URDF 限位或 `<ros2_control>` | 要同時改 `scripts/generate_cad_robot.py` 和生成的 xacro，否則下次生成會被蓋掉 |
| `dual_arm.srdf` 的 HOME | 由 `validate_model.py` 依 `runtime.json` 產生，不要手改 |
| `transfer_pipeline.json` 顯示 `FAIL` | 流程跑完前的預設值就是 `FAIL`；先確認程序是否還在跑 |
| 指令裡設定 `PYTHONPATH=...` | 會蓋掉 ROS 路徑；要 import `rclpy` 時不要整個覆寫 |
| `build.sh`、舊 pipeline、`test_cm530_mock.py` 會覆寫 `docs/evidence/` 的舊紀錄 | 新結果另存到自己的子目錄，舊檔用 `git restore` 還原 |
| 從 Git Bash 呼叫 `wsl.exe bash -lc '...$VAR...'` | 變數會先被展開，指令會靜默出錯；寫成腳本再執行 |
| 已有模擬在執行 | 先用 `pgrep -af 'gz sim'` 確認，不要重複啟動 |
| Gazebo 關不掉 | 已知問題，launch 結束後可能要對殘留的 `gz sim` 送 SIGTERM |
| `tests/test_bridge.c` 有 11 項失敗 | 上游測試仍預期 HOME=512，實際韌體是 90／590 |
| `CM530_ROS_BRIDGE` 規格書寫 HOME 是 512 | 規格書過時，以 `arm_config.h` 和板上 `GET_HOME` 為準 |
| CAD 的 q=0 | 不是手臂伸直；伸直對應 q=(0, −35, −55, 0)° |

## 專案慣例

- 視覺、任務決策、運動規劃、控制和末端工具要分成獨立模組。
- 上游的 `vision_interfaces` 不可改動欄位或服務名稱。
- 只有一個程序可以持有 CM-530 序列埠。
- 完成一段工作後，更新 `docs/PROGRESS.md`、`docs/TEST_REPORT.md` 和 `docs/RESUME.md`，寫清楚沒完成和沒驗證的部分。
