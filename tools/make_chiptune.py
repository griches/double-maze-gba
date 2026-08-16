#!/usr/bin/env python3
"""Compose the background music, and render what the GBA will make of it.

The original's 89-second track is a 936KB PCM sample -- 90% of the ROM, and
still muddy, because Direct Sound is 8-bit and no sample rate fixes that. This
replaces it with a score the console plays on its own PSG channels: two pulse
waves, a 4-bit programmable wave, and noise. Those four sit idle otherwise,
since maxmod only drives the two Direct Sound channels, so the music costs no
mixer channels and about 3KB instead of 936KB.

Two outputs, from one score:

    source/music.h          the note data and rate tables the GBA plays
    docs/music-preview.wav  the same score rendered here, to listen to

The renderer is not a nice-sounding approximation -- it's meant to sound like
the hardware will. It quantises every note to the 11-bit rate register the
console actually programs, runs the same 15-step volume envelopes, and clocks
the noise channel through the same LFSR. What comes out of the speaker should
be what comes out of this file.

    python3 tools/make_chiptune.py [--wav out.wav] [--header source/music.h]
"""

import argparse
import math
import os
import struct
import wave

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

# The player ticks once per frame off the VBlank it already waits on, so
# timing is quantised to frames rather than to a tempo. Ten frames a row puts
# a sixteenth note at 167ms -- a shade under 90bpm, unhurried.
FRAME_HZ = 59.7275
ROW_FRAMES = 10
ROWS_PER_BAR = 16
BARS = 32
ROWS = BARS * ROWS_PER_BAR

ROW_SECONDS = ROW_FRAMES / FRAME_HZ

# Channel slots in the emitted tables.
SQ1, SQ2, WAV, NOI = 0, 1, 2, 3
CHANNELS = 4

# Row bytes: 0 holds whatever is sounding, 1 releases it, anything else is a
# MIDI note to trigger. Note 1 is never used musically, so it's free to mean
# "off" -- which keeps a row to one byte with no escape codes.
HOLD, OFF = 0, 1

RENDER_HZ = 44100

#---------------------------------------------------------------------------
# notes

STEPS = {"C": 0, "D": 2, "E": 4, "F": 5, "G": 7, "A": 9, "B": 11}


def midi(name):
    """"A4" -> 69, "G#4" -> 68. Middle C is C4 = 60."""
    step = STEPS[name[0].upper()]
    i = 1
    if len(name) > 1 and name[1] in "#b":
        step += 1 if name[1] == "#" else -1
        i = 2
    return (int(name[i:]) + 1) * 12 + step


def hz(note):
    return 440.0 * (2.0 ** ((note - 69) / 12.0))


# The GBA programs a period, not a frequency, so every note lands on the
# nearest value an 11-bit register can hold. Rounding here rather than at
# playback is what keeps this preview honest about the tuning.
def square_rate(note):
    return max(0, min(2047, int(round(2048 - 131072.0 / hz(note)))))


def wave_rate(note):
    return max(0, min(2047, int(round(2048 - 65536.0 / hz(note)))))


def square_hz(note):
    return 131072.0 / (2048 - square_rate(note))


def wave_hz(note):
    return 65536.0 / (2048 - wave_rate(note))


#---------------------------------------------------------------------------
# the score
#
# A minor throughout, one chord to the bar, in four eight-bar sections: a
# theme, a variation on it, a lift, and the theme again to close. The melody
# is deliberately full of holes -- this plays under someone thinking, and the
# rests are what keep it from nagging.

CHORDS = {
    "Am": ("A2", ["A4", "C5", "E5"]),
    "F":  ("F2", ["F4", "A4", "C5"]),
    "C":  ("C3", ["C4", "E4", "G4"]),
    "G":  ("G2", ["G4", "B4", "D5"]),
    "Dm": ("D3", ["D4", "F4", "A4"]),
    "E":  ("E2", ["E4", "G#4", "B4"]),
}

PROGRESSION = [
    # A -- the theme
    "Am", "F", "C", "G", "Am", "F", "Dm", "E",
    # A' -- same shape, sitting higher
    "Am", "F", "C", "G", "Am", "Dm", "E", "Am",
    # B -- the lift
    "F", "C", "G", "Am", "F", "C", "Dm", "E",
    # A'' -- back down, and close on the tonic
    "Am", "F", "C", "G", "Am", "F", "E", "Am",
]

# (bar, row within the bar, note, length in rows)
MELODY = [
    # A
    (0, 4, "E5", 8), (0, 12, "D5", 4),
    (1, 0, "C5", 10),
    (2, 4, "E5", 4), (2, 8, "G5", 4), (2, 12, "E5", 4),
    (3, 0, "D5", 12),
    (4, 4, "C5", 4), (4, 8, "B4", 4), (4, 12, "A4", 4),
    (5, 0, "A4", 10),
    (6, 4, "D5", 4), (6, 8, "F5", 4), (6, 12, "E5", 4),
    (7, 0, "B4", 10),
    # A'
    (8, 4, "A5", 8), (8, 12, "G5", 4),
    (9, 0, "F5", 10),
    (10, 4, "E5", 4), (10, 8, "G5", 4), (10, 12, "A5", 4),
    (11, 0, "G5", 12),
    (12, 4, "E5", 4), (12, 8, "D5", 4), (12, 12, "C5", 4),
    (13, 0, "D5", 10),
    (14, 4, "B4", 4), (14, 8, "G#4", 4), (14, 12, "B4", 4),
    (15, 0, "A4", 12),
    # B
    (16, 0, "C5", 4), (16, 4, "F5", 4), (16, 8, "A5", 8),
    (17, 0, "G5", 4), (17, 4, "E5", 4), (17, 8, "C5", 8),
    (18, 0, "D5", 4), (18, 4, "G5", 4), (18, 8, "D5", 8),
    (19, 0, "C5", 4), (19, 4, "A4", 12),
    (20, 0, "C5", 4), (20, 4, "F5", 4), (20, 8, "A5", 8),
    (21, 0, "G5", 4), (21, 4, "E5", 4), (21, 8, "G5", 8),
    (22, 0, "F5", 4), (22, 4, "D5", 4), (22, 8, "A4", 8),
    (23, 0, "B4", 8), (23, 8, "G#4", 8),
    # A''
    (24, 4, "E5", 8), (24, 12, "D5", 4),
    (25, 0, "C5", 10),
    (26, 4, "E5", 4), (26, 8, "G5", 4), (26, 12, "E5", 4),
    (27, 0, "D5", 12),
    (28, 4, "C5", 4), (28, 8, "B4", 4), (28, 12, "A4", 4),
    (29, 0, "A4", 10),
    (30, 4, "B4", 4), (30, 8, "G#4", 4), (30, 12, "B4", 4),
    (31, 0, "A4", 14),
]

# The bass hits beats one and three, a little short of filling them, so the
# bar breathes. The arpeggio falls on the off-beats between, which is what
# gives the whole thing its sway.
BASS_HITS = [(0, 7), (8, 7)]
ARP_ROWS = [2, 6, 10, 14]

# Barely there: one soft tick to mark every fourth bar, and a pair to lean
# into the final turnaround.
PERCUSSION = [(3, 12), (7, 12), (11, 12), (15, 12),
              (19, 12), (23, 12), (27, 12), (31, 8), (31, 12)]


def build_rows():
    """The score as four rows-of-bytes tracks."""
    track = [[HOLD] * ROWS for _ in range(CHANNELS)]

    def put(ch, row, note, length):
        track[ch][row % ROWS] = note
        end = row + length
        if end < ROWS:
            track[ch][end] = OFF

    for bar, row, name, length in MELODY:
        put(SQ1, bar * ROWS_PER_BAR + row, midi(name), length)

    for bar, chord in enumerate(PROGRESSION):
        root, tones = CHORDS[chord]
        base = bar * ROWS_PER_BAR

        for row, length in BASS_HITS:
            put(WAV, base + row, midi(root), length)

        # Root, third, fifth, third -- up and part-way back, so consecutive
        # bars join up instead of resetting.
        shape = [tones[0], tones[1], tones[2], tones[1]]
        for row, name in zip(ARP_ROWS, shape):
            put(SQ2, base + row, midi(name), 3)

    for bar, row in PERCUSSION:
        put(NOI, bar * ROWS_PER_BAR + row, 60, 1)

    return track


#---------------------------------------------------------------------------
# instruments
#
# The PSG has no attack -- a note starts at its loudest and falls -- so the
# shaping available is duty cycle and how fast the envelope drops. Melody gets
# 50% duty, which is the hollow, flute-ish one; the arpeggio gets 25% and a
# fast decay so it reads as plucked rather than sustained.

class Instrument:
    def __init__(self, duty=0, volume=15, decay=0):
        self.duty = duty          # 0=12.5% 1=25% 2=50% 3=75%
        self.volume = volume      # envelope start, 0-15
        self.decay = decay        # 0 = hold, else steps of 1/64s per level


INSTRUMENTS = {
    SQ1: Instrument(duty=2, volume=11, decay=7),
    SQ2: Instrument(duty=1, volume=6,  decay=3),
    WAV: Instrument(volume=15),
    NOI: Instrument(volume=4,  decay=1),
}

# A soft, rounded shape for the bass -- a triangle rather than another square,
# so it fills the bottom without buzzing against the two pulse channels.
WAVE_TABLE = [min(15, max(0, int(round(7.5 + 7.5 * math.sin(2 * math.pi * i / 32)))))
              for i in range(32)]

# How loud each channel sits in the mix. The GBA has a 3-bit master and
# per-channel enables but no per-channel volume, so balance has to come from
# the envelopes; these are the render's equivalent.
MIX = {SQ1: 0.42, SQ2: 0.20, WAV: 0.34, NOI: 0.12}

DUTY_FRACTION = [0.125, 0.25, 0.50, 0.75]


#---------------------------------------------------------------------------
# render

def envelope_at(inst, t):
    """Volume 0..15 t seconds into a note."""
    if inst.decay == 0:
        return inst.volume
    dropped = int(t / (inst.decay / 64.0))
    return max(0, inst.volume - dropped)


def note_spans(rows):
    """Rows -> [(start_row, end_row, note)], collapsing holds."""
    spans = []
    note, start = None, 0
    for i, value in enumerate(rows):
        if value == HOLD:
            continue
        if note is not None:
            spans.append((start, i, note))
        note = None if value == OFF else value
        start = i
    if note is not None:
        spans.append((start, len(rows), note))
    return spans


def render_square(buf, inst, note, t0, t1, gain):
    freq = square_hz(note)
    duty = DUTY_FRACTION[inst.duty]
    i0, i1 = int(t0 * RENDER_HZ), min(len(buf), int(t1 * RENDER_HZ))
    for i in range(i0, i1):
        t = (i - i0) / RENDER_HZ
        vol = envelope_at(inst, t)
        if vol == 0:
            continue
        phase = (t * freq) % 1.0
        level = 1.0 if phase < duty else -1.0
        buf[i] += level * (vol / 15.0) * gain


def render_wave(buf, inst, note, t0, t1, gain):
    freq = wave_hz(note)
    i0, i1 = int(t0 * RENDER_HZ), min(len(buf), int(t1 * RENDER_HZ))
    for i in range(i0, i1):
        t = (i - i0) / RENDER_HZ
        step = int((t * freq * 32) % 32)
        # 4-bit samples are unsigned; centre them the way the DAC does.
        buf[i] += ((WAVE_TABLE[step] - 7.5) / 7.5) * (inst.volume / 15.0) * gain


def render_noise(buf, inst, t0, t1, gain):
    """The 7-bit LFSR, which is the short, metallic one -- a tick, not a hiss."""
    lfsr = 0x7F
    clock = 262144.0        # divisor 2, shift 1: fast enough to read as a click
    i0, i1 = int(t0 * RENDER_HZ), min(len(buf), int(t1 * RENDER_HZ))
    carry = 0.0
    for i in range(i0, i1):
        t = (i - i0) / RENDER_HZ
        vol = envelope_at(inst, t)
        if vol == 0:
            continue
        carry += clock / RENDER_HZ
        while carry >= 1.0:
            carry -= 1.0
            bit = (lfsr ^ (lfsr >> 1)) & 1
            lfsr = (lfsr >> 1) | (bit << 6)
        buf[i] += (1.0 if (lfsr & 1) else -1.0) * (vol / 15.0) * gain


def render(track, path):
    total = ROWS * ROW_SECONDS
    buf = [0.0] * int(total * RENDER_HZ)

    for ch in range(CHANNELS):
        inst = INSTRUMENTS[ch]
        gain = MIX[ch]
        for start, end, note in note_spans(track[ch]):
            t0, t1 = start * ROW_SECONDS, end * ROW_SECONDS
            if ch == WAV:
                render_wave(buf, inst, note, t0, t1, gain)
            elif ch == NOI:
                render_noise(buf, inst, t0, t1, gain)
            else:
                render_square(buf, inst, note, t0, t1, gain)

    peak = max(abs(v) for v in buf) or 1.0
    scale = 0.89 / peak
    frames = b"".join(struct.pack("<h", int(v * scale * 32767)) for v in buf)

    with wave.open(path, "wb") as fh:
        fh.setnchannels(1)
        fh.setsampwidth(2)
        fh.setframerate(RENDER_HZ)
        fh.writeframes(frames)
    print("wrote %s (%.1f s)" % (path, total))


#---------------------------------------------------------------------------
# header

def write_header(track, path):
    used = sorted({v for ch in track for v in ch if v > OFF})
    lo, hi = min(used), max(used)

    def rows_c(name, rows):
        out = ["static const u8 %s[MUSIC_ROWS] = {" % name]
        for i in range(0, ROWS, 16):
            out.append("    " + ", ".join("%3d" % v for v in rows[i:i + 16]) + ",")
        return out + ["};", ""]

    def rates_c(name, fn):
        out = ["static const u16 %s[MUSIC_NOTE_COUNT] = {" % name]
        values = [fn(n) for n in range(lo, hi + 1)]
        for i in range(0, len(values), 8):
            out.append("    " + ", ".join("%4d" % v for v in values[i:i + 8]) + ",")
        return out + ["};", ""]

    lines = [
        "// Generated by tools/make_chiptune.py -- do not edit by hand.",
        "",
        "#ifndef DOUBLE_MAZE_MUSIC_H",
        "#define DOUBLE_MAZE_MUSIC_H",
        "",
        "#include <tonc.h>",
        "",
        "// One row per sixteenth note, %d frames apart -- about %d bpm."
        % (ROW_FRAMES, round(60.0 / (ROW_SECONDS * 4))),
        "// A row of 0 holds whatever is sounding, 1 releases it, and anything",
        "// else is a MIDI note to trigger.",
        "#define MUSIC_ROW_FRAMES %d" % ROW_FRAMES,
        "#define MUSIC_ROWS       %d" % ROWS,
        "#define MUSIC_HOLD       %d" % HOLD,
        "#define MUSIC_OFF        %d" % OFF,
        "",
        "// The rate tables cover only the notes the score uses, so a lookup is",
        "// note - MUSIC_NOTE_FIRST. They're precomputed rather than derived on",
        "// the GBA because the rounding is what fixes the tuning, and it has to",
        "// match what tools/make_chiptune.py rendered to WAV.",
        "#define MUSIC_NOTE_FIRST %d" % lo,
        "#define MUSIC_NOTE_COUNT %d" % (hi - lo + 1),
        "",
        "// Envelope and duty per channel, as the hardware wants them.",
        "#define MUSIC_SQ1_DUTY   %d" % INSTRUMENTS[SQ1].duty,
        "#define MUSIC_SQ1_VOL    %d" % INSTRUMENTS[SQ1].volume,
        "#define MUSIC_SQ1_DECAY  %d" % INSTRUMENTS[SQ1].decay,
        "#define MUSIC_SQ2_DUTY   %d" % INSTRUMENTS[SQ2].duty,
        "#define MUSIC_SQ2_VOL    %d" % INSTRUMENTS[SQ2].volume,
        "#define MUSIC_SQ2_DECAY  %d" % INSTRUMENTS[SQ2].decay,
        "#define MUSIC_NOI_VOL    %d" % INSTRUMENTS[NOI].volume,
        "#define MUSIC_NOI_DECAY  %d" % INSTRUMENTS[NOI].decay,
        "",
    ]

    lines += rates_c("music_rate_square", square_rate)
    lines += rates_c("music_rate_wave", wave_rate)

    lines += ["// The bass waveform, two 4-bit samples to a byte.",
              "static const u8 music_wave_table[16] = {"]
    packed = ["0x%02X" % ((WAVE_TABLE[i] << 4) | WAVE_TABLE[i + 1])
              for i in range(0, 32, 2)]
    lines += ["    " + ", ".join(packed) + ","]
    lines += ["};", ""]

    lines += rows_c("music_sq1", track[SQ1])
    lines += rows_c("music_sq2", track[SQ2])
    lines += rows_c("music_wave", track[WAV])
    lines += rows_c("music_noise", track[NOI])

    lines += ["#endif // DOUBLE_MAZE_MUSIC_H", ""]

    with open(path, "w") as fh:
        fh.write("\n".join(lines))

    size = 4 * ROWS + 2 * 2 * (hi - lo + 1) + 16
    print("wrote %s (%d rows, notes %d-%d, %d bytes of data)"
          % (path, ROWS, lo, hi, size))


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--wav", default=os.path.join(HERE, "docs",
                                                  "music-preview.wav"))
    ap.add_argument("--header", default=os.path.join(HERE, "source",
                                                     "music.h"))
    args = ap.parse_args()

    track = build_rows()
    write_header(track, args.header)
    render(track, args.wav)


if __name__ == "__main__":
    main()
