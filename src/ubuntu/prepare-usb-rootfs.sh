#!/usr/bin/env bash
# Produce a separate, small rootfs for the stock 512 MiB A/B slots.
set -Eeuo pipefail
export LC_ALL=C
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
[[ $EUID == 0 ]] || exit 1
rootfs="$PWD/work/swu/rootfs"
[[ -f $rootfs/etc/os-release && -f work/rootfs.complete ]] || exit 1
mounted=()
cleanup() {
    for ((i=${#mounted[@]}-1; i>=0; i--)); do umount -R "${mounted[i]}"; done
    rm -f "$rootfs/etc/resolv.conf"
    ln -s /run/systemd/resolve/stub-resolv.conf "$rootfs/etc/resolv.conf"
}
trap cleanup EXIT
for target in dev proc sys; do
    mount --rbind "/$target" "$rootfs/$target"
    mounted+=("$rootfs/$target")
    mount --make-rslave "$rootfs/$target"
done
printf '#!/bin/sh\nexit 101\n' > "$rootfs/usr/sbin/policy-rc.d"
chmod 755 "$rootfs/usr/sbin/policy-rc.d"
rm -f "$rootfs/etc/resolv.conf"
cp -L /etc/resolv.conf "$rootfs/etc/resolv.conf"
chroot "$rootfs" /usr/bin/env LC_ALL=C DEBIAN_FRONTEND=noninteractive \
    apt-get install -y --no-install-recommends python3-pil python3-evdev fonts-dejavu-core
chroot "$rootfs" /usr/bin/env LC_ALL=C DEBIAN_FRONTEND=noninteractive \
    apt-get purge -y build-essential gcc g++ cpp gcc-11 g++-11 cpp-11 \
    binutils binutils-aarch64-linux-gnu libc6-dev linux-libc-dev libssl-dev
chroot "$rootfs" /usr/bin/env LC_ALL=C DEBIAN_FRONTEND=noninteractive apt-get autoremove --purge -y
chroot "$rootfs" apt-get clean
chroot "$rootfs" systemctl disable expandfs
rm -f "$rootfs/etc/systemd/system/expandfs.service" "$rootfs/usr/local/bin/expandfs_enable.sh"
rm -f "$rootfs/usr/sbin/policy-rc.d"
rm -rf "$rootfs/var/lib/apt/lists/"*
rm -rf "$rootfs/run/"*
printf 'LABEL=UBUNTUROOT / ext4 noatime,lazytime,rw 0 1\n' > "$rootfs/etc/fstab"
chroot "$rootfs" dpkg-query -W > out/usb-packages.tsv
[[ -z $(chroot "$rootfs" dpkg --audit) ]]
du -sxh "$rootfs"
