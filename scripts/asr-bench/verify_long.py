"""Is the previous backend's long-clip truncation real, or a mis-consumed generator?

`WhisperModel.transcribe` returns a lazy segment generator, so "only one sentence
came back" could just as easily be a bug in the caller. This prints every segment
with its timestamps under four decoder configurations. All four return a single
segment spanning the whole clip, which is what makes the truncation the backend's.

Needs `faster-whisper` — see README.md. Run make_clips.py first.
"""

import json
import os
import tempfile
from pathlib import Path

from faster_whisper import WhisperModel

OUT_ROOT = Path(os.environ.get("BENCH_OUT", Path(tempfile.gettempdir()) / "whispy-asr-bench"))
manifest = json.loads((OUT_ROOT / "manifest.json").read_text())
wav = next(m["wav"] for m in manifest if m["id"] == "long")

model = WhisperModel("small", device="cpu", compute_type="int8")

CONFIGS = [
    ("forced-en, beam=1 (pre-migration defaults)", {"language": "en", "beam_size": 1}),
    ("auto language, beam=5", {"beam_size": 5}),
    ("forced-en, vad_filter=True", {"language": "en", "beam_size": 1, "vad_filter": True}),
    (
        "forced-en, condition_on_previous_text=False",
        {"language": "en", "beam_size": 1, "condition_on_previous_text": False},
    ),
]
for label, kwargs in CONFIGS:
    segments, info = model.transcribe(wav, **kwargs)
    segs = list(segments)
    print(f"\n--- {label}: {len(segs)} segment(s), audio duration {info.duration:.2f}s")
    for s in segs:
        print(f"    [{s.start:6.2f} -> {s.end:6.2f}] {s.text.strip()!r}")
