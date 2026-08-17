#!/usr/bin/env python3
"""Build the GBA tilesets from the original iOS Double Maze artwork.

The iOS game composites each cell from up to three layers: a floor tile, a goal
overlay, and a wall image drawn at 1.375x the cell size so it overhangs its
neighbours. The GBA draws a tilemap, so we bake those layers down into one
16x16 metatile per (skin, tile id) and clip the wall overhang to the cell.

Emits, for each of the three skins purple / orange / greentile:
    gfx/tiles_<skin>.png   21 metatiles as a 336x16 strip, 16-colour paletted
    gfx/tiles_<skin>.grit

plus gfx/ball.png, gfx/font.png and source/skins.h.

    python3 tools/make_assets.py [path-to-ios-project]
"""

import colorsys
import os
import sys
from collections import Counter

from PIL import Image

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
GFX = os.path.join(HERE, "gfx")
SRC_OUT = os.path.join(HERE, "source")
DEFAULT_IOS = "/Users/garyriches/Documents/Source/DoubleMaze/DoubleMaze"

CELL = 16                 # GBA cell size in pixels (2x2 hardware tiles)
SCREEN_W, SCREEN_H = 240, 160

# iOS draws each floor tile at 1.2x the cell height but steps down a row by
# exactly one cell, so the bottom 20% of every tile is covered by the tile
# below it. Only the last tile in a run shows that lip, which is what gives
# the board its sense of depth. Squashing the art to a square cell bakes the
# lip into every tile and draws a dark line under every row instead.
#
# iOS adds the tiles as subviews in row order, so a lower tile's own image
# paints over the overhang of the tile above it. The lip is therefore only
# ever visible on a cell that draws nothing itself -- the plain void tiles.
# That's where it lives here too: floor tiles keep a full-size face, and the
# void tiles get variants carrying the lip along their top edge. Same result,
# and the faces all stay the same size.
TILE_TALL = int(round(CELL * 1.2))       # 19
LIP_PX = TILE_TALL - CELL                # 3

# The iOS renderer draws the whole 44x44 wall image at 1.375x the cell, centred,
# so the bar inside it straddles the boundary and overhangs both neighbours.
# A tilemap can't overhang. Scaling the image down to the cell instead loses
# what that 1.375 was really buying -- the bar ends up 68% of the cell wide and
# 3px thick instead of 94% and 4px, reading as a stray stick floating inside
# the tile.
#
# So: crop the bar out of its frame, scale it at the original's proportions,
# and seat it flush against the edge it blocks. Same size and weight as iOS,
# just wholly inside the cell instead of straddling it.
WALL_SCALE = 1.375
WALL_SRC_FRAME = 44
MT_COUNT = 27             # 16 ids + 5 lit goals + 6 carrying a lip

# The high-contrast palettes, for playing on hardware.
#
# The iOS art was drawn for a backlit sRGB phone. An unlit AGB or a frontlit
# AGS-001 panel is reflective: it bottoms out at whatever light bounces off it
# and tops out around paper white, so the whole picture lands inside a narrow
# band of pale grey, and the weak colour filters desaturate it on the way
# through. Taken straight, the original palette puts the backdrop, the floor
# tiles and the wall bars within about forty luminance points of each other --
# which survives that squeeze as one flat tone. tools/washout.py simulates it.
#
# Graded for that, the art looks dark and oversaturated on a monitor -- which
# is the same trade in reverse, and why this is a second palette rather than a
# replacement. Nothing below touches the tiles: the grade is applied to each
# palette entry after quantising, so both modes share one tileset and the
# toggle is sixteen colours per bank.
#
# Each layer is pushed onto its own tier, and everything gets a saturation
# boost to make up for the filters:
#
#   backdrop   darkest     the empty space around the maze
#   floor      middle      the playable cells
#   walls      brightest   the bars, which matter most to read at a glance
#
# Ordering the three by brightness means they stay told apart by luminance
# alone, so it survives the desaturation as well as the contrast squeeze.
# sat scales HSV saturation; gain scales value; lift shifts it afterwards.
#
# The floor gain is per skin because the source art doesn't start out level:
# the green tiles are drawn a good deal lighter than the purple ones. One
# shared gain would leave green sitting up in the walls' tier, which is where
# the bars stop reading. Landing all three on the same middle tier -- a mean
# luminance around 85 -- is what keeps them equally legible.
#
# The tiles keep white_gain at 1, so the goal ring and the highlight along each
# tile's top edge stay white while the coloured face drops away underneath
# them. Those two are the only cues for "this is the square you're aiming at"
# and "this is where one cell ends and the next begins", and both were being
# lost.
SKIN_GRADE = {
    "purple": dict(sat=1.55, gain=0.95, lift=-0.06, white_gain=1.0),
    "orange": dict(sat=1.55, gain=0.80, lift=-0.06, white_gain=1.0),
    "green":  dict(sat=1.55, gain=0.64, lift=-0.06, white_gain=1.0),
}
WALL_GRADE = dict(sat=0.95, gain=0.55, lift=0.45)
BACKDROP_GRADE = dict(sat=1.70, gain=0.26, lift=0.02)
# The ball only needs its colour back -- it already sits above the floor tier
# in brightness. Leaving the value alone keeps the death frames fading out
# through pale RGB the way build_sprites relies on; they're near-neutral, so a
# saturation boost barely touches them.
BALL_GRADE = dict(sat=1.45, gain=1.0, lift=0.0)
# The title screen is one flat field of green with white lettering over it, and
# the menus print white text on top of it. Dropping the field well below the
# text is the whole job here -- so the green takes the gain and the white
# doesn't.
TITLE_GRADE = dict(sat=1.45, gain=0.52, lift=0.0, white_gain=1.0)

# skin name -> (tile art prefix, background image)
SKINS = [
    ("purple",    "purple",    "blackbg.png"),
    ("orange",    "orange",    "orangebg.png"),
    ("green",     "greentile", "greenbg.png"),
]

# Which edges each tile id walls off, and whether it gets floor / goal.
# Straight from renderLevel in Double_MazeViewController.m. Tile 15 walls all
# four; the original has a dedicated wall5.png for it, but composing it from
# the same four bars keeps every edge consistent.
EDGE_SRC = {
    "top":    "wall1.png",
    "right":  "wall2.png",
    "bottom": "wall3.png",
    "left":   "wall4.png",
}
WALL_EDGES_FOR_ID = {
    1: ("top",),    7: ("top",),    11: ("top",),
    2: ("right",),  8: ("right",),  12: ("right",),
    3: ("bottom",), 9: ("bottom",), 13: ("bottom",),
    4: ("left",),   10: ("left",),  14: ("left",),
    15: ("top", "right", "bottom", "left"),
}
FLOOR_IDS = set(range(0, 6))            # 0-5 get a floor tile
GOAL_IDS = [5, 11, 12, 13, 14]          # these get the target overlay
# Tiles that paint nothing of their own, so an overhanging lip from the tile
# above stays visible. The rest cover it with their own floor or target image.
BARE_IDS = [6, 7, 8, 9, 10, 15]


def load(ios, name):
    path = os.path.join(ios, name)
    if not os.path.exists(path):
        raise SystemExit("missing source art: %s" % path)
    return Image.open(path).convert("RGBA")


def fit(img, size):
    return img.resize((size, size), Image.LANCZOS)


def tile_faces(img):
    """A 32x36 tile image -> (face, lip).

    The face is the tile at iOS proportions with its lip cropped off, so it
    fills the cell exactly. The lip is the strip that overhangs the cell below.
    """
    tall = img.resize((CELL, TILE_TALL), Image.LANCZOS)
    return (tall.crop((0, 0, CELL, CELL)),
            tall.crop((0, CELL, CELL, TILE_TALL)))


def make_bars(ios):
    """Crop each wall bar from its frame and scale it to the cell."""
    scale = CELL * WALL_SCALE / WALL_SRC_FRAME
    bars = {}
    for edge, name in EDGE_SRC.items():
        img = load(ios, name)
        box = img.getchannel("A").point(lambda a: 255 if a > 16 else 0).getbbox()
        bar = img.crop(box)
        w = min(CELL, max(1, int(round(bar.width * scale))))
        h = min(CELL, max(1, int(round(bar.height * scale))))

        # Span the full edge. The maths gives the horizontal bars 15 of the 16
        # pixels, which leaves a notch where two walls meet at a corner; iOS
        # doesn't show one because its bar straddles the cell and covers the
        # whole width once rasterised.
        if edge in ("top", "bottom"):
            w = CELL
        else:
            h = CELL

        bar = bar.resize((w, h), Image.LANCZOS)

        # Scaling a 9px bar down to 4px leaves its outer columns partly
        # transparent, and quantise() then drops anything under half alpha --
        # which silently shaved a column off one side of the vertical bars and
        # two rows off their ends. Harden the edges so the bar keeps its full
        # size no matter how the source was anti-aliased.
        bar.putalpha(bar.getchannel("A").point(lambda a: 255 if a > 60 else 0))
        bars[edge] = bar
    return bars


def bar_position(edge, bar):
    """Centre a bar on the edge it blocks, the way iOS does.

    The original draws the bar straddling the boundary, so half of it sits in
    each of the two cells it divides. Seating it wholly inside the cell instead
    reads as two pixels too far in -- the bar looks like it belongs to the tile
    rather than to the line between tiles. Half of it falls outside the cell
    and gets clipped, since a tilemap can't draw into its neighbour.
    """
    if edge == "top":
        return ((CELL - bar.width) // 2, -(bar.height // 2))
    if edge == "bottom":
        return ((CELL - bar.width) // 2, CELL - (bar.height // 2))
    if edge == "left":
        return (-(bar.width // 2), (CELL - bar.height) // 2)
    return (CELL - (bar.width // 2), (CELL - bar.height) // 2)   # right


def paste_bar(cell, bar, x, y):
    """Composite a bar that may hang off the top or left of the cell."""
    if x < 0:
        bar = bar.crop((-x, 0, bar.width, bar.height))
        x = 0
    if y < 0:
        bar = bar.crop((0, -y, bar.width, bar.height))
        y = 0
    if x >= CELL or y >= CELL:
        return
    bar = bar.crop((0, 0, min(bar.width, CELL - x), min(bar.height, CELL - y)))
    cell.alpha_composite(bar, (x, y))


def compose_cell(floor, goal, edges, bars, top_lip=None):
    """Bake one 16x16 RGBA cell from its layers."""
    cell = Image.new("RGBA", (CELL, CELL), (0, 0, 0, 0))
    if top_lip is not None:
        # The overhang belongs to the tile above, so it goes down first and
        # this cell's own walls draw over it.
        cell.alpha_composite(top_lip, (0, 0))
    if floor is not None:
        cell.alpha_composite(floor)
    if goal is not None:
        cell.alpha_composite(goal)
    for edge in edges:
        bar = bars[edge]
        paste_bar(cell, bar, *bar_position(edge, bar))
    return cell


def grade_rgb(rgb, sat, gain, lift, white_gain=None):
    """Push one colour onto its tier: saturate, then scale and shift value.

    Near-neutral colours take white_gain instead of gain. That split matters
    because a saturated colour and a white one can share an HSV value while
    reading nothing like each other -- the title's green field sits at the same
    value as the white it's lettered on, and the goal ring at the same value as
    the tile it's drawn on. Scaling both equally just moves the pair down
    together; scaling only the coloured one opens the gap. white_gain defaults
    to gain, which grades everything uniformly.

    WHITE_S is where "near-neutral" stops. It has to be low: the pale tile
    faces still carry a good half of full saturation, and anything generous
    enough to include them exempts the whole tileset from its own grade.
    """
    WHITE_S = 0.35

    h, s, v = colorsys.rgb_to_hsv(*[c / 255.0 for c in rgb[:3]])
    if white_gain is None:
        white_gain = gain

    whiteness = max(0.0, 1.0 - s / WHITE_S)
    g = gain + (white_gain - gain) * whiteness
    s = min(1.0, s * sat)
    v = min(1.0, max(0.0, v * g + lift))
    return tuple(int(round(c * 255)) for c in colorsys.hsv_to_rgb(h, s, v))


def graded_palette(name, **kw):
    """A generated PNG's 16 palette entries, graded, as BGR15.

    Index 0 is the transparent slot and never reaches the screen -- except for
    the backdrop, which is set separately -- so it passes through untouched.
    """
    pal = Image.open(os.path.join(GFX, name + ".png")).getpalette()[: 16 * 3]
    entries = [tuple(pal[i * 3:i * 3 + 3]) for i in range(16)]
    return [bgr15(entries[0])] + [bgr15(grade_rgb(c, **kw)) for c in entries[1:]]


def quantise(strip, alpha_cutoff=128):
    """RGBA strip -> paletted image with index 0 reserved for transparency.

    4bpp tiles are all-or-nothing per pixel, so the alpha channel has to
    collapse to a mask. The cutoff matters for the death frames: they fade out
    via alpha, and at the default 128 the last third of the sequence masks away
    to nothing. They pass a low cutoff so the shrink stays visible, carrying the
    fade in their (increasingly pale) RGB instead.
    """
    alpha = strip.getchannel("A")
    mask = alpha.point(lambda a: 255 if a >= alpha_cutoff else 0)

    # Quantise only the opaque artwork, into indices 1..15.
    rgb = Image.new("RGB", strip.size, (0, 0, 0))
    rgb.paste(strip.convert("RGB"), (0, 0), mask)
    q = rgb.quantize(colors=15, method=Image.MEDIANCUT, dither=Image.NONE)

    src_pal = q.getpalette()[: 15 * 3]
    out = Image.new("P", strip.size, 0)
    out.putpalette([0, 0, 0] + src_pal + [0, 0, 0] * (256 - 16))

    qpx, mpx, opx = q.load(), mask.load(), out.load()
    for y in range(strip.height):
        for x in range(strip.width):
            opx[x, y] = 0 if mpx[x, y] == 0 else qpx[x, y] + 1
    return out


def build_skin(ios, skin, prefix, out_name):
    floor, lip = tile_faces(load(ios, prefix + ".png"))
    goal_off, _ = tile_faces(load(ios, prefix + "_target_off.png"))
    goal_on, _ = tile_faces(load(ios, prefix + "_target_on.png"))
    bars = make_bars(ios)

    # Walls are drawn on their own layer now -- see build_walls -- so the skin
    # tiles carry only floor, target and lip.
    def cell(tid, goal_art, top_lip=None):
        return compose_cell(
            floor if tid in FLOOR_IDS else None,
            goal_art if tid in GOAL_IDS else None,
            (), bars, top_lip,
        )

    cells = []
    for tid in range(16):                    # 0-15  plain
        cells.append(cell(tid, goal_off))
    for tid in GOAL_IDS:                     # 16-20 lit goals
        cells.append(cell(tid, goal_on))
    for tid in BARE_IDS:                     # 21-26 carrying a lip from above
        cells.append(cell(tid, goal_off, top_lip=lip))

    assert len(cells) == MT_COUNT, "%d cells, expected %d" % (len(cells), MT_COUNT)
    strip = Image.new("RGBA", (CELL * MT_COUNT, CELL), (0, 0, 0, 0))
    for i, c in enumerate(cells):
        strip.alpha_composite(c, (i * CELL, 0))

    path = os.path.join(GFX, out_name + ".png")
    quantise(strip).save(path)
    write_grit(out_name, metatile=True,
               comment="%s skin: %d metatiles of %dx%d" % (skin, MT_COUNT, CELL, CELL))
    print("wrote", path)


def write_grit(name, metatile, comment):
    lines = ["# %s" % comment,
             "# The Makefile appends -fts, so no output format here.",
             "",
             "-gt", "-gB4"]
    if metatile:
        lines += ["-Mw2 -Mh2   # 16x16 metatiles -> 4 hardware tiles each"]
    lines += ["-p", "-pn16", ""]
    with open(os.path.join(GFX, name + ".grit"), "w") as fh:
        fh.write("\n".join(lines))


# balldeath0001-0038 is three distinct beats, not one continuous shrink:
#   1-7    white flash with an expanding ring
#   8-15   the ball shrinks and fades out
#   16-20  nothing at all
#   21-37  a small white exclamation mark blooms and fades
# The iOS build only ever loaded 1-8, so it showed the flash and stopped. This
# picks frames across all three beats -- sampling 16-20 just yields blanks, and
# treating 21+ as more shrink frames gives stray slivers.
DEATH_FRAMES = [1, 2, 3, 5, 7,
                8, 9, 10, 11, 12, 13, 14, 15,
                22, 25, 28, 31, 34, 37]


def build_sprites(ios):
    """One strip: the ball, then the death frames, all sharing a palette."""
    frames = [fit(load(ios, "ball.png"), CELL)]
    for n in DEATH_FRAMES:
        frames.append(fit(load(ios, "balldeath%04d.png" % n), CELL))

    strip = Image.new("RGBA", (CELL * len(frames), CELL), (0, 0, 0, 0))
    for i, f in enumerate(frames):
        strip.alpha_composite(f, (i * CELL, 0))

    quantise(strip, alpha_cutoff=32).save(os.path.join(GFX, "ball.png"))
    write_grit("ball", metatile=True,
               comment="ball + %d death frames, 16x16 sprites"
                       % len(DEATH_FRAMES))
    print("wrote", os.path.join(GFX, "ball.png"),
          "(%d frames)" % len(frames))


def flatten_title_field(im):
    """Replace the title's graded green field with one flat colour.

    The iOS art fades the field about 15% from top to bottom. At 480x320 in
    24-bit colour that reads as a gradient; at 240x160 through a 16-entry
    palette of 15-bit colours it reads as a stack of bands, because there is
    nowhere near the precision to draw it smoothly -- and it spends thirteen
    of the sixteen slots saying so, which is most of the palette gone on the
    part of the screen with nothing in it.

    The art is white ink over that field and nothing else, so each pixel is
    unmixed into a coverage of white over its own row's field colour and then
    laid back down over the flat one. That keeps the letterforms and their
    antialiasing exactly as they were; only the field moves.
    """
    rgb = im.convert("RGB")
    w, h = rgb.size
    px = rgb.load()

    # The field colour of each row is simply its most common green -- the
    # gradient runs down the image, so a row has only one. Rows the lettering
    # nearly covers don't have enough of it to be sure, and borrow from the
    # closest row that does; the gradient is smooth, so that costs a unit or
    # two at most.
    seen = {}
    for y in range(h):
        greens = Counter(px[x, y] for x in range(w)
                         if px[x, y][1] > px[x, y][2] + 25)
        if greens:
            colour, count = greens.most_common(1)[0]
            if count >= 30:
                seen[y] = colour
    if not seen:
        raise SystemExit("title art: no green field found to flatten")

    known = sorted(seen)
    rows = [seen.get(y) or seen[min(known, key=lambda k: abs(k - y))]
            for y in range(h)]

    # The average of the gradient, so the screen keeps the weight it had.
    flat = tuple(round(sum(c[i] for c in rows) / h) for i in range(3))

    out = im.copy()
    op = out.load()
    for y in range(h):
        field = rows[y]
        span = 255 - field[2]        # blue separates ink from field furthest
        for x in range(w):
            p = px[x, y]
            ink = (p[2] - field[2]) / span if span else 0.0
            ink = 0.0 if ink < 0.0 else (1.0 if ink > 1.0 else ink)
            op[x, y] = tuple(
                [round(flat[i] + ink * (255 - flat[i])) for i in range(3)]
                + [op[x, y][3]])
    return out


def build_title(ios):
    """The title screen as a tilemap, not a bitmap.

    At 240x160 with a flattened palette the art reduces to ~133 unique tiles,
    which fits in the same charblock as the game tiles and the font -- so the
    menus and the game can share one video mode with no VRAM reloads.
    """
    im = load(ios, "title.png")
    im = flatten_title_field(im).resize((SCREEN_W, SCREEN_H), Image.LANCZOS)
    quantise(im).save(os.path.join(GFX, "title.png"))

    lines = ["# Title screen: 30x20 tiles plus its map.",
             "# The Makefile appends -fts, so no output format here.",
             "",
             "-gt", "-gB4",
             "-mRtf       # reduce duplicate and flipped tiles",
             "-mLs        # regular screenblock map layout",
             "-p", "-pn16", ""]
    with open(os.path.join(GFX, "title.grit"), "w") as fh:
        fh.write("\n".join(lines))
    print("wrote", os.path.join(GFX, "title.png"))


EDGE_BITS = {"top": 1, "right": 2, "bottom": 4, "left": 8}


def build_walls(ios):
    """One tileset of every wall-edge combination, shared by all three skins.

    Each cell draws only the half of a bar that falls inside it; the cell on
    the other side of the boundary draws the matching half. Together they make
    the full-thickness bar sitting on the line between them, which is what iOS
    gets by letting the oversized wall image overhang its neighbour.

    The wall art is identical in every skin, so this is 16 metatiles in total
    rather than 16 per skin.
    """
    bars = make_bars(ios)
    cells = []
    for mask in range(16):
        cell = Image.new("RGBA", (CELL, CELL), (0, 0, 0, 0))
        for edge, bit in EDGE_BITS.items():
            if mask & bit:
                bar = bars[edge]
                paste_bar(cell, bar, *bar_position(edge, bar))
        cells.append(cell)

    strip = Image.new("RGBA", (CELL * 16, CELL), (0, 0, 0, 0))
    for i, c in enumerate(cells):
        strip.alpha_composite(c, (i * CELL, 0))

    quantise(strip).save(os.path.join(GFX, "walls.png"))
    write_grit("walls", metatile=True,
               comment="wall edges: one 16x16 metatile per edge combination")
    print("wrote", os.path.join(GFX, "walls.png"))


# A 5x7 pixel font, drawn by hand rather than rasterised from a TTF -- at this
# size a real typeface turns to mush, and the menus need to stay readable.
GLYPHS = {
    " ": ["00000", "00000", "00000", "00000", "00000", "00000", "00000"],
    "!": ["00100", "00100", "00100", "00100", "00100", "00000", "00100"],
    "'": ["00100", "00100", "00000", "00000", "00000", "00000", "00000"],
    ",": ["00000", "00000", "00000", "00000", "01100", "01100", "11000"],
    "-": ["00000", "00000", "00000", "11111", "00000", "00000", "00000"],
    ".": ["00000", "00000", "00000", "00000", "00000", "01100", "01100"],
    "/": ["00001", "00010", "00010", "00100", "01000", "01000", "10000"],
    "0": ["01110", "10001", "10011", "10101", "11001", "10001", "01110"],
    "1": ["00100", "01100", "00100", "00100", "00100", "00100", "01110"],
    "2": ["01110", "10001", "00001", "00010", "00100", "01000", "11111"],
    "3": ["11111", "00010", "00100", "00010", "00001", "10001", "01110"],
    "4": ["00010", "00110", "01010", "10010", "11111", "00010", "00010"],
    "5": ["11111", "10000", "11110", "00001", "00001", "10001", "01110"],
    "6": ["00110", "01000", "10000", "11110", "10001", "10001", "01110"],
    "7": ["11111", "00001", "00010", "00100", "01000", "01000", "01000"],
    "8": ["01110", "10001", "10001", "01110", "10001", "10001", "01110"],
    "9": ["01110", "10001", "10001", "01111", "00001", "00010", "01100"],
    ":": ["00000", "01100", "01100", "00000", "01100", "01100", "00000"],
    "?": ["01110", "10001", "00001", "00010", "00100", "00000", "00100"],
    "A": ["01110", "10001", "10001", "11111", "10001", "10001", "10001"],
    "B": ["11110", "10001", "10001", "11110", "10001", "10001", "11110"],
    "C": ["01110", "10001", "10000", "10000", "10000", "10001", "01110"],
    "D": ["11110", "10001", "10001", "10001", "10001", "10001", "11110"],
    "E": ["11111", "10000", "10000", "11110", "10000", "10000", "11111"],
    "F": ["11111", "10000", "10000", "11110", "10000", "10000", "10000"],
    "G": ["01110", "10001", "10000", "10111", "10001", "10001", "01111"],
    "H": ["10001", "10001", "10001", "11111", "10001", "10001", "10001"],
    "I": ["11111", "00100", "00100", "00100", "00100", "00100", "11111"],
    "J": ["00111", "00010", "00010", "00010", "00010", "10010", "01100"],
    "K": ["10001", "10010", "10100", "11000", "10100", "10010", "10001"],
    "L": ["10000", "10000", "10000", "10000", "10000", "10000", "11111"],
    "M": ["10001", "11011", "10101", "10101", "10001", "10001", "10001"],
    "N": ["10001", "11001", "10101", "10011", "10001", "10001", "10001"],
    "O": ["01110", "10001", "10001", "10001", "10001", "10001", "01110"],
    "P": ["11110", "10001", "10001", "11110", "10000", "10000", "10000"],
    "Q": ["01110", "10001", "10001", "10001", "10101", "10010", "01101"],
    "R": ["11110", "10001", "10001", "11110", "10100", "10010", "10001"],
    "S": ["01111", "10000", "10000", "01110", "00001", "00001", "11110"],
    "T": ["11111", "00100", "00100", "00100", "00100", "00100", "00100"],
    "U": ["10001", "10001", "10001", "10001", "10001", "10001", "01110"],
    "V": ["10001", "10001", "10001", "10001", "10001", "01010", "00100"],
    "W": ["10001", "10001", "10001", "10101", "10101", "11011", "10001"],
    "X": ["10001", "10001", "01010", "00100", "01010", "10001", "10001"],
    "Y": ["10001", "10001", "01010", "00100", "00100", "00100", "00100"],
    "Z": ["11111", "00001", "00010", "00100", "01000", "10000", "11111"],
    # cursor / selection marker
    ">": ["10000", "11000", "11100", "11110", "11100", "11000", "10000"],
    # a filled block, handy for rules and progress marks
    "#": ["11111", "11111", "11111", "11111", "11111", "11111", "11111"],
    # tick, for completed levels
    "*": ["00000", "00001", "00011", "10110", "11100", "01000", "00000"],
}
FONT_CHARS = "".join(sorted(GLYPHS))


def build_font():
    """Glyphs with a one-pixel drop shadow.

    The text sits on its own background layer, so index 0 has to stay
    genuinely transparent -- and white-on-anything needs the shadow to stay
    legible over the title art's pale greens.
    """
    img = Image.new("P", (8 * len(FONT_CHARS), 8), 0)
    img.putpalette([0, 0, 0,          # 0 transparent
                    255, 255, 255,    # 1 glyph
                    18, 18, 26]       # 2 shadow
                   + [0, 0, 0] * 253)
    px = img.load()

    for i, ch in enumerate(FONT_CHARS):
        rows = GLYPHS[ch]
        # Shadow first, offset by one pixel, then the glyph over the top.
        for dx, dy, colour in ((2, 1, 2), (1, 0, 1)):
            for y, row in enumerate(rows):
                for x, bit in enumerate(row):
                    if bit == "1":
                        px[i * 8 + x + dx, y + dy] = colour

    img.save(os.path.join(GFX, "font.png"))
    write_grit("font", metatile=False, comment="HUD font, 8x8 glyphs")
    print("wrote", os.path.join(GFX, "font.png"))


def write_fontmap():
    """ASCII -> glyph index, so C can print strings without a switch."""
    table = []
    for code in range(32, 128):
        ch = chr(code)
        table.append(FONT_CHARS.index(ch) if ch in GLYPHS else 0xFF)

    lines = [
        "// Generated by tools/make_assets.py -- do not edit by hand.",
        "",
        "#ifndef DOUBLE_MAZE_FONTMAP_H",
        "#define DOUBLE_MAZE_FONTMAP_H",
        "",
        "#include <tonc.h>",
        "",
        "#define FONT_GLYPH_COUNT %d" % len(FONT_CHARS),
        "#define FONT_FIRST_ASCII 32",
        "",
        "// 0xFF means the character has no glyph; callers should skip it.",
        "static const u8 font_lookup[96] = {",
    ]
    for row in range(0, 96, 16):
        lines.append("    " + ", ".join("0x%02X" % v
                                        for v in table[row:row + 16]) + ",")
    lines += ["};", "", "#endif // DOUBLE_MAZE_FONTMAP_H", ""]

    path = os.path.join(SRC_OUT, "fontmap.h")
    with open(path, "w") as fh:
        fh.write("\n".join(lines))
    print("wrote", path, "(%d glyphs)" % len(FONT_CHARS))


def bgr15(rgb):
    r, g, b = [v >> 3 for v in rgb[:3]]
    return (b << 10) | (g << 5) | r


def backdrop_colours(ios):
    """Each skin's backdrop, in both modes, sampled from its iOS background."""
    normal, high = [], []
    for _skin, _prefix, bg in SKINS:
        im = load(ios, bg)
        centre = im.getpixel((im.width // 2, im.height // 2))
        normal.append(bgr15(centre))
        high.append(bgr15(grade_rgb(centre, **BACKDROP_GRADE)))
    return normal, high


def c_palette(name, values):
    lines = ["static const COLOR %s = {" % name]
    for row in range(0, len(values), 8):
        lines.append("    " + ", ".join("0x%04X" % v
                                        for v in values[row:row + 8]) + ",")
    return lines + ["};", ""]


def write_palettes_header(ios):
    """The high-contrast palettes, one bank per tileset.

    Only colours -- both modes run off the same tiles and the same maps, so
    switching is a handful of memcpy16s into palette RAM.
    """
    _normal, high = backdrop_colours(ios)

    lines = [
        "// Generated by tools/make_assets.py -- do not edit by hand.",
        "",
        "#ifndef DOUBLE_MAZE_PALETTES_H",
        "#define DOUBLE_MAZE_PALETTES_H",
        "",
        "#include <tonc.h>",
        "",
        "#include \"skins.h\"",
        "",
        "// An unlit GBA screen bottoms out at reflected room light and tops",
        "// out near paper white, so the art's own palette -- drawn for a phone",
        "// -- collapses to one flat tone on hardware. These are the same",
        "// colours regraded onto three separated brightness tiers: backdrop",
        "// darkest, floor in the middle, wall bars brightest. See the grade",
        "// constants in tools/make_assets.py for the reasoning.",
        "",
    ]

    skin_rows = []
    for skin, _prefix, _bg in SKINS:
        pal = graded_palette("tiles_" + skin, **SKIN_GRADE[skin])
        skin_rows.append("    { " + ", ".join("0x%04X" % v for v in pal)
                         + " },   // " + skin)
    lines += ["static const COLOR pal_hc_skin[SKIN_COUNT][16] = {"] \
        + skin_rows + ["};", ""]

    lines += c_palette("pal_hc_walls[16]",
                       graded_palette("walls", **WALL_GRADE))
    lines += c_palette("pal_hc_title[16]",
                       graded_palette("title", **TITLE_GRADE))
    lines += c_palette("pal_hc_ball[16]",
                       graded_palette("ball", **BALL_GRADE))
    lines += c_palette("skin_backdrop_hc[SKIN_COUNT]", high)

    lines += ["#endif // DOUBLE_MAZE_PALETTES_H", ""]

    path = os.path.join(SRC_OUT, "palettes.h")
    with open(path, "w") as fh:
        fh.write("\n".join(lines))
    print("wrote", path)


def write_skins_header(ios):
    normal, _high = backdrop_colours(ios)
    backdrops = list(zip([s[0] for s in SKINS], normal))

    lines = [
        "// Generated by tools/make_assets.py -- do not edit by hand.",
        "",
        "#ifndef DOUBLE_MAZE_SKINS_H",
        "#define DOUBLE_MAZE_SKINS_H",
        "",
        "#include <tonc.h>",
        "",
        "#define CELL_PX      %d" % CELL,
        "#define SKIN_COUNT   %d" % len(SKINS),
        "#define MT_COUNT     %d   // %d ids + %d lit goals + %d carrying a lip"
        % (MT_COUNT, 16, len(GOAL_IDS), len(BARE_IDS)),
        "#define MT_TILES     4    // hardware tiles per 16x16 metatile",
        "",
        "// Sprite strip: metatile 0 is the ball, then the death sequence.",
        "#define SPR_BALL        0",
        "#define SPR_DEATH_FIRST 1",
        "#define SPR_DEATH_COUNT %d" % len(DEATH_FRAMES),
        "",
        "// Backdrop colour behind the void tiles, sampled from each skin's iOS",
        "// background image. palettes.h carries the high-contrast variant.",
        "static const COLOR skin_backdrop[SKIN_COUNT] = { %s };"
        % ", ".join("0x%04X" % c for _n, c in backdrops),
        "",
        "// Lit variant for each tile id; a non-goal tile maps to itself.",
        "static const u8 mt_lit[16] = {",
        "    " + ", ".join(
            str(16 + GOAL_IDS.index(t)) if t in GOAL_IDS else str(t)
            for t in range(16)),
        "};",
        "",
        "// Variant carrying the overhanging lip of the tile above, or itself",
        "// for tiles that paint over it. Indexed by metatile, so it composes",
        "// after mt_lit.",
        "static const u8 mt_toplip[MT_COUNT] = {",
        "    " + ", ".join(
            str(21 + BARE_IDS.index(m)) if m in BARE_IDS else str(m)
            for m in range(MT_COUNT)),
        "};",
        "",
        "// Which edges each tile id walls off, as EDGE_* bits. Tile 15 draws",
        "// all four, and now blocks all four to match -- the original's tile",
        "// switch filed it with the holes, which is what made level 27",
        "// impossible. See the note in tools/extract_levels.py.",
        "#define EDGE_TOP    1",
        "#define EDGE_RIGHT  2",
        "#define EDGE_BOTTOM 4",
        "#define EDGE_LEFT   8",
        "",
        "static const u8 tile_wall_edges[16] = {",
        "    " + ", ".join(
            str(sum(EDGE_BITS[e] for e in WALL_EDGES_FOR_ID.get(i, ())))
            for i in range(16)),
        "};",
        "",
        "// Whether a tile paints a floor or target of its own -- and so has a",
        "// lip that overhangs the cell below it.",
        "static const u8 tile_draws_image[16] = {",
        "    " + ", ".join(
            "1" if (t in FLOOR_IDS or t in GOAL_IDS) else "0"
            for t in range(16)),
        "};",
        "",
        "#endif // DOUBLE_MAZE_SKINS_H",
        "",
    ]
    path = os.path.join(SRC_OUT, "skins.h")
    with open(path, "w") as fh:
        fh.write("\n".join(lines))
    print("wrote", path, "backdrops:", [(n, "0x%04X" % c) for n, c in backdrops])


def main():
    ios = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_IOS
    os.makedirs(GFX, exist_ok=True)

    # Clear out the placeholder art from the scaffold.
    for stale in ("tiles.png", "tiles.grit", "sprites.png", "sprites.grit"):
        p = os.path.join(GFX, stale)
        if os.path.exists(p):
            os.remove(p)
            print("removed placeholder", stale)

    for skin, prefix, _bg in SKINS:
        build_skin(ios, skin, prefix, "tiles_" + skin)
    build_sprites(ios)
    build_title(ios)
    build_walls(ios)
    build_font()
    write_fontmap()
    write_skins_header(ios)
    write_palettes_header(ios)


if __name__ == "__main__":
    main()
