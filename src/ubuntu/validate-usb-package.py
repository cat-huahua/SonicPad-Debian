#!/usr/bin/env python3
"""Verify the stock unsigned archives, and prepare signed copies for distro checks.

Ubuntu's SWUpdate validator requires signatures. Temporary test signatures are
added only to separate validation copies; the stock-format output is unchanged.
"""
import base64
import hashlib
import json
from pathlib import Path
import subprocess

BASE = Path(__file__).resolve().parent
WORK = BASE / 'work/swu'
VALIDATION = WORK / 'validation'


def run(*args, **kwargs):
    return subprocess.run(args, check=True, **kwargs)


def main():
    VALIDATION.mkdir(exist_ok=True)
    key, cert, public = [VALIDATION / x for x in ('key.pem', 'cert.pem', 'public.pem')]
    run('openssl', 'req', '-new', '-x509', '-newkey', 'rsa:2048', '-nodes', '-days', '1',
        '-subj', '/CN=Sonic Pad local format validation/', '-addext', 'extendedKeyUsage=emailProtection',
        '-keyout', str(key), '-out', str(cert), stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    run('openssl', 'pkey', '-in', str(key), '-pubout', '-out', str(public))
    pairs = [(BASE / 'out/usb/t800-sonic_lcd-ab_1.0.6.54.21.swu', WORK / 'package', 'installer'),
             (BASE / 'out/usb/RETURN-TO-UBUNTU/t800-sonic_lcd-ab_1.0.6.54.22.swu', WORK / 'return-package', 'return'),
             (BASE / 'out/usb/POWER-CONTROLS-UPDATE/t800-sonic_lcd-ab_1.0.6.54.23.swu', WORK / 'power-package', 'power')]
    for archive, stage, name in pairs:
        with archive.open('rb') as f:
            run('cpio', '-it', '--only-verify-crc', '--quiet', stdin=f, stdout=subprocess.DEVNULL)
        decoded = base64.decodebytes((archive.parent / 'config.ini').read_bytes())
        clear = run('openssl', 'enc', '-d', '-aes-256-ecb', '-K', b'BCNZXCBGDASHJDHAJKDHJSH'.ljust(32, b'\0').hex(), '-nopad', input=decoded, stdout=subprocess.PIPE).stdout
        meta = json.loads(clear.rstrip(b'\0'))
        with archive.open('rb') as f:
            digest = hashlib.file_digest(f, 'md5').hexdigest()
        assert meta['hash'] == digest and meta['file'] == archive.name
        assert meta['type'] == 'whole_machine'
        run('md5sum', '-c', 'cpio_item_md5', cwd=stage)
        files = run('cpio', '-it', '--quiet', input=archive.read_bytes(), stdout=subprocess.PIPE).stdout.decode().splitlines()
        assert files[0] == 'sw-description'
        assert len(files) == len(set(files))
        for entry in files:
            assert '/' not in entry and entry not in ('.', '..')
        for mode in ('rsa', 'cms'):
            sig = stage / 'sw-description.sig'
            if mode == 'rsa':
                run('openssl', 'dgst', '-sha256', '-sign', str(key), '-out', str(sig), str(stage / 'sw-description'))
            else:
                run('openssl', 'cms', '-sign', '-binary', '-nosmimecap', '-in', str(stage / 'sw-description'),
                    '-signer', str(cert), '-inkey', str(key), '-outform', 'DER', '-out', str(sig))
            signed_files = [files[0], 'sw-description.sig'] + files[1:]
            with (VALIDATION / f'{name}-{mode}.swu').open('wb') as f:
                run('cpio', '-o', '-H', 'crc', '--quiet', input=('\n'.join(signed_files) + '\n').encode(), cwd=stage, stdout=f)
            sig.unlink()
        print(f'CRC, payload checksums, and encrypted config verified: {archive.name}')
    key.unlink()
    print(f'Validation copies ready: {VALIDATION}')


if __name__ == '__main__':
    main()
