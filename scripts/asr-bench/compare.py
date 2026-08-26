"""Score the two result sets: WER, latency, and the three bug cases.

Run make_clips.py, run_parakeet.py and run_whisper.py first.
"""

import json

from _bench import OUT_ROOT, duration, wer

pk = json.loads((OUT_ROOT / "results_parakeet.json").read_text())
wh = json.loads((OUT_ROOT / "results_whisper.json").read_text())
by_id = {r["id"]: r for r in wh["rows"]}

print("== WER (phrase clips) ==")
print(f"{'clip':14s} {'parakeet':>9s} {'whisper(en)':>12s} {'whisper(auto)':>14s}")
totals = {"pk": [0, 0], "wh": [0, 0], "auto": [0, 0]}
for r in pk["rows"]:
    if r["case"] != "wer":
        continue
    w = by_id[r["id"]]
    errors = {"pk": wer(r["ref"], r["hyp"]), "wh": wer(r["ref"], w["hyp"]), "auto": wer(r["ref"], w["hyp_auto"])}
    for key, (e, n) in errors.items():
        totals[key][0] += e
        totals[key][1] += n
    n = errors["pk"][1]
    print(f"{r['id']:14s} {errors['pk'][0] / n:8.1%} {errors['wh'][0] / n:11.1%} {errors['auto'][0] / n:13.1%}")
print(f"{'TOTAL':14s} " + " ".join(f"{e / n:8.1%}" for e, n in (totals["pk"], totals["wh"], totals["auto"])))

print("\n== Latency (best of 3) ==")
print(f"{'clip':14s} {'audio':>7s} {'parakeet':>9s} {'whisper':>9s} {'speedup':>8s}")
for r in pk["rows"]:
    w = by_id[r["id"]]
    dur = duration(r["wav"])
    print(
        f"{r['id']:14s} {dur:6.2f}s {r['latency_s']:8.3f}s {w['latency_s']:8.3f}s {w['latency_s'] / r['latency_s']:7.1f}x"
    )
print(f"\nmodel load: parakeet {pk['load_s']:.2f}s | whisper {wh['load_s']:.2f}s")

print("\n== Bug cases ==")
for cid in ("long", "chunk_1500ms", "fr_1", "silence_1s", "noise_1s"):
    r = next((x for x in pk["rows"] if x["id"] == cid), None)
    if r is None:
        continue
    w = by_id[cid]
    print(f"\n{cid}  (ref: {r['ref'][:70]!r})")
    print(f"  parakeet      : {r['hyp']!r}")
    print(f"  whisper (en)  : {w['hyp']!r}")
    print(f"  whisper (auto): {w['hyp_auto']!r}")
