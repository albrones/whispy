"""How often does loud non-speech become text, and does the speech gate stop it?

The RMS gate only catches near-silence. Non-speech that is merely loud — a noisy
room, a fan, mains hum — measures 0.010-0.035 normalized RMS against a 0.005
threshold, so it reaches the model. `sox` draws a fresh noise realization per
call, so a single sample proves nothing: this runs N per type and reports a rate.

Measured before the speech gate existed: 3 leaks in 100. After: 0 in 100. The
same 100 clips through faster-whisper small leaked 52-100% depending on the noise
type (see run_whisper.py for how to get that interpreter).
"""

from _bench import audio_engine, load_parakeet, noise, out_dir, read_pcm

from whispy.core.audio import MIN_SPEECH_DURATION_S, SILENCE_RMS_THRESHOLD
from whispy.core.segmentation import speech_duration_s

N = 25
OUT = out_dir("noiserate")
model = load_parakeet()
engine = audio_engine()

TYPES = {
    "whitenoise 0.05": ["whitenoise", "vol", "0.05"],
    "brownnoise 0.03": ["brownnoise", "vol", "0.03"],
    "pinknoise 0.05": ["pinknoise", "vol", "0.05"],
    "mains hum": ["sine", "50", "vol", "0.05"],
    "fan (pink+lowpass)": ["pinknoise", "lowpass", "500", "vol", "0.08"],
}

print(f"rms gate={SILENCE_RMS_THRESHOLD}  speech gate={MIN_SPEECH_DURATION_S}s  n={N} per type\n")
for label, synth in TYPES.items():
    leaked, samples, rms_sum, voiced_max = 0, [], 0.0, 0.0
    for i in range(N):
        wav = noise(OUT / f"{label.split()[0]}_{i}.wav", synth)
        rms_sum += engine._get_audio_rms(str(wav)) or 0.0
        pcm, rate = read_pcm(wav)
        voiced_max = max(voiced_max, speech_duration_s(pcm, sample_rate=rate) or 0.0)
        out = engine.transcribe(str(wav), model=model)  # full pipeline, gates included
        if out:
            leaked += 1
            samples.append(out)
    print(
        f"{label:20s} rms~{rms_sum / N:.4f}  voiced_max={voiced_max:.2f}s  "
        f"leak {leaked}/{N} ({leaked / N:4.0%})" + (f"  e.g. {samples[:3]}" if samples else "")
    )

print("\n== real speech, for scale ==")
for wav in sorted(out_dir("clips").glob("en_*.wav")):
    pcm, rate = read_pcm(wav)
    print(
        f"  {wav.name:12s} rms={engine._get_audio_rms(str(wav)):.4f} voiced={speech_duration_s(pcm, sample_rate=rate):.2f}s"
    )
