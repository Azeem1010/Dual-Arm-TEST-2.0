# 2026-11-10 模擬配置改為 A 區在手臂右方

依據：2026-11-10 H1（arm1）實測，A 區在手臂自身右方、j1 方向 +1（[../hardware/README.md](../hardware/README.md)）。使用者依實測決定 D0。只驗證模擬；實機 `NOT_RUN`。

## 修改

- 模型：原始 CAD 組合（兩支手臂與平台）整組繞 world Z 轉 180°，不鏡射。arm1 在 (-0.10, +0.08725)、arm2 在 (+0.10, +0.08725)，都面向 -Y；A 區在 -X，使用者看到 A | B | C。取代 commit `c7dfba3` 的鏡像配置（A 在手臂左邊）。
- 所有場地座標相對 `c7dfba3` 只把 x 取負號：A 區 x = -0.30～-0.10、C 區格位 x = 0.1675 / 0.1325、瓶蓋、模擬相機、視覺基座原點。格位編號規則不變，格位 1、2 仍在 y = -0.090（靠使用者，2026-11-09 口述，未實測）。
- `runtime.json`：兩臂 j1 方向 −1 → +1（arm1 實測，arm2 假設）。`raw_at_cad_zero` 不變，所以 home_A 是自身右轉 30°、home_C 是自身左轉 22.87°，TCP 與舊配置互為 x 鏡像。
- `truth.py`：判斷 B／C 區不再假設 A 在 +X，改由 `a_min_xy_m`、`a_max_xy_m` 推得。
- `vision_sim`、`hmi_sim` launch 對環境相機設 `field.reverse: true`（模擬俯視影像左側是 -X，也就是 A 區）。實機的 `env_vision.yaml` 維持 `false`，要在 V0 依相機安裝方向決定。
- 板寬（CAD 300 mm，實測約 235 mm）與軸心到板緣距離（CAD 板內約 63 mm，實測板外約 10 mm）**沒有改**，留待現場直接量測後處理。

## 結果

| 檢查 | 結果 | 檔案 |
|---|---|---|
| 產生模型、場景；`test_cad_pose.py`（264 個元件 = CAD 整組轉 180°） | PASS | 01_generate.log |
| `build.sh`（13 套件、模型結構、MoveIt 設定） | PASS | 02_build.log |
| `report_home_poses.py` | PASS | 03_home_poses.log；home_A TCP (-166.3, -27.7, 140.8) mm，home_C (151.6, -35.0, 140.8) mm，都在限位內 |
| `test_ik.py` | FAIL（16/18，與改版前相同） | 04_ik.log；arm1 (-0.2, -0.085) 與 arm2 格位 1 (0.1675, -0.09) 搆不到，是改版前兩個失敗點的鏡像 |
| coordinator pytest | PASS（259） | 05_coordinator_pytest.log。第一次 5 項失敗，原因是測試夾具：停放點 (0.5, 0.5) 落到新的 C 側、視覺替身仍回傳 A 在 y > 0。修正夾具後通過；第一次的輸出被覆寫，未保留 |
| HMI pytest | PASS（262） | 06_hmi_pytest.log |
| vision_pkg pytest | PASS（99） | 07_vision_pytest.log |
| HOME 碰撞（3 組姿態） | PASS | 08_sim_checks.log、../home_collision.json |
| 格位候選自碰撞（3 種位移，各 0 / 248 invalid） | 無效 | 08_sim_checks.log。**更正（同日稍後）：** 這項讀的是 `slot_adjustment.json` 裡舊配置算出的關節解，結果不代表新配置。同一份日誌裡 `verify_slot_proposals.py` 其實是 FAIL（traceback：toward_arm_y 在格位 1 FK 不符），被錯誤的 exit 碼蓋過，當時漏報。重跑位移研究後兩項都通過，見 ../checks_20261110/t1/ |
| 冒煙測試（控制器、回授、三相機、MoveIt 規劃） | 項目 PASS；整體 FAIL | 08_sim_runtime_first.json、10_sim_runtime_rerun.json：兩次都是 Gazebo 收到 SIGINT 後 5 秒內沒結束，被判 `shutdown: FAIL`。舊紀錄（`gazebo_pipeline_launch.log`、HMI stage2 launch 日誌）也出現過同一訊息，判斷是既有的間歇問題，與配置無關的推論**未驗證** |
| 模擬影像格位／座標驗證 | 與改版前相同 | ../sim_detection.json（環境相機 grid FAIL，改版前也是 FAIL；手臂相機 PASS）、../sim_coordinate_validation.json（三顆 PASS） |
| 舊 pipeline 兩物體搬運，第一次 | FAIL | 09_transfer_pipeline_FAIL.json：`demo_transfer_pipeline.py` 的「物件已離開 B」判斷寫死 `x > -0.10`，鏡像時漏改。已改成 `x < 0.10` |
| 舊 pipeline 兩物體搬運，修正後 | PASS | 10_sim_rerun.log、11_transfer_pipeline.json；Gazebo 真值，放到格位 3、4 |
| `test_motion_gateway.py`、`test_operator_tools.py`、`test_safety_supervisor.py`（MoveIt mock，各自新開場景） | PASS | 14_mock_tests.log、14_*.json；無殘留程序 |
| coordinator `demo_pick_place.launch.py` 一輪 | PASS（SUCCEEDED，completed 1） | 12_demo_launch.log、12_demo_status.txt；結束後無殘留程序（13_leftover.txt） |

**08_sim_checks.log 的 `exit` 數字不可信：** 該腳本的 `echo "... $(date) exit $?"` 先執行 `$(date)`，`$?` 一律是 0。各項結論以輸出內容判讀；10_sim_rerun.log 已修正，exit 數字是實際值。

被覆寫的上一版證據存在 [../before_a_right_layout_20261110/](../before_a_right_layout_20261110/)。

## 未做

- 視覺驅動的取料（`test_vision_pick_sim.py`）與 `probe_sim_vision.py`：座標已改，未重跑。
- `measure_slot_adjustment.py`（格位位移研究）：本階段未重跑；已在 ../checks_20261110/t1/ 補跑。
- README 截圖（`capture_readme_images.py`）：本階段未重新擷取；已在 ../checks_20261110/t2/ 重新擷取並發布到 docs/images/。視覺取料與 probe 的重跑結果也在 ../checks_20261110/。
