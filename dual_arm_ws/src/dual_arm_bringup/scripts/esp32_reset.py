#!/usr/bin/env python3
"""Restart the ESP32 suction board through its USB bridge, like pressing EN.

The firmware looks for the micro-ROS agent only while it boots, so a board that
booted before the agent never connects (field runs 2026-11-17/18: someone had to
press EN after every start). On the dev board RTS drives EN through the
auto-reset transistors: RTS on holds EN low. DTR stays off, so IO0 stays high
and the board boots its program, not the bootloader.

Tested 2026-11-18 on the Orin: with the agent running and no pulse, no session in
15 s; after this pulse the session came up in 2.2 s. The agent keeps the port
open meanwhile; the line settings are left as the agent set them (115200).
"""
import argparse
import sys
import time

import serial


def pulse(port, baud, low_s):
    link = serial.Serial()
    link.port, link.baudrate = port, baud
    # Set before opening, or opening asserts both lines and holds the board in reset/bootloader.
    link.dtr, link.rts = False, False
    link.open()
    try:
        link.rts = True
        time.sleep(low_s)
        link.rts = False
    finally:
        link.close()


def main():
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument('port')
    parser.add_argument('--baud', type=int, default=115200)
    parser.add_argument('--low-s', type=float, default=0.1, help='how long EN is held low')
    args = parser.parse_args()
    try:
        pulse(args.port, args.baud, args.low_s)
    except (OSError, serial.SerialException) as error:
        print(f'ESP32 自動重開失敗（{error}）：請手動按 EN', file=sys.stderr)
        return 1
    print(f'ESP32 已自動重開（{args.port}）')
    return 0


if __name__ == '__main__':
    sys.exit(main())
