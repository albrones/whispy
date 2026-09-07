"""Does merging a short chunk with its neighbour recover the language?

`probe_chunk_language.py` established the failure: a chunk holding one isolated
short word can come back in another language ("bref" -> "Dress.", 6/6) or as an
invented English sentence ("oui" -> "We're going to be able to do it"), while the
same speech inside a longer clip transcribes correctly.

The proposed fix is to stop emitting such a chunk at all: keep buffering until it
carries enough *voiced* audio, so the short word rides along with its neighbour.
Before touching the segmenter, this checks the premise -- that context is what
fixes it -- and finds how much is needed.

Each case is transcribed through `AudioEngine.transcribe`, so the production
gates apply, and every clip is built the way the segmenter would actually cut:
speech plus the trailing `pause_ms` of silence that triggered the boundary.
"""

import json

from _bench import OUT_ROOT, audio_engine, duration, load_parakeet, out_dir, pick_voice, say, sox

OUT = out_dir("chunk-merge")
N_REAL = 5
PAUSE_S = "0.6"  # the trailing silence that triggers a boundary (pause_ms=600)

# The short word under test, and the phrase that would precede it in a dictation.
SHORT = ("oui", ["oui"])
LEAD = "il faut que je vérifie le rapport avant la réunion de demain"
# How much of the preceding phrase to prepend, in seconds. 0 = the isolated chunk.
PREPEND_S = [0.0, 0.5, 1.0, 2.0, 3.4]


def main() -> None:
    voice = pick_voice("fr")
    model = load_parakeet()
    eng = audio_engine()
    word, expect = SHORT

    gap = OUT / "gap.wav"
    sox("-n", "-r", "16000", "-c", "1", "-b", "16", str(gap), "trim", "0.0", PAUSE_S)
    lead_wav = say(LEAD, OUT / "lead.wav", voice)
    lead_s = duration(lead_wav)
    print(f"voice: {voice}   lead phrase: {lead_s:.2f}s\n")

    rows = []
    for prepend in PREPEND_S:
        wrong = 0
        for k in range(N_REAL):
            word_wav = say(word, OUT / f"w_{k}.wav", voice, pad=("0.10", "0.10"))
            case = OUT / f"case_{prepend}_{k}.wav"
            if prepend <= 0:
                # The isolated chunk exactly as the segmenter emits it.
                sox(str(word_wav), str(gap), str(case))
            else:
                # Take the LAST `prepend` seconds of the lead phrase: a merged
                # chunk carries the audio immediately before the short word.
                tail = OUT / f"tail_{prepend}_{k}.wav"
                start = max(0.0, lead_s - prepend)
                sox(str(lead_wav), str(tail), "trim", f"{start:.2f}")
                sox(str(tail), str(word_wav), str(gap), str(case))
            secs = duration(case)
            text = eng.transcribe(str(case), model=model, min_recording_duration=0.4) or ""
            low = text.lower()
            if not text:
                outcome = "discarded"
            elif any(w in low for w in expect):
                outcome = "ok"
            else:
                outcome = "wrong"
                wrong += 1
            rows.append({"prepend_s": prepend, "k": k, "seconds": round(secs, 2), "outcome": outcome, "text": text})
            print(f"  prepend={prepend:4.1f}s  #{k}  {secs:5.2f}s  {outcome:9s}  {text!r}")
        print(f"  -> prepend={prepend}s: {wrong}/{N_REAL} wrong\n")

    (OUT_ROOT / "results_chunk_merge.json").write_text(json.dumps(rows, indent=2, ensure_ascii=False))
    print(f"wrote {OUT_ROOT / 'results_chunk_merge.json'}")


if __name__ == "__main__":
    main()
