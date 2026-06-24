#!/usr/bin/env python3
"""Render the Whispy macOS app icon (.icns) from the brand logo.

Mirrors website/assets/logo.svg (rounded dark square + mint waveform) at 1024px,
then builds packaging/macos/whispy.icns via `iconutil`. The menu-bar glyph lives
in generate_icons.py; this is the larger Finder/Dock/TCC app icon.

Run: python packaging/macos/make_icns.py
"""

import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image, ImageDraw

HERE = Path(__file__).resolve().parent
OUT_ICNS = HERE / "whispy.icns"

# Brand palette (from website/assets/logo.svg).
BG = (22, 22, 28, 255)       # #16161c
MINT = (36, 191, 158)        # #24bf9e

# logo.svg uses a 64-unit viewBox; we render at 1024 so 1 unit = SCALE px.
VIEWBOX = 64
MASTER = 1024
SCALE = MASTER / VIEWBOX

# Waveform bars: (x, y_top, y_bottom, opacity) in viewBox units. The first is a
# dot (y_top == y_bottom). Matches lines in logo.svg.
BARS = [
    (16, 32, 32, 0.55),
    (24, 24, 40, 1.0),
    (32, 16, 48, 1.0),
    (40, 22, 42, 1.0),
    (48, 28, 36, 0.7),
]
STROKE = 3.4  # viewBox units


def _u(v: float) -> float:
    """viewBox units -> master pixels."""
    return v * SCALE


def render_master() -> Image.Image:
    """Render the 1024px app icon as an RGBA image."""
    img = Image.new("RGBA", (MASTER, MASTER), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Rounded-square background (rect x=2 y=2 w=60 h=60 rx=16 in the SVG).
    draw.rounded_rectangle(
        [_u(2), _u(2), _u(62), _u(62)],
        radius=_u(16),
        fill=BG,
    )

    # Waveform bars: capsules (rounded-cap thick strokes) and a dot.
    half = _u(STROKE) / 2
    for x, y0, y1, op in BARS:
        cx = _u(x)
        color = (*MINT, round(255 * op))
        if y0 == y1:  # dot
            cy = _u(y0)
            draw.ellipse([cx - half, cy - half, cx + half, cy + half], fill=color)
        else:
            draw.rounded_rectangle(
                [cx - half, _u(y0) - half, cx + half, _u(y1) + half],
                radius=half,
                fill=color,
            )
    return img


def build_icns(master: Image.Image) -> None:
    """Write an .iconset of the required sizes and run iconutil -> .icns."""
    sizes = [16, 32, 64, 128, 256, 512, 1024]
    with tempfile.TemporaryDirectory() as tmp:
        iconset = Path(tmp) / "whispy.iconset"
        iconset.mkdir()
        for s in sizes:
            resized = master.resize((s, s), Image.LANCZOS)
            # Apple naming: icon_<pt>x<pt>.png and @2x variants.
            if s <= 512:
                resized.save(iconset / f"icon_{s}x{s}.png")
            if s >= 32:
                half = s // 2
                resized.save(iconset / f"icon_{half}x{half}@2x.png")
        subprocess.run(
            ["iconutil", "-c", "icns", str(iconset), "-o", str(OUT_ICNS)],
            check=True,
        )


def main() -> int:
    master = render_master()
    build_icns(master)
    print(f"[OK] wrote {OUT_ICNS}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
