# What's in the iOS original

Extracted from `/Users/garyriches/Documents/Source/DoubleMaze`. This is the
reference for the GBA port — the rules below are what the shipped game actually
does, read out of the source rather than inferred.

**It's Objective-C, not Swift.** ~7,200 lines across `DoubleMaze/Classes`, UIKit
with `.xib` files, dating from 2009 with modernisation passes since. That's
good news for the port: the game logic is already C-adjacent, so most of it
transliterates rather than needing a redesign.

## The grid

15 wide x 8 tall, 120 tiles, stored row-major. `Player.m` hardcodes
`#define arrayWidth 15` and derives neighbours as `current ± 1` and
`current ± 15`.

Both balls live on the **same** grid. There aren't two separate mazes — column 7
is a wall spine, the left ball plays cols 1-6 and the right ball cols 8-13. Start
positions across all 40 levels span cols 1-13 and rows 1-6, so rows 0/7 and cols
0/14 are the border.

> `ScreenDimensions.m` has `optimalGridHeight` returning 15 with the comment
> "Keep original 15x15 grid". That's wrong and unused for indexing — the data is
> definitively 15x8. Don't copy that constant across.

## Tile semantics

Walls sit on tile **edges**, not on whole cells. Each tile id encodes at most one
blocked edge, plus optional goal/death flags. From the `switch (i)` in
`Double_MazeViewController.m:2971`:

| id | meaning | up | down | left | right | finish | death |
|----|---------|:--:|:----:|:----:|:-----:|:------:|:-----:|
| 0  | floor              | Y | Y | Y | Y | – | – |
| 1  | wall on top        | · | Y | Y | Y | – | – |
| 2  | wall on right      | Y | Y | Y | · | – | – |
| 3  | wall on bottom     | Y | · | Y | Y | – | – |
| 4  | wall on left       | Y | Y | · | Y | – | – |
| 5  | goal               | Y | Y | Y | Y | Y | – |
| 6  | hole               | Y | Y | Y | Y | – | Y |
| 7  | wall on top + hole    | · | Y | Y | Y | – | Y |
| 8  | wall on right + hole  | Y | Y | Y | · | – | Y |
| 9  | wall on bottom + hole | Y | · | Y | Y | – | Y |
| 10 | wall on left + hole   | Y | Y | · | Y | – | Y |
| 11 | wall on top + goal    | · | Y | Y | Y | Y | – |
| 12 | wall on right + goal  | Y | Y | Y | · | Y | – |
| 13 | wall on bottom + goal | Y | · | Y | Y | Y | – |
| 14 | wall on left + goal   | Y | Y | · | Y | Y | – |
| 15 | hole (duplicate of 6) | Y | Y | Y | Y | – | Y |

Tile 6 is by far the most common (2,243 of 4,680 placed tiles) — it's both the
border and the interior obstacle. Tile 11 appears exactly once in the whole set,
and 12 never appears at all.

## Movement

Swipe-driven, from `touchesEnded:` at `Double_MazeViewController.m:3756`:

- Direction is the dominant axis of the swipe, with a 20-point deadzone.
- **One step per swipe.** Not sliding — the ball moves exactly one cell.
- **Both balls move on every swipe, in the same direction.** Each is tested
  independently, so one can move while the other is blocked. That coupling is
  the whole game.
- A move is legal when the current tile's edge is open **and** the target tile's
  opposite edge is open. Both sides are checked.
- Moving off the grid edge is deliberately allowed and kills you.
- Animation is 0.4s (`kAnimationSpeed`), and input is locked while `isAnimating`.

**Death**: landing on a tile with `death` set restarts the level after a 1.5s
delay, with the death animation and the whistle sound.

**Win**: both balls on `finish` tiles simultaneously. Progresses after 1.0s.
Standing on one goal while the other ball isn't on one plays a chime as
feedback — a nice touch worth keeping.

## Levels

40 pairs of `levelN.txt` (120 comma-separated tile ids) and `levelNPOS.txt`
(`leftX,leftY,rightX,rightY`).

**39 are usable. `level35.txt` is empty** — zero bytes of tile data. Its
`level35POS.txt` is intact, so the tile file was lost rather than never
authored. The extractor skips it, which renumbers everything after it; if you
want level 35 back it needs re-authoring.

Everything else validates clean: no unknown tile ids, no start position on a
death tile, every level has at least two goals.

`tools/extract_levels.py` converts them to `source/levels.c` / `source/levels.h`,
emitting both the raw ids and a pre-decoded bitfield (`WALL_UP`, `WALL_DOWN`,
`WALL_LEFT`, `WALL_RIGHT`, `FLAG_FINISH`, `FLAG_DEATH`) so the movement check is
two bit tests rather than a table lookup. 39 levels x 240 bytes = 9.4KB of ROM.

## Graphics

293 PNGs, each with an `@2x` sibling. Sizes below are 1x.

**Gameplay**
| Asset | Size | Notes |
|---|---|---|
| `purple/orange/greentile/black/blue.png` | 32x36 | Five tile skins; 36 tall because of the 3D top lip |
| `*_target_off.png` / `*_target_on.png` | 32x36 | Goal tile, unlit and lit |
| `blankTile.png` | 32x36 | |
| `wall1..wall5.png` | 44x44 | |
| `ball.png` | 32x32 | |
| `*bg.png` (black/orange/green/blue/maroon/blank) | 480x320 | Full-screen backgrounds |

Only three of the five tile skins are wired up — `tileSets` lists purple, orange
and greentile. `black` and `blue` exist as art but are unreferenced.

**Screens** (all 480x320): `title`, `selectLevel`, `selectCustomLevel`,
`instructions`, `Default`, `DefaultRotated`, `splash` (320x480), plus
`loading` at 278x141 and an assortment of buttons from 39x39 up to 232x54.

The whole game is **480x320 landscape**. The GBA is 240x160 — exactly half in
both axes, which is about as clean a target as you could ask for.

## Animations

| Set | Frames | Size | Status |
|---|---|---|---|
| `balldeath0001-0038` | 38 | 32x32 | present |
| `move0001-0022` | 22 | 32x32 | present, **never referenced in code** |
| `bounce0001-0013` | 13 | 122x156 | launch screen; code plays 1, 2, 13 only |
| `ballleft/ballright/ballup/balldown 0001-0008` | 8 each | — | **missing from the project** |

That last row is a live bug in the iOS app. `initializeGameData` builds four
directional roll animations via `imageNamed:@"ballleft0001..."` etc. at
`Double_MazeViewController.m:2860-2899`, but no such files exist anywhere in the
repo — `imageNamed:` returns nil for all 32 of them, so the arrays are full of
nils and the rolling animation never plays. The unreferenced `move0001-0022`
set is almost certainly what those calls were meant to point at.

`File.txt` in the project root is a note asking for the launch bounce to play
frames 0, 1, 2, 13 four times; the code plays 1, 2, 13.

## Audio

Six effects plus one music track, loaded at `Double_MazeViewController.m:2847`:

| Slot | File | Used for |
|---|---|---|
| 0 | `CARTOON_WHISTLE__40017804.wav` | death |
| 1 | `Stone_on_Metal_23.wav` | ball roll |
| 2 | `Books_Manuals_Ma_NF060382.wav` | page turn / screen transition |
| 3 | `Glass_Chime_Tinkle_Low.wav` | goal reached, level complete |
| 4 | `Stone_on_Metal_23.wav` | same file as slot 1 |
| 5 | `buttonclick.wav` | UI click |

Plus `music.mp3`, 713KB, looping background music.

## Mapping onto GBA hardware

**Screen.** 15 columns x 16px = 240, exactly the GBA width. At 16x16 tiles the
grid is 240x128, leaving 32px for a HUD band. Don't try to preserve the 32x36
aspect — 36 isn't a multiple of 8 and the hardware will fight you. Squash to
16x16 and move the 3D lip into the tile art.

**Tiles.** 16 tile types as 16x16 metatiles = 4 hardware tiles each = 64 tiles,
plus goal-lit variants. A charblock holds 512 4bpp tiles, so there's room for
all five skins resident at once if you want them.

**Sprites.** Ball at 16x16 = one OBJ, 4 tiles. Two balls is trivial. The
animations need cutting down hard: 38 death frames at 16x16 is 152 tiles of the
1024-tile OBJ budget. Eight frames is plenty at this size, and 22 roll frames
should come down to 4-8.

**Screens.** The 480x320 title/menu art halves to 240x160, which is exactly a
mode 4 framebuffer (8bpp, 256 colours, 37.5KB). Store them compressed in ROM
and DMA to VRAM on transition.

**Audio.** The mp3 can't be used as-is. Convert `music.mp3` to a tracker module
(MOD/XM/IT) for maxmod, and the six wavs to 8-bit mono at ~11kHz through
`mmutil`. That's roughly 50KB of samples for the effects.

**Input.** Swipes become D-pad presses, which is a straight upgrade — the
20-point deadzone and the `isAnimating` input lock both disappear. Keep a short
lockout during the step animation or hold-to-repeat will outrun it.

## Decisions taken

1. **Level 35** — dropped. Shipping 39 levels, renumbered contiguously.
2. **Roll animation** — ball stays static for now. `move0001-0022` is extracted
   and available whenever it's worth wiring up.
3. **Tile skins** — all three carried across (purple, orange, greentile), with
   the original's every-two-levels cycle intact.
4. **Custom levels and the editor** — dropped. No HTTP downloader, no in-app
   editor on a cartridge.

One deliberate visual deviation: the iOS renderer draws the whole 44x44 wall
image at 1.375x the cell, centred, so the bar inside it straddles the boundary
and overhangs both neighbours. A tilemap can't overhang. Simply scaling the
image down to the cell loses what that 1.375 was buying -- the bar comes out
68% of the cell wide and 3px thick instead of 94% and 4px, and reads as a stray
stick floating inside the tile. So the GBA build crops the bar out of its
frame, scales it at the original's proportions, and seats it flush against the
edge it blocks: same size and weight, wholly inside the cell rather than
straddling it.
