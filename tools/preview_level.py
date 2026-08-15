#!/usr/bin/env python3
"""Render what the GBA should be drawing, as a 240x160 PNG.

This reimplements the tilemap layout from source/render.c against the same
generated tilesets and level data, so it catches bad level data, wrong metatile
indices and layout mistakes without needing to read pixels out of an emulator.
It does NOT execute the ROM -- gameplay bugs won't show up here.

    python3 tools/preview_level.py [level-number] [output.png]
"""

import os
import re
import sys
from PIL import Image

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GFX = os.path.join(HERE, "gfx")

CELL = 16
GRID_W, GRID_H = 15, 8
SCREEN_W, SCREEN_H = 240, 160
GRID_TOP_PX = 16
SKINS = ["purple", "orange", "green"]
GOAL_IDS = [5, 11, 12, 13, 14]


def parse_levels():
    """Pull the level tables back out of the generated C."""
    text = open(os.path.join(HERE, "source", "levels.c")).read()
    levels = []
    for block in re.findall(r"\{ // level (\d+)(.*?)\n    \},", text, re.S):
        num, body = int(block[0]), block[1]
        pos = re.search(r"\.left_x = (\d+), \.left_y = (\d+), "
                        r"\.right_x = (\d+), \.right_y = (\d+),", body)
        tiles_txt = re.search(r"\.tiles = \{(.*?)\},", body, re.S).group(1)
        tiles = [int(v) for v in re.findall(r"\d+", tiles_txt)]
        levels.append({
            "number": num,
            "pos": [int(g) for g in pos.groups()],
            "tiles": tiles,
        })
    return levels


def load_strip(name):
    """A skin strip as a list of 21 RGBA cells, index 0 made transparent."""
    im = Image.open(os.path.join(GFX, name + ".png"))
    pal = im.getpalette()
    idx = im.load()
    cells = []
    for m in range(im.width // CELL):
        cell = Image.new("RGBA", (CELL, CELL), (0, 0, 0, 0))
        px = cell.load()
        for y in range(CELL):
            for x in range(CELL):
                v = idx[m * CELL + x, y]
                if v == 0:
                    continue
                px[x, y] = (pal[v * 3], pal[v * 3 + 1], pal[v * 3 + 2], 255)
        cells.append(cell)
    return cells


def backdrop_for(skin_index):
    """Read the BGR15 backdrops straight out of the generated header."""
    text = open(os.path.join(HERE, "source", "skins.h")).read()
    vals = re.search(r"skin_backdrop\[SKIN_COUNT\] = \{(.*?)\};", text).group(1)
    raw = [int(v, 16) for v in re.findall(r"0x([0-9A-Fa-f]+)", vals)]
    c = raw[skin_index]
    r, g, b = (c & 31), ((c >> 5) & 31), ((c >> 10) & 31)
    return (r << 3, g << 3, b << 3, 255)


def render(level, out_path):
    index = level["number"] - 1
    skin_index = (index // 2) % len(SKINS)
    cells = load_strip("tiles_" + SKINS[skin_index])
    ball = load_strip("ball")[0]

    img = Image.new("RGBA", (SCREEN_W, SCREEN_H), backdrop_for(skin_index))

    lx, ly, rx, ry = level["pos"]
    lit = {(lx, ly), (rx, ry)}

    for cy in range(GRID_H):
        for cx in range(GRID_W):
            t = level["tiles"][cy * GRID_W + cx]
            mt = t
            if t in GOAL_IDS and (cx, cy) in lit:
                mt = 16 + GOAL_IDS.index(t)
            img.alpha_composite(cells[mt], (cx * CELL, GRID_TOP_PX + cy * CELL))

    for (bx, by) in ((lx, ly), (rx, ry)):
        img.alpha_composite(ball, (bx * CELL, GRID_TOP_PX + by * CELL))

    img.convert("RGB").save(out_path)
    print("level %d, skin %s -> %s" % (level["number"], SKINS[skin_index], out_path))


def main():
    levels = parse_levels()
    want = int(sys.argv[1]) if len(sys.argv) > 1 else 1
    out = sys.argv[2] if len(sys.argv) > 2 else "level%d_preview.png" % want

    for lv in levels:
        if lv["number"] == want:
            render(lv, out)
            return
    raise SystemExit("level %d not in source/levels.c (35 was dropped)" % want)


if __name__ == "__main__":
    main()
