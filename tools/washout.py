#!/usr/bin/env python3
"""Simulate a non-backlit GBA screen, to sanity-check contrast.

An AGB / AGS-001 panel is reflective: it never gets darker than the ambient
light bouncing off it, and it never gets brighter than white paper. Its whole
range lands in a narrow band of pale grey, and the colour filters are weak so
everything desaturates on the way through. Art that reads fine on an sRGB
monitor can collapse to one flat tone once it's squeezed through that.

Numbers here are eyeballed from photos of the real thing: black comes out
around 130 and white around 232, with roughly a third of the saturation left.

    python3 tools/washout.py in.png out.png
"""

import sys
from PIL import Image, ImageEnhance

BLACK_POINT = 130      # what a 0 pixel actually looks like on the panel
WHITE_POINT = 232      # what a 255 pixel actually looks like
SATURATION = 0.35      # how much colour survives the filters
TINT = (0.98, 0.98, 1.06)   # the panel's slight lavender cast


def washout(img):
    img = ImageEnhance.Color(img.convert("RGB")).enhance(SATURATION)
    span = WHITE_POINT - BLACK_POINT
    return Image.merge("RGB", [
        ch.point(lambda v, t=t: min(255, int(BLACK_POINT + v * span / 255 * t)))
        for ch, t in zip(img.split(), TINT)
    ])


def main():
    src, dst = sys.argv[1], sys.argv[2]
    im = Image.open(src)
    out = washout(im)
    out = out.resize((out.width * 3, out.height * 3), Image.NEAREST)
    out.save(dst)
    print("wrote", dst)


if __name__ == "__main__":
    main()
