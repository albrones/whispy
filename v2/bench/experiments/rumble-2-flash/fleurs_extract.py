"""Extract the first 20 distinct French FLEURS test utterances under 15 s as 16 kHz WAV + reference text.

usage: python -I fleurs_extract.py <fleurs-fr_fr-test.parquet> <corpus-dir>
The parquet comes from https://huggingface.co/api/datasets/google/fleurs/parquet/fr_fr/test/0.parquet
"""

import io
import sys

import librosa
import pyarrow.parquet as pq
import soundfile as sf

COUNT = 20
MAX_SECONDS = 15


def main() -> None:
    source, corpus = sys.argv[1], sys.argv[2]
    seen: set[int] = set()
    written = 0
    for row in pq.read_table(source).to_pylist():
        if row["id"] in seen:
            continue
        seen.add(row["id"])
        audio, rate = sf.read(io.BytesIO(row["audio"]["bytes"]), dtype="float32")
        if audio.ndim > 1:
            audio = audio.mean(1)
        if rate != 16000:
            audio = librosa.resample(audio, orig_sr=rate, target_sr=16000)
        if len(audio) / 16000 > MAX_SECONDS:
            continue
        written += 1
        stem = f"{corpus}/fleurs-{written:02d}"
        sf.write(stem + ".wav", audio, 16000, subtype="PCM_16")
        with open(stem + ".txt", "w", encoding="utf-8") as reference:
            reference.write(row["raw_transcription"])
        if written == COUNT:
            break
    print(written)


if __name__ == "__main__":
    main()
