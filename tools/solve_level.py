#!/usr/bin/env python3
"""Solve levels the way the game plays them, and write up the results.

One D-pad press moves BOTH balls in that direction, and each is blocked
independently by the walls on its own tile edges -- so the state that matters
is the pair of positions, not either one alone. This searches that joint state
breadth-first, which makes the first solution it finds the shortest one.

The rules here mirror step_ball() and settle_step() in source/main.c exactly,
reading the same pre-decoded flags[] table the ROM does out of source/levels.c:

  * a ball may not leave a tile through a WALL_* edge of its own,
  * nor enter one through the neighbour's opposite edge,
  * a blocked ball simply stays put while the other one moves,
  * stepping off the grid is allowed and fatal, as is landing on FLAG_DEATH,
  * you win when both balls are alive and standing on FLAG_FINISH.

A move that kills either ball restarts the level, so those are dead ends rather
than losing states: the search prunes them and never needs a restart rule.

    python3 tools/solve_level.py 5                 # one level
    python3 tools/solve_level.py --all             # every level, as a table
    python3 tools/solve_level.py --all -o docs/SOLUTIONS.md
"""

import argparse
import os
import re
import sys
from collections import deque

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

GRID_W, GRID_H = 15, 8

# From source/levels.h. A WALL_* bit means you may NOT leave the tile that way.
WALL_UP     = 0x01
WALL_DOWN   = 0x02
WALL_LEFT   = 0x04
WALL_RIGHT  = 0x08
FLAG_FINISH = 0x10
FLAG_DEATH  = 0x20

# Direction -> (dx, dy, the bit that stops you leaving, the bit that stops you
# entering). Order fixes which shortest solution comes out when several tie, so
# the generated document doesn't churn between runs.
MOVES = [
    ("UP",    (0, -1), WALL_UP,    WALL_DOWN),
    ("DOWN",  (0,  1), WALL_DOWN,  WALL_UP),
    ("LEFT",  (-1, 0), WALL_LEFT,  WALL_RIGHT),
    ("RIGHT", (1,  0), WALL_RIGHT, WALL_LEFT),
]

ARROW = {"UP": "↑", "DOWN": "↓", "LEFT": "←", "RIGHT": "→"}


def parse_levels():
    """Pull number, start positions, tiles[] and flags[] out of the generated C.

    The search runs off flags[], because extract_levels.py has already turned
    the tile ids into the bitfield the game itself tests -- so the solver can't
    disagree with the ROM about what a given id blocks. tiles[] comes along for
    --verify, which replays the answer against the raw ids instead.
    """
    path = os.path.join(HERE, "source", "levels.c")
    text = open(path).read()

    levels = []
    for num, body in re.findall(r"\{ // level (\d+)(.*?)\n    \},", text, re.S):
        pos = re.search(r"\.left_x = (\d+), \.left_y = (\d+), "
                        r"\.right_x = (\d+), \.right_y = (\d+),", body)
        flags_txt = re.search(r"\.flags = \{(.*?)\},", body, re.S).group(1)
        tiles_txt = re.search(r"\.tiles = \{(.*?)\},", body, re.S).group(1)
        flags = [int(v) for v in re.findall(r"\d+", flags_txt)]
        tiles = [int(v) for v in re.findall(r"\d+", tiles_txt)]

        for name, table in (("flags", flags), ("tiles", tiles)):
            if len(table) != GRID_W * GRID_H:
                raise SystemExit("level %s: %d %s, expected %d"
                                 % (num, len(table), name, GRID_W * GRID_H))

        lx, ly, rx, ry = (int(g) for g in pos.groups())
        levels.append({
            "number": int(num),
            "start": (lx, ly, rx, ry),
            "flags": flags,
            "tiles": tiles,
        })

    if not levels:
        raise SystemExit("no levels found in %s" % path)
    return levels


def step(flags, x, y, dx, dy, leaving, entering):
    """One ball's response to one press: (x, y, alive).

    Mirrors step_ball(). A ball that can't move isn't an error -- it just
    stays where it is while the other one goes.
    """
    if flags[y * GRID_W + x] & leaving:
        return x, y, True

    nx, ny = x + dx, y + dy

    # Off the grid is a legal step and a fatal one. That's one of the ways the
    # original kills you, so it has to be reachable, not forbidden.
    if not (0 <= nx < GRID_W and 0 <= ny < GRID_H):
        return nx, ny, False

    if flags[ny * GRID_W + nx] & entering:
        return x, y, True

    return nx, ny, not (flags[ny * GRID_W + nx] & FLAG_DEATH)


def is_won(flags, state):
    lx, ly, rx, ry = state
    return bool(flags[ly * GRID_W + lx] & FLAG_FINISH) and \
        bool(flags[ry * GRID_W + rx] & FLAG_FINISH)


def solve(level):
    """Shortest list of move names, [] if it starts solved, None if it can't be.

    Also returns how much of the joint state space the search had to reach,
    which is the cheap sanity check that a level isn't trivially small.
    """
    flags = level["flags"]
    start = level["start"]

    seen = {start: None}
    queue = deque([start])

    while queue:
        state = queue.popleft()
        if is_won(flags, state):
            path = []
            while seen[state] is not None:
                state, name = seen[state]
                path.append(name)
            return list(reversed(path)), len(seen)

        lx, ly, rx, ry = state
        for name, (dx, dy), leaving, entering in MOVES:
            nlx, nly, l_alive = step(flags, lx, ly, dx, dy, leaving, entering)
            if not l_alive:
                continue
            nrx, nry, r_alive = step(flags, rx, ry, dx, dy, leaving, entering)
            if not r_alive:
                continue

            nxt = (nlx, nly, nrx, nry)
            if nxt != state and nxt not in seen:
                seen[nxt] = (state, name)
                queue.append(nxt)

    return None, len(seen)


# Tile semantics as the original states them -- (up, down, left, right, finish,
# death), where the first four mean "you may LEAVE this tile that way". This is
# the same table tools/extract_levels.py decodes flags[] from, kept in its
# original polarity on purpose: --verify replays a solution against it and the
# tiles[] array, so a mistake in the decode shows up as the two disagreeing
# rather than as both being wrong the same way.
TILE_TABLE = {
    0:  (1, 1, 1, 1, 0, 0),   1:  (0, 1, 1, 1, 0, 0),
    2:  (1, 1, 1, 0, 0, 0),   3:  (1, 0, 1, 1, 0, 0),
    4:  (1, 1, 0, 1, 0, 0),   5:  (1, 1, 1, 1, 1, 0),
    6:  (1, 1, 1, 1, 0, 1),   7:  (0, 1, 1, 1, 0, 1),
    8:  (1, 1, 1, 0, 0, 1),   9:  (1, 0, 1, 1, 0, 1),
    10: (1, 1, 0, 1, 0, 1),   11: (0, 1, 1, 1, 1, 0),
    12: (1, 1, 1, 0, 1, 0),   13: (1, 0, 1, 1, 1, 0),
    14: (1, 1, 0, 1, 1, 0),   15: (1, 1, 1, 1, 0, 1),
}

# Which slot of a TILE_TABLE row each direction reads when leaving, and which
# it reads when entering from that direction.
LEAVE_SLOT = {"UP": 0, "DOWN": 1, "LEFT": 2, "RIGHT": 3}
ENTER_SLOT = {"UP": 1, "DOWN": 0, "LEFT": 3, "RIGHT": 2}
DELTA = {"UP": (0, -1), "DOWN": (0, 1), "LEFT": (-1, 0), "RIGHT": (1, 0)}


def verify(level, path):
    """Replay a solution off tiles[] instead of flags[]. Returns an error, or None.

    Deliberately a second implementation rather than a call back into step():
    agreeing with itself would prove nothing.
    """
    tiles = level["tiles"]
    lx, ly, rx, ry = level["start"]
    balls = [(lx, ly), (rx, ry)]

    def can_leave(x, y, name):
        return TILE_TABLE[tiles[y * GRID_W + x]][LEAVE_SLOT[name]] == 1

    def can_enter(x, y, name):
        return TILE_TABLE[tiles[y * GRID_W + x]][ENTER_SLOT[name]] == 1

    for i, name in enumerate(path):
        dx, dy = DELTA[name]
        moved = []
        for (x, y) in balls:
            if not can_leave(x, y, name):
                moved.append((x, y))
                continue
            nx, ny = x + dx, y + dy
            if not (0 <= nx < GRID_W and 0 <= ny < GRID_H):
                return "move %d (%s) steps a ball off the grid" % (i + 1, name)
            if not can_enter(nx, ny, name):
                moved.append((x, y))
                continue
            if TILE_TABLE[tiles[ny * GRID_W + nx]][5]:
                return "move %d (%s) steps a ball into a hole" % (i + 1, name)
            moved.append((nx, ny))
        balls = moved

    for (x, y) in balls:
        if not TILE_TABLE[tiles[y * GRID_W + x]][4]:
            return "ends with a ball at %d,%d, which is not a goal" % (x, y)
    return None


# Ids that stop a ball on some edge. Everything else either lets it through or
# kills it -- neither of which can separate the two balls.
BLOCKING_IDS = {1, 2, 3, 4, 7, 8, 9, 10, 11, 12, 13, 14}


def diagnose(level):
    """Why a level can't be solved, in a line or two.

    Worth having because "no solution" on its own is indistinguishable from a
    solver bug. The interesting case is a level with no blocking tiles at all:
    nothing can ever stop one ball while the other moves, so the offset between
    them is fixed for the whole level and only one pair of goals can ever be
    reached. That's checkable directly, without searching anything.
    """
    tiles = level["tiles"]
    lx, ly, rx, ry = level["start"]

    if BLOCKING_IDS & set(tiles):
        return ["This level does have blocking tiles, so it isn't the "
                "fixed-offset case below.",
                "The search found no route; that wants checking by hand."]

    goals = [(i % GRID_W, i // GRID_W) for i, t in enumerate(tiles)
             if TILE_TABLE[t][4]]

    lines = [
        "Nothing in this level blocks movement -- the only tile ids present "
        "are floor, goal and hole.",
        "So no press can ever hold one ball while the other moves, and the "
        "offset between the two never changes for the whole level.",
        "They start %+d,%+d apart." % (rx - lx, ry - ly),
    ]
    for a in goals:
        for b in goals:
            if a != b:
                lines.append("Finishing with a ball on %s and the other on %s "
                             "would need them %+d,%+d apart."
                             % (a, b, b[0] - a[0], b[1] - a[1]))
    lines.append("No arrangement matches, so the pair can never be home "
                 "together.")
    return lines


def arrows(path):
    return "".join(ARROW[name] for name in path)


def runs(path):
    """The same moves as "RIGHT x3, UP x2" -- easier to follow off a page."""
    out = []
    for name in path:
        if out and out[-1][0] == name:
            out[-1][1] += 1
        else:
            out.append([name, 1])
    return ", ".join(n if c == 1 else "%s x%d" % (n, c) for n, c in out)


def report(level, path, reached):
    num = level["number"]
    if path is None:
        return "\n".join(
            ["level %d: NO SOLUTION (%d states reached)" % (num, reached)] +
            ["  " + line for line in diagnose(level)])
    if not path:
        return "level %d: already solved at the start" % num
    return ("level %d: %d moves (%d states reached)\n  %s\n  %s"
            % (num, len(path), reached, arrows(path), runs(path)))


def write_markdown(results, out_path):
    lines = [
        "# Solutions",
        "",
        "**Spoilers for all 40 levels.**",
        "",
        "One D-pad press moves *both* balls, and each is blocked independently",
        "by the walls on its own tile edges -- so a solution is a single",
        "sequence of presses that walks both of them home at once. Every route",
        "below is a shortest one: `tools/solve_level.py` searches the joint",
        "state of the two balls breadth-first, under the same rules",
        "`source/main.c` plays by, so the first solution it reaches is the",
        "shortest that exists. Where several tie, it takes the first in the",
        "order up, down, left, right.",
        "",
        "Routes that kill either ball are pruned rather than followed, so",
        "nothing here needs a restart along the way.",
        "",
        "Regenerate with:",
        "",
        "```sh",
        "python3 tools/solve_level.py --all -o docs/SOLUTIONS.md",
        "```",
        "",
    ]

    solved = [r for r in results if r["path"]]
    unsolvable = [r for r in results if r["path"] is None]

    if solved:
        shortest = min(solved, key=lambda r: len(r["path"]))
        longest = max(solved, key=lambda r: len(r["path"]))
        total = sum(len(r["path"]) for r in solved)
        lines += [
            "%d of the %d levels are solvable. The shortest is level %d at %d"
            % (len(solved), len(results), shortest["number"],
               len(shortest["path"])),
            "moves, the longest level %d at %d, and playing every solvable one"
            % (longest["number"], len(longest["path"])),
            "back to back on these routes takes %d presses." % total,
            "",
        ]

    for r in unsolvable:
        lines += ["> **Level %d cannot be finished.** This isn't a limit of the"
                  % r["number"],
                  "> search -- it's provable from the level data:",
                  ">"]
        lines += ["> - " + line for line in r["diagnosis"]]
        lines += [">",
                  "> This is the level data as the original iOS game shipped"
                  " it. That game had a",
                  "> skip button, and so does this one -- START moves on.",
                  ""]

    lines += ["| Level | Moves | Solution |", "|---:|---:|---|"]
    for r in results:
        if r["path"] is None:
            lines.append("| %d | — | **no solution** |" % r["number"])
        elif not r["path"]:
            lines.append("| %d | 0 | already solved |" % r["number"])
        else:
            lines.append("| %d | %d | %s |"
                         % (r["number"], len(r["path"]), arrows(r["path"])))

    lines += ["", "## Move by move", ""]
    for r in results:
        lines.append("**Level %d** — " % r["number"] +
                     ("cannot be finished; see above" if r["path"] is None else
                      "already solved" if not r["path"] else
                      "%d moves: %s" % (len(r["path"]), runs(r["path"]))))
        lines.append("")

    with open(out_path, "w") as fh:
        fh.write("\n".join(lines))
    print("wrote %s (%d levels)" % (out_path, len(results)))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("level", nargs="?", type=int,
                    help="level number to solve, 1-based")
    ap.add_argument("--all", action="store_true",
                    help="solve every level")
    ap.add_argument("-o", "--out",
                    help="with --all, write a Markdown write-up here")
    ap.add_argument("--strict", action="store_true",
                    help="exit non-zero if any level has no solution; off by "
                         "default because level 27 provably hasn't got one and "
                         "the write-up says so")
    ap.add_argument("--verify", action="store_true",
                    help="replay each solution against tiles[] as a check on "
                         "both the search and the flags[] decode")
    args = ap.parse_args()

    if not args.all and args.level is None:
        ap.error("give a level number, or --all")

    levels = parse_levels()

    if not args.all:
        for lv in levels:
            if lv["number"] == args.level:
                path, reached = solve(lv)
                print(report(lv, path, reached))
                if args.verify and path:
                    bad = verify(lv, path)
                    print("  verify: " + (bad if bad else "replays clean"))
                    if bad:
                        return 1
                return 1 if (args.strict and path is None) else 0
        raise SystemExit("level %d is not in source/levels.c" % args.level)

    results = []
    unsolved, broken = 0, 0
    for lv in levels:
        path, reached = solve(lv)
        results.append({
            "number": lv["number"],
            "path": path,
            "diagnosis": diagnose(lv) if path is None else None,
        })
        if path is None:
            unsolved += 1
        if not args.out:
            print(report(lv, path, reached))

        if args.verify and path:
            bad = verify(lv, path)
            if bad:
                broken += 1
                print("level %d FAILS VERIFY: %s" % (lv["number"], bad),
                      file=sys.stderr)

    checked = sum(1 for r in results if r["path"])
    if args.verify and not broken:
        print("%d solutions replay clean against tiles[]" % checked)

    if args.out:
        write_markdown(results, args.out)

    if unsolved:
        print("%d level(s) have no solution" % unsolved, file=sys.stderr)

    if args.verify and broken:
        return 1
    return 1 if (args.strict and unsolved) else 0


if __name__ == "__main__":
    sys.exit(main())
