#ifndef DOUBLE_MAZE_AUDIO_H
#define DOUBLE_MAZE_AUDIO_H

#include <tonc.h>

// Named for what they mean in the game rather than what the sample is, since
// the identifiers mmutil generates (SFX_ROLL and friends) are already taken.
typedef enum Sound
{
    SND_MOVE,       // a ball steps
    SND_FALL,       // a ball dies
    SND_GOAL,       // a ball reaches a goal while the other hasn't
    SND_COMPLETE,   // both balls home, level solved
    SND_PAGE,       // screen transition
    SND_UI,         // menu movement / selection
    SND_COUNT
} Sound;

// Call after irq_init -- this installs maxmod's own VBlank handler.
void audio_init(void);

// Once per frame, after VBlankIntrWait.
void audio_frame(void);

void audio_play(Sound s);

void audio_music_set(bool on);
bool audio_music_enabled(void);

// Diagnostics: the capture pipeline has no way to hear the output, so these
// let a debug build report how far the sequencer has got and whether the PSG
// channels say they're sounding.
int  audio_music_row(void);
bool audio_music_playing(void);

#endif // DOUBLE_MAZE_AUDIO_H
