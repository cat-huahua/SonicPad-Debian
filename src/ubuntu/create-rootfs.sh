#!/usr/bin/env bash
set -Eeuo pipefail
cd -- "$(dirname -- "${BASH_SOURCE[0]}")"
[[ $EUID == 0 ]] || exit 1
rootfs="$PWD/work/rootfs"
base=ubuntu-base-22.04.5-base-arm64.tar.gz
url=https://cdimage.ubuntu.com/ubuntu-base/releases/22.04/release
mkdir -p cache work
[[ ! -e $rootfs ]] || { echo "Rootfs exists: $rootfs; move it aside before rebuilding." >&2; exit 1; }
for name in SHA256SUMS SHA256SUMS.gpg "$base"; do
    curl --fail --location --retry 3 "$url/$name" -o "cache/$name"
done
gpgv --keyring /usr/share/keyrings/ubuntu-archive-keyring.gpg cache/SHA256SUMS.gpg cache/SHA256SUMS
(cd cache; awk -v name="$base" '$2 == "*" name || $2 == name' SHA256SUMS > base.sha256; test -s base.sha256; sha256sum -c base.sha256)
mkdir -p "$rootfs"
tar --numeric-owner -xpf "cache/$base" -C "$rootfs"
# binfmt must support executing aarch64 from an amd64 build host.
chroot "$rootfs" /bin/true
mkdir -p "$rootfs/proc" "$rootfs/sys" "$rootfs/dev" "$rootfs/run"
mounted=()
cleanup() {
    local target
    for ((i=${#mounted[@]}-1; i>=0; i--)); do
        target=${mounted[i]}
        umount -R "$target"
    done
}
trap cleanup EXIT
for target in dev proc sys; do
    mount --rbind "/$target" "$rootfs/$target"
    mounted+=("$rootfs/$target")
    mount --make-rslave "$rootfs/$target"
done
cp -L /etc/resolv.conf "$rootfs/etc/resolv.conf"
cat > "$rootfs/etc/apt/sources.list" <<'EOF'
deb http://ports.ubuntu.com/ubuntu-ports jammy main restricted universe multiverse
deb http://ports.ubuntu.com/ubuntu-ports jammy-updates main restricted universe multiverse
deb http://ports.ubuntu.com/ubuntu-ports jammy-security main restricted universe multiverse
EOF
# Bootstrap CA certificates using signed APT metadata, then require HTTPS.
printf '#!/bin/sh\nexit 101\n' > "$rootfs/usr/sbin/policy-rc.d"
chmod 755 "$rootfs/usr/sbin/policy-rc.d"
cp provision.sh "$rootfs/tmp/provision.sh"
chroot "$rootfs" /usr/bin/env DEBIAN_FRONTEND=noninteractive /bin/bash /tmp/provision.sh
cp -a ../base_rootfs/lib/modules "$rootfs/lib/"
cp -a ../base_rootfs/lib/firmware "$rootfs/lib/"
cp ../base_rootfs/etc/fstab "$rootfs/etc/fstab"
cp ../base_rootfs/etc/fw_env.config "$rootfs/etc/fw_env.config"
cp ../base_rootfs/etc/modules-load.d/modules.conf "$rootfs/etc/modules-load.d/sonicpad.conf"
for service in depmod_boot expandfs ledmmc usbhost; do
    install -m 644 "../base_rootfs/etc/systemd/system/$service.service" "$rootfs/etc/systemd/system/"
    chroot "$rootfs" systemctl enable "$service"
done
for script in depmod_enable expandfs_enable ledmmc_enable usbhost_enable; do
    install -m 755 "../base_rootfs/usr/local/bin/$script.sh" "$rootfs/usr/local/bin/"
done
chroot "$rootfs" depmod 4.9.191
install -m 644 ../scripts/resources/brightness/{brightness.c,sunxi_display_v2.h} "$rootfs/tmp/"
chroot "$rootfs" gcc -o /usr/local/bin/brightness /tmp/brightness.c
rm "$rootfs/tmp/brightness.c" "$rootfs/tmp/sunxi_display_v2.h"
mkdir -p "$rootfs/etc/NetworkManager/conf.d"
cp ../base_rootfs/etc/NetworkManager/conf.d/99-unmanaged-devices.conf "$rootfs/etc/NetworkManager/conf.d/"
mkdir -p "$rootfs/etc/ssh/sshd_config.d"
printf 'PermitRootLogin no\nPasswordAuthentication yes\n' > "$rootfs/etc/ssh/sshd_config.d/sonicpad.conf"
rm -f "$rootfs"/etc/ssh/ssh_host_* "$rootfs/etc/machine-id"
touch "$rootfs/etc/machine-id"
cat > "$rootfs/etc/systemd/system/ssh-host-keys.service" <<'EOF'
[Unit]
Description=Generate unique SSH host keys
Before=ssh.service
ConditionPathExists=!/etc/ssh/ssh_host_ed25519_key
[Service]
Type=oneshot
ExecStart=/usr/bin/ssh-keygen -A
[Install]
WantedBy=multi-user.target
EOF
chroot "$rootfs" systemctl enable ssh-host-keys ssh NetworkManager systemd-resolved systemd-timesyncd
mkdir -p "$rootfs/etc/netplan"
cat > "$rootfs/etc/netplan/01-ethernet.yaml" <<'EOF'
network:
  version: 2
  renderer: NetworkManager
  ethernets:
    eth0:
      dhcp4: true
EOF
chmod 600 "$rootfs/etc/netplan/01-ethernet.yaml"
rm -f "$rootfs/etc/resolv.conf"
ln -s /run/systemd/resolve/stub-resolv.conf "$rootfs/etc/resolv.conf"
rm -f "$rootfs/usr/sbin/policy-rc.d" "$rootfs/tmp/provision.sh"
chroot "$rootfs" apt-get clean
chroot "$rootfs" dpkg-query -W > out/packages.tsv
cp cache/base.sha256 out/ubuntu-base.sha256
repo=$(realpath ../..)
git -c safe.directory="$repo" -C "$repo" rev-parse HEAD > out/source-commit.txt
git -c safe.directory="$repo" -C "$repo" diff HEAD > out/source-changes.patch
touch work/rootfs.complete
echo 'Ubuntu arm64 root filesystem ready.'
