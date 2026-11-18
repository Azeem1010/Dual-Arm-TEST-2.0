#!/bin/bash
set -u
cd "/mnt/e/dual_arm_system/dual_arm_ws/third_party/CM530_ROS_BRIDGE/18 ROS to CM530 ver. dual arm"
OUT="$1"; mkdir -p "$OUT"
for SAN in "" "-fsanitize=address,undefined -fno-omit-frame-pointer -g"; do
  echo "== bridge test, flags: ${SAN:-none}"
  gcc -std=gnu89 -Wall -Wextra -Werror $SAN -IAPP/inc APP/src/bridge.c APP/src/ax12.c APP/src/dynamixel.c tests/test_bridge.c -o "$OUT/test_bridge" && "$OUT/test_bridge"; echo "exit=$?"
  echo "== led test, flags: ${SAN:-none}"
  gcc -std=gnu89 -Wall -Wextra -Werror $SAN -Itests/fakes -IAPP/inc APP/src/arm_led.c tests/test_arm_led.c -o "$OUT/test_arm_led" && "$OUT/test_arm_led"; echo "exit=$?"
done
