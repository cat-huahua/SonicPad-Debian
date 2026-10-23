#!/usr/bin/env python3
"""Package a completed small rootfs using Creality's published SWUpdate format."""
import base64
import datetime
import hashlib
import json
import os
from pathlib import Path
import shutil
import struct
import subprocess
from zoneinfo import ZoneInfo

BASE = Path(__file__).resolve().parent
WORK = BASE / 'work/swu'
PACKAGE = 't800-sonic_lcd-ab_1.0.6.54.21.swu'
VERSION = '1.0.6.54.21'


def run(*args, **kw):
    return subprocess.run(args, check=True, **kw)


def sha(path):
    with path.open('rb') as f:
        return hashlib.file_digest(f, 'sha256').hexdigest()


def boot_image(slot, output):
    image = bytearray((BASE / 'work/kernel/images/boot.img').read_bytes())
    assert image[:8] == b'ANDROID!'
    assert len(image) <= 21424 * 512
    cmdline = (f'console=ttyS0,115200 console=tty0 root=PARTLABEL=rootfs{slot} '
               'rootfstype=ext4 rootwait rw init=/sbin/init loglevel=4 gpt=1').encode()
    assert len(cmdline) < 512
    # Legacy Android boot header: command line is not covered by its SHA1 ID.
    assert struct.unpack_from('<I', image, 36)[0] == 2048
    image[64:576] = cmdline.ljust(512, b'\0')
    image[608:1632] = bytes(1024)
    output.write_bytes(image)


def main():
    assert os.geteuid() == 0, 'Run with sudo'
    rootfs = WORK / 'rootfs'
    for name in ('sonicpad-boot', 'sonicpad-menu.py'):
        destination = rootfs / 'usr/local/sbin' / name
        shutil.copyfile(BASE / name, destination)
        destination.chmod(0o755)
    shutil.copyfile(BASE / 'sonicpad-menu.service', rootfs / 'etc/systemd/system/sonicpad-menu.service')
    run('systemctl', f'--root={rootfs}', 'enable', 'sonicpad-menu.service')
    # Stock A/B layout has two boot-resource partitions; the original
    # single-rootfs project's hardcoded mmc partition numbers are not valid.
    (rootfs / 'etc/fw_env.config').write_text('/dev/disk/by-partlabel/env 0x0000 0x20000\n/dev/disk/by-partlabel/env-redund 0x0000 0x20000\n')
    assert (rootfs / 'etc/fstab').read_text().startswith('LABEL=UBUNTUROOT ')
    assert not (rootfs / 'etc/systemd/system/multi-user.target.wants/expandfs.service').exists()
    stage = WORK / 'package'
    stage.mkdir(exist_ok=True)
    raw = WORK / 'rootfs.img'
    tool = BASE / 'work/kernel/tools/make_ext4fs'
    run(str(tool), '-l', '536870912', '-b', '4096', '-i', '32768', '-m', '0', str(raw))
    mount = WORK / 'mount'
    mount.mkdir(exist_ok=True)
    run('mount', '-o', 'loop', str(raw), str(mount))
    try:
        run('cp', '-a', str(rootfs) + '/.', str(mount) + '/')
        space = shutil.disk_usage(mount)
        assert space.free >= 40 * 1024**2, 'Require at least 40 MiB free space'
    finally:
        run('umount', str(mount))
    run('tune2fs', '-O', '^resize_inode', '-L', 'UBUNTUROOT', str(raw))
    fsck = subprocess.run(['e2fsck', '-fy', str(raw)])
    assert fsck.returncode in (0, 1)
    run('e2fsck', '-fn', str(raw))
    with (stage / 'rootfs.img.gz').open('wb') as f:
        run('gzip', '-n', '-c', str(raw), stdout=f)
    for slot in 'AB':
        boot_image(slot, stage / f'boot{slot}.img')
    shutil.copyfile(BASE / 'usb-preflight.sh', stage / 'preflight.sh')
    sections = []
    for current, dest in [('A', 'B'), ('B', 'A')]:
        boot = f'boot{dest}.img'
        env = {'swu_mode': '', 'boot_partition': f'boot{dest}',
               'root_partition': f'rootfs{dest}', 'systemAB_next': dest,
               'swu_version': VERSION, 'build_type': 'release', 'swu_next': 'reboot',
               'sonicpad_ubuntu_slot': dest, 'sonicpad_official_slot': current}
        bootenv = ',\n'.join('{ name = ' + json.dumps(k) + '; value = ' + json.dumps(v) + '; }'
                              for k, v in env.items())
        sections.append(f'''now_{current}_next_{dest} = {{
            scripts: ({{ filename = "preflight.sh"; type = "shellscript";
                data = "{dest}"; sha256 = "{sha(stage / 'preflight.sh')}"; }});
            images: (
                {{ filename = "{boot}"; device = "/dev/by-name/boot{dest}";
                   type = "raw"; sha256 = "{sha(stage / boot)}"; }},
                {{ filename = "rootfs.img.gz"; device = "/dev/by-name/rootfs{dest}";
                   type = "raw"; compressed = true;
                   sha256 = "{sha(stage / 'rootfs.img.gz')}"; }}
            );
            bootenv: ({bootenv});
        }};''')
    description = 'software = {\n version = "' + VERSION + '";\n hardware-compatibility: ["1.0"];\n description = "Experimental Ubuntu 22.04 ARM64 base OS";\n stable = {\n' + '\n'.join(sections) + '\n };\n};\n'
    (stage / 'sw-description').write_text(description)
    files = ['sw-description', 'preflight.sh', 'bootA.img', 'bootB.img', 'rootfs.img.gz']
    md5s = []
    for name in files:
        with (stage / name).open('rb') as f:
            md5s.append(f'{hashlib.file_digest(f, "md5").hexdigest()}  {name}\n')
    (stage / 'cpio_item_md5').write_text(''.join(md5s))
    files.append('cpio_item_md5')
    out = BASE / 'out/usb'
    out.mkdir(exist_ok=True)
    path = out / PACKAGE
    with path.open('wb') as f:
        run('cpio', '-o', '-H', 'crc', '--quiet', input=('\n'.join(files) + '\n').encode(), cwd=stage, stdout=f)
    write_config(path)
    (out / 'SHA256SUMS').write_text(f'{sha(path)}  {PACKAGE}\n{sha(out / "config.ini")}  config.ini\n')
    build_return_package(out)
    print(f'USB package built: {path}; {path.stat().st_size:,} bytes')


def write_config(path):
    with path.open('rb') as f:
        digest = hashlib.file_digest(f, 'md5').hexdigest()
    metadata = json.dumps({'version': int(datetime.datetime.now(ZoneInfo('Asia/Singapore')).strftime('%Y%m%d%H%M%S')),
                           'hash': digest, 'type': 'whole_machine', 'file': path.name}).encode()
    key = b'BCNZXCBGDASHJDHAJKDHJSH'.ljust(32, b'\0')
    metadata += bytes((-len(metadata)) % 16)
    encrypted = run('openssl', 'enc', '-aes-256-ecb', '-K', key.hex(), '-nopad', input=metadata, stdout=subprocess.PIPE).stdout
    (path.parent / 'config.ini').write_bytes(base64.encodebytes(encrypted))


def build_return_package(out):
    """A second USB update changes the slot selection without reinstalling Ubuntu."""
    destination = out / 'RETURN-TO-UBUNTU'
    destination.mkdir(exist_ok=True)
    stage = WORK / 'return-package'
    stage.mkdir(exist_ok=True)
    shutil.copyfile(BASE / 'usb-return-preflight.sh', stage / 'return-preflight.sh')
    sections = []
    for current, dest in [('A', 'B'), ('B', 'A')]:
        env = {'swu_mode': '', 'boot_partition': f'boot{dest}', 'root_partition': f'rootfs{dest}',
               'systemAB_next': dest, 'swu_version': '1.0.6.54.22', 'swu_next': 'reboot'}
        bootenv = ',\n'.join('{ name = ' + json.dumps(k) + '; value = ' + json.dumps(v) + '; }' for k, v in env.items())
        sections.append(f'''now_{current}_next_{dest} = {{
            scripts: ({{filename = "return-preflight.sh"; type = "shellscript";
              data = "{dest}"; sha256 = "{sha(stage / 'return-preflight.sh')}"; }});
            bootenv: ({bootenv});
        }};''')
    (stage / 'sw-description').write_text('software = {\n version = "1.0.6.54.22";\n hardware-compatibility: ["1.0"];\n description = "Return to existing Ubuntu slot (no image writes)";\n stable = {\n' + '\n'.join(sections) + '\n };\n};\n')
    files = ['sw-description', 'return-preflight.sh']
    lines = []
    for name in files:
        with (stage / name).open('rb') as f:
            lines.append(f'{hashlib.file_digest(f, "md5").hexdigest()}  {name}\n')
    (stage / 'cpio_item_md5').write_text(''.join(lines))
    files.append('cpio_item_md5')
    path = destination / 't800-sonic_lcd-ab_1.0.6.54.22.swu'
    with path.open('wb') as f:
        run('cpio', '-o', '-H', 'crc', '--quiet', input=('\n'.join(files) + '\n').encode(), cwd=stage, stdout=f)
    write_config(path)
    (destination / 'SHA256SUMS').write_text(f'{sha(path)}  {path.name}\n{sha(destination / "config.ini")}  config.ini\n')


if __name__ == '__main__':
    main()
