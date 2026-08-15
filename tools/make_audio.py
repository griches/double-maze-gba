#!/usr/bin/env python3
"""Convert the iOS audio into a maxmod soundbank source directory.

Effects are downsampled to 8-bit mono at 11025 Hz, which is plenty for the
GBA's mixer and keeps them a few KB each.

The music is the awkward one. maxmod's streaming API is Nintendo DS only, and
an 89-second recording can't become a tracker module without transcribing it.
What does work: mmutil reads loop points from a WAV's `smpl` chunk, so a long
sample tagged with a full-length loop plays as a seamlessly looping effect.
Nothing off the shelf writes `smpl`, so we emit that WAV by hand.

Decoding goes through macOS's built-in afconvert rather than ffmpeg, which
needs no install and handles both the wavs and the mp3.

    python3 tools/make_audio.py [path-to-ios-project]
"""

import os
import struct
import subprocess
import sys
import tempfile

HERE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
AUDIO = os.path.join(HERE, "audio")
DEFAULT_IOS = "/Users/garyriches/Documents/Source/DoubleMaze/DoubleMaze"

SFX_RATE = 11025
MUSIC_RATE = 10512        # 89s at this rate is ~915KB of ROM

# output name -> source file. The name becomes mmutil's SFX_<NAME> identifier.
EFFECTS = [
    ("death",   "CARTOON_WHISTLE__40017804.wav"),  # slot 0: falling
    ("roll",    "Stone_on_Metal_23.wav"),          # slot 1: ball movement
    ("page",    "Books_Manuals_Ma_NF060382.wav"),  # slot 2: screen transition
    ("chime",   "Glass_Chime_Tinkle_Low.wav"),     # slot 3: goal reached
    ("fanfare", "Glass_Chime_Tinkle_High.wav"),    # level complete
    ("click",   "buttonclick.wav"),                # slot 5: UI
]
MUSIC = "music.mp3"


def read_data_chunk(path):
    """Pull the raw samples out of a RIFF/WAVE file."""
    with open(path, "rb") as fh:
        blob = fh.read()
    if blob[:4] != b"RIFF" or blob[8:12] != b"WAVE":
        raise SystemExit("not a WAVE file: %s" % path)
    pos = 12
    while pos + 8 <= len(blob):
        cid = blob[pos:pos + 4]
        size = struct.unpack("<I", blob[pos + 4:pos + 8])[0]
        if cid == b"data":
            return blob[pos + 8:pos + 8 + size]
        pos += 8 + size + (size & 1)
    raise SystemExit("no data chunk in %s" % path)


def decode_pcm_u8(src, rate):
    """Decode anything to raw unsigned 8-bit mono PCM at the given rate."""
    with tempfile.NamedTemporaryFile(suffix=".wav", delete=False) as tmp:
        tmp_path = tmp.name
    try:
        subprocess.run(
            ["afconvert", "-f", "WAVE", "-d", "UI8@%d" % rate, "-c", "1",
             src, tmp_path],
            check=True, capture_output=True)
        return read_data_chunk(tmp_path)
    finally:
        os.unlink(tmp_path)


def write_wav(path, pcm, rate, loop=False):
    # An odd-length data chunk needs a RIFF pad byte before the next chunk --
    # and mmutil doesn't account for it, so it reads the following `smpl`
    # chunk one byte out and silently drops the loop point (the sample comes
    # out marked one-shot). Pad the samples themselves so the chunk is even
    # and the question never arises.
    if len(pcm) % 2:
        pcm = pcm + pcm[-1:]

    fmt = struct.pack("<HHIIHH", 1, 1, rate, rate, 1, 8)
    body = b"fmt " + struct.pack("<I", len(fmt)) + fmt
    body += b"data" + struct.pack("<I", len(pcm)) + pcm

    if loop:
        # One forward loop spanning the whole sample. mmutil turns this into a
        # real loop point instead of the 0xFFFFFFFF "one shot" marker.
        smpl = struct.pack("<IIIIIIIII",
                           0, 0, int(1e9 / rate), 60, 0, 0, 0, 1, 0)
        smpl += struct.pack("<IIIIII", 0, 0, 0, len(pcm) - 1, 0, 0)
        body += b"smpl" + struct.pack("<I", len(smpl)) + smpl

    with open(path, "wb") as fh:
        fh.write(b"RIFF" + struct.pack("<I", 4 + len(body)) + b"WAVE" + body)


def main():
    ios = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_IOS
    os.makedirs(AUDIO, exist_ok=True)

    total = 0
    for name, src in EFFECTS:
        path = os.path.join(ios, src)
        if not os.path.exists(path):
            raise SystemExit("missing audio source: %s" % path)
        pcm = decode_pcm_u8(path, SFX_RATE)
        out = os.path.join(AUDIO, name + ".wav")
        write_wav(out, pcm, SFX_RATE)
        total += len(pcm)
        print("%-10s %7d bytes  %5.2fs  <- %s"
              % (name, len(pcm), len(pcm) / SFX_RATE, src))

    pcm = decode_pcm_u8(os.path.join(ios, MUSIC), MUSIC_RATE)
    write_wav(os.path.join(AUDIO, "music.wav"), pcm, MUSIC_RATE, loop=True)
    total += len(pcm)
    print("%-10s %7d bytes  %5.2fs  <- %s (looping)"
          % ("music", len(pcm), len(pcm) / MUSIC_RATE, MUSIC))

    print("\n%d bytes of sample data total" % total)


if __name__ == "__main__":
    main()
