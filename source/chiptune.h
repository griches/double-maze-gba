#ifndef DOUBLE_MAZE_CHIPTUNE_H
#define DOUBLE_MAZE_CHIPTUNE_H

#include <tonc.h>

// Background music, played on the GBA's four PSG channels rather than
// streamed as PCM. maxmod only drives the two Direct Sound channels, so these
// four sit idle otherwise: the music costs no mixer channel, no Direct Sound
// bandwidth, and about 2KB of ROM instead of the 936KB the sampled track took.
//
// Call after audio_init(), since maxmod owns the master sound enable and the
// Direct Sound half of REG_SNDDSCNT.
void chiptune_init(void);

void chiptune_set(bool on);
bool chiptune_enabled(void);

// Overall level of the music, 0-100. Split across the PSG's master volume and
// the per-channel envelopes, so the scale is finer than the eight steps the
// master register alone would give -- see chiptune.c.
void chiptune_set_volume(int vol);

// Once per frame, alongside audio_frame().
void chiptune_frame(void);

// Diagnostics. Nothing here can hear the output, so a debug build reports the
// row the sequencer has reached and whether the hardware says the PSG
// channels are actually sounding -- which is as close to "is there music" as
// a screenshot can get.
int  chiptune_row(void);
bool chiptune_active(void);

#endif // DOUBLE_MAZE_CHIPTUNE_H
