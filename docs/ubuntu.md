# Sonic Pad Ubuntu port

Experimental Ubuntu 22.04.5 Base ARM64 (Jammy), updated from Ubuntu's signed
repositories during the build. Retains the R818 bootloader, device tree, vendor
Linux 4.9.191 kernel, modules and firmware from Jpe230/SonicPad-Debian.
Bullseye is a Debian release name; this uses that project's board support
rather than mixing Debian packages into Ubuntu. The current upstream main
branch has already moved to Bookworm and arm64.

This is a base OS image with SSH, Ethernet DHCP, NetworkManager, Python and build
tools. Klipper, Moonraker, KlipperScreen and a desktop are not installed by this
build. The original Debian installers remain in `src/scripts` for reference and
need separate Ubuntu validation. Packaging and chroot checks do not prove that
the image boots; display, touch, Wi-Fi, USB and expansion need hardware tests.
The old vendor kernel remains a maintenance limitation.

## Build on x86-64 Ubuntu

On Ubuntu 26.04:

```sh
sudo apt-get install qemu-user qemu-user-binfmt ubuntu-keyring curl gnupg \
  libc6-i386 lib32stdc++6 e2fsprogs util-linux git sunxi-tools
sudo ./src/ubuntu/build.sh
```

Older hosts may require `qemu-user-static` instead of `qemu-user`. Enable the
aarch64 binfmt handler. This build uses root, chroot, bind mounts and a loop
mount. Canonical's signed SHA256SUMS authenticates the Ubuntu Base archive.
The vendor formatter and `dragon` produce a PhoenixSuit/LiveSuit firmware
container, **not** a raw disk image for `dd`. The upstream partition table stays
intact. Paths containing spaces are supported.

Output: `src/ubuntu/out/ubuntu-jammy-arm64-sonicpad.img`, its checksum,
package manifest, base archive checksum and source commit. Outputs are ignored
by Git. `sudo ./src/ubuntu/build.sh rootfs` builds only the filesystem;
`sudo ./src/ubuntu/build.sh pack` packs an already completed filesystem.
The builder refuses to erase an existing rootfs. Move `src/ubuntu/work` aside
before a fresh complete build, only when no build is running.

## Connect and flash

Connect a data cable from the computer to the Pad's rear USB-A **CAM** port.
USB-C at the computer is usable only if the cable/connection enumerates the
device. Power the Pad off, hold its outermost recessed button, then power it
on while holding that button. Its screen should stay black in burning mode.
If a direct A-to-C cable produces no USB event, use the documented A-to-A cable
with a USB-C host adapter, or a computer USB-A port.

```sh
sudo ./src/ubuntu/check-device.sh
```

Expect Allwinner FEL USB ID `1f3a:efe8`. Resolve a missing device before flashing.
Here `sunxi-fel` only detects the device; it does not install this container.
Save printer configuration before replacing firmware. Follow the
[upstream flashing instructions](flashing.md) with the Ubuntu image. Their Linux
LiveSuit tool is proprietary and requires its own driver; sunxi-tools alone is
insufficient. Flashing replaces the OS and can erase stored configuration.
[Creality recovery images](https://github.com/CrealityOfficial/Creality_Sonic_Pad_Firmware)
are available separately.

## First boot

Connect Ethernet for DHCP, SSH as `sonic` with initial password `pad`, then
change the password when prompted. Root password login is locked. SSH host keys
are generated per device at boot. Timezone is Asia/Singapore. Use `sudo nmtui`
to configure Wi-Fi after login.

Validate `/etc/os-release`, `uname -r`, `lsmod`, `ip address`, Wi-Fi and reboot.
Inspect `journalctl -b -p warning`, `systemctl --failed`, `/dev/fb0`, input
devices and `df -h /`. The upstream expansion service targets `/dev/mmcblk0p5`;
confirm this layout during hardware testing. Use `sudo poweroff` for clean
shutdown of the writable filesystem.
