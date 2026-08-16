#include <tonc.h>

#include "render.h"
#include "fontmap.h"
#include "skins.h"
#include "palettes.h"

#include "tiles_purple.h"
#include "tiles_orange.h"
#include "tiles_green.h"
#include "ball.h"
#include "font.h"
#include "title.h"
#include "walls.h"

#define CBB_BG    0
#define SBB_ART   30   // BG0: tilemap art (grid, title)
#define SBB_TEXT  29   // BG1: text overlay, transparent everywhere else
#define SBB_WALLS 28   // BG2: wall bars straddling the cell boundaries

#define MAP_PITCH  32                          // a 32x32 screenblock's row stride
#define SKIN_TILES (MT_COUNT * MT_TILES)       // 108 hardware tiles per skin

// A screen entry's tile field is 10 bits, so a background reaches 1024 tiles
// from its charblock base -- two charblocks' worth, and well clear of the
// screenblocks at 29/30 and of OBJ VRAM. Three skins plus the font and title
// art currently come to 506. Index linearly rather than through tile_mem[],
// whose CHARBLOCK type stops at 512, so adding metatiles can't quietly run
// off the end of it.
#define BG_TILE(n) (((TILE *)MEM_VRAM) + (n))

// Charblock 0 layout.
#define SKIN_BASE  0
#define FONT_BASE  (SKIN_COUNT * SKIN_TILES)   // 252
#define TITLE_BASE (FONT_BASE + FONT_GLYPH_COUNT)
#define WALL_BASE  (TITLE_BASE + 134)          // after the title art

// BG palette banks.
#define FONT_BANK  3
#define TITLE_BANK 4
#define WALL_BANK  5

static const unsigned int *const skin_tiles[SKIN_COUNT] = {
    tiles_purpleTiles, tiles_orangeTiles, tiles_greenTiles,
};
static const unsigned short *const skin_pal[SKIN_COUNT] = {
    tiles_purplePal, tiles_orangePal, tiles_greenPal,
};
static const u32 skin_tiles_len[SKIN_COUNT] = {
    tiles_purpleTilesLen, tiles_orangeTilesLen, tiles_greenTilesLen,
};

//--- palettes --------------------------------------------------------------
//
// Two colour schemes over one set of tiles. The artwork's own palette is drawn
// for a phone screen and goes flat on an unlit GBA; the high-contrast one in
// palettes.h regrades it onto separated brightness tiers, which looks heavy on
// a monitor and readable on hardware. Nothing but palette RAM differs, so the
// switch is seven memcpy16s and can happen mid-level.

static bool g_high_contrast;

// Which backdrop the current screen wants. The backdrop lives in a single
// palette entry that every screen overwrites, so a toggle has to know what to
// put back. TITLE_BACKDROP means "whatever the title art's own bank says".
#define TITLE_BACKDROP (-1)
static int g_backdrop_src = TITLE_BACKDROP;

static void apply_backdrop(void)
{
    if (g_backdrop_src == TITLE_BACKDROP)
        pal_bg_mem[0] = g_high_contrast ? pal_hc_title[0] : titlePal[0];
    else
        pal_bg_mem[0] = g_high_contrast ? skin_backdrop_hc[g_backdrop_src]
                                        : skin_backdrop[g_backdrop_src];
}

static void upload_palettes(void)
{
    for (int s = 0; s < SKIN_COUNT; s++)
        memcpy16(&pal_bg_mem[s * 16],
                 g_high_contrast ? pal_hc_skin[s] : skin_pal[s], 16);

    // The font is white on a near-black shadow either way, so it has nothing
    // to gain from a regrade.
    memcpy16(&pal_bg_mem[FONT_BANK * 16], fontPal, 16);
    memcpy16(&pal_bg_mem[TITLE_BANK * 16],
             g_high_contrast ? pal_hc_title : titlePal, 16);
    memcpy16(&pal_bg_mem[WALL_BANK * 16],
             g_high_contrast ? pal_hc_walls : wallsPal, 16);
    memcpy16(pal_obj_mem, g_high_contrast ? pal_hc_ball : ballPal, 16);

    apply_backdrop();
}

void render_set_contrast(bool high)
{
    g_high_contrast = high;
    upload_palettes();
}

//---------------------------------------------------------------------------

static inline SCR_ENTRY *art_map(void)
{
    return se_mem[SBB_ART];
}

static inline SCR_ENTRY *text_map(void)
{
    return se_mem[SBB_TEXT];
}

static inline SCR_ENTRY *wall_map(void)
{
    return se_mem[SBB_WALLS];
}

// The space glyph is blank, which makes it the transparent filler for the
// text layer.
static inline u16 text_blank(void)
{
    return (FONT_BASE + font_lookup[' ' - FONT_FIRST_ASCII])
           | SE_PALBANK(FONT_BANK);
}

//---------------------------------------------------------------------------

void render_init(void)
{
    for (int s = 0; s < SKIN_COUNT; s++)
        memcpy32(BG_TILE(SKIN_BASE + s * SKIN_TILES),
                 skin_tiles[s], skin_tiles_len[s] / 4);

    memcpy32(BG_TILE(FONT_BASE), fontTiles, fontTilesLen / 4);
    memcpy32(BG_TILE(TITLE_BASE), titleTiles, titleTilesLen / 4);
    memcpy32(BG_TILE(WALL_BASE), wallsTiles, wallsTilesLen / 4);

    // Both schemes share these tiles; only the palettes differ.
    upload_palettes();

    // Text gets its own layer. A tilemap cell shows exactly one tile, so
    // drawing glyphs into the art layer would punch them through it -- and
    // their transparent pixels fall to the backdrop colour, which is what put
    // black boxes behind every word. On BG1 the gaps show BG0 instead.
    // BG_MOSAIC only opts each layer in; REG_MOSAIC stays 0 until a
    // transition wants it, so this is inert the rest of the time.
    REG_BG0CNT = BG_CBB(CBB_BG) | BG_SBB(SBB_ART) | BG_4BPP | BG_REG_32x32
               | BG_MOSAIC | BG_PRIO(3);
    REG_BG1CNT = BG_CBB(CBB_BG) | BG_SBB(SBB_TEXT) | BG_4BPP | BG_REG_32x32
               | BG_MOSAIC | BG_PRIO(1);
    REG_BG2CNT = BG_CBB(CBB_BG) | BG_SBB(SBB_WALLS) | BG_4BPP | BG_REG_32x32
               | BG_MOSAIC | BG_PRIO(2);

    // Nothing here scrolls, but the scroll registers are write-only and their
    // power-on contents aren't guaranteed on real hardware -- so pin them.
    REG_BG0HOFS = 0;
    REG_BG0VOFS = 0;
    REG_BG1HOFS = 0;
    REG_BG1VOFS = 0;
    REG_BG2HOFS = 0;
    REG_BG2VOFS = 0;

    render_text_clear();
    render_walls_clear();
    render_mosaic(0);

    REG_DISPCNT = DCNT_MODE0 | DCNT_BG0 | DCNT_BG1 | DCNT_BG2
                | DCNT_OBJ | DCNT_OBJ_1D;
}

//--- gameplay --------------------------------------------------------------

static inline u16 void_entry(int skin)
{
    // Tile id 6 is the hole/void, which draws as pure backdrop.
    return (SKIN_BASE + skin * SKIN_TILES + 6 * MT_TILES) | SE_PALBANK(skin);
}

void render_walls_clear(void)
{
    SCR_ENTRY *m = wall_map();
    u16 blank = WALL_BASE | SE_PALBANK(WALL_BANK);   // mask 0: no edges

    for (int i = 0; i < MAP_PITCH * MAP_PITCH; i++)
        m[i] = blank;
}

static inline u8 edges_of(const LevelData *lv, int cx, int cy)
{
    return tile_wall_edges[lv->tiles[cy * GRID_W + cx]];
}

// A boundary is declared by whichever side of it owns the wall, but the bar
// straddles both cells. So a cell shows its own edges plus the facing edges of
// its four neighbours; each contributes the half that falls inside it, and the
// two halves meet on the line between them.
static u8 wall_mask(const LevelData *lv, int cx, int cy)
{
    u8 mask = edges_of(lv, cx, cy);

    if (cy > 0 && (edges_of(lv, cx, cy - 1) & EDGE_BOTTOM))
        mask |= EDGE_TOP;
    if (cy < GRID_H - 1 && (edges_of(lv, cx, cy + 1) & EDGE_TOP))
        mask |= EDGE_BOTTOM;
    if (cx > 0 && (edges_of(lv, cx - 1, cy) & EDGE_RIGHT))
        mask |= EDGE_LEFT;
    if (cx < GRID_W - 1 && (edges_of(lv, cx + 1, cy) & EDGE_LEFT))
        mask |= EDGE_RIGHT;

    return mask;
}

static void render_cell_walls(const LevelData *lv, int cx, int cy)
{
    u16 base = WALL_BASE + wall_mask(lv, cx, cy) * MT_TILES;
    u16 bank = SE_PALBANK(WALL_BANK);

    SCR_ENTRY *m = wall_map();
    int col = cx * 2;
    int row = GRID_TOP_ROW + cy * 2;

    m[row * MAP_PITCH + col]           = (base + 0) | bank;
    m[row * MAP_PITCH + col + 1]       = (base + 1) | bank;
    m[(row + 1) * MAP_PITCH + col]     = (base + 2) | bank;
    m[(row + 1) * MAP_PITCH + col + 1] = (base + 3) | bank;
}

void render_cell(const LevelData *lv, int skin, int cx, int cy, bool lit)
{
    int mt = lv->tiles[cy * GRID_W + cx];
    if (lit)
        mt = mt_lit[mt];

    // iOS draws floor and target images 20% taller than the row step, so each
    // overhangs the cell below. A tilemap can't overlap, so that overhang is
    // baked into variants of the cells that would receive it -- and only the
    // ones painting nothing of their own, since anything else covers it.
    if (cy > 0 && tile_draws_image[lv->tiles[(cy - 1) * GRID_W + cx]])
        mt = mt_toplip[mt];

    // Each metatile is 4 consecutive hardware tiles: TL, TR, BL, BR.
    u16 base = SKIN_BASE + skin * SKIN_TILES + mt * MT_TILES;
    u16 bank = SE_PALBANK(skin);

    SCR_ENTRY *m = art_map();
    int col = cx * 2;
    int row = GRID_TOP_ROW + cy * 2;

    m[row * MAP_PITCH + col]           = (base + 0) | bank;
    m[row * MAP_PITCH + col + 1]       = (base + 1) | bank;
    m[(row + 1) * MAP_PITCH + col]     = (base + 2) | bank;
    m[(row + 1) * MAP_PITCH + col + 1] = (base + 3) | bank;
}

void render_level(const LevelData *lv, int skin)
{
    render_plain(skin);

    for (int cy = 0; cy < GRID_H; cy++)
    {
        for (int cx = 0; cx < GRID_W; cx++)
        {
            render_cell(lv, skin, cx, cy, false);
            render_cell_walls(lv, cx, cy);
        }
    }
}

// Replaces the HUD line for a moment -- used for "LEVEL COMPLETE".
void render_banner(const char *s)
{
    render_clear_row(HUD_ROW);
    render_text_centred(HUD_ROW, s);
}

void render_hud(int level_display_number)
{
    char buf[10] = "LEVEL 00";
    buf[6] = '0' + (level_display_number / 10) % 10;
    buf[7] = '0' + level_display_number % 10;

    render_clear_row(HUD_ROW);
    render_text_centred(HUD_ROW, buf);
}

//--- menus -----------------------------------------------------------------

void render_plain(int skin)
{
    u16 blank = void_entry(skin);
    SCR_ENTRY *m = art_map();

    for (int i = 0; i < MAP_PITCH * MAP_PITCH; i++)
        m[i] = blank;

    render_text_clear();
    render_walls_clear();

    g_backdrop_src = skin;
    apply_backdrop();
}

// grit's -mLs lays the map out in 32x32 screenblock chunks, padding the
// 240x160 source up to 256x256 to do it. So the source stride is 32, not the
// 30 columns actually on screen -- reading it as 30 skews every row by two
// tiles and turns the art into a staircase.
#define TITLE_MAP_PITCH 32

void render_title_art(void)
{
    // Tile indices are relative to the art's own base within the charblock.
    const u16 *src = (const u16 *)titleMap;
    SCR_ENTRY *m = art_map();

    for (int row = 0; row < SCREEN_ROWS; row++)
        for (int col = 0; col < SCREEN_COLS; col++)
            m[row * MAP_PITCH + col] =
                (src[row * TITLE_MAP_PITCH + col] + TITLE_BASE)
                | SE_PALBANK(TITLE_BANK);

    render_text_clear();
    render_walls_clear();

    // Columns 30-31 are off-screen; leave them as whatever the caller set.
    g_backdrop_src = TITLE_BACKDROP;
    apply_backdrop();
}

// Hardware brightness fade over every layer, sprites and the backdrop
// included. 0 is the normal picture, 16 is fully black.
void render_fade(int level)
{
    if (level <= 0)
    {
        REG_BLDCNT = BLD_OFF;
        REG_BLDY = 0;
        return;
    }

    REG_BLDCNT = BLD_ALL | BLD_BACKDROP | BLD_BLACK;
    REG_BLDY = (level > 16) ? 16 : level;
}

// Mosaic over the backgrounds and sprites. 0 is the normal picture, 16 the
// coarsest the hardware offers (16x16 blocks). Only layers with BG_MOSAIC set
// are affected, which render_init does once -- REG_MOSAIC is 0 until a
// transition asks for something, so it costs nothing the rest of the time.
void render_mosaic(int level)
{
    int n = level * 15 / 16;
    if (n < 0)
        n = 0;
    if (n > 15)
        n = 15;

    REG_MOSAIC = MOS_BUILD(n, n, n, n);
}

void render_text_clear(void)
{
    SCR_ENTRY *m = text_map();
    u16 blank = text_blank();

    for (int i = 0; i < MAP_PITCH * MAP_PITCH; i++)
        m[i] = blank;
}

void render_clear_row(int row)
{
    SCR_ENTRY *m = text_map();
    u16 blank = text_blank();

    for (int col = 0; col < SCREEN_COLS; col++)
        m[row * MAP_PITCH + col] = blank;
}

void render_text(int col, int row, const char *s)
{
    SCR_ENTRY *m = text_map();

    for (; *s && col < SCREEN_COLS; s++, col++)
    {
        u8 c = (u8)*s;
        if (c < FONT_FIRST_ASCII || c >= FONT_FIRST_ASCII + 96)
            continue;

        u8 glyph = font_lookup[c - FONT_FIRST_ASCII];
        if (glyph == 0xFF)
            continue;

        m[row * MAP_PITCH + col] = (FONT_BASE + glyph) | SE_PALBANK(FONT_BANK);
    }
}

void render_text_centred(int row, const char *s)
{
    int len = 0;
    while (s[len])
        len++;

    int col = (SCREEN_COLS - len) / 2;
    if (col < 0)
        col = 0;

    render_text(col, row, s);
}
