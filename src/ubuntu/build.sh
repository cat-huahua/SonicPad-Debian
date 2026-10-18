#!/usr/bin/env bash
# Ubuntu userspace with the upstream Sonic Pad R818 board support package.
set -Eeuo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
[[ $EUID == 0 ]] || { echo 'Run with sudo.' >&2; exit 1; }
mode=${1:-all}
[[ $mode == all || $mode == rootfs || $mode == pack ]] || exit 2
mkdir -p work cache out
exec 9>work/build.lock
flock -n 9 || { echo 'Another build is running.' >&2; exit 1; }
if [[ $mode != pack ]]; then
    ./create-rootfs.sh
fi
if [[ $mode != rootfs ]]; then
    ./pack.sh
fi
