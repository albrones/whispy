"""Ask a larger reference model whether each lost clip holds speech at all.

Criterion 3 counts recovered lost clips only among those that really hold
speech: V1 also lost clips of breath, clicks and silence, and no engine should
type anything for those. This script is the referee: whisper large-v3-turbo
(MLX, ~1.6 GB), far larger than the engines V2 ships, run offline on each
clip. It never ships in the app.

Run it from v2/ with a throwaway venv that has `mlx-audio` (see README.md):

    ls ~/.whispy/lost/*.wav | HF_HUB_OFFLINE=1 <venv>/bin/python -I -B bench/oracle.py bench/oracle

One WAV path per stdin line. It writes to the output directory, which is
gitignored because everything in it is the user's voice or words:

- `oracle.tsv`: `clip<TAB>class<TAB>language<TAB>avg_logprob<TAB>words<TAB>text`,
  `class` being `speech`, `doubtful` or `no-speech` (rules in `classify`);
- `clips/`: a copy of each clip, so the page still plays after V1 rotates
  `~/.whispy/lost/`;
- `listen.html`: every clip with a player, doubtful ones first, and a button
  that copies the listener's verdicts as `verdicts.tsv` lines
  (`clip<TAB>speech|no-speech`), which the bench reads over the oracle's class.
"""

import html
import os
import shutil
import sys
import wave

import numpy as np

MODEL_DIR = os.environ.get(
    "WHISPY_ORACLE_MODEL",
    os.path.expanduser("~/models/whisper-large-v3-turbo-asr-fp16"),
)
SAMPLE_RATE = 16_000
# Same target as V2's `Louder` strategy: V1's quiet lost dictation sat at
# RMS 0.010-0.013 and came back at 0.05.
LOUDER_RMS = 0.05
# The user dictates in French and English; any other language or script on a
# lost clip is whisper decoding noise, as the first bench saw (Georgian, Khmer).
SPOKEN_LANGUAGES = {"fr", "en"}
# Whisper's stock outputs on silence (subtitle credits), seen in V1's log.
HALLUCINATIONS = (
    "sous-titres",
    "amara.org",
    "merci d'avoir regardé",
    "thank you for watching",
    "thanks for watching",
    "abonnez-vous",
)
# Whisper's stock one-liners on breath and room noise (V1's log, the first
# bench, and this oracle on V1's lost clips). A user can say "thank you", so a
# confident one is left to an ear (listen.html), never counted as speech.
FILLERS = {"you", "so", "one", "thank you", "thanks", "bye", "okay", "merci", "i'm going to go"}
# A confident decode, as on every clip that held a real utterance.
CLEAR_LOGPROB = -0.6
# Whisper's own threshold for a failed decode. large-v3-turbo under mlx-audio
# reports a no-speech probability near 0 even on silence, so the log
# probability carries the decision.
FAILED_LOGPROB = -1.0


def read_wav(path):
    with wave.open(path, "rb") as clip:
        if clip.getframerate() != SAMPLE_RATE or clip.getnchannels() != 1 or clip.getsampwidth() != 2:
            raise SystemExit(
                f"{path}: expected 16 kHz mono 16-bit, got {clip.getframerate()} Hz, "
                f"{clip.getnchannels()} channel(s), {8 * clip.getsampwidth()}-bit"
            )
        frames = clip.readframes(clip.getnframes())
    return np.frombuffer(frames, dtype=np.int16).astype(np.float32) / 32768.0


def louder(samples):
    rms = float(np.sqrt(np.mean(samples**2))) if samples.size else 0.0
    if rms == 0.0 or rms >= LOUDER_RMS:
        return samples
    return np.clip(samples * (LOUDER_RMS / rms), -1.0, 1.0)


def decode(model, samples):
    # Deterministic and unfiltered: the referee reports its confidence instead
    # of dropping low-confidence text, so `classify` sees every guess.
    result = model.generate(
        samples,
        temperature=0.0,
        condition_on_previous_text=False,
        no_speech_threshold=None,
        logprob_threshold=None,
        compression_ratio_threshold=None,
    )
    segments = [s for s in result.segments if s.get("text", "").strip()]
    text = " ".join(" ".join(s["text"] for s in segments).split())
    if not segments:
        return {"text": "", "language": result.language or "", "logprob": -99.0}
    weights = [max(s["end"] - s["start"], 0.01) for s in segments]
    return {
        "text": text,
        "language": result.language or "",
        "logprob": float(np.average([s["avg_logprob"] for s in segments], weights=weights)),
    }


def normalized(text):
    kept = "".join(c if c.isalnum() or c in " '" else " " for c in text.lower())
    return " ".join(kept.split())


def is_latin(text):
    return all(ord(c) < 0x250 for c in text if c.isalpha())


def classify(guess):
    text = normalized(guess["text"])
    if not text or any(phrase in guess["text"].lower() for phrase in HALLUCINATIONS):
        return "no-speech"
    if guess["logprob"] < FAILED_LOGPROB and text in FILLERS:
        return "no-speech"
    if (
        guess["language"] in SPOKEN_LANGUAGES
        and is_latin(guess["text"])
        and guess["logprob"] > CLEAR_LOGPROB
        and text not in FILLERS
    ):
        return "speech"
    return "doubtful"


def best_guess(model, samples):
    """The clip as recorded and turned up to speech level; the more confident wins."""
    guesses = [decode(model, samples), decode(model, louder(samples))]
    return max(guesses, key=lambda guess: (bool(guess["text"]), guess["logprob"]))


ORDER = {"doubtful": 0, "no-speech": 1, "speech": 2}


def listen_page(rows):
    """A local page to settle the doubtful clips by ear."""
    cards = []
    for row in sorted(rows, key=lambda r: (ORDER[r["class"]], r["clip"])):
        clip = html.escape(row["clip"])
        options = "".join(
            f'<label><input type="radio" name="{clip}" value="{value}"> {label}</label>'
            for value, label in (("speech", "speech"), ("no-speech", "no speech"))
        )
        cards.append(
            f'<li class="{row["class"]}" data-clip="{clip}">'
            f'<div class="head"><b>{clip}</b> <span class="tag">{row["class"]}</span>'
            f' <span class="meta">{row["language"]} · log p {row["logprob"]:.2f}</span></div>'
            f'<audio controls preload="none" src="clips/{clip}.wav"></audio>'
            f'<div class="heard">oracle heard: <q>{html.escape(row["text"]) or "(nothing)"}</q></div>'
            f"<fieldset>{options}</fieldset></li>"
        )
    counts = {name: sum(r["class"] == name for r in rows) for name in ORDER}
    return PAGE.format(
        cards="\n".join(cards),
        speech=counts["speech"],
        doubtful=counts["doubtful"],
        silent=counts["no-speech"],
    )


PAGE = """<!doctype html>
<html lang="en"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>Lost clips, by ear</title>
<style>
:root {{ color-scheme: light dark; --line: #8884; --doubt: #c80; --no: #888; --yes: #2a7; }}
body {{ font: 15px/1.45 system-ui, sans-serif; max-width: 46rem; margin: 0 auto; padding: 16px; }}
ul {{ list-style: none; padding: 0; }}
li {{ border-top: 1px solid var(--line); padding: 12px 0; }}
.tag {{ font-size: 12px; padding: 1px 6px; border-radius: 8px; color: #fff; }}
.doubtful .tag {{ background: var(--doubt); }} .no-speech .tag {{ background: var(--no); }} .speech .tag {{ background: var(--yes); }}
.meta, .heard {{ color: #888; font-size: 13px; }}
audio {{ width: 100%; margin: 6px 0; }}
fieldset {{ border: 0; padding: 0; display: flex; gap: 16px; }}
textarea {{ width: 100%; min-height: 8rem; font: 13px ui-monospace, monospace; }}
</style></head><body>
<h1>Lost clips, by ear</h1>
<p>The oracle (whisper large-v3-turbo) heard clear speech in {speech} clips, no speech in {silent},
and is unsure about {doubtful}: those come first. For each clip you can judge, pick
<i>speech</i> if you hear yourself saying words, <i>no speech</i> for breath, clicks or silence.
Then copy the lines below into <code>v2/bench/oracle/verdicts.tsv</code> and rerun the bench.
Nothing here is committed.</p>
<ul>
{cards}
</ul>
<h2>verdicts.tsv</h2>
<textarea id="out" readonly></textarea>
<p><button id="copy" type="button">Copy</button></p>
<script>
const out = document.getElementById("out");
const key = "whispy-oracle-verdicts";
let saved = {{}};
try {{ saved = JSON.parse(localStorage.getItem(key) || "{{}}"); }} catch (error) {{ saved = {{}}; }}
for (const [clip, value] of Object.entries(saved)) {{
  const input = document.querySelector(`input[name="${{clip}}"][value="${{value}}"]`);
  if (input) input.checked = true;
}}
function render() {{
  const picked = [...document.querySelectorAll("input:checked")].map(input => [input.name, input.value]);
  out.value = picked.map(([clip, value]) => clip + "\\t" + value).join("\\n");
  try {{ localStorage.setItem(key, JSON.stringify(Object.fromEntries(picked))); }} catch (error) {{}}
}}
document.addEventListener("change", render);
document.getElementById("copy").addEventListener("click", () => navigator.clipboard.writeText(out.value));
render();
</script>
</body></html>
"""


def main():
    if len(sys.argv) != 2:
        raise SystemExit("usage: oracle.py <output directory>  (WAV paths on stdin)")
    out_dir = sys.argv[1]
    os.makedirs(os.path.join(out_dir, "clips"), exist_ok=True)
    from mlx_audio.stt.utils import load_model

    model = load_model(MODEL_DIR)
    rows = []
    for line in sys.stdin:
        path = line.strip()
        if not path:
            continue
        guess = best_guess(model, read_wav(path))
        clip = os.path.splitext(os.path.basename(path))[0].removeprefix("lost-")
        shutil.copyfile(path, os.path.join(out_dir, "clips", f"{clip}.wav"))
        rows.append({"clip": clip, "class": classify(guess), **guess})
        print(f"{clip}\t{rows[-1]['class']}", file=sys.stderr, flush=True)
    with open(os.path.join(out_dir, "oracle.tsv"), "w", encoding="utf-8") as table:
        for row in rows:
            fields = [
                row["clip"],
                row["class"],
                row["language"],
                f"{row['logprob']:.3f}",
                str(len(row["text"].split())),
                row["text"],
            ]
            table.write("\t".join(fields) + "\n")
    with open(os.path.join(out_dir, "listen.html"), "w", encoding="utf-8") as page:
        page.write(listen_page(rows))
    return 0


if __name__ == "__main__":
    sys.exit(main())
