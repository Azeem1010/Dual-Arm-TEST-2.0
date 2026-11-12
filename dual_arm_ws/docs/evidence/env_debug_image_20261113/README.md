# env_scene 框線影像給操作介面（2026-11-13）

來源：`Azeem1010/Dual-Arm-TEST-2.0` 的 `env-scene-debug-image` 分支，commit `52a6518`（Orin 上做的修正），已快轉合入 main 並推送。

改動：

- `env_scene_node` 把 OpenCV 框線影像發布到 `/vision/env/debug_image`（`publish_debug_image`，預設開；場地找不到時也發布，畫面標 `FIELD NOT FOUND`）。實機原本沒有節點發布這個 topic（`vision_hardware.launch.py` 不啟動 `env_vision_node`），操作介面的環境相機只能顯示原始影像。
- `vision_hardware.launch.py` 新增 `show_debug`（Orin 桌面另開 OpenCV 視窗，預設 false）與 `publish_debug_image`（預設 true）。vision_pkg 的 include 改用 `GroupAction(scoped=True)`，避免它的 `show_debug:=false` 蓋掉 env_scene 的設定。
- 這是對 `src/env_scene`（上游 env_camera_vision `6b059eb` 的副本）的本地修改，上游還沒有；換版時要帶過去。

| 紀錄 | 內容 | 結果 |
|---|---|---|
| （commit 訊息） | Orin，只接環境相機、沒接 CM-530：框線影像約 7 fps、640x480 bgr8；`show_debug:=true` 開得出視窗；zone state valid；env_scene 10、vision_pkg 104、vision_adapter 36、hmi 298 | PASS（Orin 端回報，此處未重跑） |
| `wsl_build.log` | Windows 的 WSL Ubuntu 重建 `env_scene`、`dual_arm_bringup` | PASS |
| `wsl_env_scene_tests.log` | env_scene 上游 10 項測試 | PASS |
| `wsl_show_args.log` | `vision_hardware.launch.py --show-args`，含 `show_debug`、`publish_debug_image` | PASS |

未完成：

- 操作介面實際顯示框線畫面只有 Orin 端回報，這台 Windows 沒接相機，沒看到畫面。
- HSV 標定檔不存在時節點在畫框線前就返回，這時沒有框線影像，介面退回原始影像。
