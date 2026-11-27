"""Transcribe the experiment corpus with Rumble-2-Flash through Transformers.

usage: python -I rumble.py <mps|cpu> <French|auto> <corpus-dir> > results/rumble-<run>.tsv

Prints one line per clip: name, warm latency (preprocessing + generation), transcript as JSON.
The first clip is transcribed once before the timed pass to warm the device up.
"""

import glob
import json
import os
import sys
import time

import soundfile as sf
import torch
from transformers import AutoModelForMultimodalLM, AutoProcessor

MODEL_ID = "Reson8/Rumble-2-Flash"


def main() -> None:
    device, language, corpus = sys.argv[1], sys.argv[2], sys.argv[3]
    started = time.time()
    processor = AutoProcessor.from_pretrained(MODEL_ID)
    dtype = torch.float16 if device == "mps" else torch.float32
    model = AutoModelForMultimodalLM.from_pretrained(MODEL_ID, dtype=dtype).to(device).eval()
    print(f"load\t{time.time() - started:.2f}s", file=sys.stderr)

    def transcribe(path: str) -> tuple[float, str]:
        audio, _ = sf.read(path, dtype="float32")
        options = {} if language == "auto" else {"language": language}
        begin = time.time()
        inputs = processor.apply_transcription_request(audio=audio, **options).to(device, dtype=model.dtype)
        with torch.inference_mode():
            output = model.generate(**inputs, max_new_tokens=256, do_sample=False)
        generated = output[:, inputs["input_ids"].shape[-1] :]
        text = processor.decode(generated, return_format="transcription_only")[0]
        if device == "mps":
            torch.mps.synchronize()
        return time.time() - begin, text

    files = sorted(glob.glob(f"{corpus}/tts-*.wav")) + sorted(glob.glob(f"{corpus}/fleurs-*.wav"))
    transcribe(files[0])
    for path in files:
        elapsed, text = transcribe(path)
        print(f"{os.path.basename(path)}\t{elapsed:.3f}s\t{json.dumps(text, ensure_ascii=False)}", flush=True)


if __name__ == "__main__":
    main()
