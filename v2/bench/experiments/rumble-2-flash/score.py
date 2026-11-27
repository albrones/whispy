"""Score the transcripts in results/ against the corpus references.

usage: python -I score.py <corpus-dir> <results-dir> [diff] > results/score.out

Text is normalized before WER: NFKC, lowercase, digits spelled out in French
(both engines write some numbers as digits), punctuation dropped, elisions split.
The Parakeet file starts with one warm-up line, which is skipped.
"""

import json
import re
import statistics
import sys
import unicodedata

import jiwer
import soundfile as sf
from num2words import num2words

RUNS = {
    "Parakeet (Whispy, ONNX int8, CPU)": ("parakeet.tsv", True),
    "Rumble-2-Flash (French forced, MPS fp16)": ("rumble-mps.tsv", False),
    "Rumble-2-Flash (auto language, MPS fp16)": ("rumble-auto.tsv", False),
    "Rumble-2-Flash (French forced, CPU fp32)": ("rumble-cpu.tsv", False),
}


def normalize(text: str) -> str:
    text = unicodedata.normalize("NFKC", text).lower().replace("’", "'")
    text = re.sub(r"\d+", lambda match: " " + num2words(int(match.group()), lang="fr") + " ", text)
    text = re.sub(r"[^\w']+", " ", text).replace("'", "' ")
    return " ".join(text.split())


def load(path: str, skip_first: bool) -> dict[str, tuple[float, str]]:
    rows = [line.rstrip("\n").split("\t") for line in open(path, encoding="utf-8") if line.strip()]
    if skip_first:
        rows = rows[1:]
    return {
        name.split("/")[-1].removesuffix(".wav"): (float(seconds.rstrip("s")), json.loads(text))
        for name, seconds, text in rows
    }


def main() -> None:
    corpus, results = sys.argv[1], sys.argv[2]
    runs = {label: load(f"{results}/{file}", skip) for label, (file, skip) in RUNS.items()}
    names = sorted(next(iter(runs.values())))
    duration = {name: sf.info(f"{corpus}/{name}.wav").duration for name in names}
    reference = {name: normalize(open(f"{corpus}/{name}.txt", encoding="utf-8").read()) for name in names}

    print("| Model | Set | WER | Median latency | p95 latency | RTF |\n|---|---|---|---|---|---|")
    for label, run in runs.items():
        for subset in ("tts", "fleurs", ""):
            chosen = [name for name in names if name.startswith(subset)]
            wer = jiwer.wer([reference[n] for n in chosen], [normalize(run[n][1]) for n in chosen])
            latencies = sorted(run[n][0] for n in chosen)
            p95 = latencies[min(len(latencies) - 1, round(0.95 * (len(latencies) - 1)))]
            rtf = sum(latencies) / sum(duration[n] for n in chosen)
            print(
                f"| {label} | {subset or 'all'} ({len(chosen)}) | {wer * 100:.1f} % "
                f"| {statistics.median(latencies):.2f} s | {p95:.2f} s | {rtf:.3f} |"
            )

    if len(sys.argv) > 3:
        for name in names:
            print(f"\n{name}\n  REF {reference[name]}")
            for label, run in runs.items():
                hypothesis = normalize(run[name][1])
                if hypothesis != reference[name]:
                    print(f"  {label}: {hypothesis}")


if __name__ == "__main__":
    main()
