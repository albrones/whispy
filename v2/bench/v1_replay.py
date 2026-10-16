"""Transcribe WAV clips with Whispy V1 exactly as its daemon does, for the V2 bench.

The bench (`cargo run --release --bin banc`) runs this with V1's own venv:
one WAV path per stdin line, one `path<TAB>seconds<TAB>text` line out, where
seconds is the time of `AudioEngine.transcribe` alone (model already loaded).

Read-only toward the installed V1: a lost clip is not copied into
~/.whispy/lost/ (that would rotate the very clips under test), stale-recording
cleanup is skipped, and the caller points TMPDIR at a private directory and
sets HF_HUB_OFFLINE=1 so nothing leaves the Mac.
"""

import os
import sys
import time

REPO = os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
sys.path.insert(0, os.path.join(REPO, "src"))

from whispy.core import audio  # noqa: E402

audio._keep_lost_clip = lambda _path: "not kept (V2 bench replay)"
audio._cleanup_stale_recordings = lambda: None

from whispy.core.engine import _load_model  # noqa: E402
from whispy.core.state_machine import StateMachine  # noqa: E402


def main() -> int:
    model = _load_model({})
    engine = audio.AudioEngine(StateMachine())
    for line in sys.stdin:
        path = line.strip()
        if not path:
            continue
        started = time.perf_counter()
        text = engine.transcribe(path, model) or ""
        elapsed = time.perf_counter() - started
        flat = " ".join(text.split())
        print(f"{path}\t{elapsed:.4f}\t{flat}", flush=True)
    return 0


if __name__ == "__main__":
    sys.exit(main())
