# 格位 8：傾斜吸盤（2026-11-12）

使用者決定：放寬「吸盤朝下」讓模擬放滿 8 格；傾斜目標調高接觸高度；移動模擬的 cap_8；軸心到板緣用 5 mm；模擬相機先不處理（D7）。執行環境 WSL2 Ubuntu 24.04、ROS 2 Jazzy、Gazebo Harmonic。各資料夾 `commit.txt` 是當時的 HEAD，修改都還在工作目錄。

## 最後的做法

| 項目 | 內容 |
|---|---|
| IK（`kinematics.py`） | 先找吸盤正朝下的解；沒有時才在 `motion.max_tool_tilt_deg` 內找傾斜解，取「離目前關節最近」的那一個（沒有 seed 時取傾斜最小） |
| 傾斜上限 | 模擬 9°（實物示教格位 8 約 8.7°）；實機範本留空，要現場量 |
| Gazebo 吸盤外掛 | 角度門檻 10°（留 1° 給追蹤誤差），垂直容差 1 → 2 mm |
| 接觸高度（運動 gateway） | 傾斜時目標提高：空手用 `cup_radius_m × sin(吸盤傾斜)`；持物用 `cap_radius_m × sin(瓶蓋傾斜)`，再加上吸取時多抬的高度。正朝下不變 |
| 設定 | 新增 `heights.cup_radius_m`（模擬 0.009）、`motion.max_tool_tilt_deg`（模擬 9.0），實機範本兩者都是 null |
| 模擬 cap_8 起點 | (-0.17, -0.055) → (-0.24, 0.05)，正朝下可取、不被 HOME 的手臂擋住（`scripts/field_layout.py`） |
| 單一來源 | 手臂軸心、C 格位、瓶蓋起點集中在 `scripts/field_layout.py`，6 個腳本改為引用 |

## 過程（每一輪的紀錄都保留）

| 資料夾 | 改動 | 結果 |
|---|---|---|
| `t1_min_tilt/`、`sim_min_tilt/`、`t2_stopped_min_tilt/` | 傾斜解取「傾斜最小」、上限 10° | IK 18/18；八物體放 7 件，格位 8 MoveIt 判定 `arm2_cad_link_2` 撞 `arm2_base_link`。在 MoveIt mock 掃描格位 8 的解：肩膀前傾那一支一路相撞，較低那一支（實物 8.7° 示教也在這側）5.5°～10° 都不撞。t2 中途停止 |
| `sim_stale_coordinator/`、`t2_stale_coordinator/` | 改成「離目前關節最近」、上限 9° | 無效：前一輪停止時留下的 coordinator 搶答服務，所有結果都是舊狀態。已清掉；`run_checks.sh` 因此改成把 coordinator 等節點列入檢查 |
| `t1_before_lift/`、`sim_rim_contact/` | 同上，重跑 | 放 6 件；arm1 傾斜下降到 cap_8 時吸盤邊緣先碰到瓶蓋，停在 1.00 mm 外 |
| `t1_cup_lift_only/`、`sim_cup_lift_only/`、`t2_cup_lift_only/` | 加入吸盤邊緣的高度補償 | 吸起 cap_8；放到 B 區時瓶蓋跟著歪 9°，停在 2.63 mm 外。`faults`、兩物體、運動 gateway、操作工具 PASS |
| `t1_cap_tilt/`、`sim_cap_tilt_only/`、`t2_cap_tilt/` | 加入持物瓶蓋的傾斜補償 | 停在 1.36 mm 外：吸取時多抬的 1.4 mm 讓瓶蓋掛得更低 |
| `t1_tilted_cap8_shift/`、`sim_tilted_cap8_shift/` | 再補上吸取時多抬的高度 | cap_8 放到 B 區後，arm2 在 B 標準點吸取 `fault:no_contact`：傾斜吸起的瓶蓋放下時先以邊緣著地再倒平，中心偏約 1 mm |
| `final_t1/`、`final_sim/`、`final_t2/` | cap_8 移到 (-0.205, 0.015) | t1、gtest、八物體（8 格全滿，`FULL`）、`faults`、兩物體、運動 gateway、操作工具 PASS；視覺取料 FAIL：該位置被 HOME 的手臂擋住一部分，arm1 校正誤差 2.21 mm |
| `final2_t1/`、`final2_t2/`、`final2_sim/` | cap_8 移到 (-0.24, 0.05) | 見下方 |

## 最終結果

最後的程式與場景（cap_8 在 (-0.24, 0.05)）。`final_*` 那一輪的程式相同，只差 cap_8 位置，其中與 cap_8 無關的步驟沿用。

| 檢查 | 結果 | 紀錄 |
|---|---|---|
| t1：模型與場景產生、`test_cad_pose`、建置、IK、可達性 | PASS；IK 18/18，只有格位 8 用到傾斜（無 seed 時 4.96°） | `final2_t1/` |
| 單元測試 coordinator／介面／vision、HOME 碰撞、HOME | PASS（293／293／100） | `final_t1/` |
| 吸盤外掛 gtest | PASS | `final_gripper_test.log` |
| 八物體回歸（從空 C 區） | PASS：8 件全部放好，任務結束在 `FULL`，真值 8 格都有瓶蓋 | `final2_sim/` |
| `faults` 情境 | PASS | `final_sim/` |
| 兩物體回歸、運動 gateway（格位 8 傾斜接受、需 22° 的目標拒絕）、操作工具 | PASS | `final_t2/` |
| 視覺校正、偵測探測、視覺取料 | PASS；arm1 校正誤差 0.70 mm（預算 1 mm） | `final2_t2/` |

## 發現

- 四軸手臂在格位 8 只有「肩膀前傾」與「肩膀較低」兩支傾斜解；傾斜最小的解在前傾那支，CAD 模型中會撞底座。實機示教用的是較低那支。
- 傾斜吸取的瓶蓋放下時會偏移約 1 mm。實機若必須在很遠處吸瓶蓋，B 區要有位置修正（視覺）才能讓 arm2 接得到。
- 吸盤傾斜時邊緣比中心低 `半徑 × sin(傾斜)`；實機矽膠吸盤會變形，要壓多近需現場量。
