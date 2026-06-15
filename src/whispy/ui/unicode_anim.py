"""Unicode braille animation frames for the menu bar.

The ``waverows`` frames are vendored (ported to Python) from unicode-animations
by gunnargray-dev — https://github.com/gunnargray-dev/unicode-animations — which
is MIT licensed. Pure data, no third-party dependency.

``waverows`` is a sine wave scrolling left->right across 4 braille characters
(8 dot-columns); it reads like an audio waveform, matching the Whispy brand.

To regenerate the frames, the original generator is (8x4 dot grid, 16 frames):

    row = round((sin((f - c*0.5) * 0.8) + 1) / 2 * 3)   # per column c, frame f
    plus a sparse trailing dot one row above when (f + c) % 3 == 0
"""

# 16 scrolling-wave frames (4 braille chars each).
WAVEROWS: list[str] = [
    "⠖⠉⠉⠑",
    "⡠⠖⠉⠉",
    "⣠⡠⠖⠉",
    "⣄⣠⡠⠖",
    "⠢⣄⣠⡠",
    "⠙⠢⣄⣠",
    "⠉⠙⠢⣄",
    "⠊⠉⠙⠢",
    "⠜⠊⠉⠙",
    "⡤⠜⠊⠉",
    "⣀⡤⠜⠊",
    "⢤⣀⡤⠜",
    "⠣⢤⣀⡤",
    "⠑⠣⢤⣀",
    "⠉⠑⠣⢤",
    "⠋⠉⠑⠣",
]

# Frame interval in seconds (90 ms in the original library).
WAVEROWS_INTERVAL = 0.09

# Static frame shown when idle: a calm centered waveform.
IDLE_FRAME = "⣀⣤⣶⣤"
