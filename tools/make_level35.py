#!/usr/bin/env python3
"""Author a replacement for the missing level 35, and prove it's solvable.

level35.txt is empty in the original project -- the tile data was lost at some
point, though level35POS.txt survived with the two start positions. This builds
a level around those positions and verifies it with a breadth-first search over
the joint state of both balls, which also yields the shortest solution.

    python3 tools/make_level35.py [--seed N]

Writes levels/level35.txt. tools/extract_levels.py prefers anything in levels/
over the original project, so the iOS repo is left untouched.
"""

import argparse
import os
import random
from collections import deque

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT_DIR = os.path.join(HERE, "levels")

GRID_W, GRID_H = 15, 8
BORDER = 6                      # hole: lethal, and what surrounds both mazes

# Interior of each maze: columns, and rows 1-6 for both.
LEFT_COLS = range(1, 7)
RIGHT_COLS = range(8, 14)
ROWS = range(1, 7)

START_L = (2, 4)                # from the surviving level35POS.txt
START_R = (9, 3)

# Tile ids for a floor carrying a wall on one edge.
WALL_TILE = {"top": 1, "right": 2, "bottom": 3, "left": 4}
FLOOR, GOAL = 0, 5

# Which edges each tile blocks, mirroring the table in the game.
BLOCKS = {
    0: (), 5: (),
    1: ("top",), 2: ("right",), 3: ("bottom",), 4: ("left",),
}
OPPOSITE = {"top": "bottom", "bottom": "top", "left": "right", "right": "left"}
STEP = {"top": (0, -1), "bottom": (0, 1), "left": (-1, 0), "right": (1, 0)}
MOVE_NAME = {"top": "UP", "bottom": "DOWN", "left": "LEFT", "right": "RIGHT"}


def in_maze(x, y, cols):
    return x in cols and y in ROWS


def can_step(tiles, x, y, edge):
    """Both sides of the boundary must be open, as the game checks it."""
    if edge in BLOCKS[tiles[y][x]]:
        return False
    dx, dy = STEP[edge]
    nx, ny = x + dx, y + dy
    if not (0 <= nx < GRID_W and 0 <= ny < GRID_H):
        return False
    if OPPOSITE[edge] in BLOCKS.get(tiles[ny][nx], ()):
        return False
    return True


def lethal(tiles, x, y):
    return tiles[y][x] == BORDER


def solve(tiles, start_l, start_r, goal_l, goal_r):
    """Shortest move sequence with neither ball dying, or None."""
    start = (start_l[0], start_l[1], start_r[0], start_r[1])
    goal = (goal_l[0], goal_l[1], goal_r[0], goal_r[1])

    seen = {start: None}
    queue = deque([start])
    while queue:
        state = queue.popleft()
        if state == goal:
            path = []
            while seen[state] is not None:
                state, edge = seen[state]
                path.append(edge)
            return list(reversed(path))

        lx, ly, rx, ry = state
        for edge in ("top", "bottom", "left", "right"):
            dx, dy = STEP[edge]
            nxt = []
            died = False
            for (x, y) in ((lx, ly), (rx, ry)):
                if can_step(tiles, x, y, edge):
                    tx, ty = x + dx, y + dy
                    if lethal(tiles, tx, ty):
                        died = True
                        break
                    nxt.append((tx, ty))
                else:
                    nxt.append((x, y))
            if died:
                continue

            new = (nxt[0][0], nxt[0][1], nxt[1][0], nxt[1][1])
            if new != state and new not in seen:
                seen[new] = (state, edge)
                queue.append(new)
    return None


def solo_solve(tiles, start, goal):
    """Shortest route for one ball on its own, ignoring the other."""
    seen = {start: 0}
    queue = deque([start])
    while queue:
        x, y = queue.popleft()
        if (x, y) == goal:
            return seen[(x, y)]
        for edge in ("top", "bottom", "left", "right"):
            if not can_step(tiles, x, y, edge):
                continue
            dx, dy = STEP[edge]
            nxt = (x + dx, y + dy)
            if lethal(tiles, *nxt) or nxt in seen:
                continue
            seen[nxt] = seen[(x, y)] + 1
            queue.append(nxt)
    return None


def build(rng, cols, start, goal, barrier_count):
    """Pick barriers for one maze and assign each to a cell that's still free.

    A barrier between two cells can be written as a wall on either side of it,
    since the game checks both. That freedom matters because a tile can only
    carry one wall -- so when one cell is taken, the other side is tried.
    """
    edges = []
    for y in ROWS:
        for x in cols:
            if x + 1 in cols:
                edges.append(((x, y), (x + 1, y), "right", "left"))
            if y + 1 in ROWS:
                edges.append(((x, y), (x, y + 1), "bottom", "top"))
    rng.shuffle(edges)

    assigned = {}
    placed = 0
    for a, b, a_edge, b_edge in edges:
        if placed >= barrier_count:
            break
        for cell, edge in ((a, a_edge), (b, b_edge)):
            if cell in assigned or cell == goal:
                continue
            assigned[cell] = edge
            placed += 1
            break
    return assigned


def compose(left_walls, right_walls, goal_l, goal_r):
    tiles = [[BORDER] * GRID_W for _ in range(GRID_H)]
    for cols, walls, goal in ((LEFT_COLS, left_walls, goal_l),
                              (RIGHT_COLS, right_walls, goal_r)):
        for y in ROWS:
            for x in cols:
                tiles[y][x] = FLOOR
        tiles[goal[1]][goal[0]] = GOAL
        for (x, y), edge in walls.items():
            tiles[y][x] = WALL_TILE[edge]
    return tiles


def far_from(rng, cols, start, min_dist):
    while True:
        g = (rng.choice(list(cols)), rng.choice(list(ROWS)))
        if abs(g[0] - start[0]) + abs(g[1] - start[1]) >= min_dist:
            return g


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--seed", type=int, default=None)
    ap.add_argument("--min-moves", type=int, default=14)
    ap.add_argument("--max-moves", type=int, default=26)
    args = ap.parse_args()

    rng = random.Random(args.seed)
    best = None

    for attempt in range(200000):
        goal_l = far_from(rng, LEFT_COLS, START_L, 5)
        goal_r = far_from(rng, RIGHT_COLS, START_R, 5)
        lw = build(rng, LEFT_COLS, START_L, goal_l, rng.randint(9, 14))
        rw = build(rng, RIGHT_COLS, START_R, goal_r, rng.randint(9, 14))
        tiles = compose(lw, rw, goal_l, goal_r)

        path = solve(tiles, START_L, START_R, goal_l, goal_r)
        if not path or not (args.min_moves <= len(path) <= args.max_moves):
            continue

        # Prefer a puzzle where the two balls genuinely interfere. If the joint
        # solution is barely longer than the harder ball's own route, the
        # second maze isn't contributing anything.
        solo_l = solo_solve(tiles, START_L, goal_l)
        solo_r = solo_solve(tiles, START_R, goal_r)
        if solo_l is None or solo_r is None:
            continue
        slack = len(path) - max(solo_l, solo_r)
        score = (slack, len(path))

        if best is None or score > best[0]:
            best = (score, tiles, path, goal_l, goal_r, attempt)
            if slack >= 6:
                break

    if best is None:
        raise SystemExit("no level found; widen the move range")

    score, tiles, path, goal_l, goal_r, attempt = best
    os.makedirs(OUT_DIR, exist_ok=True)
    flat = [tiles[y][x] for y in range(GRID_H) for x in range(GRID_W)]
    with open(os.path.join(OUT_DIR, "level35.txt"), "w") as fh:
        fh.write(",".join(str(v) for v in flat))

    print("wrote levels/level35.txt  (attempt %d, slack %d)" % (attempt, score[0]))
    print("start  left %s   right %s" % (START_L, START_R))
    print("goals  left %s   right %s" % (goal_l, goal_r))
    print("\ngrid:")
    for y in range(GRID_H):
        print("  " + " ".join("%2d" % tiles[y][x] for x in range(GRID_W)))
    print("\nsolution (%d moves):" % len(path))
    print("  " + " ".join(MOVE_NAME[e] for e in path))


if __name__ == "__main__":
    main()
