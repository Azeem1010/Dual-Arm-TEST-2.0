# V0 相機對應（遮蓋測試，2026-11-11 16:08～16:11）

方法：capture_all.py 依 USB 埠各擷取一張原始畫面；測試人員依序遮住一顆實體相機，平均亮度掉到 ≈1 的埠即為該相機。

| 角色 | 路徑（by-path） | 裝置（當下） | 型號／序號 | 基準亮度 | 遮住時亮度 |
|---|---|---|---|---|---|
| env_cam | /dev/v4l/by-path/platform-3610000.usb-usb-0:4.3:1.0-video-index0 | video4 | AONI Live Streamer CAM 310P／20210120002 | 99.5 | 0.5 |
| arm1_cam | /dev/v4l/by-path/platform-3610000.usb-usb-0:4.4.3:1.0-video-index0 | video2 | Alcor USB 2.0 uvc pc Camera／無序號 | 130.2 | 1.1 |
| arm2_cam | /dev/v4l/by-path/platform-3610000.usb-usb-0:4.4.1:1.0-video-index0 | video0 | Alcor USB 2.0 uvc pc Camera／無序號 | 125.5 | 0.6 |

每輪遮蓋時，其他兩埠亮度維持 116～127，無交叉。

env_cam 另有 by-id：/dev/v4l/by-id/usb-SHENZHEN_AONI_ELECTRONIC_CO.__LTD_Live_Streamer_CAM_310P_20210120002-video-index0
arm1／arm2 兩顆 Alcor 無序號，by-id 名稱相同只剩一條連結（指向 video2），無法用 by-id 區分 → 與手冊「用 by-id」不符，待負責人決定是否改用 by-path（by-path 綁定實體 USB 插孔：Orin USB → hub 4 → hub 4.4 的 port 1／3，線不可互換）。

## arm1_cam 方向（2026-11-11 16:25）
- 暫定定義（文件未定義，待負責人確認）：人站在 arm1 底座後方面向手臂前方，看到的紙面為「正」；畫面上方應為手臂前方。
- 紙：寫「ARM1 R」與箭頭，箭頭由底座指向吸盤外側，紙在瓶蓋外側。
- 原始畫面 snapshots/orient_arm1_text_port4.4.3_162502.jpg：箭頭朝下、字上下顛倒且字母順序反轉（R 1 M R A 由左至右）→ 純 180° 旋轉，非鏡像。
- 轉 180° 預覽 snapshots/orient_arm1_text_port4.4.3_162502_rot180_preview.jpg：箭頭朝上、「ARM1 R」正讀。
- 結論：cameras.yaml 的 arm1_cam rotate: 180（2026-11-06）仍正確，不需修改 → 不需重做 arm1 校正。
- 附註：紙的擺放位置由測試人員口頭確認依示意圖擺放；底座後方俯視照片未提供。
- 狀態：PASS（依暫定定義）
