#include <tonc.h>

#include "render.h"
#include "fontmap.h"
#include "skins.h"

#include "tiles_purple.h"
#include "tiles_orange.h"
#include "tiles_green.h"
#include "font.h"
#include "title.h"

#define CBB_BG   0
#define SBB_ART  30   // BG0: tilemap art (grid, title)
#define SBB_TEXT 29   // BG1: text overlay, transparent everywhere else

#define MAP_PITCH  32                          // a 32x32 screenblock's row stride
#define SKIN_TILES (MT_COUNT * MT_TILES)       // 112 hardware tiles per skin

// A screen entry's tile field is 10 bits, so a background can reach 1024 tiles
// from its charblock base -- two charblocks' worth. Three skins plus the font
// and title art come to 518, which overruns charblock 0 but stays well clear
// of the screenblocks at 29/30 and of OBJ VRAM. Index it linearly rather than
// through tile_mem[], whose CHARBLOCK type stops at 512.
#define BG_TILE(n) (((TILE *)MEM_VRAM) + (n))

// Charblock 0 layout.
#define SKIN_BASE  0
#define FONT_BASE  (SKIN_COUNT * SKIN_TILES)   // 252
#define TITLE_BASE (FONT_BASE + FONT_GLYPH_COUNT)

// BG palette banks.
#define FONT_BANK  3
#define TITLE_BANK 4

static const unsigned int *const skin_tiles[SKIN_COUNT] = {
    tiles_purpleTiles, tiles_orangeTiles, tiles_greenTiles,
};
static const unsigned short *const skin_pal[SKIN_COUNT] = {
    tiles_purplePal, tiles_orangePal, tiles_greenPal,
};
static const u32 skin_tiles_len[SKIN_COUNT] = {
    tiles_purpleTilesLen, tiles_orangeTilesLen, tiles_greenTilesLen,
};

static inline SCR_ENTRY *art_map(void)
{
    return se_mem[SBB_ART];
}

static inline SCR_ENTRY *text_map(void)
{
    return se_mem[SBB_TEXT];
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
    {
        memcpy32(BG_TILE(SKIN_BASE + s * SKIN_TILES),
                 skin_tiles[s], skin_tiles_len[s] / 4);
        memcpy16(&pal_bg_mem[s * 16], skin_pal[s], 16);
    }

    memcpy32(BG_TILE(FONT_BASE), fontTiles, fontTilesLen / 4);
    memcpy16(&pal_bg_mem[FONT_BANK * 16], fontPal, 16);

    memcpy32(BG_TILE(TITLE_BASE), titleTiles, titleTilesLen / 4);
    memcpy16(&pal_bg_mem[TITLE_BANK * 16], titlePal, 16);

    // Text gets its own layer. A tilemap cell shows exactly one tile, so
    // drawing glyphs into the art layer would punch them through it -- and
    // their transparent pixels fall to the backdrop colour, which is what put
    // black boxes behind every word. On BG1 the gaps show BG0 instead.
    REG_BG0CNT = BG_CBB(CBB_BG) | BG_SBB(SBB_ART) | BG_4BPP | BG_REG_32x32
               | BG_PRIO(1);
    REG_BG1CNT = BG_CBB(CBB_BG) | BG_SBB(SBB_TEXT) | BG_4BPP | BG_REG_32x32
               | BG_PRIO(0);

    // Nothing here scrolls, but the scroll registers are write-only and their
    // power-on contents aren't guaranteed on real hardware -- so pin them.
    REG_BG0HOFS = 0;
    REG_BG0VOFS = 0;
    REG_BG1HOFS = 0;
    REG_BG1VOFS = 0;

    render_text_clear();

    REG_DISPCNT = DCNT_MODE0 | DCNT_BG0 | DCNT_BG1 | DCNT_OBJ | DCNT_OBJ_1D;
}

//--- gameplay --------------------------------------------------------------

static inline u16 void_entry(int skin)
{
    // Tile id 6 is the hole/void, which draws as pure backdrop.
    return (SKIN_BASE + skin * SKIN_TILES + 6 * MT_TILES) | SE_PALBANK(skin);
}

void render_cell(const LevelData *lv, int skin, int cx, int cy, bool lit)
{
    int mt = lv->tiles[cy * GRID_W + cx];
    if (lit)
        mt = mt_lit[mt];

    // iOS draws floor tiles 20% taller than the row step, so each one's bottom
    // lip is hidden by the tile below and only the last in a run shows it.
    // A tilemap can't overlap, so the lip is a separate variant chosen here.
    bool covered = (cy + 1 < GRID_H) &&
                   (lv->tiles[(cy + 1) * GRID_W + cx] <= FLOOR_ID_MAX);
    if (!covered)
        mt = mt_lip[mt];

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
        for (int cx = 0; cx < GRID_W; cx++)
            render_cell(lv, skin, cx, cy, false);
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
    pal_bg_mem[0] = skin_backdrop[skin];
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

    // Columns 30-31 are off-screen; leave them as whatever the caller set.
    pal_bg_mem[0] = titlePal[0];
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
