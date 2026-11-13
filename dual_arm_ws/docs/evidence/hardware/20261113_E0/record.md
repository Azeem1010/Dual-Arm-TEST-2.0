evidence_kind: physical

階段：E0 ESP32 吸盤通電檢查（2026-11-13）
日期與時間：2026-11-13T13:12+08:00 起（ESP32 接上），E0 作動 13:26 與 13:28 兩輪
操作者／記錄者：現場成員／Claude Code 協助執行與記錄
程式版本（git rev-parse HEAD）：1e80cde1f1f73769c0cefe196b2b6275cb8d9893（工作區有未提交修改）
ESP32 序列埠：/dev/serial/by-id/usb-Silicon_Labs_CP2102_USB_to_UART_Bridge_Controller_0001-if00-port0（CM-530 為 FTDI 那一個）

## 結果

| 項目 | 狀態 | 內容 |
|---|---|---|
| 協定（命令回音） | PASS | 兩輪各 4 個命令都收到相同數值的回音，見 run_01.txt、run_02.txt |
| 模組與手臂對應 | PASS | 現場回報：命令 1、2 作用在 arm1，3、4 作用在 arm2 → `gripper.esp32_modules: {arm1: 1, arm2: 2}` |
| 回音時間 | PASS | 吸取 57～59 ms（第二輪第一個命令 257 ms），釋放 557～563 ms |
| 真空建立時間（arm1） | PASS | 約 1 秒吸穩（現場估計，不是碼表量）→ `vacuum_settle_s: 2.0`（hardware 與 prototype） |
| 吸住與釋放（arm1） | PASS | 手臂抬起懸空時瓶蓋一直吸住，釋放命令後掉下 |
| 真空建立、吸住與釋放（arm2） | PASS | 現場回報與 arm1 一致：約 1 秒吸穩、懸空吸住、釋放後掉下 |
| 上電／開機時泵、閥誤動作（GPIO12 strapping） | PASS | 兩次開機（線材脫落後重新上電、agent 重開造成的重置）現場都沒看到誤動作 |
| 斷電後自動重連 | FAIL | 重新上電後 ESP32 沒有連上 agent，要重開 agent 才恢復（韌體只試連一次） |

韌體沒有真空感測，回音只代表繼電器被驅動。模組對應是現場目視回報，沒有錄影。

## 韌體

ESP32 原本的韌體不是專案預期的版本：節點 `esp32_suction_node`，只訂閱 `/suction_cmd`（`std_msgs/Bool`），沒有 status。本機 `~/.platformio/microros_suction/build/esp32dev/firmware.bin`（2026-10-01）也是這個舊版。

經現場要求重新燒錄：

1. `git clone https://github.com/ray000518/micro-ros.git`，`git checkout 0c28c7f`，專案 `mircorostest/`
2. 現場已改接線，所以在本地改腳位（見 firmware_pin_change.diff）：泵 1 4→12、閥 1 5→13、泵 2 18→25、閥 2 19→26。其他程式不變。**上游 repo 仍是 4/5/18/19。**
3. `~/.platformio/penv/bin/pio run -e esp32dev`，然後加上 `-t upload --upload-port <ESP32>`。燒錄 hash 驗證通過。firmware.bin sha256 `baab2842b3702f3e7bfdb2332098c316f9bb29003168c934e043ce990e4e74cf`
4. agent：`ros2 run micro_ros_agent micro_ros_agent serial --dev <ESP32> -b 115200 -v4`。打開序列埠時 ESP32 會自動重開並連上，不用按 EN。
5. `ros2 topic info -v` 確認：`suction_controller_node` 訂閱 `/suction_command`，發布 `/suction_status`。

（同一天第一次燒錄的是未改腳位的 0c28c7f，接著才換成新腳位版本。）

## E0 作動

腳本 e0_suction.py：送 1 → 等 5 s → 2 → 等 3 s → 3 → 等 5 s → 4，記錄回音時間。執行時 `hardware_prototype.launch.py` 正在跑（Coordinator 待命、沒有任務），手臂遠離工件，由現場確認。

## 真空建立（arm1）

腳本 e0_vacuum_arm1.py：送 1 → 等 10 s → 送 2。arm1 吸盤下放一顆瓶蓋，手機錄影。

- 第 0 次（約 13:32）：FAIL，腳本 IndentationError，沒有送出任何命令。
- 第 1 次 13:32:52：回音 384 ms／558 ms，見 vacuum_arm1_run_01.txt。
- 第 2 次 13:33:50：回音 58 ms／557 ms，見 vacuum_arm1_run_02.txt。

現場回報：「9.8 秒」（解讀為吸取到瓶蓋掉落，和 10 s 的設定一致）；吸穩「有一點點延遲」，經現場同意以約 1 秒記錄；手臂抬起懸空時一直吸住，時間到就掉下來。沒有分別記錄這兩次的結果。

## 真空建立（arm2）

腳本 e0_vacuum_arm2.py：送 3 → 等 10 s → 送 4。13:41:51，回音 58 ms／557 ms，見 vacuum_arm2_run_01.txt。現場回報「都與 arm1 一致」。

## 開機檢查

原本要按 EN，但測試時 ESP32 的線材脫落，板子斷電又重新上電：

1. agent 日誌（agent.log）在 1794548888.9 顯示 `server stopped`、`Serial port not found`，0.5 s 後序列埠重新出現、`running...`，之後 120 s 都沒有新的 session。ESP32 是否開機成功無法從這次確認。
2. 13:49:06 重開 agent（agent_02.log）。開序列埠時 ESP32 被重置，之後正常開機、建立 session、publisher 與 subscriber；`ros2 topic info -v` 看到 `suction_controller_node` 兩個 endpoint。
3. 現場回報：兩次開機泵和閥都沒有動。

判讀：GPIO12 在重置開機時沒有讓 ESP32 開不了機。重新上電沒有連上，比較可能是 ESP32 開機比 agent 重新打開序列埠早，韌體試連一次失敗後就不再試。

處理方式：ESP32 斷電、拔插 USB 之後，要重開 agent。打開序列埠時 ESP32 會被重置，然後重新連上。

## 異常或和手冊不同之處

- E0 規定不要啟動 Coordinator，但這次 prototype launch 一直開著；Coordinator 沒有送吸盤命令。
- 第一輪結束時腳本印出 `terminate called without an active exception`，是 rclpy 收尾的訊息，命令都已經送完。
- GPIO12 是 ESP32 的 strapping 腳（開機時高電位會把 flash 電壓設成 1.8 V）。這次開機正常，若之後偶爾連不上 agent，先檢查這一點。
