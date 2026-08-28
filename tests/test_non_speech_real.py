"""Non-speech never reaches the model — against the real model, on every platform.

Tier: both real-seam tiers. This module carries `macos` and `linux` markers, so
`pytest -m macos` and `pytest -m linux` each run it and the default run skips it.
The guarantee is platform-neutral, so the tests are too.

Clips are synthesized with numpy rather than an external tool. That is not
incidental: it removes the only reason this module used to need `sox` (and the
CI job used to install it), it makes the audio byte-identical on both platforms
and reproducible from a seed, and it lets each clip state the RMS it is aiming
for instead of trusting a `vol` multiplier to land there. Every level below was
measured to sit above `SILENCE_RMS_THRESHOLD` and below `MIN_SPEECH_DURATION_S`
of voiced audio — that band is exactly what these tests are about.

What it guards: a clip must clear the duration guard, the RMS gate *and* the
speech gate before the model sees it. Parakeet answers non-speech with short
conversational fillers ("Yeah.", "Okay.", "Mm-hmm.", "Ha ha ha."), and those
would be typed into whatever the user had focused.
"""

import sys
import wave
from pathlib import Path

import numpy as np
import pytest

_src = Path(__file__).parent.parent / "src"
if str(_src) not in sys.path:
    sys.path.insert(0, str(_src))

pytestmark = [pytest.mark.macos, pytest.mark.linux]

from whispy.core.audio import MIN_SPEECH_DURATION_S, SAMPLE_RATE, SILENCE_RMS_THRESHOLD  # noqa: E402
from whispy.core.segmentation import speech_duration_s  # noqa: E402

FIXTURES = Path(__file__).parent / "fixtures" / "audio"


def _write(path: Path, samples: np.ndarray) -> Path:
    """Write float samples as the pipeline's format: 16 kHz mono 16-bit PCM."""
    with wave.open(str(path), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SAMPLE_RATE)
        w.writeframes(np.clip(samples, -32768, 32767).astype("<i2").tobytes())
    return path


def _noise(path: Path, kind: str, seconds: float, target_rms: float, seed: int = 1) -> Path:
    """Synthesize non-speech of a given spectrum, scaled to an exact normalized RMS.

    Seeded: the model answers only a small fraction of noise realizations, so an
    unseeded draw would make these tests a coin flip that fails on someone
    else's machine rather than a regression check.
    """
    rng = np.random.default_rng(seed)
    n = int(SAMPLE_RATE * seconds)

    if kind == "white":
        sig = rng.standard_normal(n)
    elif kind == "brown":
        sig = np.cumsum(rng.standard_normal(n))
    elif kind == "hum":  # 50 Hz mains
        sig = np.sin(2 * np.pi * 50 * np.arange(n) / SAMPLE_RATE)
    elif kind in ("pink", "fan"):
        # Shape white noise in the frequency domain: 1/sqrt(f) for pink, plus a
        # hard cut above 500 Hz for the fan-like rumble.
        spectrum = np.fft.rfft(rng.standard_normal(n))
        freqs = np.fft.rfftfreq(n, 1 / SAMPLE_RATE)
        shape = np.ones_like(freqs)
        shape[1:] = 1 / np.sqrt(freqs[1:])
        if kind == "fan":
            shape[freqs > 500] = 0.0
        sig = np.fft.irfft(spectrum * shape, n)
    else:  # pragma: no cover - guards a typo in a parametrize list
        raise ValueError(f"unknown noise kind {kind!r}")

    sig = sig - sig.mean()
    sig = sig / np.sqrt(np.mean(sig**2)) * (target_rms * 32768.0)
    return _write(path, sig)


def _silence(path: Path, seconds: float) -> Path:
    return _write(path, np.zeros(int(SAMPLE_RATE * seconds)))


def _voiced_seconds(path: Path) -> float:
    with wave.open(str(path)) as w:
        return speech_duration_s(w.readframes(w.getnframes()), sample_rate=w.getframerate())


class TestSilenceIsNeverTranscribed:
    """The RMS gate's territory: near-silence."""

    @pytest.mark.parametrize("seconds", [0.6, 1.0, 1.5, 2.0])
    def test_pure_silence(self, asr_model, real_audio_engine, tmp_path, seconds):
        """Parameterized over duration: the model's invented output for silence
        varies non-monotonically with it ("Yeah." at 0.6/1.0/1.5s, "Thank you."
        at 2.0s), so one duration proves nothing."""
        wav = _silence(tmp_path / f"sil_{seconds}.wav", seconds)
        assert real_audio_engine.transcribe(str(wav), model=asr_model) is None

    @pytest.mark.parametrize("rms", [0.0005, 0.002])
    def test_quiet_room_noise(self, asr_model, real_audio_engine, tmp_path, rms):
        """The live case — a real microphone never reaches digital zero."""
        wav = _noise(tmp_path / f"quiet_{rms}.wav", "white", 1.0, rms)
        assert real_audio_engine._get_audio_rms(str(wav)) < SILENCE_RMS_THRESHOLD
        assert real_audio_engine.transcribe(str(wav), model=asr_model) is None


class TestLoudNonSpeechIsNeverTranscribed:
    """The speech gate's territory: non-speech the RMS gate cannot catch."""

    @pytest.mark.parametrize(
        "kind,seconds,rms",
        [
            ("white", 2.0, 0.016),
            ("brown", 2.0, 0.017),
            ("pink", 2.0, 0.010),
            ("hum", 2.0, 0.035),
            ("fan", 2.0, 0.013),
            # A long hold in a noisy room: more frames, more chances to look voiced.
            ("white", 8.0, 0.016),
        ],
    )
    def test_loud_non_speech(self, asr_model, real_audio_engine, tmp_path, kind, seconds, rms):
        wav = _noise(tmp_path / f"loud_{kind}_{seconds}.wav", kind, seconds, rms)

        measured = real_audio_engine._get_audio_rms(str(wav))
        assert measured > SILENCE_RMS_THRESHOLD, f"{kind} no longer clears the RMS gate (RMS {measured})"
        assert _voiced_seconds(wav) < MIN_SPEECH_DURATION_S, f"{kind} now reads as voiced"
        assert real_audio_engine.transcribe(str(wav), model=asr_model) is None


class TestRealSpeechSurvivesBothGates:
    """The counterweight: every guard above must leave recorded speech alone.

    Uses the committed fixtures rather than synthesized speech — a gate that
    passes TTS but eats a real recording would be the failure that matters, and
    the macOS-only `say` cannot produce the same assertion on both platforms.
    """

    @pytest.mark.parametrize("fixture", ["en_speech.wav", "fr_speech.wav"])
    def test_committed_speech_is_transcribed(self, asr_model, real_audio_engine, fixture):
        out = real_audio_engine.transcribe(str(FIXTURES / fixture), model=asr_model)
        assert out and out.strip(), f"{fixture} was discarded by a gate or returned nothing"

    def test_committed_silence_is_discarded(self, asr_model, real_audio_engine):
        assert real_audio_engine.transcribe(str(FIXTURES / "silence.wav"), model=asr_model) is None

    def test_speech_clears_the_speech_gate_by_a_wide_margin(self):
        """Guards against a future threshold change creeping up into real speech.

        No model needed — this measures the gate's input, not its output.
        """
        voiced = _voiced_seconds(FIXTURES / "en_speech.wav")
        assert voiced is not None
        assert voiced > MIN_SPEECH_DURATION_S * 3, f"recorded speech carries only {voiced:.2f}s of voiced frames"
