"""Shared plumbing for the ASR bench scripts.

Every script here synthesizes audio with macOS `say`, converts it to the
pipeline's 16 kHz mono int16 WAV with `sox`, and runs it through either the
current backend or the previous one. This module holds the parts they all need
so each script is only the experiment it answers.

Outputs go to a scratch directory outside the repo (override with `BENCH_OUT`),
so running a bench never dirties the working tree.
"""

import os
import subprocess
import sys
import tempfile
import wave
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
_SRC = REPO_ROOT / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

OUT_ROOT = Path(os.environ.get("BENCH_OUT", Path(tempfile.gettempdir()) / "whispy-asr-bench"))

# `say` voices worth benching. The alphabetically-first macOS voice is a legacy
# novelty one ("Albert", "Bells", "Boing") whose synthesis the model
# legitimately fails on, which measures the voice rather than the backend.
EN_VOICES = ["Samantha", "Daniel", "Alex", "Aman"]
FR_VOICES = ["Amélie", "Aurelie", "Jacques"]


def out_dir(name: str) -> Path:
    """Create and return a scratch subdirectory for one script's artifacts."""
    d = OUT_ROOT / name
    d.mkdir(parents=True, exist_ok=True)
    return d


def sox(*args, seeded: bool = False) -> None:
    """Run sox quietly. `seeded` adds -R, so synthesized noise is reproducible."""
    cmd = ["sox"]
    if seeded:
        cmd.append("-R")
    cmd += [str(a) for a in args]
    subprocess.run(cmd, check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


def installed_voices() -> set[str]:
    out = subprocess.run(["say", "-v", "?"], capture_output=True, text=True).stdout
    return {line.split()[0] for line in out.splitlines() if line.split()}


def pick_voice(locale: str) -> str:
    """First installed voice for 'en'/'fr', preferring the modern ones."""
    available = installed_voices()
    for name in EN_VOICES if locale == "en" else FR_VOICES:
        if name in available:
            return name
    raise SystemExit(f"no usable {locale} `say` voice installed")


def say(phrase: str, dest: Path, voice: str, pad: tuple[str, str] = ("0.3", "0.2")) -> Path:
    """Synthesize `phrase` to a 16 kHz mono 16-bit WAV, padded front and back."""
    aiff = dest.with_suffix(".aiff")
    subprocess.run(["say", "-v", voice, phrase, "-o", str(aiff)], check=True)
    sox(aiff, "-r", "16000", "-c", "1", "-b", "16", dest, "pad", *pad)
    aiff.unlink(missing_ok=True)
    return dest


def noise(dest: Path, synth_args: list[str], seconds: str = "2.0") -> Path:
    """Synthesize non-speech (`synth_args` is sox's synth tail, e.g. ['whitenoise','vol','0.05'])."""
    sox("-n", "-r", "16000", "-c", "1", "-b", "16", dest, "synth", seconds, *synth_args, seeded=False)
    return dest


def silence(dest: Path, seconds: str = "1.0") -> Path:
    sox("-n", "-r", "16000", "-c", "1", "-b", "16", dest, "trim", "0.0", seconds)
    return dest


def duration(path: Path) -> float:
    return float(subprocess.run(["soxi", "-D", str(path)], capture_output=True, text=True).stdout)


def read_pcm(path: Path) -> tuple[bytes, int]:
    with wave.open(str(path)) as w:
        return w.readframes(w.getnframes()), w.getframerate()


def load_parakeet(timestamps: bool = False):
    """Load the model exactly as the daemon does, via the engine's own loader."""
    from whispy.core.engine import _load_model

    model = _load_model({})
    return model.with_timestamps() if timestamps else model


def audio_engine():
    """An AudioEngine for the real `transcribe` path (gates included, no recording)."""
    from whispy.core.audio import AudioEngine
    from whispy.core.state_machine import StateMachine

    return AudioEngine(StateMachine())


def wer(reference: str, hypothesis: str) -> tuple[int, int]:
    """Word-level Levenshtein distance and reference length: (errors, n_words)."""
    import re

    def norm(s: str) -> list[str]:
        s = (s or "").lower().replace("'", " ").replace("’", " ")
        return re.sub(r"[^a-z0-9à-ÿ ]", " ", s).split()

    r, h = norm(reference), norm(hypothesis)
    d = [[0] * (len(h) + 1) for _ in range(len(r) + 1)]
    for i in range(len(r) + 1):
        d[i][0] = i
    for j in range(len(h) + 1):
        d[0][j] = j
    for i in range(1, len(r) + 1):
        for j in range(1, len(h) + 1):
            d[i][j] = min(d[i - 1][j] + 1, d[i][j - 1] + 1, d[i - 1][j - 1] + (r[i - 1] != h[j - 1]))
    return d[len(r)][len(h)], len(r)
