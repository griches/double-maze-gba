# Solutions

**Spoilers for all 40 levels.**

One D-pad press moves *both* balls, and each is blocked independently
by the walls on its own tile edges -- so a solution is a single
sequence of presses that walks both of them home at once. Every route
below is a shortest one: `tools/solve_level.py` searches the joint
state of the two balls breadth-first, under the same rules
`source/main.c` plays by, so the first solution it reaches is the
shortest that exists. Where several tie, it takes the first in the
order up, down, left, right.

Routes that kill either ball are pruned rather than followed, so
nothing here needs a restart along the way.

Regenerate with:

```sh
python3 tools/solve_level.py --all -o docs/SOLUTIONS.md
```

All 40 levels are solvable.
The shortest is level 25 at 6 moves, the longest level 4 at 39,
and playing every one back to back on these routes takes 675
presses.

| Level | Moves | Solution |
|---:|---:|---|
| 1 | 8 | ↓→→→↓→←← |
| 2 | 13 | ↑→↑←↓↑←↓→→↓←↓ |
| 3 | 24 | →↑↑←↑→↑↑←↓→←↑→→←↓→←↑→→→→ |
| 4 | 39 | ↓↓↓↓←↑↑↑↑↑→→↓↓↓↓↓→↑↑↑↑↑→↓→→↓↓→↓↓↓←↓↑↑↑↑ |
| 5 | 15 | →←↑↑↓→↓←←←→→↑↑← |
| 6 | 16 | →↑↓→↓→→↑↑↑↑←←↓←↓ |
| 7 | 12 | ↑↑↓↓→→→→←↑↑← |
| 8 | 16 | ↑↑→→↓↓←↓→↑↑→→→↓↓ |
| 9 | 16 | ←↓↓↓↑→↑↓→→→↑↑←↑← |
| 10 | 20 | ↓←↓←↑→↑→→↓→↓↓←↑←↑↑→↑ |
| 11 | 21 | ←←↓↓↓↓→↑↑↑↑↑→↓→→↓→↓←↑ |
| 12 | 12 | →→←↑←←←→→↓←↑ |
| 13 | 26 | ←←↓←↑→→→→←↓→↓↓↓←←←↓→→→↑←←↑ |
| 14 | 22 | →→←←↓→→→↓←↑←←↓→→↓↓↓←↓← |
| 15 | 20 | ↑→→→→→↓↓↑←←←→↑→↓↓↑↑→ |
| 16 | 23 | ↓↓↓→↑↑↑↑↑←→↓→→→↑→↑↑↑↑←↓ |
| 17 | 19 | →↓→→→←↓←←←←↑↑↓↓↓←←↓ |
| 18 | 21 | →→↑↓→→↓→↑↑↑↑↑↓←↓↓→↑↑↑ |
| 19 | 16 | ↑↑→→↑→↑→→↑↑↓←←←↑ |
| 20 | 20 | →↑↑↑↓→→↓↓←←←→↑↑↑←→↓↓ |
| 21 | 16 | ↑←←↓←↓←↑↑↑↓↓↓←→→ |
| 22 | 9 | ↑←↓→→→↓↓↓ |
| 23 | 17 | →↓←←←↓↓↓→→↑↑→↓←←← |
| 24 | 18 | →→→↑←↓←↓↓→→→↑↑←←↑→ |
| 25 | 6 | ↓→↓↓↑← |
| 26 | 21 | ←↓↓↑→→↓→→→←↑←←↑→→↓←↑↑ |
| 27 | 7 | ↓→↓←↑↑→ |
| 28 | 14 | ↑↓→→↑↑↑↓↓→↓→→↓ |
| 29 | 9 | →→←←↑↑←←↓ |
| 30 | 14 | ↑→↑↑↑→→→↓←←←↓↓ |
| 31 | 13 | →↓↓←←←←←→→→↑↑ |
| 32 | 13 | ↓↓↑→→↓↓←←←←↑↑ |
| 33 | 20 | ↓→↑←↓←←←↓↓↑→↑→→→↑↑←← |
| 34 | 17 | ↓→→↑↑←←↑→→↓↓↓↑↑↑← |
| 35 | 15 | ↓↓↑→↑↑↑←←→→↓↓→→ |
| 36 | 10 | ↓↓←←↑↑→↑↑↑ |
| 37 | 16 | ←→↑←↑↑↓←←↑→↓→→↑↑ |
| 38 | 14 | ↓→→→↑↑↑↑↑←↑←←↓ |
| 39 | 16 | ↓↓←↑↑↑→→↑←↓←↓↓↓← |
| 40 | 31 | →→←←↑↑→↓↓→↓↓←←←↑↑←↓↑←↓↓→→→↑↑→↑↑ |

## Move by move

**Level 1** — 8 moves: DOWN, RIGHT x3, DOWN, RIGHT, LEFT x2

**Level 2** — 13 moves: UP, RIGHT, UP, LEFT, DOWN, UP, LEFT, DOWN, RIGHT x2, DOWN, LEFT, DOWN

**Level 3** — 24 moves: RIGHT, UP x2, LEFT, UP, RIGHT, UP x2, LEFT, DOWN, RIGHT, LEFT, UP, RIGHT x2, LEFT, DOWN, RIGHT, LEFT, UP, RIGHT x4

**Level 4** — 39 moves: DOWN x4, LEFT, UP x5, RIGHT x2, DOWN x5, RIGHT, UP x5, RIGHT, DOWN, RIGHT x2, DOWN x2, RIGHT, DOWN x3, LEFT, DOWN, UP x4

**Level 5** — 15 moves: RIGHT, LEFT, UP x2, DOWN, RIGHT, DOWN, LEFT x3, RIGHT x2, UP x2, LEFT

**Level 6** — 16 moves: RIGHT, UP, DOWN, RIGHT, DOWN, RIGHT x2, UP x4, LEFT x2, DOWN, LEFT, DOWN

**Level 7** — 12 moves: UP x2, DOWN x2, RIGHT x4, LEFT, UP x2, LEFT

**Level 8** — 16 moves: UP x2, RIGHT x2, DOWN x2, LEFT, DOWN, RIGHT, UP x2, RIGHT x3, DOWN x2

**Level 9** — 16 moves: LEFT, DOWN x3, UP, RIGHT, UP, DOWN, RIGHT x3, UP x2, LEFT, UP, LEFT

**Level 10** — 20 moves: DOWN, LEFT, DOWN, LEFT, UP, RIGHT, UP, RIGHT x2, DOWN, RIGHT, DOWN x2, LEFT, UP, LEFT, UP x2, RIGHT, UP

**Level 11** — 21 moves: LEFT x2, DOWN x4, RIGHT, UP x5, RIGHT, DOWN, RIGHT x2, DOWN, RIGHT, DOWN, LEFT, UP

**Level 12** — 12 moves: RIGHT x2, LEFT, UP, LEFT x3, RIGHT x2, DOWN, LEFT, UP

**Level 13** — 26 moves: LEFT x2, DOWN, LEFT, UP, RIGHT x4, LEFT, DOWN, RIGHT, DOWN x3, LEFT x3, DOWN, RIGHT x3, UP, LEFT x2, UP

**Level 14** — 22 moves: RIGHT x2, LEFT x2, DOWN, RIGHT x3, DOWN, LEFT, UP, LEFT x2, DOWN, RIGHT x2, DOWN x3, LEFT, DOWN, LEFT

**Level 15** — 20 moves: UP, RIGHT x5, DOWN x2, UP, LEFT x3, RIGHT, UP, RIGHT, DOWN x2, UP x2, RIGHT

**Level 16** — 23 moves: DOWN x3, RIGHT, UP x5, LEFT, RIGHT, DOWN, RIGHT x3, UP, RIGHT, UP x4, LEFT, DOWN

**Level 17** — 19 moves: RIGHT, DOWN, RIGHT x3, LEFT, DOWN, LEFT x4, UP x2, DOWN x3, LEFT x2, DOWN

**Level 18** — 21 moves: RIGHT x2, UP, DOWN, RIGHT x2, DOWN, RIGHT, UP x5, DOWN, LEFT, DOWN x2, RIGHT, UP x3

**Level 19** — 16 moves: UP x2, RIGHT x2, UP, RIGHT, UP, RIGHT x2, UP x2, DOWN, LEFT x3, UP

**Level 20** — 20 moves: RIGHT, UP x3, DOWN, RIGHT x2, DOWN x2, LEFT x3, RIGHT, UP x3, LEFT, RIGHT, DOWN x2

**Level 21** — 16 moves: UP, LEFT x2, DOWN, LEFT, DOWN, LEFT, UP x3, DOWN x3, LEFT, RIGHT x2

**Level 22** — 9 moves: UP, LEFT, DOWN, RIGHT x3, DOWN x3

**Level 23** — 17 moves: RIGHT, DOWN, LEFT x3, DOWN x3, RIGHT x2, UP x2, RIGHT, DOWN, LEFT x3

**Level 24** — 18 moves: RIGHT x3, UP, LEFT, DOWN, LEFT, DOWN x2, RIGHT x3, UP x2, LEFT x2, UP, RIGHT

**Level 25** — 6 moves: DOWN, RIGHT, DOWN x2, UP, LEFT

**Level 26** — 21 moves: LEFT, DOWN x2, UP, RIGHT x2, DOWN, RIGHT x3, LEFT, UP, LEFT x2, UP, RIGHT x2, DOWN, LEFT, UP x2

**Level 27** — 7 moves: DOWN, RIGHT, DOWN, LEFT, UP x2, RIGHT

**Level 28** — 14 moves: UP, DOWN, RIGHT x2, UP x3, DOWN x2, RIGHT, DOWN, RIGHT x2, DOWN

**Level 29** — 9 moves: RIGHT x2, LEFT x2, UP x2, LEFT x2, DOWN

**Level 30** — 14 moves: UP, RIGHT, UP x3, RIGHT x3, DOWN, LEFT x3, DOWN x2

**Level 31** — 13 moves: RIGHT, DOWN x2, LEFT x5, RIGHT x3, UP x2

**Level 32** — 13 moves: DOWN x2, UP, RIGHT x2, DOWN x2, LEFT x4, UP x2

**Level 33** — 20 moves: DOWN, RIGHT, UP, LEFT, DOWN, LEFT x3, DOWN x2, UP, RIGHT, UP, RIGHT x3, UP x2, LEFT x2

**Level 34** — 17 moves: DOWN, RIGHT x2, UP x2, LEFT x2, UP, RIGHT x2, DOWN x3, UP x3, LEFT

**Level 35** — 15 moves: DOWN x2, UP, RIGHT, UP x3, LEFT x2, RIGHT x2, DOWN x2, RIGHT x2

**Level 36** — 10 moves: DOWN x2, LEFT x2, UP x2, RIGHT, UP x3

**Level 37** — 16 moves: LEFT, RIGHT, UP, LEFT, UP x2, DOWN, LEFT x2, UP, RIGHT, DOWN, RIGHT x2, UP x2

**Level 38** — 14 moves: DOWN, RIGHT x3, UP x5, LEFT, UP, LEFT x2, DOWN

**Level 39** — 16 moves: DOWN x2, LEFT, UP x3, RIGHT x2, UP, LEFT, DOWN, LEFT, DOWN x3, LEFT

**Level 40** — 31 moves: RIGHT x2, LEFT x2, UP x2, RIGHT, DOWN x2, RIGHT, DOWN x2, LEFT x3, UP x2, LEFT, DOWN, UP, LEFT, DOWN x2, RIGHT x3, UP x2, RIGHT, UP x2
