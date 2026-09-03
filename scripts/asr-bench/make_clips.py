"""Build the bench corpus and write the manifest the other scripts read.

Covers the four things the backend swap had to be judged on: ordinary dictation
(WER), a long recording (the previous backend truncated one silently), a
sub-second chunk (it looped on those), and non-speech (both backends answer it
with something).
"""

import json

from _bench import OUT_ROOT, duration, noise, out_dir, pick_voice, say, silence, sox

OUT = out_dir("clips")

EN_PHRASES = [
    "hello world this is a test",
    "please send the report to the whole team before friday",
    "the quick brown fox jumps over the lazy dog",
    "let me know if the meeting is moved to next tuesday",
    "we should refactor the transcription engine this week",
]
FR_PHRASES = [
    "bonjour tout le monde",
    "je vais envoyer le rapport a l equipe demain matin",
]

en_voice, fr_voice = pick_voice("en"), pick_voice("fr")
manifest = []

for i, phrase in enumerate(EN_PHRASES):
    manifest.append(
        {"id": f"en_{i}", "wav": str(say(phrase, OUT / f"en_{i}.wav", en_voice)), "ref": phrase, "case": "wer"}
    )
for i, phrase in enumerate(FR_PHRASES):
    manifest.append(
        {"id": f"fr_{i}", "wav": str(say(phrase, OUT / f"fr_{i}.wav", fr_voice)), "ref": phrase, "case": "wer"}
    )

# A long recording: en_0 eight times over. The previous backend returned only
# the first sentence for this, dropping ~87% of the audio with no error.
long_wav = OUT / "long.wav"
sox(*[OUT / "en_0.wav"] * 8, long_wav)
manifest.append({"id": "long", "wav": str(long_wav), "ref": " ".join([EN_PHRASES[0]] * 8), "case": "long"})

# A sub-second chunk cut mid-word: the previous backend looped on these.
chunk = OUT / "chunk_1500ms.wav"
sox(OUT / "en_0.wav", chunk, "trim", "0", "1.5")
manifest.append({"id": "chunk_1500ms", "wav": str(chunk), "ref": "", "case": "chunk"})

# Latency ladder. Whisper's cost was flat (it padded to a 30s window); Parakeet's
# is proportional to real audio, which is what push-to-talk chunking needs.
for secs in ("0.5", "2.2"):
    d = OUT / f"lat_{secs}s.wav"
    sox(long_wav, d, "trim", "0", secs)
    manifest.append({"id": f"lat_{secs}s", "wav": str(d), "ref": "", "case": "latency"})

manifest.append({"id": "silence_1s", "wav": str(silence(OUT / "silence_1s.wav")), "ref": "", "case": "silence"})
manifest.append(
    {
        "id": "noise_1s",
        "wav": str(noise(OUT / "noise_1s.wav", ["whitenoise", "vol", "0.002"], seconds="1.0")),
        "ref": "",
        "case": "silence",
    }
)

(OUT_ROOT / "manifest.json").write_text(json.dumps(manifest, indent=2))
print(f"{len(manifest)} clips -> {OUT}")
for m in manifest:
    print(f"  {m['id']:16s} {duration(m['wav']):6.2f}s  {m['case']}")
print(f"manifest -> {OUT_ROOT / 'manifest.json'}")
