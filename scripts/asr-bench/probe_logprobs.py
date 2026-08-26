"""Can token confidence gate out invented short output? Measured answer: no.

Parakeet answers a clip cut mid-word with a plausible wrong phrase rather than a
truncated one ("hell" -> "Help me."). Token logprobs, exposed through
`with_timestamps()`, look like the obvious way to reject that. They are not: the
invented output scores *higher* than real one-word dictation, so any threshold
that catches the invention discards real speech first.

Kept in the repo so the next person weighing a confidence gate can re-run it in a
minute instead of re-deriving it.
"""

import numpy as np
from _bench import load_parakeet, out_dir, pick_voice, say, silence, sox

OUT = out_dir("logprobs")
model = load_parakeet(timestamps=True)
en, fr = pick_voice("en"), pick_voice("fr")

rows = []


def probe(group, label, wav):
    r = model.recognize(str(wav))
    if not r.tokens:
        print(f"  [{group}] {label:26s} -> '' (no tokens)")
        return
    lp = np.asarray(r.logprobs, dtype=float)
    rows.append({"group": group, "mean": float(lp.mean()), "min": float(lp.min())})
    print(f"  [{group}] {label:26s} mean={lp.mean():7.3f} min={lp.min():7.3f} n={lp.size:2d} -> {r.text!r}")


print("A. real speech, multi-word (must pass any gate)")
for i, phrase in enumerate(["hello world this is a test", "we should refactor the transcription engine this week"]):
    probe("A", f"en phrase {i}", say(phrase, OUT / f"a_en{i}.wav", en))
probe("A", "fr phrase", say("je vais envoyer le rapport demain matin", OUT / "a_fr.wav", fr))

print("\nB. legitimate one-word dictation (must pass)")
for word, voice in [("yes", en), ("okay", en), ("non", fr), ("stop", fr)]:
    probe("B", f"{word!r}", say(word, OUT / f"b_{word}.wav", voice))

print("\nC. mid-word cuts (what a confidence gate would need to drop)")
src = say("hello world this is a test", OUT / "c_src.wav", en)
for secs in ("0.4", "0.5", "0.6", "0.7", "1.0"):
    cut = OUT / f"c_cut{secs}.wav"
    sox(src, cut, "trim", "0", secs)
    probe("C", f"cut at {secs}s", cut)

print("\nD. near-silence fillers (already handled by the RMS gate)")
for secs in ("0.6", "1.0", "1.5", "2.0"):
    probe("D", f"silence {secs}s", silence(OUT / f"d_sil{secs}.wav", secs))

print("\n== separability ==")
for metric in ("mean", "min"):
    keep = [r[metric] for r in rows if r["group"] in "AB"]
    drop = [r[metric] for r in rows if r["group"] in "CD"]
    if not keep or not drop:
        continue
    verdict = "SEPARABLE" if min(keep) > max(drop) else "OVERLAP — a confidence gate cannot work"
    print(f"  {metric:5s}: keep(A,B) worst={min(keep):7.3f}  drop(C,D) best={max(drop):7.3f}  -> {verdict}")
