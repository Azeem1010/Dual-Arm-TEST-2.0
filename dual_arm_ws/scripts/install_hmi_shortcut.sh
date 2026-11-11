#!/usr/bin/env bash
# Adds the operator interface to the application menu, and to the desktop when one exists.
# For the Orin or any Ubuntu desktop. Run once after building the workspace.
set -euo pipefail
WS="$(cd "$(dirname "$0")/.." && pwd)"
APPS="${XDG_DATA_HOME:-$HOME/.local/share}/applications"
FILE="$APPS/dual_arm_hmi.desktop"
mkdir -p "$APPS"
cat > "$FILE" <<EOF
[Desktop Entry]
Type=Application
Name=Dual Arm Operator
Name[zh_TW]=雙臂系統操作介面
Comment=Start, stop and watch the dual arm system
Exec=bash -c 'cd "$WS" && source install/setup.bash && exec ros2 run dual_arm_hmi hmi'
Icon=applications-engineering
Terminal=false
Categories=Utility;
EOF
chmod +x "$FILE"
echo "Installed $FILE"
DESKTOP="$(xdg-user-dir DESKTOP 2>/dev/null || echo "$HOME/Desktop")"
if [ -d "$DESKTOP" ]; then
  cp "$FILE" "$DESKTOP/"
  chmod +x "$DESKTOP/dual_arm_hmi.desktop"
  # GNOME asks before running a desktop file it has not been told to trust.
  gio set "$DESKTOP/dual_arm_hmi.desktop" metadata::trusted true 2>/dev/null || true
  echo "Copied to $DESKTOP"
fi
