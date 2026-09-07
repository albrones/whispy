"""Does streaming segmentation cause the language to flip mid-dictation?

Reported symptom: dictating in French, part of the transcript comes back in
English. Hypothesis H1 is that this is not a language-detection failure at all
but a consequence of chunking: streaming transcribes every chunk as an
*independent* model call (`Engine._transcribe_and_inject_chunk`), so the
transducer re-detects the language on each one. With `pause_ms=600` and the
minimum-size guard of the time (`_buffered_s >= min_chunk_s`, which measured
total buffered seconds and so could never bind), an interjection like "donc" or
"en fait" reached the model as half a second of audio carrying almost no
language evidence.

That is what this script found, and the fix replaced the guard with one on
*voiced* seconds (`min_speech_s`, default 0.7). The cfg below tracks production,
so pass B now shows the short word carried into its neighbouring chunk rather
than emitted alone.

Three passes over the same French speech, so the variable is isolated:

  A. whole file    -- one recognize() over the concatenated dictation
  B. chunked       -- the engine's own SpeechSegmenter replayed over the same
                      PCM, one recognize() per chunk (what the daemon does)
  C. phrase alone  -- each source phrase on its own, to separate "short audio"
                      from "chunking" as such

Both A and B go through `AudioEngine.transcribe`, so the RMS / speech / duration
gates are identical to production.

If B flips to English where A does not, H1 holds and the fix is chunk sizing,
not a language setting -- which matters, because `language=` is a silent no-op
on this backend (onnx-asr exposes it for Whisper and Canary only).
"""

import json
import wave

from _bench import OUT_ROOT, audio_engine, duration, load_parakeet, out_dir, pick_voice, read_pcm, say, sox

OUT = out_dir("chunk-language")

# Long phrases plus the short interjections H1 accuses. `expect` is the
# French-keyword bar used by tests/test_transcription_quality.py: at least one
# hit means the clip was recognized as French rather than rendered as English.
PHRASES = [
    ("p0", "bonjour tout le monde je vais vous expliquer le problème", ["bonjour", "monde", "explique"]),
    ("p1", "donc", ["donc"]),
    ("p2", "il faut que je vérifie le rapport avant la réunion de demain", ["rapport", "réunion", "demain"]),
    ("p3", "en fait", ["fait"]),
    ("p4", "oui", ["oui"]),
    ("p5", "je pense que la transcription fonctionne plutôt bien maintenant", ["pense", "transcription", "bien"]),
    ("p6", "voilà", ["voilà", "voila"]),
]

GAP_S = "0.8"  # > pause_ms (600 ms), so the segmenter actually cuts between phrases

# Pass D: one-word chunks, the shortest thing streaming can hand the model.
N_REAL = 6
SHORT_WORDS = [
    ("oui", ["oui"]),
    ("non", ["non"]),
    ("donc", ["donc"]),
    ("voilà", ["voilà", "voila"]),
    ("bref", ["bref"]),
]


def hits(text: str, expect: list[str]) -> bool:
    low = (text or "").lower()
    return any(word in low for word in expect)


def main() -> None:
    voice = pick_voice("fr")
    print(f"voice: {voice}\n")

    parts = []
    for pid, phrase, _ in PHRASES:
        parts.append(say(phrase, OUT / f"{pid}.wav", voice))
        parts.append(sox_silence(OUT / f"{pid}_gap.wav", GAP_S))

    long_wav = OUT / "dictation.wav"
    sox(*[str(p) for p in parts], str(long_wav))
    print(f"concatenated dictation: {duration(long_wav):.2f}s\n")

    model = load_parakeet()
    eng = audio_engine()
    cfg = {"pause_ms": 600, "min_speech_s": 0.7, "max_chunk_s": 12.0, "aggressiveness": 2}
    # The engine's per-chunk discard duration -- a different threshold from the
    # segmenter's, and not something the segmenter takes.
    min_chunk_s = 0.4

    # -- Pass A: whole file --------------------------------------------------
    whole = eng.transcribe(str(long_wav), model=model, min_recording_duration=0.3) or ""
    print("=== A. whole file ===")
    print(f"  {whole!r}\n")

    # -- Pass B: the engine's segmentation, replayed -------------------------
    from whispy.core.segmentation import SpeechSegmenter

    pcm, rate = read_pcm(long_wav)
    seg = SpeechSegmenter(**cfg)
    chunks, buf = [], bytearray()
    block = 2048  # bytes per simulated capture callback
    for i in range(0, len(pcm), block):
        blk = pcm[i : i + block]
        buf += blk
        if seg.feed(bytes(blk)):
            chunks.append(bytes(buf))
            buf.clear()
            seg.reset_chunk()
    if seg.flush_tail() and buf:
        chunks.append(bytes(buf))

    print(f"=== B. chunked ({len(chunks)} chunks, as the daemon would) ===")
    chunk_rows, assembled = [], []
    for n, data in enumerate(chunks):
        path = OUT / f"chunk_{n}.wav"
        with wave.open(str(path), "wb") as w:
            w.setnchannels(1)
            w.setsampwidth(2)
            w.setframerate(rate)
            w.writeframes(data)
        secs = len(data) / (rate * 2)
        text = eng.transcribe(str(path), model=model, min_recording_duration=min_chunk_s) or ""
        chunk_rows.append({"n": n, "seconds": round(secs, 2), "text": text})
        if text:
            assembled.append(text)
        print(f"  chunk {n}  {secs:5.2f}s  {text!r}")
    print(f"\n  assembled: {' '.join(assembled)!r}\n")

    # -- Pass C: each phrase alone -------------------------------------------
    print("=== C. each phrase alone ===")
    phrase_rows = []
    for pid, phrase, expect in PHRASES:
        wav = OUT / f"{pid}.wav"
        text = eng.transcribe(str(wav), model=model, min_recording_duration=min_chunk_s) or ""
        ok = hits(text, expect)
        phrase_rows.append({"id": pid, "seconds": round(duration(wav), 2), "ref": phrase, "text": text, "fr": ok})
        print(f"  {pid}  {duration(wav):5.2f}s  fr={'Y' if ok else 'N'}  {text!r}")

    # -- Pass D: the short-chunk zone, N realizations ------------------------
    # Pass B's chunks kept the surrounding silence and never got short. The
    # daemon's discard floor is min_chunk_s=0.4, so probe that zone directly,
    # below what the new min_speech_s gate would let out as a chunk. `say` is
    # not byte-stable between runs, so a marginal result needs N realizations
    # (see the README caveats), and trimming the pad is what makes the clip as
    # short as a real chunk of one word.
    from whispy.core.segmentation import speech_duration_s

    print(f"\n=== D. short clips, {N_REAL} realizations each ===")
    short_rows = []
    for word, expect in SHORT_WORDS:
        bad = 0
        for k in range(N_REAL):
            wav = say(word, OUT / f"s_{word}_{k}.wav", voice, pad=("0.05", "0.05"))
            tight = OUT / f"s_{word}_{k}_tight.wav"
            sox(
                str(wav), str(tight), "silence", "1", "0.1", "0.5%", "reverse", "silence", "1", "0.1", "0.5%", "reverse"
            )
            secs = duration(tight)
            pcm, rate = read_pcm(tight)
            voiced = speech_duration_s(pcm, sample_rate=rate)
            text = eng.transcribe(str(tight), model=model, min_recording_duration=0.4) or ""
            # Three outcomes, not two. An empty result means a gate discarded the
            # clip -- the safe failure, and NOT a language error. Conflating it
            # with a wrong-language result would overstate the problem.
            if not text:
                outcome = "discarded"
            elif hits(text, expect):
                outcome = "ok"
            else:
                outcome = "wrong"
                bad += 1
            short_rows.append(
                {
                    "word": word,
                    "k": k,
                    "seconds": round(secs, 2),
                    "voiced_s": round(voiced, 2) if voiced is not None else None,
                    "text": text,
                    "outcome": outcome,
                }
            )
            flag = "<<" if outcome == "wrong" else "  "
            v = f"{voiced:.2f}" if voiced is not None else "  na"
            print(f"  {word:7s} #{k}  {secs:5.2f}s  voiced={v}s  {outcome:9s} {flag} {text!r}")
        print(f"  -> {word}: {bad}/{N_REAL} wrong language (discards not counted)\n")

    (OUT_ROOT / "results_chunk_language.json").write_text(
        json.dumps(
            {"whole": whole, "chunks": chunk_rows, "phrases": phrase_rows, "short": short_rows},
            indent=2,
            ensure_ascii=False,
        )
    )
    print(f"\nwrote {OUT_ROOT / 'results_chunk_language.json'}")


def sox_silence(dest, seconds):
    sox("-n", "-r", "16000", "-c", "1", "-b", "16", str(dest), "trim", "0.0", seconds)
    return dest


if __name__ == "__main__":
    main()
