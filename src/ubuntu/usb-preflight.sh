#!/bin/sh
# SWUpdate passes preinst/postinst and the destination slot in $2.
set -eu
stage=${1:-}
slot=${2:-}
case "$slot" in A|B) ;; *) echo 'Invalid destination slot' >&2; exit 1;; esac
package=t800-sonic_lcd-ab_1.0.6.54.21.swu
usb=
mounts=$(awk '$3 == "vfat" {print $2}' /proc/mounts)
while IFS= read -r path; do
    path=$(printf '%b' "$path")
    if [ -f "$path/$package" ]; then
        [ -z "$usb" ] || { echo 'Multiple installer sticks found' >&2; exit 1; }
        usb=$path
    fi
done <<EOF
$mounts
EOF
[ -n "$usb" ] || { echo 'Installer USB stick not found' >&2; exit 1; }
log() { echo "$*" | tee -a "$usb/ubuntu-install.log"; }
fail() { log "ABORTED: $*"; exit 1; }
cleanup() {
    result=$?
    if [ "$result" -ne 0 ]; then
        fw_setenv swu_mode '' || true
        fw_setenv swu_next '' || true
        log 'Update aborted. Check ubuntu-install.log. No automatic reboot requested.'
    fi
}
trap cleanup EXIT
if [ "$stage" = postinst ]; then
    log "Ubuntu images installed in slot $slot. Bootloader and partition table were not replaced."
    sync
    exit 0
fi
[ "$stage" = preinst ] || fail 'Unexpected installer stage'
log "Starting Ubuntu preflight for inactive slot $slot"
tr '\000' '\n' < /proc/device-tree/compatible | grep -Eq 'r818|sun50iw10' || fail 'Unsupported SoC'
current=$(fw_printenv -n boot_partition)
root=$(fw_printenv -n root_partition)
previous=$(fw_printenv -n sonicpad_ubuntu_slot 2>/dev/null || true)
[ -z "$previous" ] || fail 'Ubuntu was already installed; use the return-to-Ubuntu package instead of reinstalling'
case "$current:$root:$slot" in
    bootA:rootfsA:B|bootB:rootfsB:A) ;;
    *) fail "Expected stock A/B boot environment; got $current, $root, destination $slot";;
esac
for name in bootA bootB rootfsA rootfsB env env-redund rootfs_data; do
    [ -b "/dev/by-name/$name" ] || fail "Missing partition $name"
done
configs=0
while read -r device offset size rest; do
    case "$device" in ''|'#'*) continue;; esac
    resolved=$(readlink -f "$device")
    case "$resolved" in
        "$(readlink -f /dev/by-name/env)"|"$(readlink -f /dev/by-name/env-redund)") ;;
        *) fail 'Unsupported boot-environment device';;
    esac
    [ "$((offset))" -eq 0 ] && [ "$((size))" -eq 131072 ] || fail 'Unsupported boot-environment format'
    configs=$((configs + 1))
done < /etc/fw_env.config
[ "$configs" -eq 2 ] || fail 'Expected redundant boot environment'
boot=$(readlink -f "/dev/by-name/boot$slot")
target=$(readlink -f "/dev/by-name/rootfs$slot")
case "$boot:$target" in /dev/mmcblk0p*:/dev/mmcblk0p*) ;; *) fail 'Unexpected storage device';; esac
boot_sectors=$(cat "/sys/class/block/${boot##*/}/size")
root_sectors=$(cat "/sys/class/block/${target##*/}/size")
[ "$boot_sectors" -ge 21424 ] || fail 'Boot partition too small'
[ "$root_sectors" -eq 1048576 ] || fail 'Expected a 512 MiB system slot'
awk -v b="$boot" -v r="$target" '$1 == b || $1 == r {found=1} END {exit found ? 0 : 1}' /proc/mounts && fail 'Destination slot is mounted'
[ "$(readlink -f "/dev/by-name/$root")" != "$target" ] || fail 'Destination is the active rootfs'
total=0
for name in bootA bootB rootfsA rootfsB env env-redund rootfs_data; do
    dev=$(readlink -f "/dev/by-name/$name")
    sectors=$(cat "/sys/class/block/${dev##*/}/size")
    # Each FAT32 backup file must be smaller than 4 GiB.
    [ "$sectors" -lt 8388608 ] || fail "Backup partition too large: $name"
    total=$((total + sectors / 2))
done
free=$(df -Pk "$usb" | awk 'NR == 2 {print $4}')
[ "$free" -gt $((total + 131072)) ] || fail 'Insufficient USB space for backups'
backup="$usb/sonicpad-backup-$(date +%Y%m%d-%H%M%S)"
mkdir "$backup"
fw_printenv > "$backup/boot-environment.txt"
cat /proc/cmdline > "$backup/cmdline.txt"
cat /proc/partitions > "$backup/partitions.txt"
cat /proc/mounts > "$backup/mounts.txt"
for name in bootA bootB rootfsA rootfsB env env-redund rootfs_data; do
    log "Backing up $name"
    dd if="/dev/by-name/$name" of="$backup/$name.img" bs=1048576
    dev=$(readlink -f "/dev/by-name/$name")
    sectors=$(cat "/sys/class/block/${dev##*/}/size")
    bytes=$(wc -c < "$backup/$name.img")
    [ "$bytes" -eq $((sectors * 512)) ] || fail "Incomplete backup: $name"
    backup_hash=$(sha256sum "$backup/$name.img" | awk '{print $1}')
    if [ "$name" = rootfs_data ]; then
        log 'rootfs_data is copied live; it is not an atomic filesystem snapshot.'
    else
        source_hash=$(sha256sum "/dev/by-name/$name" | awk '{print $1}')
        [ "$source_hash" = "$backup_hash" ] || fail "Backup verification failed: $name"
    fi
    printf '%s  %s.img\n' "$backup_hash" "$name" >> "$backup/SHA256SUMS"
done
sync
log "Backups verified in $backup. Preflight passed; writing inactive slot $slot."
