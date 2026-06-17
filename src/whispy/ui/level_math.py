"""Pure audio-level math for the recording visualization.

Extracted from ``audio_level.AudioLevelMonitor`` so the normalize + smoothing
step is unit-testable without sounddevice. The monitor computes the raw RMS
from the audio block (numpy) and passes it here.
"""

# Gain applied to the raw RMS before clamping to the 0.0-1.0 display range.
_LEVEL_GAIN = 10.0


def rms_to_level(rms: float, prev_smoothed: float, smoothing: float) -> float:
    """Map a raw RMS amplitude to a smoothed 0.0-1.0 level.

    Normalizes the RMS (gain then clamp to 1.0) and applies an exponential
    moving average against the previous smoothed level:
    ``smoothing * prev + (1 - smoothing) * normalized``.
    """
    normalized = min(rms * _LEVEL_GAIN, 1.0)
    return smoothing * prev_smoothed + (1.0 - smoothing) * normalized
