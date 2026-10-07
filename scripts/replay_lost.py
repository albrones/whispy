"""Replay clips the model lost, as is and under each variant worth suspecting.

Usage: .venv/bin/python scripts/replay_lost.py ~/.whispy/lost/*.wav

Whispy keeps every clip that cleared the gates but came back empty (see
LOST_CLIPS_DIR in src/whispy/core/audio.py). For each one this prints what the
model returns on the clip untouched, trimmed the way Whispy trims it, trimmed
with a wider margin, and gain-normalized -- so a cause is measured on real
losses instead of guessed at. Empty output prints as "" so a loss stays visible.
"""

import os
import sys
import tempfile
import wave
from collections.abc import Callable

import numpy as np

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

from whispy.core.audio import TRIM_MARGIN_S, AudioEngine  # noqa: E402
from whispy.core.engine import _load_model  # noqa: E402
from whispy.core.state_machine import StateMachine  # noqa: E402

WIDER_MARGIN_S = 1.0
NORMALIZED_PEAK = 0.9


def _read(path: str) -> tuple[np.ndarray, int]:
    with wave.open(path, "rb") as wf:
        rate = wf.getframerate()
        samples = np.frombuffer(wf.readframes(wf.getnframes()), dtype=np.int16)
    return samples, rate


def _write(samples: np.ndarray, rate: int) -> str:
    handle, path = tempfile.mkstemp(suffix=".wav", prefix="whispy-replay-")
    os.close(handle)
    with wave.open(path, "wb") as wf:
        wf.setnchannels(1)
        wf.setsampwidth(2)
        wf.setframerate(rate)
        wf.writeframes(samples.astype(np.int16).tobytes())
    return path


def _trimmed(margin_s: float, span: tuple[float, float, float] | None) -> Callable[[str], str | None]:
    def variant(path: str) -> str | None:
        if span is None:
            return None
        samples, rate = _read(path)
        start = max(0, int((span[0] - margin_s) * rate))
        end = min(len(samples), int((span[1] + margin_s) * rate))
        return _write(samples[start:end], rate)

    return variant


def _normalized(path: str) -> str | None:
    samples, rate = _read(path)
    peak = int(np.abs(samples.astype(np.int32)).max()) if len(samples) else 0
    if peak == 0:
        return None
    return _write(samples * (NORMALIZED_PEAK * 32767 / peak), rate)


def replay(path: str, model, engine: AudioEngine) -> None:
    span = engine._speech_span(path)
    rms = engine._get_peak_rms(path)
    print(
        f"== {os.path.basename(path)}  {engine._get_audio_duration(path) or 0:.2f}s, "
        f"peak RMS {'unknown' if rms is None else f'{rms:.6f}'}, "
        f"voiced {'unknown' if span is None else f'{span[2]:.2f}s'}"
    )
    variants: dict[str, Callable[[str], str | None]] = {
        "untouched": lambda p: p,
        f"trimmed {TRIM_MARGIN_S}s (Whispy)": _trimmed(TRIM_MARGIN_S, span),
        f"trimmed {WIDER_MARGIN_S}s": _trimmed(WIDER_MARGIN_S, span),
        "gain normalized": _normalized,
    }
    for label, make in variants.items():
        variant_path = make(path)
        if variant_path is None:
            print(f"   {label:24s} (not applicable)")
            continue
        try:
            print(f"   {label:24s} {(model.recognize(variant_path) or '').strip()!r}")
        finally:
            if variant_path != path:
                os.remove(variant_path)


def main(paths: list[str]) -> int:
    if not paths:
        print(__doc__, file=sys.stderr)
        return 2
    missing = [p for p in paths if not os.path.isfile(p)]
    if missing:
        print(f"Not a file: {', '.join(missing)} (expected WAV clips from ~/.whispy/lost/)", file=sys.stderr)
        return 2
    model = _load_model({})
    engine = AudioEngine(StateMachine())
    for path in paths:
        replay(path, model, engine)
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
