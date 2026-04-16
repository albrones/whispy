#!/usr/bin/env python3
"""Generate menu bar icons for Whisper Dictation.

Creates 22x22 template-style PNGs (black on transparent) in icons/ directory.
Run once after install: python generate_icons.py
"""

import os

from PIL import Image, ImageDraw

ICONS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icons")
SIZE = 22


def _new_image():
    return Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))


def _draw_mic(draw):
    draw.rounded_rectangle((6, 3, 12, 13), radius=3, fill="black")
    draw.arc((4, 8, 14, 18), start=0, end=180, fill="black", width=2)
    draw.line((9, 18, 9, 20), fill="black", width=2)
    draw.line((6, 20, 12, 20), fill="black", width=2)


def _draw_wave_arc(draw, index):
    offsets = [(2, 2, 16, 16), (-1, -1, 19, 19), (-4, -4, 22, 22)]
    if index < len(offsets):
        bbox = offsets[index]
        draw.arc(bbox, start=315, end=45, fill="black", width=2)


def generate_icons():
    os.makedirs(ICONS_DIR, exist_ok=True)

    img = _new_image()
    _draw_mic(ImageDraw.Draw(img))
    path = os.path.join(ICONS_DIR, "mic-idle.png")
    img.save(path)
    print(f"  {path}")

    for frame in range(1, 4):
        img = _new_image()
        draw = ImageDraw.Draw(img)
        _draw_mic(draw)
        for i in range(frame):
            _draw_wave_arc(draw, i)
        path = os.path.join(ICONS_DIR, f"mic-recording-{frame}.png")
        img.save(path)
        print(f"  {path}")

    img = _new_image()
    draw = ImageDraw.Draw(img)
    _draw_mic(draw)
    draw.ellipse((13, 16, 15, 18), fill="black")
    draw.ellipse((16, 16, 18, 18), fill="black")
    draw.ellipse((19, 16, 21, 18), fill="black")
    path = os.path.join(ICONS_DIR, "mic-transcribing.png")
    img.save(path)
    print(f"  {path}")


if __name__ == "__main__":
    print("Generating icons...")
    generate_icons()
    print("Done.")
