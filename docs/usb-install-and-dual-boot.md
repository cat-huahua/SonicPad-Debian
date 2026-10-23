# USB installation and official / Ubuntu selection

This is an experimental stock-updater installation for a Sonic Pad currently
running V1.0.6.54.20. It does not need SSH for installation. The previously built
PhoenixSuit `.img` is not used. Instead, a compressed, smaller Ubuntu filesystem
and the matching board kernel are packaged in Creality's `.swu` format.

The startup selector is a Python framebuffer application on Ubuntu, not GRUB,
UEFI or a firmware configuration utility. The published Tina U-Boot configuration
does not enable an EFI loader or bootmenu, and the supplied bootloader binary
does not expose those commands. Enabling them would require different firmware;
this installation does not replace the bootloader or partition table.

## Install from the prepared stick

The stick root contains `config.ini` and `t800-sonic_lcd-ab_1.0.6.54.21.swu`.
The higher version identifies this custom update; it is not a Creality release.
Safely eject the stick, insert it into the normally running Pad, and accept
the USB update prompt. Keep power and the stick connected throughout the update.

Before writing images, the installer checks the stock A/B environment, R818
compatibility, inactive slot, 512 MiB slot size, and redundant environment format.
It backs up both existing boot and rootfs slots plus environment and rootfs_data
to a timestamped `sonicpad-backup-*` folder on the same stick. Static partition
backups are checked against their sources. The rootfs_data copy is live rather
than an atomic filesystem snapshot; that partition itself is not overwritten.

Only the inactive boot/rootfs slot is replaced. The active official slot and user
data remain in place. Boot environment variables select the Ubuntu slot after
successful installation. An unexpected layout aborts the installation; read
`ubuntu-install.log` on the stick. Recovery can still require FEL/serial access
if something fails; retaining a bootloader does not guarantee recovery from every
bad update or power failure.

## Startup selector

On Ubuntu startup a framebuffer selector offers Ubuntu, Official firmware, and
Boot information. Ubuntu continues after 10 seconds. Touch is attempted using
evdev input coordinates, and a USB keyboard supports U / O / I. Hardware display
and touch operation have not yet been tested. A display/input failure must not
prevent Ubuntu from booting.

Selecting Official verifies the saved slot map and switches the boot environment,
then restarts into the preserved official slot. This selection persists. The
menu does not run within official firmware. From an Ubuntu terminal the same
action is `sudo sonicpad-boot official`; `sudo sonicpad-boot status` shows the map.

## Return from official firmware to Ubuntu

On a computer, replace the stick root's `config.ini` and `.swu` with the two files
from its `RETURN-TO-UBUNTU` folder. Remove/move the original `.swu` so only the
chosen update is at the root. Insert the stick into the normally running official
firmware and accept the update prompt. This small update checks the recorded slot
map and Ubuntu filesystem label, then changes only boot-selection variables.
It does not reinstall Ubuntu or overwrite a filesystem image.

Keep the original installer files in `INSTALL-UBUNTU` on the stick for reference.
The installer refuses to reinstall once it finds an existing Ubuntu slot map.
Ordinary official firmware updates reuse the inactive slot and can overwrite
Ubuntu, so the two installations are not independent of the vendor updater.

## Ubuntu contents and access

The 512 MiB system image contains Ubuntu 22.04 ARM64, SSH, NetworkManager and the
startup selector. It has no desktop, Klipper, Moonraker or printer interface.
Development packages were removed to fit the slot. The system partition has
limited free space and is not expanded into the other stock partitions.

Connect Ethernet for DHCP and SSH as `sonic` with initial password `pad`, then
change it when prompted. Root password login is disabled. Each device generates
its own SSH host keys and machine identity. The stock account/password are not
used by Ubuntu. After the menu Ubuntu leaves a static information screen; that
screen does not confirm successful networking or completion of boot.

## Build and validation

On the configured x86-64 host with Python 3.11+:

```sh
sudo mkdir -p src/ubuntu/work/swu/rootfs
sudo cp -a --reflink=auto src/ubuntu/work/rootfs/. src/ubuntu/work/swu/rootfs/
sudo ./src/ubuntu/prepare-usb-rootfs.sh
sudo python3 src/ubuntu/build-usb-package.py
sudo python3 src/ubuntu/validate-usb-package.py
```

The builder requires a completed base build and existing vendor kernel tools.
Use a fresh `work/swu/rootfs` for a new preparation. Original outputs remain in
`out/`; USB outputs are in `out/usb`. Dependencies include cpio and openssl.
The validator checks cpio CRCs, payload MD5s and Creality's encrypted config.
Ubuntu's packaged SWUpdate requires signed images; temporary RSA/CMS signatures
are added to separate validation copies for parser/check-mode testing. The actual
package remains unsigned, matching the published stock configuration. This does
not prove that the installed Pad firmware will accept the package.

No hardware flash or hardware boot test has been completed. Check-mode validation
does not execute preflight scripts or test real eMMC, framebuffer, input or boot
environment access.

Validation completed on 2026-10-24: both installer and return packages passed
SWUpdate check mode for both A-to-B and B-to-A selections, using temporary CMS
signatures on separate validation archives. Original cpio CRCs, payload MD5s,
encrypted config metadata, and the ext4 filesystem passed checks. The ARM64
rootfs package database and enabled services passed inspection. Menu rendering
was checked with the target ARM64 Pillow version, and framebuffer structure
sizes, button bounds and opaque pixel encoding were checked at 1024x600 and
800x480. The installer archive is about 129 MiB.

Format references:

- [Creality USB update instructions](https://github.com/CrealityTech/sonic_pad_os)
- [Stock A/B descriptor](https://github.com/CrealityTech/sonic_pad_os/blob/main/target/allwinner/r818-sonic_lcd/swupdate/sw-description-ab)
- [USB config generator](https://github.com/CrealityTech/sonic_pad_os/blob/main/target/allwinner/r818-sonic_lcd/swupdate/create_c-smart-brain_install_config.py)
- [Stock partition table](https://github.com/CrealityTech/sonic_pad_os/blob/main/device/config/chips/r818/configs/sonic_lcd/linux/sys_partition.fex)
- [Board U-Boot configuration](https://github.com/CrealityTech/sonic_pad_os/blob/main/lichee/brandy-2.0/u-boot-2018/configs/sun50iw10p1_tina_defconfig)
