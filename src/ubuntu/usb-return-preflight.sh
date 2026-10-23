#!/bin/sh
set -eu
case "${1:-}" in postinst) exit 0;; preinst) ;; *) exit 1;; esac
slot=${2:-}
case "$slot" in A|B) ;; *) exit 1;; esac
abort() {
    echo "Return-to-Ubuntu aborted: $*" >&2
    fw_setenv swu_mode '' || true
    fw_setenv swu_next '' || true
    exit 1
}
ubuntu=$(fw_printenv -n sonicpad_ubuntu_slot) || abort 'Missing installer slot map'
official=$(fw_printenv -n sonicpad_official_slot) || abort 'Missing official slot map'
[ "$slot" = "$ubuntu" ] || abort 'Selected slot does not contain the recorded Ubuntu installation'
case "$ubuntu:$official" in A:B|B:A) ;; *) abort 'Invalid slot map';; esac
[ "$(fw_printenv -n boot_partition)" = "boot$official" ] || abort 'Not running the official slot'
[ -b "/dev/by-name/boot$slot" ] && [ -b "/dev/by-name/rootfs$slot" ] || abort 'Missing Ubuntu partitions'
[ "$(blkid -s LABEL -o value "/dev/by-name/rootfs$slot")" = UBUNTUROOT ] || abort 'Ubuntu filesystem label mismatch'
echo "Selecting existing Ubuntu slot $slot; no partition images will be written."
