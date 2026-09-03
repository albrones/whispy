"""Why the speech gate measures voiced seconds and not a voiced/silent ratio.

A ratio looks like the obvious metric until you try the realistic case: hold the
trigger, think, say one word, release. That clip is ~6% voiced frames — the same
as steady room noise — so a ratio gate would discard it. Voiced *duration* does
not care how long the key was held.

Prints both metrics over the two populations, so the choice is checkable rather
than asserted. Also sweeps noise level past speech level to find where webrtcvad
stops discriminating at all — the gate's documented ceiling.
"""

from _bench import audio_engine, noise, out_dir, pick_voice, read_pcm, say, silence

from whispy.core.audio import MIN_SPEECH_DURATION_S
from whispy.core.segmentation import speech_duration_s

OUT = out_dir("vadsec")
engine = audio_engine()
en, fr = pick_voice("en"), pick_voice("fr")


def measure(path, agg=2):
    pcm, rate = read_pcm(path)
    seconds = speech_duration_s(pcm, sample_rate=rate, aggressiveness=agg)
    frames = len(pcm) // (rate * 30 // 1000 * 2)
    return seconds, (seconds / (frames * 0.03) if frames else 0.0)


keep, drop = [], []

print("== KEEP: one-word dictation, tight padding ==")
for word, voice in [("yes", en), ("okay", en), ("non", fr), ("stop", fr)]:
    p = say(word, OUT / f"k_{word}.wav", voice, pad=("0.05", "0.05"))
    s, r = measure(p)
    keep.append((word, s, r))
    print(f"  {word:6s} voiced={s:.2f}s ratio={r:.2f}")

print("\n== KEEP: one word inside a long hold (the case a ratio gets wrong) ==")
for pad in (("2.0", "3.0"), ("4.0", "6.0")):
    p = say("okay", OUT / f"k_buried_{pad[0]}.wav", en, pad=pad)
    s, r = measure(p)
    keep.append((f"buried+{pad[0]}s", s, r))
    print(f"  'okay' padded to {pad}: voiced={s:.2f}s ratio={r:.2f}")

print("\n== KEEP: ordinary phrases ==")
for phrase, voice, name in [
    ("hello world this is a test", en, "p_en"),
    ("je vais envoyer le rapport demain matin", fr, "p_fr"),
]:
    p = say(phrase, OUT / f"{name}.wav", voice)
    s, r = measure(p)
    keep.append((name, s, r))
    print(f"  {name:6s} voiced={s:.2f}s ratio={r:.2f}")

print("\n== DROP: loud non-speech, 25 realizations per type ==")
TYPES = {
    "whitenoise": ["whitenoise", "vol", "0.05"],
    "brownnoise": ["brownnoise", "vol", "0.03"],
    "pinknoise": ["pinknoise", "vol", "0.05"],
    "fan": ["pinknoise", "lowpass", "500", "vol", "0.08"],
}
for label, synth in TYPES.items():
    worst_s, worst_r = 0.0, 0.0
    for i in range(25):
        p = noise(OUT / f"d_{label}_{i}.wav", synth)
        s, r = measure(p)
        drop.append((label, s, r))
        worst_s, worst_r = max(worst_s, s), max(worst_r, r)
    print(f"  {label:12s} worst voiced={worst_s:.2f}s  worst ratio={worst_r:.2f}")
# A long hold in a noisy room, and digital silence, belong to the same population.
for extra, path in [
    ("whitenoise 8s", noise(OUT / "d_long.wav", ["whitenoise", "vol", "0.05"], seconds="8.0")),
    ("silence", silence(OUT / "d_silence.wav", "2.0")),
]:
    s, r = measure(path)
    drop.append((extra, s, r))
    print(f"  {extra:12s} voiced={s:.2f}s ratio={r:.2f}")

print(f"\n== separability (gate is {MIN_SPEECH_DURATION_S}s) ==")
# A gate needs room for audio this corpus does not contain -- a quieter speaker, a
# further mic, a noisier room. Ordering the two populations correctly on one draw
# is not enough; anything under 2x has flipped to overlap on another draw here.
MIN_USABLE_MARGIN = 2.0
for name, idx in (("voiced seconds", 1), ("voiced ratio", 2)):
    k, d = min(x[idx] for x in keep), max(x[idx] for x in drop)
    margin = k / d if d else float("inf")
    if k <= d:
        verdict = "OVERLAP — unusable"
    elif margin < MIN_USABLE_MARGIN:
        verdict = f"ordered but only {margin:.1f}x — too tight to gate on"
    else:
        verdict = f"SEPARABLE, {margin:.1f}x margin"
    print(f"  {name:15s} KEEP min={k:.2f}  DROP max={d:.2f}  -> {verdict}")

print("\n== ceiling: where webrtcvad stops telling noise from speech ==")
for vol in ("0.05", "0.1", "0.2", "0.4"):
    p = noise(OUT / f"lvl_{vol}.wav", ["whitenoise", "vol", vol])
    s, _ = measure(p)
    rms = engine._get_audio_rms(str(p))
    print(
        f"  whitenoise vol={vol:5s} rms={rms:.4f} voiced={s:.2f}s "
        f"{'blocked by gate' if s < MIN_SPEECH_DURATION_S else 'PASSES gate (model must handle it)'}"
    )
