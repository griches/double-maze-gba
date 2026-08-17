#include <tonc.h>

#include "chiptune.h"
#include "music.h"

// One row of the score every MUSIC_ROW_FRAMES frames. The player is a
// sequencer and nothing more: the hardware holds each note and runs its own
// volume envelope, so a row costs four register writes at most and nothing at
// all on the rows in between.

// The loudest the player can ask for -- the reference level everything below
// is a fraction of.
#define VOL_MAX 100

// Wave RAM is double-banked: you write the bank that isn't playing, then
// point the channel at it. Only one waveform is ever used here, so this
// happens once at init and bank 0 plays forever after.
#define SND3_BANK_MODE_1  0x0000   // one 32-sample bank
#define SND3_BANK_1       0x0040   // select the second bank...
#define SND3_BANK_0       0x0000   // ...and the first
#define SND3_OUTPUT       0x0080   // channel 3 output enable

#define SND3_VOL_0        0x0000
#define SND3_VOL_100      0x2000

// Noise: divisor 2, 7-bit LFSR. Short and metallic, which is what makes it a
// tick rather than a hiss.
#define SND4_DIVISOR      2
#define SND4_WIDTH_7BIT   0x0008
#define SND4_SHIFT(n)     ((n) << 4)

static bool g_on;
static int  g_frame;      // frames until the next row
static int  g_row;

static int  g_vol = VOL_MAX;   // what the player asked for, 0-100

//---------------------------------------------------------------------------
// volume
//
// Two registers scale the tone generators, and only these two: the master
// volume in REG_SNDDMGCNT, which is (n+1)/8 for n of 0-7, and the two bits of
// REG_SNDDSCNT that set the generators against Direct Sound at 25, 50 or 100
// percent. Their product is the whole ladder the hardware can produce.
//
// Scaling the note envelopes instead would give more steps, but they are four
// bits each and the four channels are mixed at different levels, so rounding
// them separately quietens the parts by different amounts -- the arrangement
// thins out as it gets quieter, and at the points where the master volume
// changes step the rounding can even make a higher setting play quieter than
// the one below it. The ladder below can't: it is a plain product of two
// exact factors, so it is monotonic by construction and every setting plays
// the same mix, just further away.
//
// Gains are in units of 1/32 -- the ratio's 25% times the master's 1/8 -- so
// the reference, 100% at master 6, is 28. The one louder rung the hardware can
// reach, 100% at master 7, is deliberately left off the top: that headroom
// under the sound effects is what full volume means here.

typedef struct GainStep
{
    u8 gain;      // 1/32 of full PSG output
    u8 ratio;     // SDS_DMG25 / 50 / 100, the low two bits of REG_SNDDSCNT
    u8 master;    // REG_SNDDMGCNT master volume, 0-7
} GainStep;

static const GainStep gain_ladder[] = {
    {  1, SDS_DMG25,  0 }, {  2, SDS_DMG25,  1 }, {  3, SDS_DMG25,  2 },
    {  4, SDS_DMG25,  3 }, {  5, SDS_DMG25,  4 }, {  6, SDS_DMG25,  5 },
    {  7, SDS_DMG25,  6 }, {  8, SDS_DMG25,  7 },
    { 10, SDS_DMG50,  4 }, { 12, SDS_DMG50,  5 }, { 14, SDS_DMG50,  6 },
    { 16, SDS_DMG50,  7 },
    { 20, SDS_DMG100, 4 }, { 24, SDS_DMG100, 5 }, { 28, SDS_DMG100, 6 },
};

#define GAIN_STEPS ((int)(sizeof(gain_ladder) / sizeof(gain_ladder[0])))
#define GAIN_REF   28   // the last entry: what the music played at before

static void apply_gain(void)
{
    // Volume zero unroutes the channels rather than turning them down. There
    // is no master volume that means silence -- 0 is the quietest step, not
    // an off switch -- and the sequencer keeps running either way.
    if (g_vol <= 0)
    {
        REG_SNDDSCNT = (REG_SNDDSCNT & ~3) | SDS_DMG25;
        REG_SNDDMGCNT = SDMG_BUILD_LR(0, 0);
        return;
    }

    // Nearest rung, not the one below: the ladder is coarse at the top, and
    // always rounding down would cost most of a step across that half.
    const GainStep *best = &gain_ladder[0];
    int want = GAIN_REF * g_vol;                  // scaled by VOL_MAX
    int best_err = best->gain * VOL_MAX - want;
    if (best_err < 0)
        best_err = -best_err;

    for (int i = 1; i < GAIN_STEPS; i++)
    {
        int err = gain_ladder[i].gain * VOL_MAX - want;
        if (err < 0)
            err = -err;
        if (err < best_err)
        {
            best = &gain_ladder[i];
            best_err = err;
        }
    }

    // Read-modify-write: the upper bits of this register are maxmod's Direct
    // Sound settings, and clobbering them would kill the effects.
    REG_SNDDSCNT = (REG_SNDDSCNT & ~3) | best->ratio;
    REG_SNDDMGCNT = SDMG_BUILD_LR(SDMG_SQR1 | SDMG_SQR2 | SDMG_WAVE
                                  | SDMG_NOISE, best->master);
}

//---------------------------------------------------------------------------

static inline u16 square_rate(u8 note)
{
    return music_rate_square[note - MUSIC_NOTE_FIRST];
}

static inline u16 wave_rate(u8 note)
{
    return music_rate_wave[note - MUSIC_NOTE_FIRST];
}

static void load_wave_table(void)
{
    // Write into bank 1 while bank 0 is selected for playback, then leave
    // playback pointed at the bank just written.
    // tonc's REG_WAVE_RAM is an unparenthesised cast, so it can't be indexed
    // directly -- REG_WAVE_RAM[i] subscripts the address, not the register.
    vu32 *wave_ram = REG_WAVE_RAM;

    // Both banks get the same table. Only one is ever played, but the CPU can
    // only see the bank that isn't playing -- so filling just one leaves the
    // readback showing zeroes, which is indistinguishable from having written
    // nothing at all. Two extra stores at init buys a diagnostic that means
    // something: see tools/grab_sound.py.
    for (int bank = 0; bank < 2; bank++)
    {
        // Selecting a bank for playback exposes the other one to the CPU.
        REG_SND3SEL = SND3_BANK_MODE_1 | (bank ? SND3_BANK_0 : SND3_BANK_1);
        for (int i = 0; i < 4; i++)
        {
            const u8 *b = &music_wave_table[i * 4];
            wave_ram[i] = b[0] | (b[1] << 8) | (b[2] << 16) | (b[3] << 24);
        }
    }

    REG_SND3SEL = SND3_BANK_MODE_1 | SND3_BANK_0 | SND3_OUTPUT;
}

//---------------------------------------------------------------------------
// one channel's worth of "start this note" / "stop"

static void square1(u8 row)
{
    if (row == MUSIC_OFF)
    {
        // Envelope volume zero silences the channel; there's no gate to close
        // on a PSG channel, and letting the note run would hold it forever.
        REG_SND1CNT = SSQR_ENV_BUILD(0, 0, 0) | SSQR_DUTY(MUSIC_SQ1_DUTY);
        REG_SND1FREQ = SFREQ_RESET;
        return;
    }

    REG_SND1CNT = SSQR_ENV_BUILD(MUSIC_SQ1_VOL, 0, MUSIC_SQ1_DECAY)
                | SSQR_DUTY(MUSIC_SQ1_DUTY);
    REG_SND1FREQ = square_rate(row) | SFREQ_RESET;
}

static void square2(u8 row)
{
    if (row == MUSIC_OFF)
    {
        REG_SND2CNT = SSQR_ENV_BUILD(0, 0, 0) | SSQR_DUTY(MUSIC_SQ2_DUTY);
        REG_SND2FREQ = SFREQ_RESET;
        return;
    }

    REG_SND2CNT = SSQR_ENV_BUILD(MUSIC_SQ2_VOL, 0, MUSIC_SQ2_DECAY)
                | SSQR_DUTY(MUSIC_SQ2_DUTY);
    REG_SND2FREQ = square_rate(row) | SFREQ_RESET;
}

static void wave(u8 row)
{
    if (row == MUSIC_OFF)
    {
        REG_SND3CNT = SND3_VOL_0;
        return;
    }

    REG_SND3CNT = SND3_VOL_100;
    REG_SND3FREQ = wave_rate(row) | SFREQ_RESET;
}

static void noise(u8 row)
{
    if (row == MUSIC_OFF)
    {
        REG_SND4CNT = SSQR_ENV_BUILD(0, 0, 0);
        return;
    }

    REG_SND4CNT = SSQR_ENV_BUILD(MUSIC_NOI_VOL, 0, MUSIC_NOI_DECAY);
    REG_SND4FREQ = SND4_DIVISOR | SND4_WIDTH_7BIT | SND4_SHIFT(4) | SFREQ_RESET;
}

static void silence(void)
{
    square1(MUSIC_OFF);
    square2(MUSIC_OFF);
    wave(MUSIC_OFF);
    noise(MUSIC_OFF);
}

//---------------------------------------------------------------------------

void chiptune_init(void)
{
    // maxmod has already set the master enable and claimed the Direct Sound
    // half of REG_SNDDSCNT. Only the bottom two bits are ours, and apply_gain
    // owns them along with REG_SNDDMGCNT and the channel routing.
    apply_gain();

    // Channel 1 shares its registers with a frequency sweep. Left at whatever
    // it powers up as, it slides every note out of tune.
    REG_SND1SWEEP = 0;

    load_wave_table();
    silence();

    g_on = false;
    g_row = 0;
    g_frame = 0;
}

void chiptune_set(bool on)
{
    if (on == g_on)
        return;

    g_on = on;

    if (on)
    {
        // Restart at the top rather than resuming: coming back mid-phrase
        // sounds like a glitch, and nothing here is long enough to miss.
        g_row = 0;
        g_frame = 0;
    }
    else
    {
        silence();
    }
}

bool chiptune_enabled(void)
{
    return g_on;
}

void chiptune_set_volume(int vol)
{
    if (vol < 0)       vol = 0;
    if (vol > VOL_MAX) vol = VOL_MAX;

    g_vol = vol;
    apply_gain();
}

int chiptune_row(void)
{
    return g_row;
}

bool chiptune_active(void)
{
    // REG_SNDSTAT's low four bits are read-only flags for the PSG channels.
    return (REG_SNDSTAT & (SSTAT_SQR1 | SSTAT_SQR2 | SSTAT_WAVE | SSTAT_NOISE))
           != 0;
}

void chiptune_frame(void)
{
    if (!g_on)
        return;

    if (--g_frame > 0)
        return;

    g_frame = MUSIC_ROW_FRAMES;

    u8 a = music_sq1[g_row];
    u8 b = music_sq2[g_row];
    u8 c = music_wave[g_row];
    u8 d = music_noise[g_row];

    if (a != MUSIC_HOLD) square1(a);
    if (b != MUSIC_HOLD) square2(b);
    if (c != MUSIC_HOLD) wave(c);
    if (d != MUSIC_HOLD) noise(d);

    if (++g_row >= MUSIC_ROWS)
        g_row = 0;
}
