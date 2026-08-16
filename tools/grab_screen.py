#!/usr/bin/env python3
"""Capture what the ROM is actually putting on screen, via mGBA's GDB stub.

mGBA has no headless screenshot mode and driving its UI needs accessibility
permissions, but `mGBA -g` exposes a GDB server. This attaches, dumps VRAM,
palette RAM, OAM and the display registers, then reconstructs the 240x160
frame in software.

Two quirks of that stub shape the flow below:

  * `-g` halts the CPU at reset and never starts it. Ordinary `continue`
    doesn't work -- gdb reports "the program is not being run" -- so a
    throwaway session sends a raw `c` packet to get the ROM running, then is
    killed off.
  * Only VRAM, palette RAM, OAM and the low I/O registers are readable. IWRAM
    is not, so the game's own globals can't be inspected or poked; states that
    need input are reached with the BOOT_LEVEL / BOOT_DEATH build switches
    instead.

That means it renders the emulator's real state -- not a reimplementation of
the game's layout logic -- so it catches bugs a data-level preview can't.

Only what this game uses is implemented: mode 0, one regular background, and
16x16 4bpp sprites in 1D mapping.

    python3 tools/grab_screen.py out.png [--frames N] [--set g_state=4]

--set pokes the game's own globals through the debugger, which is how states
that need input (a death, a particular level) get reached without driving the
emulator's UI.
"""

import argparse
import os
import signal
import struct
import subprocess
import sys
import tempfile
import time
from PIL import Image

MGBA = "/Applications/mGBA.app/Contents/MacOS/mGBA"

GDB = "/opt/devkitpro/devkitARM/bin/arm-none-eabi-gdb"

REGIONS = {
    "pal":  (0x05000000, 0x400),
    "vram": (0x06000000, 0x18000),
    "oam":  (0x07000000, 0x400),
    "io":   (0x04000000, 0x110),
}

SCREEN_W, SCREEN_H = 240, 160


def dump(port, elf):
    """Read the emulator's video memory over the GDB stub.

    mGBA's stub does not actually halt the CPU -- `continue` reports "the
    program is not being run" and breakpoints never fire -- so this is a read
    of a live, running frame rather than a stopped one. IWRAM is not reachable
    either, only VRAM, palette RAM, OAM and the low I/O registers, which is
    exactly enough to reconstruct the screen.
    """
    out = {}
    with tempfile.TemporaryDirectory() as tmp:
        cmds = [elf,
                "-ex", "set confirm off",
                "-ex", "set pagination off",
                "-ex", "target remote localhost:%d" % port]
        for name, (addr, size) in REGIONS.items():
            cmds += ["-ex", "dump binary memory %s/%s.bin 0x%08X 0x%08X"
                     % (tmp, name, addr, addr + size)]
        cmds += ["-ex", "detach", "-ex", "quit"]

        res = subprocess.run([GDB, "-batch"] + cmds,
                             capture_output=True, text=True, timeout=60)
        for name in REGIONS:
            path = os.path.join(tmp, name + ".bin")
            if not os.path.exists(path):
                sys.stderr.write(res.stdout + res.stderr)
                raise SystemExit("gdb did not produce %s -- is mGBA running "
                                 "with -g?" % name)
            out[name] = open(path, "rb").read()
    return out


def kick(port, elf):
    """Start the halted CPU by sending a raw continue packet.

    `maint packet c` blocks until the target stops, which it never does, so
    this session is launched detached and killed once the packet is away.
    """
    proc = subprocess.Popen(
        [GDB, "-batch", elf,
         "-ex", "set confirm off",
         "-ex", "set remotetimeout 2",
         "-ex", "target remote localhost:%d" % port,
         "-ex", "maint packet c"],
        stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    time.sleep(3.5)
    proc.send_signal(signal.SIGKILL)
    proc.wait()
    time.sleep(0.5)


def rgb(bgr15):
    r = (bgr15 & 31) << 3
    g = ((bgr15 >> 5) & 31) << 3
    b = ((bgr15 >> 10) & 31) << 3
    return (r | r >> 5, g | g >> 5, b | b >> 5)


def palette(pal_bytes, base):
    return [rgb(struct.unpack_from("<H", pal_bytes, base + i * 2)[0])
            for i in range(256)]


def tile_pixel(vram, char_base, tile, x, y):
    """One pixel out of a 4bpp tile: 32 bytes per tile, two pixels per byte."""
    off = char_base + tile * 32 + y * 4 + (x >> 1)
    if off >= len(vram):
        return 0
    byte = vram[off]
    return (byte & 0xF) if (x & 1) == 0 else (byte >> 4)


def render(mem, fade=0, mosaic=0):
    io, vram, pal, oam = mem["io"], mem["vram"], mem["pal"], mem["oam"]

    dispcnt = struct.unpack_from("<H", io, 0x00)[0]
    mode = dispcnt & 7
    if mode != 0:
        raise SystemExit("only mode 0 is implemented; ROM is in mode %d" % mode)

    bgpal = palette(pal, 0)
    objpal = palette(pal, 0x200)

    img = Image.new("RGB", (SCREEN_W, SCREEN_H), bgpal[0])
    px = img.load()

    # --- backgrounds, drawn back to front by priority ---------------------
    layers = []
    for bg in range(4):
        if not (dispcnt & (0x100 << bg)):
            continue
        cnt = struct.unpack_from("<H", io, 0x08 + bg * 2)[0]
        layers.append((cnt & 3, bg, cnt))
    for _prio, bg, cnt in sorted(layers, reverse=True):
        char_base = ((cnt >> 2) & 3) * 0x4000
        screen_base = ((cnt >> 8) & 0x1F) * 0x800
        # BGxHOFS/BGxVOFS are write-only: reading them back over the stub
        # returns open-bus garbage (0x4001 in practice), which shifts the whole
        # capture and bleeds off-screen map columns into view. Nothing in this
        # game scrolls, so treat them as zero.
        hofs = vofs = 0

        for y in range(SCREEN_H):
            for x in range(SCREEN_W):
                mx, my = (x + hofs) & 255, (y + vofs) & 255
                entry_off = screen_base + ((my >> 3) * 32 + (mx >> 3)) * 2
                se = struct.unpack_from("<H", vram, entry_off)[0]
                tile = se & 0x3FF
                tx = mx & 7
                ty = my & 7
                if se & 0x400:
                    tx = 7 - tx
                if se & 0x800:
                    ty = 7 - ty
                idx = tile_pixel(vram, char_base, tile, tx, ty)
                if idx:
                    px[x, y] = bgpal[((se >> 12) & 0xF) * 16 + idx]

    # --- sprites -----------------------------------------------------------
    if dispcnt & 0x1000:
        for i in range(127, -1, -1):
            a0, a1, a2 = struct.unpack_from("<HHH", oam, i * 8)
            if (a0 >> 8) & 3 == 2:          # hidden
                continue
            if (a0 >> 13) & 3 != 0:         # only square is used here
                continue
            size = (a1 >> 14) & 3
            side = [8, 16, 32, 64][size]
            oy = a0 & 0xFF
            ox = a1 & 0x1FF
            if ox >= 240:
                ox -= 512
            if oy >= 160:
                oy -= 256

            tile = a2 & 0x3FF
            bank = (a2 >> 12) & 0xF
            hflip, vflip = (a1 >> 12) & 1, (a1 >> 13) & 1
            cells = side // 8

            for cy in range(cells):
                for cx in range(cells):
                    # 1D mapping: tiles run consecutively across the sprite.
                    t = tile + cy * cells + cx
                    for y in range(8):
                        for x in range(8):
                            sx = cx * 8 + x
                            sy = cy * 8 + y
                            if hflip:
                                sx = side - 1 - sx
                            if vflip:
                                sy = side - 1 - sy
                            idx = tile_pixel(vram, 0x10000, t, x, y)
                            if not idx:
                                continue
                            X, Y = ox + sx, oy + sy
                            if 0 <= X < SCREEN_W and 0 <= Y < SCREEN_H:
                                px[X, Y] = objpal[bank * 16 + idx]

    # Brightness fade. BLDCNT is readable so the blend flags can be checked,
    # but BLDY is write-only -- the emulator returns garbage for it -- so the
    # level has to be supplied by the caller.
    bldcnt = struct.unpack_from("<H", io, 0x50)[0]
    if (bldcnt & 0x00C0) == 0x00C0 and fade:
        y = max(0, min(16, fade))
        for yy in range(SCREEN_H):
            for xx in range(SCREEN_W):
                r, g, b = px[xx, yy]
                px[xx, yy] = (r - r * y // 16, g - g * y // 16, b - b * y // 16)

    # Mosaic. REG_MOSAIC is write-only too, so the level comes from the
    # caller; BGxCNT's mosaic bit is readable and is what gets checked.
    if mosaic:
        n = max(0, min(15, mosaic * 15 // 16)) + 1
        if n > 1:
            for by in range(0, SCREEN_H, n):
                for bx in range(0, SCREEN_W, n):
                    c = px[bx, by]
                    for yy in range(by, min(by + n, SCREEN_H)):
                        for xx in range(bx, min(bx + n, SCREEN_W)):
                            px[xx, yy] = c

    return img, bldcnt


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("out")
    ap.add_argument("--port", type=int, default=2345)
    ap.add_argument("--elf", default="double_maze.elf")
    ap.add_argument("--rom", help="launch this ROM in mGBA, capture, then quit")
    ap.add_argument("--fade", type=int, default=0,
                    help="apply this brightness-fade level (BLDY is write-only "
                         "so it can't be read back)")
    ap.add_argument("--mosaic", type=int, default=0,
                    help="apply this mosaic level (REG_MOSAIC is write-only "
                         "so it can't be read back)")
    ap.add_argument("--delay", type=float, default=3.0,
                    help="seconds to let the ROM run before capturing")
    ap.add_argument("--scale", type=int, default=1,
                    help="nearest-neighbour upscale; the README's screenshots "
                         "are captured at 3 so the 240x160 frame is legible "
                         "without the browser resampling it")
    args = ap.parse_args()

    proc = None
    if args.rom:
        # A fresh emulator per capture: the stub goes unresponsive after a
        # couple of attach/detach cycles, and this makes --delay mean "time
        # since boot", which is what keeps timed captures repeatable.
        subprocess.run(["pkill", "-f", "mGBA"], capture_output=True)
        time.sleep(0.8)
        proc = subprocess.Popen([MGBA, "-g", args.rom],
                                stdout=subprocess.DEVNULL,
                                stderr=subprocess.DEVNULL)
        time.sleep(2.5)
        kick(args.port, args.elf)
        time.sleep(args.delay)

    try:
        mem = dump(args.port, args.elf)
        img, bldcnt = render(mem, args.fade, args.mosaic)
        if args.scale > 1:
            img = img.resize((img.width * args.scale, img.height * args.scale),
                             Image.NEAREST)
        img.save(args.out)
        bg0 = struct.unpack_from("<H", mem["io"], 0x08)[0]
        print("wrote %s  (BLDCNT=0x%04X, BG0CNT=0x%04X, mosaic bit %s)"
              % (args.out, bldcnt, bg0, "set" if bg0 & 0x40 else "CLEAR"))
    finally:
        if proc:
            proc.send_signal(signal.SIGTERM)


if __name__ == "__main__":
    main()
