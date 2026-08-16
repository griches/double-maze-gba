#ifndef DOUBLE_MAZE_SAVE_H
#define DOUBLE_MAZE_SAVE_H

#include <tonc.h>

#include "levels.h"

typedef struct SaveData
{
    u8 completed[LEVEL_COUNT];   // 1 once the level has been solved
    u8 last_level;               // where the cursor sits on the select screen
    u8 music_on;
    u8 high_contrast;            // the palette regraded for an unlit screen
} SaveData;

extern SaveData g_save;

// Reads SRAM into g_save, falling back to defaults if the contents are absent
// or corrupt. Returns true if an existing save was found.
bool save_load(void);

void save_store(void);

// Wipes progress in memory and on the cartridge.
void save_reset(void);

#endif // DOUBLE_MAZE_SAVE_H
