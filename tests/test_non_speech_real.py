"""Non-speech never reaches the model — against the real model, on every platform.

Tier: both real-seam tiers. This module carries `macos` and `linux` markers, so
`pytest -m macos` and `pytest -m linux` each run it and the default run skips it.
That is deliberate: the guarantee it pins is platform-neutral, but it was only
ever exercised on macOS because it used to live in `test_transcription_quality.py`,
whose synthesis toolchain (`say`) is macOS-only. Nothing here needs `say` — the
clips are synthesized with `sox`, which exists on both platforms — so nothing
justified leaving Linux uncovered.

What it guards: a clip must clear the duration guard, the RMS gate *and* the
speech gate before the model sees it. Parakeet answers non-speech with short
conversational fillers ("Yeah.", "Okay.", "Mm-hmm.", "Ha ha ha."), and those
would be typed into whatever the user had focused.
"""

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

_src = Path(__file__).parent.parent / "src"
if str(_src) not in sys.path:
    sys.path.insert(0, str(_src))

pytestmark = [pytest.mark.macos, pytest.mark.linux]

if shutil.which("sox") is None:
    pytest.skip("requires `sox`", allow_module_level=True)

from whispy.core.audio import MIN_SPEECH_DURATION_S, SILENCE_RMS_THRESHOLD  # noqa: E402


def _sox(*args, seeded=False):
    cmd = ["sox"] + (["-R"] if seeded else []) + [str(a) for a in args]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def _silence(dest: Path, seconds: float) -> Path:
    _sox("-n", "-r", "16000", "-c", "1", "-b", "16", dest, "trim", "0.0", str(seconds))
    return dest


def _noise(dest: Path, synth_args: list[str], seeded=True) -> Path:
    # Seeded by default: `sox` draws a fresh realization per call, and the model
    # answers only a small fraction of them, so an unseeded draw turns a
    # regression test into a coin flip that fails on someone else's machine.
    _sox("-n", "-r", "16000", "-c", "1", "-b", "16", dest, "synth", *synth_args, seeded=seeded)
    return dest


class TestSilenceIsNeverTranscribed:
    """The RMS gate's territory: near-silence."""

    @pytest.mark.parametrize("seconds", [0.6, 1.0, 1.5, 2.0])
    def test_pure_silence(self, asr_model, real_audio_engine, tmp_path, seconds):
        """Parameterized over duration: the model's invented output for silence
        varies non-monotonically with it ("Yeah." at 0.6/1.0/1.5s, "Thank you."
        at 2.0s), so one duration proves nothing."""
        wav = _silence(tmp_path / f"sil_{seconds}.wav", seconds)
        assert real_audio_engine.transcribe(str(wav), model=asr_model) is None

    @pytest.mark.parametrize("amplitude", ["0.0005", "0.002"])
    def test_quiet_room_noise(self, asr_model, real_audio_engine, tmp_path, amplitude):
        """The live case — a real microphone never reaches digital zero."""
        wav = _noise(tmp_path / f"quiet_{amplitude}.wav", ["1.0", "whitenoise", "vol", amplitude])
        assert real_audio_engine.transcribe(str(wav), model=asr_model) is None


class TestLoudNonSpeechIsNeverTranscribed:
    """The speech gate's territory: non-speech the RMS gate cannot catch."""

    @pytest.mark.parametrize(
        "label,synth",
        [
            ("whitenoise", ["2.0", "whitenoise", "vol", "0.05"]),
            ("brownnoise", ["2.0", "brownnoise", "vol", "0.03"]),
            ("mains hum", ["2.0", "sine", "50", "vol", "0.05"]),
            ("fan", ["2.0", "pinknoise", "lowpass", "500", "vol", "0.08"]),
            # A long hold in a noisy room: more frames, more chances to look voiced.
            ("long whitenoise", ["8.0", "whitenoise", "vol", "0.05"]),
        ],
    )
    def test_loud_non_speech(self, asr_model, real_audio_engine, tmp_path, label, synth):
        wav = _noise(tmp_path / f"loud_{label.replace(' ', '_')}.wav", synth)
        rms = real_audio_engine._get_audio_rms(str(wav))
        assert rms is not None and rms > SILENCE_RMS_THRESHOLD, f"{label} no longer clears the RMS gate (RMS {rms})"
        assert real_audio_engine.transcribe(str(wav), model=asr_model) is None


class TestRealSpeechSurvivesBothGates:
    """The counterweight: every guard above must leave recorded speech alone.

    Uses the committed fixtures rather than synthesized speech, so this is the
    same assertion on both platforms — `say` is macOS-only, and a gate that
    passes TTS but eats a real recording would be the failure that matters.
    """

    @pytest.mark.parametrize("fixture", ["en_speech.wav", "fr_speech.wav"])
    def test_committed_speech_is_transcribed(self, asr_model, real_audio_engine, fixture):
        wav = Path(__file__).parent / "fixtures" / "audio" / fixture
        out = real_audio_engine.transcribe(str(wav), model=asr_model)
        assert out and out.strip(), f"{fixture} was discarded by a gate or returned nothing"

    def test_committed_silence_is_discarded(self, asr_model, real_audio_engine):
        wav = Path(__file__).parent / "fixtures" / "audio" / "silence.wav"
        assert real_audio_engine.transcribe(str(wav), model=asr_model) is None

    def test_speech_clears_the_speech_gate_by_a_wide_margin(self, real_audio_engine):
        """Guards against a future threshold change creeping up into real speech.

        No model needed — this measures the gate's input, not its output.
        """
        import wave

        from whispy.core.segmentation import speech_duration_s

        wav = Path(__file__).parent / "fixtures" / "audio" / "en_speech.wav"
        with wave.open(str(wav)) as w:
            voiced = speech_duration_s(w.readframes(w.getnframes()), sample_rate=w.getframerate())
        assert voiced is not None
        assert voiced > MIN_SPEECH_DURATION_S * 3, f"recorded speech carries only {voiced:.2f}s of voiced frames"
