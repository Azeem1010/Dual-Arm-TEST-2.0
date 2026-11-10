階段：SETUP 環境與建置
日期與時間：2026-11-10T14:26:10.652971+08:00
操作者／記錄者：Codex；現場操作者尚未提供姓名
程式版本：3fd258c8e81c3bada92df92ef9a95e5749ca5178（main）
實際輸入的指令與完整輸出：見 output.txt、install_output.txt、apt_policy_after_cleanup.txt；clone 進度未另存。
量測工具與解析度：系統指令；未進行實體量測
照片檔名：無
結果：FAIL

- 環境 PASS：aarch64、Ubuntu 24.04.5 LTS；初次可用磁碟空間 837 GB。
- 下載 PASS：main 與四個鎖定子模組完成；兩份必要現場手冊存在。
- 安裝 FAIL：退出碼 100。既有 ros2-apt-source 1.3.0~noble 使用 ros2.sources 內嵌金鑰；腳本新增 ros2.list，Signed-By 與既有來源衝突。
- 已完成的系統變更：升級 ca-certificates、curl、libcurl3t64-gnutls、libcurl4-openssl-dev、libcurl4t64；執行 universe 設定、寫入 ROS keyring。ROS 套件安裝尚未完成。
- 清理 PASS：備份新增 ros2.list 至本資料夾，將來源改名 ros2.list.disabled-20261110；保留原有 ros2.sources。apt-cache policy 退出碼 0。
- build.sh、dialout 設定、所有離線測試、mock 啟動：NOT_RUN，依流程在安裝失敗處停止。
- 沒有操作序列埠或硬體。未修改腳本、測試、third_party 或實機設定；未 commit/push。
- 待負責人確認既有 ros2-apt-source 的相容處理，再重新安裝與建置；失敗紀錄不可覆蓋。
