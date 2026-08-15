#ifndef DOUBLE_MAZE_RENDER_H
#define DOUBLE_MAZE_RENDER_H

#include <tonc.h>

#include "levels.h"

#define SCREEN_COLS 30
#define SCREEN_ROWS 20

// The 15x8 grid of 16x16 cells is 240x128, so it fills the screen width and
// leaves 32 pixels of vertical slack. Split that as 16 above and 16 below,
// putting the HUD on the bottom row.
#define GRID_TOP_ROW 2                        // in 8x8 tile rows
#define GRID_TOP_PX  (GRID_TOP_ROW * 8)
#define HUD_ROW      18

// Everything -- game tiles, font and title art -- shares charblock 0, so the
// menus and the game run in one video mode with no VRAM reloads between them.
void render_init(void);

//--- gameplay --------------------------------------------------------------

// Applies a skin's backdrop colour and repaints the whole grid.
void render_level(const LevelData *lv, int skin);

// Repaints one cell, optionally using the lit-goal variant.
void render_cell(const LevelData *lv, int skin, int cx, int cy, bool lit);

void render_hud(int level_display_number);

//--- menus -----------------------------------------------------------------

// Fills the map with a skin's void tile and sets the backdrop, giving a plain
// coloured screen to draw text on.
void render_plain(int skin);

void render_title_art(void);

// Wipes the whole text layer back to transparent.
void render_text_clear(void);

void render_text(int col, int row, const char *s);
void render_text_centred(int row, const char *s);
void render_clear_row(int row);

#endif // DOUBLE_MAZE_RENDER_H
