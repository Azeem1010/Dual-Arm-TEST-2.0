#!/usr/bin/env python3
"""唯讀擺位輔助：反覆送 READ，顯示每軸與目標 raw 的差，協助人工扶到指定姿勢。

只透過 cm530_probe 的 Probe（白名單只允許 VERSION/PING/GET_HOME/READ）通訊，
不會送 TORQUE、AX、HOME、HOLD。任何逾時或異常回覆立即結束，不重送。
用法：
  python3 pose_guide.py --port /dev/serial/by-id/<控制板> --arm arm1 --target 90,567,712,825
Ctrl+C 結束；每筆讀值記錄到 --log（CSV）。
"""
import argparse
import csv
import datetime
import sys
import time

from dual_arm_coordinator.tools.cm530_probe import Probe, ProbeError, SerialPort


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--port', required=True)
    ap.add_argument('--arm', choices=('arm1', 'arm2'), required=True)
    ap.add_argument('--target', required=True, help='四個 raw，逗號分隔')
    ap.add_argument('--tol', type=int, default=5, help='視為對到的容許 raw（只用於顯示）')
    ap.add_argument('--period', type=float, default=0.3)
    ap.add_argument('--log', default=None)
    args = ap.parse_args()
    target = [int(v) for v in args.target.split(',')]
    assert len(target) == 4
    log_path = args.log or f'pose_guide_{args.arm}_{datetime.datetime.now():%Y%m%d_%H%M%S}.csv'

    status = 0
    last = None
    import os
    if os.path.exists(log_path):
        print(f'紀錄檔 {log_path} 已存在，為避免覆寫舊資料，請換一個 --log 檔名。')
        return 2
    try:
        port = SerialPort(args.port)
    except OSError as error:
        print(f'無法開啟序列埠（可能有其他程式占用，例如 manual_position_terminal.py）：{error}')
        return 3
    probe = Probe(port, 1.0)
    fh = open(log_path, 'x', newline='')  # 不覆寫既有紀錄
    with fh:
        log = csv.writer(fh)
        log.writerow(['time', 'j1', 'j2', 'j3', 'j4', 'd1', 'd2', 'd3', 'd4'])
        try:
            probe.prepare()
            print(f'目標 {args.arm} = {target}；容許 ±{args.tol} raw（1 raw ≈ 0.293°）。Ctrl+C 結束。')
            while True:
                pos = probe.send(f'READ,{args.arm}')
                diff = [p - t for p, t in zip(pos, target)]
                last = (pos, diff)
                log.writerow([datetime.datetime.now().isoformat(timespec='milliseconds'), *pos, *diff])
                cells = []
                for i, (p, d) in enumerate(zip(pos, diff), 1):
                    mark = 'OK' if abs(d) <= args.tol else ('調小' if d > 0 else '調大')
                    cells.append(f'j{i}={p:4d} 差{d:+5d} {mark:2s}')
                print('\r' + ' | '.join(cells) + '   ', end='', flush=True)
                time.sleep(args.period)
        except KeyboardInterrupt:
            pass
        except ProbeError as error:
            print(f'\n停止（不重送）：{error}')
            status = 1
        finally:
            port.close()
    print()
    if last:
        print(f'最後讀值 {args.arm}: {last[0]}  與目標差: {last[1]}')
    print(f'紀錄檔：{log_path}')
    return status


if __name__ == '__main__':
    sys.exit(main())
