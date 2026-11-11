#!/usr/bin/env bash
cd /mnt/e/dual_arm_system/dual_arm_ws || exit 90
python3 scripts/capture_readme_images.py publish docs/evidence/readme_images/raw docs/images
echo "publish_exit=$?"
