#include <string.h>
#include <tonc.h>

#include "save.h"

// Cartridge SRAM. The bus is 8 bits wide here: every access must be a byte,
// which is why this is a u8 pointer and why the copy loops below are hand
// written rather than memcpy (the compiler's memcpy uses wider loads).
#define SRAM ((volatile u8 *)0x0E000000)

// Emulators and flashcarts sniff the ROM for this string to decide what backup
// hardware to emulate. Without it, writes go nowhere.
//
// `used` alone isn't enough: gba.specs links with --gc-sections, which drops
// the section even though the compiler kept it, and this binutils ignores the
// `retain` attribute. keep_save_signature() below forces a real reference,
// which is what actually survives the link.
__attribute__((used, aligned(4)))
static const char save_signature[] = "SRAM_V113";

static void keep_save_signature(void)
{
    __asm__ __volatile__("" :: "r"(save_signature));
}

#define SAVE_MAGIC   0x324D4244u   // 'DBM2'
#define SAVE_VERSION 2   // bumped when level 35 was restored: completed[] grew

typedef struct SaveBlock
{
    u32      magic;
    u8       version;
    u8       pad[3];
    SaveData data;
    u32      checksum;
} SaveBlock;

//---------------------------------------------------------------------------

SaveData g_save;

static u32 checksum_of(const SaveBlock *b)
{
    // Everything up to but not including the checksum field itself.
    const u8 *p = (const u8 *)b;
    u32 sum = 0x1505;
    for (u32 i = 0; i < sizeof(SaveBlock) - sizeof(u32); i++)
        sum = (sum * 33) ^ p[i];
    return sum;
}

static void sram_read(void *dst, u32 len)
{
    u8 *d = (u8 *)dst;
    for (u32 i = 0; i < len; i++)
        d[i] = SRAM[i];
}

static void sram_write(const void *src, u32 len)
{
    const u8 *s = (const u8 *)src;
    for (u32 i = 0; i < len; i++)
        SRAM[i] = s[i];
}

//---------------------------------------------------------------------------

static void apply_defaults(void)
{
    memset(&g_save, 0, sizeof(g_save));
    g_save.music_on = 1;
    g_save.last_level = 0;
}

bool save_load(void)
{
    SaveBlock block;

    keep_save_signature();
    sram_read(&block, sizeof(block));

    if (block.magic != SAVE_MAGIC ||
        block.version != SAVE_VERSION ||
        block.checksum != checksum_of(&block))
    {
        apply_defaults();
        return false;
    }

    g_save = block.data;

    // A corrupt-but-checksumming save shouldn't be able to index off the end
    // of the level table.
    if (g_save.last_level >= LEVEL_COUNT)
        g_save.last_level = 0;

    return true;
}

void save_store(void)
{
    SaveBlock block;
    memset(&block, 0, sizeof(block));
    block.magic = SAVE_MAGIC;
    block.version = SAVE_VERSION;
    block.data = g_save;
    block.checksum = checksum_of(&block);

    sram_write(&block, sizeof(block));
}

void save_reset(void)
{
    apply_defaults();
    save_store();
}
