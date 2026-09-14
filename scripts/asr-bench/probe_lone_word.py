"""Does silence around an isolated short word make Parakeet return nothing?

Live drive (type-while-speaking): the user said "test" and nothing else; every
gate passed and the model returned empty text on 7 clips out of 9, 1.9 to
16.7 s long. A lone word always reaches the model with seconds of silence
attached -- the lone-word pause, or the whole soft-cut window.

Each case is transcribed through `AudioEngine.transcribe`, so the production
gates (and, since D11, the production trim) apply. `raw` is the clip as the
segmenter would emit it; `trim` is the same clip cut to its VAD span here in the
script, which is what `transcribe` now does itself -- after D11 the two columns
should read the same.
"""

import collections
import wave

from _bench import audio_engine, duration, installed_voices, load_parakeet, out_dir, say, sox

from whispy.core.segmentation import FRAME_BYTES, SAMPLE_RATE, webrtcvad

OUT = out_dir("lone-word")
WORDS = ["test", "oui", "bonjour"]
VOICES = [v for v in ["Amélie", "Aurelie", "Jacques", "Thomas", "Eddy", "Flo"] if v in installed_voices()]
TAILS = ["0.6", "2.0", "5.0", "10.0"]
VOLS = ["1.0", "0.15"]  # full `say` level, and roughly the live-drive word level (~0.025 RMS)


def trim_to_speech(src, dst, margin=0.3):
    """Cut `src` to its outermost VAD-speech frames plus `margin` on each side."""
    with wave.open(str(src)) as w:
        pcm = w.readframes(w.getnframes())
    vad = webrtcvad.Vad(3)
    n = len(pcm) // FRAME_BYTES
    flags = [vad.is_speech(pcm[i * FRAME_BYTES : (i + 1) * FRAME_BYTES], SAMPLE_RATE) for i in range(n)]
    if not any(flags):
        sox(str(src), str(dst))
        return
    first = flags.index(True) * 0.03
    last = (n - flags[::-1].index(True)) * 0.03
    start = max(0.0, first - margin)
    end = last + margin
    sox(str(src), str(dst), "trim", f"{start:.2f}", f"={end:.2f}")


def main() -> None:
    model = load_parakeet()
    eng = audio_engine()
    tally = collections.defaultdict(lambda: [0, 0])  # (kind, vol, tail) -> [ok, n]
    for word in WORDS:
        for voice in VOICES:
            base = say(word, OUT / f"{word}_{voice}.wav", voice, pad=("0.4", "0.0"))
            for vol in VOLS:
                for tail in TAILS:
                    raw = OUT / f"{word}_{voice}_{vol}_{tail}.wav"
                    sox(str(base), str(raw), "vol", vol, "pad", "0", tail)
                    trimmed = OUT / f"{word}_{voice}_{vol}_{tail}_trim.wav"
                    trim_to_speech(raw, trimmed)
                    for kind, path in (("raw", raw), ("trim", trimmed)):
                        text = eng.transcribe(str(path), model=model, min_recording_duration=0.4) or ""
                        ok = word in text.lower()
                        key = (kind, vol, tail)
                        tally[key][0] += ok
                        tally[key][1] += 1
                        if not ok:
                            print(
                                f"  MISS {kind:4s} vol={vol} tail={tail:4s} {word:8s} {voice:8s} "
                                f"{duration(path):5.2f}s -> {text!r}"
                            )
    print("\nkind  vol   tail   ok/n")
    for (kind, vol, tail), (ok, n) in sorted(tally.items()):
        print(f"{kind:4s}  {vol:4s}  {tail:4s}  {ok}/{n}")


if __name__ == "__main__":
    main()
