#!/usr/bin/env bash
# Read-only detection; never writes to the Pad or a disk.
set -euo pipefail
lsusb
if ! lsusb -d 1f3a:efe8 | grep -q .; then
    echo 'No Allwinner FEL device (1f3a:efe8) detected.' >&2
    echo 'Use a data cable to the rear CAM port. Power off, hold the outer recessed button, then power on.' >&2
    exit 1
fi
sunxi-fel version
