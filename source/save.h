#ifndef DOUBLE_MAZE_SAVE_H
#define DOUBLE_MAZE_SAVE_H

#include <tonc.h>

#include "levels.h"

// The music comes out of the PSG and the effects out of maxmod's mixer, so
// they arrive at the speaker at whatever relative level the hardware happens
// to give them -- which is music far too loud. These are the levels that
// balance them; the options screen moves them from there.
#define MUSIC_VOLUME_DEFAULT 55
#define SFX_VOLUME_DEFAULT   100

typedef struct SaveData
{
    u8 completed[LEVEL_COUNT];   // 1 once the level has been solved
    u8 last_level;               // where the cursor sits on the select screen
    u8 music_on;
    u8 high_contrast;            // the palette regraded for an unlit screen
    u8 music_volume;             // 0-100
    u8 sfx_volume;               // 0-100
} SaveData;

extern SaveData g_save;

// Reads SRAM into g_save, falling back to defaults if the contents are absent
// or corrupt. Returns true if an existing save was found.
bool save_load(void);

void save_store(void);

// Wipes progress in memory and on the cartridge.
void save_reset(void);

#endif // DOUBLE_MAZE_SAVE_H
