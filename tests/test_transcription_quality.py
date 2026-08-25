"""Real-model semantic transcription tests (tier: macos-real).

These run the actual Parakeet model over speech synthesized with the macOS
`say` command. They are marked ``macos`` and excluded from the default run
(slow + 639 MB model download). Run them with::

    pytest -m macos tests/test_transcription_quality.py

Audio is synthesized with `say`, converted to the pipeline's 16 kHz mono WAV
with `sox`, and transcribed through the real ``AudioEngine.transcribe``.

No test passes a language: the model detects it. That is the point of several
of these — under the previous backend a forced language transcribed the *other*
language into the forced one instead of recognizing it.
"""

import shutil
import subprocess
import sys
from pathlib import Path

import pytest

_src = Path(__file__).parent.parent / "src"
if str(_src) not in sys.path:
    sys.path.insert(0, str(_src))

pytestmark = pytest.mark.macos

# Skip the whole module unless the synthesis toolchain is present.
if shutil.which("say") is None or shutil.which("sox") is None:
    pytest.skip("requires macOS `say` and `sox`", allow_module_level=True)

from whispy.core.audio import AudioEngine  # noqa: E402
from whispy.core.state_machine import StateMachine  # noqa: E402
from whispy.core.text_cleaner import clean_text  # noqa: E402


def _find_voice(locale_prefix: str) -> str | None:
    """Return a `say` voice name whose locale matches (e.g. 'fr', 'en'), or None."""
    out = subprocess.run(["say", "-v", "?"], capture_output=True, text=True).stdout
    for line in out.splitlines():
        # Format: "Name           locale    # sample text"
        parts = line.split()
        if len(parts) >= 2 and parts[1].lower().startswith(locale_prefix.lower()):
            return parts[0]
    return None


def _synthesize(phrase: str, wav_path: Path, voice: str | None = None) -> Path:
    """Synthesize `phrase` to a 16 kHz mono WAV via `say` + `sox`."""
    aiff = wav_path.with_suffix(".aiff")
    say_cmd = ["say"]
    if voice:
        say_cmd += ["-v", voice]
    say_cmd += [phrase, "-o", str(aiff)]
    subprocess.run(say_cmd, check=True)
    # Pad leading/trailing silence so a hard cut never clips the onset.
    subprocess.run(
        ["sox", str(aiff), "-r", "16000", "-c", "1", str(wav_path), "pad", "0.3", "0.2"],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    aiff.unlink(missing_ok=True)
    return wav_path


def _silence(wav_path: Path, seconds: float = 0.5) -> Path:
    """Generate a silent 16 kHz mono WAV via `sox`."""
    subprocess.run(
        ["sox", "-n", "-r", "16000", "-c", "1", str(wav_path), "trim", "0.0", str(seconds)],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return wav_path


@pytest.fixture(scope="session")
def asr_model():
    """Load the real Parakeet model once per session (int8, CPU)."""
    from whispy.core.engine import _load_model

    return _load_model({})


@pytest.fixture
def engine():
    """AudioEngine for the real transcribe path (no recording involved)."""
    return AudioEngine(StateMachine())


def _transcribe(engine, model, wav, vocabulary=None):
    """Run the real transcribe path and apply the engine-layer cleaning."""
    raw = engine.transcribe(str(wav), model=model)
    return clean_text(raw, vocabulary)


def _concat(parts, dest):
    """Join WAVs into one clip (sox), for the code-switching and length tests."""
    subprocess.run(
        ["sox", *[str(p) for p in parts], str(dest)],
        check=True,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )
    return dest


def _assert_recognized(out: str, keywords: list[str]) -> None:
    """Assert real transcription produced meaningful text overlapping intent.

    Synthetic `say` speech is not real dictation, so the bar is: non-empty
    output containing at least one expected keyword (case-insensitive). This
    proves speech really becomes the right words without flaking on the
    imperfect recall of TTS audio.
    """
    low = (out or "").lower()
    assert low.strip(), "transcription produced no text"
    hits = [k for k in keywords if k.lower() in low]
    assert hits, f"none of {keywords} found in {out!r}"


class TestSemanticFrench:
    def test_french_phrase_keywords(self, asr_model, engine, tmp_path):
        voice = _find_voice("fr")
        if voice is None:
            pytest.skip("no French `say` voice installed")
        wav = _synthesize("bonjour tout le monde", tmp_path / "fr.wav", voice=voice)
        out = _transcribe(engine, asr_model, wav)
        _assert_recognized(out, ["bonjour", "monde", "tout"])


class TestSemanticEnglish:
    def test_english_phrase_keywords(self, asr_model, engine, tmp_path):
        voice = _find_voice("en")
        wav = _synthesize("hello world this is a test", tmp_path / "en.wav", voice=voice)
        out = _transcribe(engine, asr_model, wav)
        _assert_recognized(out, ["hello", "world", "test"])


class TestCodeSwitching:
    def test_a_single_clip_with_both_languages_is_not_forced_into_one(self, asr_model, engine, tmp_path):
        """French then English in one clip: both halves must be recognized.

        The previous backend, given a forced language, translated the other
        half instead of recognizing it ("the test is done" -> "le test est
        fait"). Nothing configures a language now.
        """
        fr_voice = _find_voice("fr")
        if fr_voice is None:
            pytest.skip("no French `say` voice installed")
        fr = _synthesize("bonjour tout le monde", tmp_path / "cs_fr.wav", voice=fr_voice)
        en = _synthesize("hello world this is a test", tmp_path / "cs_en.wav", voice=_find_voice("en"))
        wav = _concat([fr, en], tmp_path / "cs.wav")

        out = (_transcribe(engine, asr_model, wav) or "").lower()
        assert any(k in out for k in ("bonjour", "monde")), f"French half lost: {out!r}"
        assert any(k in out for k in ("hello", "world", "test")), f"English half lost: {out!r}"


class TestCustomVocabulary:
    def test_near_miss_term_corrected(self, asr_model, engine, tmp_path):
        """A term the model renders *close* to the target is corrected.

        Deliberately not asserted on real audio: post-hoc correction only fixes
        near misses, and synthetic `say` speech is lossy enough that the model
        may render a brand term far from the target ("open whispy now" came back
        as "oh we'll see no" here). Asserting recovery on real audio would be
        asserting something the design explicitly does not promise, so the
        correction itself is verified deterministically in
        `test_text_cleaning.py`; this test only pins the real-audio behaviour
        that matters — cleaning never makes the output *worse*.
        """
        voice = _find_voice("en")
        wav = _synthesize("open whispy now", tmp_path / "vocab.wav", voice=voice)
        plain = _transcribe(engine, asr_model, wav) or ""
        biased = _transcribe(engine, asr_model, wav, vocabulary=["Whispy"]) or ""
        assert len(biased.split()) == len(plain.split()), f"vocabulary changed the shape: {plain!r} -> {biased!r}"

    def test_no_vocabulary_term_is_introduced_into_unrelated_speech(self, asr_model, engine, tmp_path):
        """The failure mode that got decoder prompting removed must not recur."""
        voice = _find_voice("en")
        wav = _synthesize("hello world this is a test", tmp_path / "novocab.wav", voice=voice)
        out = (_transcribe(engine, asr_model, wav, vocabulary=["Whispy", "Parakeet"]) or "").lower()
        assert "whispy" not in out, f"vocabulary leaked: {out!r}"
        assert "parakeet" not in out, f"vocabulary leaked: {out!r}"


class TestNonSpeech:
    def test_subthreshold_clip_returns_none(self, asr_model, engine, tmp_path):
        # A real clip, but the duration guard (raised here) must discard it.
        voice = _find_voice("en")
        wav = _synthesize("hello", tmp_path / "short.wav", voice=voice)
        raw = engine.transcribe(str(wav), model=asr_model, min_recording_duration=100.0)
        assert raw is None

    def test_silence_yields_nothing_through_the_transcribe_path(self, asr_model, engine, tmp_path):
        """Silence never becomes text — but the *model* is not what guarantees it.

        Deliberately does NOT assert that `recognize()` returns "" on silence:
        it often does not. Measured here, pure digital silence produced "Yeah."
        at 0.6s/1.0s/1.5s and "Thank you." at 2.0s, non-monotonically. The
        guarantee comes from the RMS gate in `AudioEngine.transcribe`, which is
        what this asserts and what `TestSilenceGate` covers in depth.
        """
        wav = _silence(tmp_path / "silence.wav", seconds=0.6)
        assert engine.transcribe(str(wav), model=asr_model) is None


class TestSilenceGate:
    """Near-silent audio must never reach the model.

    Parakeet does not hallucinate the way Whisper did, but it *does* invent
    short conversational fillers on near-silence — "Yeah.", "Okay.", "Mm-hmm.",
    "No.", "Thank you." — which would otherwise be typed into the active field.
    """

    @pytest.mark.parametrize("seconds", [0.6, 1.0, 1.5, 2.0])
    def test_pure_silence_is_never_transcribed(self, asr_model, engine, tmp_path, seconds):
        wav = _silence(tmp_path / f"sil_{seconds}.wav", seconds=seconds)
        assert engine.transcribe(str(wav), model=asr_model) is None

    @pytest.mark.parametrize("amplitude", ["0.0005", "0.002"])
    def test_quiet_room_noise_is_never_transcribed(self, asr_model, engine, tmp_path, amplitude):
        """A real microphone never reaches digital zero — this is the live case."""
        wav = tmp_path / f"noise_{amplitude}.wav"
        subprocess.run(
            [
                "sox",
                "-n",
                "-r",
                "16000",
                "-c",
                "1",
                "-b",
                "16",
                str(wav),
                "synth",
                "1.0",
                "whitenoise",
                "vol",
                amplitude,
            ],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        assert engine.transcribe(str(wav), model=asr_model) is None

    def test_real_speech_clears_the_gate_by_a_wide_margin(self, asr_model, engine, tmp_path):
        """The gate must not be anywhere near real dictation levels."""
        from whispy.core.audio import SILENCE_RMS_THRESHOLD

        voice = _find_voice("en")
        wav = _synthesize("hello world this is a test", tmp_path / "loud.wav", voice=voice)
        rms = engine._get_audio_rms(str(wav))
        assert rms is not None
        assert rms > SILENCE_RMS_THRESHOLD * 5, f"speech RMS {rms:.6f} is uncomfortably close to the gate"
        assert engine.transcribe(str(wav), model=asr_model) is not None


class TestLongAudio:
    def test_a_long_recording_is_not_silently_truncated(self, asr_model, engine, tmp_path):
        """The previous backend truncated a 22s clip to its first sentence."""
        voice = _find_voice("en")
        one = _synthesize("hello world this is a test", tmp_path / "unit.wav", voice=voice)
        wav = _concat([one] * 8, tmp_path / "long.wav")

        out = (_transcribe(engine, asr_model, wav) or "").lower()
        assert out.count("hello") >= 4, f"long recording truncated: {out!r}"


class TestShortChunks:
    def test_a_short_chunk_does_not_degenerate(self, asr_model, engine, tmp_path):
        """Whisper looped on ~1.5s chunks, injecting a word repeated 100x."""
        voice = _find_voice("en")
        full = _synthesize("hello world this is a test", tmp_path / "full.wav", voice=voice)
        chunk = tmp_path / "chunk.wav"
        subprocess.run(
            ["sox", str(full), str(chunk), "trim", "0", "1.5"],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )

        out = (_transcribe(engine, asr_model, chunk) or "").lower()
        words = out.split()
        if words:
            most_repeated = max(words.count(w) for w in set(words))
            assert most_repeated <= 3, f"degenerate repetition: {out!r}"
