#!/usr/bin/env python3
"""Framebuffer startup selector; never replaces U-Boot or claims UEFI support."""
import argparse
import ctypes as C
import fcntl
import mmap
from pathlib import Path
import select
import subprocess
import sys
import time
from PIL import Image, ImageDraw, ImageFont


class Bitfield(C.Structure):
    _fields_ = [('offset', C.c_uint32), ('length', C.c_uint32), ('msb_right', C.c_uint32)]


class Variable(C.Structure):
    _fields_ = [(n, C.c_uint32) for n in ('xres', 'yres', 'xres_virtual', 'yres_virtual', 'xoffset', 'yoffset', 'bits_per_pixel', 'grayscale')]
    _fields_ += [(n, Bitfield) for n in ('red', 'green', 'blue', 'transp')]
    _fields_ += [(n, C.c_uint32) for n in ('nonstd', 'activate', 'height', 'width', 'accel_flags', 'pixclock', 'left_margin', 'right_margin', 'upper_margin', 'lower_margin', 'hsync_len', 'vsync_len', 'sync', 'vmode', 'rotate', 'colorspace')]
    _fields_ += [('reserved', C.c_uint32 * 4)]


class Fixed(C.Structure):
    _fields_ = [('id', C.c_char * 16), ('smem_start', C.c_ulong)]
    _fields_ += [(n, C.c_uint32) for n in ('smem_len', 'type', 'type_aux', 'visual')]
    _fields_ += [(n, C.c_uint16) for n in ('xpanstep', 'ypanstep', 'ywrapstep')]
    _fields_ += [('line_length', C.c_uint32), ('mmio_start', C.c_ulong), ('mmio_len', C.c_uint32), ('accel', C.c_uint32), ('capabilities', C.c_uint16), ('reserved', C.c_uint16 * 2)]


def render(width, height, seconds, settings=False, runtime=False):
    image = Image.new('RGB', (width, height), '#101923')
    draw = ImageDraw.Draw(image)
    scale = min(width / 1024, height / 600)
    def font(size):
        return ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', max(12, int(size * scale)))
    def text(x, y, value, size=28, color='#e7eef7'):
        draw.text((int(x * width), int(y * height)), value, font=font(size), fill=color)
    text(.06, .07, 'Sonic Pad', 42)
    subtitle = 'Boot information' if settings else ('Ubuntu 22.04 - system controls' if runtime else 'Startup selector')
    text(.06, .18, subtitle, 26, '#9bafc7')
    boxes = []
    labels = [('Ubuntu 22.04', 'Continue startup', 'ubuntu'), ('Official firmware', 'Switch slot and restart', 'official'), ('Boot information', 'U-Boot / recovery details', 'info')]
    if runtime:
        text(.06, .28, 'Base system: use Ethernet and SSH as sonic. No desktop installed.', 21, '#a9bed4')
        labels = [('Shut down', 'Stop services and unmount filesystems', 'shutdown'), ('Restart', 'Orderly system restart', 'reboot'), ('Official firmware', 'Switch slot and restart', 'official'), ('Boot information', 'U-Boot / recovery details', 'info')]
    if settings:
        text(.06, .33, 'Bootloader: existing Allwinner U-Boot', 25)
        text(.06, .43, 'UEFI / GRUB: not installed', 25)
        text(.06, .53, 'Official firmware keeps its original slot.', 23)
        text(.06, .63, 'Use the return USB update to start Ubuntu again.', 22)
        labels = [('Continue Ubuntu', 'No bootloader changes', 'ubuntu')]
    for i, (label, hint, action) in enumerate(labels):
        if settings:
            x0, y0, x1, y1 = .06, .77, .65, .91
        elif runtime:
            x0, y0 = .06 + (i % 2) * .45, .38 + (i // 2) * .24
            x1, y1 = x0 + .42, y0 + .21
        else:
            x0, y0, x1, y1 = .06 + i * .30, .36, .34 + i * .30, .72
        box = tuple(int(v * (width if j % 2 == 0 else height)) for j, v in enumerate((x0, y0, x1, y1)))
        draw.rounded_rectangle(box, radius=14, fill='#1d3650' if i == 0 else '#202d3b', outline='#45617e', width=2)
        text(x0 + .018, y0 + .055, label, 23)
        # Wrap short hints so the layout remains legible at 1024x600.
        words, lines, line = hint.split(), [], ''
        for word in words:
            if len(line + ' ' + word) > 20:
                lines.append(line); line = word
            else:
                line = (line + ' ' + word).strip()
        lines.append(line)
        if not settings:
            for n, line in enumerate(lines):
                text(x0 + .018, y0 + (.115 if runtime else .15) + n * .04, line, 17, '#a9bed4')
        boxes.append((box, action))
    if not runtime:
        power = (int(width * .69), int(height * (.77 if settings else .87)), int(width * .94), int(height * (.91 if settings else .97)))
        draw.rounded_rectangle(power, radius=12, fill='#552a32', outline='#b96670', width=2)
        draw.text((power[0] + int(width * .018), power[1] + int(height * .02)), 'Shut down', font=font(23), fill='#fff0f1')
        boxes.append((power, 'shutdown'))
    if not settings and not runtime:
        text(.06, .79, f'Ubuntu starts in {seconds}s  |  U: Ubuntu  O: Official  I: Info  S: Shut down', 19, '#a9bed4')
    if runtime:
        text(.06, .91, 'Use Shut down before disconnecting power. Do not hold the power button.', 18, '#a9bed4')
    return image, boxes


def request_power(action, runner=subprocess.run):
    """Always ask systemd for an orderly stop; never force halt/poweroff."""
    if action not in ('shutdown', 'reboot'):
        raise ValueError('Unsupported power action')
    runner(['systemctl', 'poweroff' if action == 'shutdown' else 'reboot'], check=True)


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument('--preview', type=Path)
    parser.add_argument('--screen', choices=('startup', 'runtime', 'info'), default='startup')
    args = parser.parse_args()
    if args.preview:
        render(1024, 600, 10, settings=args.screen == 'info', runtime=args.screen == 'runtime')[0].save(args.preview)
        return
    import evdev
    fb = open('/dev/fb0', 'r+b', buffering=0)
    var, fix = Variable(), Fixed()
    fcntl.ioctl(fb, 0x4600, var)
    fcntl.ioctl(fb, 0x4602, fix)
    if var.bits_per_pixel not in (24, 32) or var.green.offset != 8 or any(v.length != 8 for v in (var.red, var.green, var.blue)):
        raise RuntimeError('Unsupported framebuffer format; continuing Ubuntu')
    if var.red.offset == 16 and var.blue.offset == 0:
        rawmode = 'BGRA' if var.bits_per_pixel == 32 else 'BGR'
    elif var.red.offset == 0 and var.blue.offset == 16:
        rawmode = 'RGBA' if var.bits_per_pixel == 32 else 'RGB'
    else:
        raise RuntimeError('Unsupported framebuffer channel order')
    memory = mmap.mmap(fb.fileno(), fix.smem_len)
    width, height, pixel = var.xres, var.yres, var.bits_per_pixel // 8
    assert width > 0 and height > 0
    assert (var.yoffset + height) * fix.line_length <= fix.smem_len
    assert (var.xoffset + width) * pixel <= fix.line_length
    subprocess.run(['/usr/local/bin/brightness', '-s', '1'], check=False)
    devices = []
    for path in evdev.list_devices():
        try:
            device = evdev.InputDevice(path)
            caps = device.capabilities()
            if evdev.ecodes.EV_ABS in caps or evdev.ecodes.EV_KEY in caps:
                devices.append(device)
        except OSError:
            continue
    deadline, screen, last, boxes = time.monotonic() + 10, 'startup', None, []
    positions = {}
    def display(image):
        if pixel == 4:
            image = image.convert('RGBA')
        raw = image.tobytes('raw', rawmode)
        stride = width * pixel
        for y in range(height):
            start = (var.yoffset + y) * fix.line_length + var.xoffset * pixel
            memory[start:start + stride] = raw[y * stride:(y + 1) * stride]

    def power_message(action):
        image = Image.new('RGB', (width, height), '#101923')
        draw = ImageDraw.Draw(image)
        font = ImageFont.truetype('/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf', max(18, width // 34))
        lines = ['Requesting graceful shutdown' if action == 'shutdown' else 'Requesting an orderly restart', '',
                 'Stopping services and unmounting filesystems.', 'Leave power connected while shutdown completes.']
        for i, line in enumerate(lines):
            draw.text((width // 18, height // 8 + i * height // 11), line, font=font, fill='#e7eef7')
        display(image)

    while True:
        if screen == 'startup' and time.monotonic() >= deadline:
            screen = 'runtime'
        seconds = max(0, int(deadline - time.monotonic()) + 1) if screen == 'startup' else 0
        if (seconds, screen) != last:
            image, boxes = render(width, height, seconds, settings=screen == 'info', runtime=screen == 'runtime')
            display(image)
            last = (seconds, screen)
        ready, _, _ = select.select(devices, [], [], .2)
        choice = None
        for device in ready:
            for event in device.read():
                E = evdev.ecodes
                state = positions.setdefault(device.fd, {})
                if event.type == E.EV_ABS and event.code in (E.ABS_X, E.ABS_Y, E.ABS_MT_POSITION_X, E.ABS_MT_POSITION_Y):
                    info = device.absinfo(event.code)
                    axis = 'x' if event.code in (E.ABS_X, E.ABS_MT_POSITION_X) else 'y'
                    length = width if axis == 'x' else height
                    state[axis] = int((event.value - info.min) * (length - 1) / max(1, info.max - info.min))
                release = event.type == E.EV_KEY and event.code == E.BTN_TOUCH and event.value == 0
                release |= event.type == E.EV_ABS and event.code == E.ABS_MT_TRACKING_ID and event.value == -1
                if release and 'x' in state and 'y' in state:
                    for (x0, y0, x1, y1), action in boxes:
                        if x0 <= state['x'] <= x1 and y0 <= state['y'] <= y1:
                            if choice != 'shutdown':
                                choice = action
                if event.type == E.EV_KEY and event.value == 1:
                    if choice != 'shutdown':
                        choice = {E.KEY_U: 'ubuntu', E.KEY_ENTER: 'ubuntu', E.KEY_O: 'official', E.KEY_I: 'info', E.KEY_S: 'shutdown', E.KEY_R: 'reboot', E.KEY_POWER: 'shutdown'}.get(event.code, choice)
        if choice is not None:
            if choice in ('shutdown', 'reboot'):
                power_message(choice)
                try:
                    request_power(choice)
                except subprocess.CalledProcessError as exc:
                    print(f'Power request failed: {exc}', file=sys.stderr)
                    screen, last = 'runtime', None
                    continue
                return
            if choice == 'official':
                subprocess.run(['/usr/local/sbin/sonicpad-boot', 'official'], check=True)
                return
            screen = 'info' if choice == 'info' else 'runtime'
            last = None


if __name__ == '__main__':
    try:
        main()
    except Exception as exc:
        print(f'Startup selector unavailable: {exc}', file=sys.stderr)
        # A menu/display failure must never prevent Ubuntu startup.
        sys.exit(1 if '--preview' in sys.argv else 0)
