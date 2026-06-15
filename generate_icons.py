#!/usr/bin/env python3
"""Generate the Whispy menu bar icon.

Creates the brand waveform glyph (icons/whispy.png): 5 rounded bars (center-tall,
mirrors website/assets/logo.svg) painted with a vertical mint->teal gradient,
faded edge bars, and a soft glow. Rendered at 2x (44x44) so it stays crisp when
AppKit scales it down to the menu bar height.
Run once after install: python generate_icons.py
"""

import os

from PIL import Image, ImageDraw, ImageFilter

ICONS_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "icons")

# Logical menu bar size is ~22pt; render at 2x for retina sharpness.
SCALE = 2
SIZE = 22 * SCALE

# Brand gradient: mint-green (top) -> teal (bottom). Brand green is #24bf9e.
GRAD_TOP = (63, 224, 189)   # #3fe0bd
GRAD_BOTTOM = (23, 168, 176)  # #17a8b0

NUM_BARS = 5


def _new_image():
    return Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))


def _vertical_gradient(top, bottom):
    """Full-canvas RGBA image with a vertical top->bottom color ramp."""
    grad = Image.new("RGBA", (SIZE, SIZE))
    px = grad.load()
    for y in range(SIZE):
        t = y / (SIZE - 1)
        r = round(top[0] + (bottom[0] - top[0]) * t)
        g = round(top[1] + (bottom[1] - top[1]) * t)
        b = round(top[2] + (bottom[2] - top[2]) * t)
        for x in range(SIZE):
            px[x, y] = (r, g, b, 255)
    return grad


def _waveform_mask(heights, alphas):
    """Grayscale mask: 5 rounded vertical bars, per-bar opacity via gray level.

    heights: 5 floats in [0, 1] (fraction of usable height).
    alphas:  5 floats in [0, 1] mapped to mask gray (edge fade).
    """
    mask = Image.new("L", (SIZE, SIZE), 0)
    draw = ImageDraw.Draw(mask)

    margin = 3 * SCALE
    usable_w = SIZE - 2 * margin
    gap = 2 * SCALE
    bar_w = (usable_w - gap * (NUM_BARS - 1)) / NUM_BARS
    radius = bar_w / 2
    usable_h = SIZE - 2 * margin
    center_y = SIZE / 2

    for i in range(NUM_BARS):
        h = max(bar_w, heights[i] * usable_h)  # never thinner than a dot
        x0 = margin + i * (bar_w + gap)
        x1 = x0 + bar_w
        y0 = center_y - h / 2
        y1 = center_y + h / 2
        gray = int(255 * alphas[i])
        draw.rounded_rectangle((x0, y0, x1, y1), radius=radius, fill=gray)
    return mask


def _render(mask):
    """Paint the gradient through `mask` and add a soft glow behind it."""
    gradient = _vertical_gradient(GRAD_TOP, GRAD_BOTTOM)

    # Sharp shape: gradient masked by the glyph.
    shape = gradient.copy()
    shape.putalpha(mask)

    # Glow: blurred copy of the shape, dimmed, composited underneath.
    glow = shape.filter(ImageFilter.GaussianBlur(radius=1.5 * SCALE))
    glow_alpha = glow.getchannel("A").point(lambda a: int(a * 0.5))
    glow.putalpha(glow_alpha)

    out = _new_image()
    out = Image.alpha_composite(out, glow)
    out = Image.alpha_composite(out, shape)
    return out


def generate_icons():
    os.makedirs(ICONS_DIR, exist_ok=True)

    # Single brand icon: calm waveform, edges faded (matches logo opacity falloff).
    icon = _render(_waveform_mask(
        heights=[0.30, 0.55, 1.0, 0.65, 0.40],
        alphas=[0.55, 1.0, 1.0, 1.0, 0.70],
    ))
    path = os.path.join(ICONS_DIR, "whispy.png")
    icon.save(path)
    print(f"  {path}")


if __name__ == "__main__":
    print("Generating icon...")
    generate_icons()
    print("Done.")
