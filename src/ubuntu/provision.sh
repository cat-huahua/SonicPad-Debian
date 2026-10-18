#!/usr/bin/env bash
set -Eeuo pipefail
export DEBIAN_FRONTEND=noninteractive
apt-get update
apt-get install -y --no-install-recommends ubuntu-keyring ca-certificates
sed -i 's|http://ports.ubuntu.com|https://ports.ubuntu.com|g' /etc/apt/sources.list
apt-get dist-upgrade -y
apt-get install -y --no-install-recommends \
    systemd-sysv udev kmod dbus libpam-systemd openssh-server sudo \
    network-manager netplan.io systemd-timesyncd \
    wpasupplicant wireless-tools iproute2 iputils-ping net-tools \
    locales tzdata e2fsprogs u-boot-tools usbutils spi-tools \
    git curl wget nano less python3 python3-venv python3-pip \
    build-essential libssl-dev
echo sonicpad > /etc/hostname
printf '127.0.0.1 localhost\n127.0.1.1 sonicpad\n::1 localhost ip6-localhost\n' > /etc/hosts
locale-gen en_US.UTF-8
update-locale LANG=en_US.UTF-8
ln -sf /usr/share/zoneinfo/Asia/Singapore /etc/localtime
echo Asia/Singapore > /etc/timezone
useradd -m -s /bin/bash -G sudo,dialout,video,netdev sonic
echo 'sonic:pad' | chpasswd
chage -d 0 sonic
passwd -l root
# The board boots the bundled 4.9.191 kernel; never install a generic Ubuntu kernel.
systemctl set-default multi-user.target
