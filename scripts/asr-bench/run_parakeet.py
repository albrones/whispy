"""Transcribe the corpus with the current backend. Run make_clips.py first.

Uses the engine's own `_load_model`, so this measures what the daemon actually
loads (Parakeet TDT 0.6b v3, int8 ONNX, CPUExecutionProvider) rather than a
re-declared copy of those settings.
"""

import json
import time

from _bench import OUT_ROOT, load_parakeet

manifest = json.loads((OUT_ROOT / "manifest.json").read_text())

t0 = time.perf_counter()
model = load_parakeet()
load_s = time.perf_counter() - t0

model.recognize(manifest[0]["wav"])  # warm-up: the first inference pays graph setup

rows = []
for m in manifest:
    latencies = []
    for _ in range(3):
        t = time.perf_counter()
        out = model.recognize(m["wav"])
        latencies.append(time.perf_counter() - t)
    rows.append({**m, "hyp": (out or "").strip(), "latency_s": min(latencies)})
    print(f"{m['id']:16s} {min(latencies):6.3f}s  {rows[-1]['hyp']!r}", flush=True)

(OUT_ROOT / "results_parakeet.json").write_text(json.dumps({"load_s": load_s, "rows": rows}, indent=2))
print(f"\nmodel load: {load_s:.2f}s")
