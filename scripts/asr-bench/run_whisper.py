"""Transcribe the corpus with the previous backend, for comparison.

Needs `faster-whisper`, which the project no longer depends on. Install it into a
throwaway venv rather than the project one (see README.md), then run this with
that interpreter. Deliberately does not import `_bench`: this script must run
under an interpreter that has no Whispy dependencies at all.

Reproduces the pre-migration defaults from config.py at 23cf918^: model_size
"small", language "en", beam_size 1, device cpu, compute_type int8. A second pass
with language=None keeps the comparison honest on the non-English clips, since a
forced language is the setting that made Whisper translate rather than recognize.
"""

import json
import os
import tempfile
import time
from pathlib import Path

from faster_whisper import WhisperModel

OUT_ROOT = Path(os.environ.get("BENCH_OUT", Path(tempfile.gettempdir()) / "whispy-asr-bench"))
manifest = json.loads((OUT_ROOT / "manifest.json").read_text())

t0 = time.perf_counter()
model = WhisperModel("small", device="cpu", compute_type="int8")
load_s = time.perf_counter() - t0


def run(wav, language):
    segments, _info = model.transcribe(wav, beam_size=1, language=language)
    return " ".join(s.text for s in segments).strip()


run(manifest[0]["wav"], "en")  # warm-up

rows = []
for m in manifest:
    latencies = []
    for _ in range(3):
        t = time.perf_counter()
        out = run(m["wav"], "en")
        latencies.append(time.perf_counter() - t)
    rows.append({**m, "hyp": out, "hyp_auto": run(m["wav"], None), "latency_s": min(latencies)})
    print(f"{m['id']:16s} {min(latencies):6.3f}s  forced-en={out!r}  auto={rows[-1]['hyp_auto']!r}", flush=True)

(OUT_ROOT / "results_whisper.json").write_text(json.dumps({"load_s": load_s, "rows": rows}, indent=2))
print(f"\nmodel load: {load_s:.2f}s")
