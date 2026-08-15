#include <maxmod.h>
#include <tonc.h>

#include "audio.h"
#include "soundbank.h"
#include "soundbank_bin.h"

// Eight mixing channels is generous here: at most a couple of effects overlap,
// and one is permanently occupied by the looping music.
#define MIX_CHANNELS 8

#define RATE_NORMAL  (1 << 10)   // maxmod playback rate is 6.10 fixed point
#define VOL_FULL     255
#define VOL_MUSIC    170         // sit the music under the effects
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

static mm_sfxhand g_music;
static bool       g_music_on;

//---------------------------------------------------------------------------

void audio_init(void)
{
    irq_add(II_VBLANK, mmVBlank);
    mmInitDefault((mm_addr)soundbank_bin, MIX_CHANNELS);

    // Set explicitly rather than trusting maxmod's default, so a silent build
    // can never be blamed on the global effects level. Range is 0..1024.
    mmSetEffectsVolume(1024);

    g_music_on = false;
    g_music = 0;
    audio_music_set(true);
}

void audio_frame(void)
{
    mmFrame();
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

// The music is an 89-second sample with a full-length loop point baked into
// its WAV, so playing it as an effect loops it forever. maxmod's streaming API
// is DS-only and the track can't become a tracker module without transcribing
// it, so this is the way in. See tools/make_audio.py.
void audio_music_set(bool on)
{
    if (on == g_music_on)
        return;

    g_music_on = on;

    if (on)
    {
        mm_sound_effect fx = {
            { SFX_MUSIC }, RATE_NORMAL, 0, VOL_MUSIC, PAN_CENTRE,
        };
        g_music = mmEffectEx(&fx);
    }
    else if (g_music)
    {
        mmEffectCancel(g_music);
        g_music = 0;
    }
}

bool audio_music_enabled(void)
{
    return g_music_on;
}

int audio_music_handle(void)
{
    return (int)g_music;
}

bool audio_music_playing(void)
{
    return g_music != 0 && mmEffectActive(g_music);
}
