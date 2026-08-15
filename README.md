# double_maze

Game Boy Advance port of the iOS game. Two balls share one 15x8 grid — the left
plays columns 1-6, the right columns 8-13. Every D-pad press moves **both**
balls in that direction, and each is blocked independently by the walls on its
own tile edges. Land on a hole and the level restarts; get both balls onto goal
tiles at the same time and you advance.

39 levels, carried over from the original along with its artwork. See
[EXTRACTION.md](EXTRACTION.md) for how the rules and assets were recovered.

## Controls

**Title:** START or A to play, B for how-to-play, SELECT toggles music.
**Level select:** D-pad to move, A to play, B to go back.

**In game:**

| Input | Action |
|---|---|
| D-pad | Step both balls |
| START | Skip to the next level |
| SELECT | Restart the current level |
| B | Back to level select |

## Building

```sh
make          # build double_maze.gba
make run      # build, then boot it in mGBA
make clean    # remove build output
make assets   # rebuild tilesets, sprites, title art and font
make levels   # rebuild the level tables from the iOS level files
make audio    # re-encode the iOS audio into audio/*.wav for mmutil
```

Requires `DEVKITPRO` and `DEVKITARM` in the environment (added to `~/.zshrc`
during setup). If `make` complains about `DEVKITARM`, open a fresh shell.

Both asset steps read from the original iOS project, which they expect at
`/Users/garyriches/Documents/Source/DoubleMaze/DoubleMaze`. Pass a different
path as the first argument if it moves. The generated files are checked in, so
you only need to rerun them if the source art or level data changes.

## Toolchain

| Piece | What it does | Where |
|---|---|---|
| devkitARM | `arm-none-eabi-*` cross compiler, linker scripts, CRT0 | `/opt/devkitpro/devkitARM` |
| libtonc | GBA hardware library — the one [Tonc](https://gbadev.net/tonc/) teaches | `/opt/devkitpro/libtonc` |
| grit | PNG → tile/palette converter | `/opt/devkitpro/tools/bin/grit` |
| gbafix | Stamps a valid cartridge header (run automatically) | `/opt/devkitpro/tools/bin/gbafix` |
| mGBA | Emulator, and GDB server for debugging | `/Applications/mGBA.app` |

Update the toolchain with `sudo /usr/local/bin/dkp-pacman -Syu`.

## Layout

```
Makefile                 devkitARM template + grit/mmutil rules + run target
source/
  main.c                 app state machine, movement rules, menus
  render.c / render.h    tilemap painting, goal lighting, text, HUD
  audio.c / audio.h      maxmod wrapper: effects and looping music
  save.c / save.h        SRAM progress, checksummed
  levels.c / levels.h    generated: 39 levels, tiles + decoded wall bitfields
  skins.h                generated: backdrops, lit-goal lookup, sprite indices
  fontmap.h              generated: ASCII -> glyph lookup
gfx/
  tiles_purple/orange/green.png + .grit    generated: 21 metatiles per skin
  ball.png + .grit                         generated: ball + 12 death frames
  title.png + .grit                        generated: title art, tiles + map
  font.png + .grit                         generated: 48 glyphs, 5x7 in 8x8
audio/                   generated: 6 effects + looping music, for mmutil
tools/
  extract_levels.py      iOS level*.txt  -> source/levels.c
  make_assets.py         iOS artwork     -> gfx/*.png, source/skins.h
  make_audio.py          iOS audio       -> audio/*.wav
  preview_level.py       renders a level to PNG without running the ROM
```

## How the screen is put together

Mode 0, one regular background (BG0) on charblock 0 / screenblock 30, plus two
16x16 sprites for the balls.

The grid is 15x8 cells of 16x16 pixels — 240x128, so it fills the screen width
exactly and leaves 32 pixels of vertical slack, split 16 above and 16 below.
The HUD sits on the bottom row.

Each cell is a **metatile**: a 16x16 block that grit exports as 4 consecutive
hardware tiles (`-Mw2 -Mh2`), laid out TL, TR, BL, BR. A skin is 21 metatiles —
the 16 tile ids plus lit variants of the 5 goal types — so 84 hardware tiles.
All three skins stay resident (252 of the charblock's 512 tiles), which makes
switching skins a palette-bank change rather than a VRAM upload.

Charblock 0 holds everything: three skins (252 tiles), the font (48) and the
title art (133), for 433 of the 512 available. That means the menus and the
game share one video mode with no VRAM reloads between them — the title screen
is a tilemap, not a bitmap.

BG palette banks: 0 purple, 1 orange, 2 green, 3 font, 4 title. Void tiles are
transparent, so `pal_bg_mem[0]` carries the skin's backdrop colour — sampled
from the matching iOS background image.

Like the original, the skin advances every two levels: `floor(index / 2) % 3`.

## Debugging

mGBA ships a GDB stub. In mGBA: **Tools → Start GDB server** (default port
2345), then:

```sh
arm-none-eabi-gdb double_maze.elf
(gdb) target remote localhost:2345
```

`double_maze.elf` keeps full debug info; the `.gba` is the stripped binary
image with a cartridge header.

### Screenshots

`make shot SHOT=out.png` captures what the ROM is *actually* drawing, via
`tools/grab_screen.py`. It dumps VRAM, palette RAM, OAM and the display
registers over mGBA's GDB stub and reconstructs the 240x160 frame in software,
so it catches things a data-level preview can't.

Three quirks of that stub are worth knowing before you touch the tool:

- `mGBA -g` halts the CPU at reset and never starts it. Plain `continue`
  doesn't work — gdb reports "the program is not being run" — so a throwaway
  session sends a raw `c` packet to get the ROM going, then gets killed.
- Only VRAM, palette RAM, OAM and the low I/O registers are readable. IWRAM is
  not, so the game's globals can't be inspected or poked.
- `BGxHOFS`/`BGxVOFS` are write-only and read back as open-bus garbage. The
  tool treats scroll as zero; don't "fix" that by reading the registers.

Because IWRAM is unreachable, states that need button presses are reached with
build switches instead:

```sh
make DEFINES=-DBOOT_LEVEL=0                 # boot straight into a level
make DEFINES="-DBOOT_LEVEL=0 -DBOOT_DEATH"  # ...and loop the death sequence
```

`tools/preview_level.py N` renders level N to a PNG from the level tables
without running anything. It reimplements the layout, so it validates data and
art but not the ROM — use `make shot` when you need the truth.
## Audio

Six effects plus the 89-second background track, all from the original.

maxmod's streaming API turns out to be Nintendo DS only, and an 89-second
recording can't become a tracker module without transcribing it. The way
through: mmutil reads loop points from a WAV's `smpl` chunk, so the music is a
single long sample tagged with a full-length loop, played as an effect. It
loops seamlessly and needs no retriggering from code. `tools/make_audio.py`
writes that chunk by hand, since nothing off the shelf does.

Effects are 8-bit mono at 11025 Hz; the music is 8-bit mono at 10512 Hz. That
puts 984KB of samples in a 1MB ROM — fine for a cartridge, and the reason the
ROM jumped from 23KB.

Decoding uses macOS's built-in `afconvert`. (The Homebrew `ffmpeg` on this
machine is broken — it can't find `libx265.215.dylib`.)

## Save data

32KB cartridge SRAM at `0x0E000000`, holding the completed-level flags, the
level-select cursor position and the music setting, behind a magic number and
a checksum. Progress is written the moment a level is solved.

The ROM has to carry the string `SRAM_V113` for emulators and flashcarts to
detect the backup hardware. Getting it to survive is fiddlier than it looks:
`gba.specs` links with `--gc-sections`, which drops the section even with
`__attribute__((used))`, and this binutils ignores `retain`. `save.c` forces a
real reference from live code instead. If saving ever silently stops working,
check `strings double_maze.gba | grep SRAM_V113` first.

## Not done yet

- **Ball rolling animation.** Movement is animated in code — the ball slides
  between cells over 12 frames — but there's no sprite-frame roll. The
  original's `move0001-0022` set turns out to be a flipping ring rather than a
  rolling ball, which is probably why it was never wired up.
- **Win feedback.** Death plays the real shrink-and-fade frames; the win is
  still just a chime and a pause.
- **Level 35.** Still missing, still needs re-authoring.
- **Custom levels and the level editor.** Dropped, by decision.
