"""Real-model semantic transcription tests (tier: macos-real).

These run the actual `tiny` Whisper model over speech synthesized with the
macOS `say` command. They are marked ``macos`` and excluded from the default
run (slow + model download). Run them with::

    pytest -m macos tests/test_transcription_quality.py

Audio is synthesized with `say`, converted to the pipeline's 16 kHz mono WAV
with `sox`, and transcribed through the real ``AudioEngine.transcribe`` so the
credit-strip, duration guard, and ``initial_prompt`` paths are exercised.
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

# Known Whisper hallucination phrases that must never reach injection.
_HALLUCINATIONS = ["amara.org", "soustitreur", "sous-titres", "radio-canada"]


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
    # Pad leading/trailing silence so the VAD filter (vad_filter=True in
    # AudioEngine.transcribe) does not trim the onset and drop the first words.
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
def tiny_model():
    """Load the real `tiny` model once per session (CPU int8)."""
    from faster_whisper import WhisperModel

    return WhisperModel("tiny", device="cpu", compute_type="int8")


@pytest.fixture
def engine():
    """AudioEngine for the real transcribe path (no recording involved)."""
    return AudioEngine(StateMachine())


def _transcribe(engine, model, wav, language, initial_prompt=None):
    """Run the real transcribe path and apply the engine-layer cleaning."""
    raw = engine.transcribe(str(wav), model=model, language=language, initial_prompt=initial_prompt)
    return clean_text(raw)


def _assert_recognized(out: str, keywords: list[str]) -> None:
    """Assert real transcription produced meaningful text overlapping intent.

    The `tiny` model on synthetic `say` speech is lossy — it reliably produces
    *some* of the spoken words but not always all of them. So the bar is:
    non-empty output containing at least one expected keyword (case-insensitive).
    This proves speech really becomes the right words without flaking on the
    smallest model's imperfect recall.
    """
    low = (out or "").lower()
    assert low.strip(), "transcription produced no text"
    hits = [k for k in keywords if k.lower() in low]
    assert hits, f"none of {keywords} found in {out!r}"


class TestSemanticFrench:
    def test_french_phrase_keywords(self, tiny_model, engine, tmp_path):
        voice = _find_voice("fr")
        if voice is None:
            pytest.skip("no French `say` voice installed")
        wav = _synthesize("bonjour tout le monde", tmp_path / "fr.wav", voice=voice)
        out = _transcribe(engine, tiny_model, wav, "fr")
        _assert_recognized(out, ["bonjour", "monde", "tout"])


class TestSemanticEnglish:
    def test_english_phrase_keywords(self, tiny_model, engine, tmp_path):
        voice = _find_voice("en")
        wav = _synthesize("hello world this is a test", tmp_path / "en.wav", voice=voice)
        out = _transcribe(engine, tiny_model, wav, "en")
        _assert_recognized(out, ["hello", "world", "test"])


class TestCustomVocabulary:
    def test_biased_term_recognized_with_prompt(self, tiny_model, engine, tmp_path):
        # An unusual brand term; supplying it as initial_prompt biases recognition.
        voice = _find_voice("en")
        wav = _synthesize("open whispy now", tmp_path / "vocab.wav", voice=voice)
        out = (_transcribe(engine, tiny_model, wav, "en", initial_prompt="Whispy") or "").lower()
        assert "whispy" in out, f"got: {out!r}"


class TestNonSpeech:
    def test_subthreshold_clip_returns_none(self, tiny_model, engine, tmp_path):
        # A real clip, but the duration guard (raised here) must discard it.
        voice = _find_voice("en")
        wav = _synthesize("hello", tmp_path / "short.wav", voice=voice)
        raw = engine.transcribe(str(wav), model=tiny_model, language="en", min_recording_duration=100.0)
        assert raw is None

    def test_silence_yields_no_hallucination(self, tiny_model, engine, tmp_path):
        wav = _silence(tmp_path / "silence.wav", seconds=0.6)
        out = (_transcribe(engine, tiny_model, wav, "fr") or "").lower()
        for phrase in _HALLUCINATIONS:
            assert phrase not in out, f"hallucination leaked: {out!r}"
