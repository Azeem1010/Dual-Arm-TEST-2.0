#!/usr/bin/env python3
"""V0 唯讀擷取：依 USB 埠（by-path）各抓一張原始畫面（不旋轉），印出平均亮度與清晰度。
用法：python3 capture_all.py <標籤>   → snapshots/<標籤>_port<埠>_<時間>.jpg
"""
import cv2, sys, time, datetime
PORTS = ["4.4.1", "4.4.3", "4.3"]
tag = sys.argv[1]
ts = datetime.datetime.now().strftime("%H%M%S")
print(f"# {datetime.datetime.now().isoformat(timespec='seconds')} tag={tag}")
for p in PORTS:
    dev = f"/dev/v4l/by-path/platform-3610000.usb-usb-0:{p}:1.0-video-index0"
    cap = cv2.VideoCapture(dev, cv2.CAP_V4L2)
    cap.set(cv2.CAP_PROP_FRAME_WIDTH, 640); cap.set(cv2.CAP_PROP_FRAME_HEIGHT, 480)
    ok, f, t0 = False, None, time.time()
    while time.time() - t0 < 2.5:
        r, g = cap.read()
        if r: ok, f = r, g
    cap.release()
    if not ok:
        print(f"port {p}: 擷取失敗"); continue
    gray = cv2.cvtColor(f, cv2.COLOR_BGR2GRAY)
    fn = f"snapshots/{tag}_port{p}_{ts}.jpg"
    cv2.imwrite(fn, f)
    print(f"port {p}: mean={gray.mean():6.1f} sharp={cv2.Laplacian(gray, cv2.CV_64F).var():8.1f} -> {fn}")
