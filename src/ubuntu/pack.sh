#!/usr/bin/env bash
set -Eeuo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
[[ $EUID == 0 ]] || exit 1
[[ -f work/rootfs.complete ]] || { echo 'Build a complete rootfs first.' >&2; exit 1; }
echo '1dbb863bdd610c11b0037eec695e0861918dc1ada013ed6ebfec8dc7e57449cb  ../archives/kernel_tools.tar.gz' | sha256sum -c -
kernel="$PWD/work/kernel"
rootfs="$PWD/work/rootfs"
mkdir -p "$kernel" out
tar -xzf ../archives/kernel_tools.tar.gz -C "$kernel"
chmod +x "$kernel/tools/dragon" "$kernel/tools/make_ext4fs"
image="$kernel/images/rootfs.img"
mkdir -p "$kernel/images"
# Keep the upstream partition table and its vendor-compatible ext4 formatter.
"$kernel/tools/make_ext4fs" -l 4000000000 -b 4096 -i 244140 -m 0 "$image"
mountpoint="$PWD/work/mount"
mkdir -p "$mountpoint"
trap 'if mountpoint -q "$mountpoint"; then umount "$mountpoint"; fi' EXIT
mount -o loop "$image" "$mountpoint"
cp -a "$rootfs/." "$mountpoint/"
umount "$mountpoint"
tune2fs -O ^resize_inode "$image"
status=0
e2fsck -fy "$image" || status=$?
((status <= 1)) || exit "$status"
resize2fs -M "$image"
(cd "$kernel"; ./tools/dragon image.cfg sys_partition_for_dragon.fex)
output=ubuntu-jammy-arm64-sonicpad.img
mv "$kernel/tina_r818-sonic_lcd_uart0.img" "out/$output"
(cd out; sha256sum "$output" > "$output.sha256")
echo "Firmware packaged: $PWD/out/$output (hardware boot test still required)."
