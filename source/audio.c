#include <maxmod.h>
#include <tonc.h>

#include "audio.h"
#include "chiptune.h"
#include "soundbank.h"
#include "soundbank_bin.h"

// Four mixing channels is plenty: at most a couple of effects overlap, and
// the music no longer takes one -- it plays on the PSG channels, which maxmod
// doesn't touch. See chiptune.c.
#define MIX_CHANNELS 4

#define RATE_NORMAL  (1 << 10)   // maxmod playback rate is 6.10 fixed point
#define VOL_FULL     255
#define PAN_CENTRE   128

// Game event -> soundbank sample. The duplication mirrors the original, which
// used the same stone-on-metal hit for both of its movement slots.
static const mm_word sample_for[SND_COUNT] = {
    [SND_MOVE]     = SFX_ROLL,
    [SND_FALL]     = SFX_DEATH,
    [SND_GOAL]     = SFX_CHIME,
    [SND_COMPLETE] = SFX_FANFARE,
    [SND_PAGE]     = SFX_PAGE,
    [SND_UI]       = SFX_CLICK,
};

//---------------------------------------------------------------------------

void audio_init(void)
{
    irq_add(II_VBLANK, mmVBlank);
    mmInitDefault((mm_addr)soundbank_bin, MIX_CHANNELS);

    // Set explicitly rather than trusting maxmod's default, so a silent build
    // can never be blamed on the global effects level. Range is 0..1024.
    mmSetEffectsVolume(1024);

    // After maxmod: it owns the master sound enable and the Direct Sound half
    // of the mixing register, and chiptune_init has to layer on top of both.
    chiptune_init();
    audio_music_set(true);
}

void audio_frame(void)
{
    mmFrame();
    chiptune_frame();
}

void audio_play(Sound s)
{
    if (s >= SND_COUNT)
        return;

    mm_sound_effect fx = {
        { sample_for[s] }, RATE_NORMAL, 0, VOL_FULL, PAN_CENTRE,
    };
    mmEffectEx(&fx);
}

//---------------------------------------------------------------------------

// The music used to be an 89-second PCM sample looped as an effect: 936KB, or
// 90% of the ROM, and muddy with it, since Direct Sound is 8-bit and no sample
// rate mends that. It's a score now, played on the console's own PSG channels
// -- see chiptune.c and tools/make_chiptune.py.
void audio_music_set(bool on)
{
    chiptune_set(on);
}

bool audio_music_enabled(void)
{
    return chiptune_enabled();
}

int audio_music_row(void)
{
    return chiptune_row();
}

bool audio_music_playing(void)
{
    return chiptune_active();
}
