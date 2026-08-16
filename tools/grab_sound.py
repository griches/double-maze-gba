#!/usr/bin/env python3
"""Read the sound hardware out of the running ROM, and say what it's doing.

The capture pipeline can see the screen but not hear the speaker, which leaves
the music untestable by the usual route. The registers are the next best
thing: they say which channels are enabled, how loud, at what pitch, and --
via SOUNDSTAT -- whether the hardware reckons they're actually sounding.

Same mGBA GDB stub as tools/grab_screen.py, whose dump this borrows. Note that
several sound registers are write-only in part: the frequency registers read
back as zero, so pitch is inferred from what is audible rather than printed.

    python3 tools/grab_sound.py --rom "Double Maze.gba"
"""

import argparse
import os
import signal
import struct
import subprocess
import sys
import time

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from grab_screen import MGBA, dump, kick          # noqa: E402

DMG_VOL = ["0/8", "1/8", "2/8", "3/8", "4/8", "5/8", "6/8", "7/8"]
DS_DMG = ["25%", "50%", "100%", "(reserved)"]
DUTY = ["12.5%", "25%", "50%", "75%"]
WAVE_VOL = {0: "mute", 1: "100%", 2: "50%", 3: "25%"}


def u16(io, off):
    return struct.unpack_from("<H", io, off)[0]


def envelope(value):
    vol = (value >> 12) & 15
    direction = "up" if (value & 0x0800) else "down"
    step = (value >> 8) & 7
    if step == 0:
        return "vol %2d, held" % vol
    return "vol %2d, %s every %d/64s" % (vol, direction, step)


def report(io):
    stat = u16(io, 0x84)
    dmg = u16(io, 0x80)
    ds = u16(io, 0x82)

    lines = []
    lines.append("master enable      %s" % ("on" if stat & 0x80 else "OFF"))
    lines.append("PSG vs DirectSound %s" % DS_DMG[ds & 3])
    lines.append("PSG master volume  L %s  R %s"
                 % (DMG_VOL[dmg & 7], DMG_VOL[(dmg >> 4) & 7]))

    enabled = []
    for bit, name in ((0x0100, "sq1"), (0x0200, "sq2"),
                      (0x0400, "wave"), (0x0800, "noise")):
        if dmg & bit:
            enabled.append(name)
    lines.append("PSG channels out   %s" % (", ".join(enabled) or "NONE"))

    # The other half of the register: maxmod's, and the reason for checking is
    # that the PSG volume bits live in the same word. Clobbering these would
    # take the sound effects out.
    ds_out = []
    for bit, name in ((0x0200, "A left"), (0x0100, "A right"),
                      (0x2000, "B left"), (0x1000, "B right")):
        if ds & bit:
            ds_out.append(name)
    lines.append("DirectSound out    %s  (A %s, B %s)"
                 % (", ".join(ds_out) or "NONE",
                    "100%" if ds & 0x0004 else "50%",
                    "100%" if ds & 0x0008 else "50%"))

    sounding = []
    for bit, name in ((1, "sq1"), (2, "sq2"), (4, "wave"), (8, "noise")):
        if stat & bit:
            sounding.append(name)
    lines.append("sounding right now %s" % (", ".join(sounding) or "nothing"))

    lines.append("")
    sq1, sq2 = u16(io, 0x62), u16(io, 0x68)
    lines.append("ch1 square   duty %-5s  %s"
                 % (DUTY[(sq1 >> 6) & 3], envelope(sq1)))
    lines.append("ch2 square   duty %-5s  %s"
                 % (DUTY[(sq2 >> 6) & 3], envelope(sq2)))

    sel, cnt = u16(io, 0x70), u16(io, 0x72)
    lines.append("ch3 wave     output %-3s  bank %d  volume %s"
                 % ("on" if sel & 0x80 else "off", (sel >> 6) & 1,
                    WAVE_VOL.get((cnt >> 13) & 7, "%d?" % ((cnt >> 13) & 7))))

    lines.append("ch4 noise    %s" % envelope(u16(io, 0x78)))

    lines.append("")
    lines.append("wave RAM     " + " ".join("%02X" % b for b in io[0x90:0xA0]))

    # Channel 1's sweep shares its registers. A non-zero value here slides
    # every note it plays, which is subtle enough on a screenshot-free test
    # rig to be worth calling out explicitly.
    sweep = u16(io, 0x60)
    lines.append("ch1 sweep    %s" % ("0 (off)" if sweep == 0
                                      else "0x%04X -- WILL DETUNE" % sweep))
    return "\n".join(lines)


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--rom", required=True)
    ap.add_argument("--port", type=int, default=2345)
    ap.add_argument("--elf", default="double_maze.elf")
    ap.add_argument("--delay", type=float, default=3.0)
    args = ap.parse_args()

    subprocess.run(["pkill", "-f", "mGBA"], capture_output=True)
    time.sleep(0.8)
    proc = subprocess.Popen([MGBA, "-g", args.rom],
                            stdout=subprocess.DEVNULL,
                            stderr=subprocess.DEVNULL)
    try:
        time.sleep(2.5)
        kick(args.port, args.elf)
        time.sleep(args.delay)
        print(report(dump(args.port, args.elf)["io"]))
    finally:
        proc.send_signal(signal.SIGTERM)


if __name__ == "__main__":
    main()
