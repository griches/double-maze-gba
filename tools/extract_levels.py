#!/usr/bin/env python3
"""Convert the iOS Double Maze level files into C tables for the GBA build.

Reads levelN.txt (120 comma-separated tile ids, a 15x8 grid) and levelNPOS.txt
(leftX, leftY, rightX, rightY) from the original Objective-C project and writes
source/levels.c and source/levels.h.

    python3 tools/extract_levels.py [path-to-ios-project]

Also validates each level and reports anything the GBA build would choke on.
"""

import os
import sys

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DEFAULT_SRC = "/Users/garyriches/Documents/Source/DoubleMaze/DoubleMaze"

# Levels authored here rather than recovered from the iOS project. Anything in
# this directory wins, which is how the lost level 35 gets replaced without
# touching the original repo. See tools/make_level35.py.
OVERRIDE_DIR = os.path.join(HERE, "levels")

GRID_W = 15
GRID_H = 8
GRID_AREA = GRID_W * GRID_H
LEVEL_COUNT = 40

# Tile semantics, lifted from the switch in Double_MazeViewController.m.
# (up, down, left, right, finish, death) -- up/down/left/right mean "you may
# leave this tile in that direction".
TILE_TABLE = {
    0:  (1, 1, 1, 1, 0, 0),   # floor
    1:  (0, 1, 1, 1, 0, 0),   # wall on top
    2:  (1, 1, 1, 0, 0, 0),   # wall on right
    3:  (1, 0, 1, 1, 0, 0),   # wall on bottom
    4:  (1, 1, 0, 1, 0, 0),   # wall on left
    5:  (1, 1, 1, 1, 1, 0),   # goal
    6:  (1, 1, 1, 1, 0, 1),   # hole / death
    7:  (0, 1, 1, 1, 0, 1),   # wall on top + death
    8:  (1, 1, 1, 0, 0, 1),   # wall on right + death
    9:  (1, 0, 1, 1, 0, 1),   # wall on bottom + death
    10: (1, 1, 0, 1, 0, 1),   # wall on left + death
    11: (0, 1, 1, 1, 1, 0),   # wall on top + goal
    12: (1, 1, 1, 0, 1, 0),   # wall on right + goal
    13: (1, 0, 1, 1, 1, 0),   # wall on bottom + goal
    14: (1, 1, 0, 1, 1, 0),   # wall on left + goal
    # Walled on all four edges: nothing can enter it, and it isn't fatal.
    #
    # This is the one place the port departs from the original's switch, which
    # has `case 15:` fall in with `case 6:` -- passable in every direction, and
    # death. Everything else about the tile says otherwise: renderLevel draws
    # wall5.png for it ("All walls"), and the level editor labels it with
    # editorTileWall.png and files it under "Attach a wall". It plainly means
    # a solid block, and the switch is a bug.
    #
    # It matters because tile 15 appears exactly 15 times in the whole game,
    # all of them in level 27 -- which, taken as holes, cannot be finished:
    # with nothing in that level able to block a ball, the two never change
    # their offset, and the goals aren't the offset they start at. Read as
    # blocks it's an ordinary level with a 7-move solution. See
    # tools/solve_level.py, which proves both halves of that.
    15: (0, 0, 0, 0, 0, 0),
}

WALL_UP, WALL_DOWN, WALL_LEFT, WALL_RIGHT = 1, 2, 4, 8
FLAG_FINISH, FLAG_DEATH = 16, 32


def tile_flags(t):
    """Pack a tile id into the bitfield the GBA code uses."""
    up, down, left, right, finish, death = TILE_TABLE[t]
    f = 0
    if not up:    f |= WALL_UP
    if not down:  f |= WALL_DOWN
    if not left:  f |= WALL_LEFT
    if not right: f |= WALL_RIGHT
    if finish:    f |= FLAG_FINISH
    if death:     f |= FLAG_DEATH
    return f


def read_ints(path):
    with open(path) as fh:
        raw = fh.read().strip()
    return [int(p) for p in raw.split(",") if p.strip() != ""]


def source_for(src, name):
    """Prefer an authored level over the original project's copy."""
    override = os.path.join(OVERRIDE_DIR, name)
    if os.path.exists(override):
        return override, True
    return os.path.join(src, name), False


def load(src):
    levels, problems = [], []
    authored = []
    for n in range(1, LEVEL_COUNT + 1):
        tpath, is_override = source_for(src, "level%d.txt" % n)
        ppath, _ = source_for(src, "level%dPOS.txt" % n)
        if is_override:
            authored.append(n)

        if not os.path.exists(tpath):
            problems.append("level %d: level%d.txt missing" % (n, n))
            levels.append(None)
            continue

        tiles = read_ints(tpath)
        if len(tiles) != GRID_AREA:
            problems.append("level %d: %d tiles, expected %d -- SKIPPED"
                            % (n, len(tiles), GRID_AREA))
            levels.append(None)
            continue

        bad = sorted({t for t in tiles if t not in TILE_TABLE})
        if bad:
            problems.append("level %d: unknown tile ids %s" % (n, bad))
            levels.append(None)
            continue

        pos = read_ints(ppath) if os.path.exists(ppath) else []
        if len(pos) != 4:
            problems.append("level %d: POS has %d values, expected 4 -- SKIPPED"
                            % (n, len(pos)))
            levels.append(None)
            continue

        lx, ly, rx, ry = pos
        for label, x, y in (("left", lx, ly), ("right", rx, ry)):
            if not (0 <= x < GRID_W and 0 <= y < GRID_H):
                problems.append("level %d: %s start (%d,%d) is off the grid"
                                % (n, label, x, y))
            elif TILE_TABLE[tiles[y * GRID_W + x]][5]:
                problems.append("level %d: %s start (%d,%d) is a death tile"
                                % (n, label, x, y))

        goals = [i for i, t in enumerate(tiles) if TILE_TABLE[t][4]]
        if len(goals) < 2:
            problems.append("level %d: only %d goal tile(s), needs 2"
                            % (n, len(goals)))

        levels.append({"n": n, "tiles": tiles, "pos": pos, "goals": goals})

    if authored:
        problems.append("authored locally rather than from the iOS project: "
                        + ", ".join("level %d" % n for n in authored))

    return levels, problems


def emit(levels, out_dir):
    playable = [lv for lv in levels if lv]

    h = ["// Generated by tools/extract_levels.py -- do not edit by hand.",
         "// Source: the original iOS Double Maze level%d.txt / level%dPOS.txt files.",
         "",
         "#ifndef DOUBLE_MAZE_LEVELS_H",
         "#define DOUBLE_MAZE_LEVELS_H",
         "",
         "#include <tonc.h>",
         "",
         "#define GRID_W %d" % GRID_W,
         "#define GRID_H %d" % GRID_H,
         "#define GRID_AREA (GRID_W * GRID_H)",
         "#define LEVEL_COUNT %d" % len(playable),
         "",
         "// Per-tile bitfield. A WALL_* bit means you may NOT leave the tile that way;",
         "// entering a tile additionally requires its opposite edge to be open.",
         "#define WALL_UP     0x01",
         "#define WALL_DOWN   0x02",
         "#define WALL_LEFT   0x04",
         "#define WALL_RIGHT  0x08",
         "#define FLAG_FINISH 0x10",
         "#define FLAG_DEATH  0x20",
         "",
         "typedef struct LevelData",
         "{",
         "    u8 number;              // original level number, 1-based",
         "    u8 left_x,  left_y;     // starting cell for the left ball",
         "    u8 right_x, right_y;    // starting cell for the right ball",
         "    u8 tiles[GRID_AREA];    // raw tile ids, 0-15",
         "    u8 flags[GRID_AREA];    // tiles[] pre-decoded into the bitfield above",
         "} LevelData;",
         "",
         "extern const LevelData g_levels[LEVEL_COUNT];",
         "",
         "#endif // DOUBLE_MAZE_LEVELS_H",
         ""]

    c = ["// Generated by tools/extract_levels.py -- do not edit by hand.",
         "",
         '#include "levels.h"',
         "",
         "const LevelData g_levels[LEVEL_COUNT] =",
         "{"]

    for lv in playable:
        lx, ly, rx, ry = lv["pos"]
        c.append("    { // level %d" % lv["n"])
        c.append("        .number = %d," % lv["n"])
        c.append("        .left_x = %d, .left_y = %d, .right_x = %d, .right_y = %d,"
                 % (lx, ly, rx, ry))
        for name, values in (("tiles", lv["tiles"]),
                             ("flags", [tile_flags(t) for t in lv["tiles"]])):
            c.append("        .%s = {" % name)
            for row in range(GRID_H):
                chunk = values[row * GRID_W:(row + 1) * GRID_W]
                c.append("            " + ", ".join("%3d" % v for v in chunk) + ",")
            c.append("        },")
        c.append("    },")

    c += ["};", ""]

    with open(os.path.join(out_dir, "levels.h"), "w") as fh:
        fh.write("\n".join(h))
    with open(os.path.join(out_dir, "levels.c"), "w") as fh:
        fh.write("\n".join(c))

    return len(playable)


def main():
    src = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_SRC
    out_dir = os.path.join(HERE, "source")

    levels, problems = load(src)
    count = emit(levels, out_dir)

    print("wrote source/levels.c and source/levels.h -- %d playable levels" % count)
    if problems:
        print("\n%d problem(s) in the source data:" % len(problems))
        for p in problems:
            print("  " + p)


if __name__ == "__main__":
    main()
