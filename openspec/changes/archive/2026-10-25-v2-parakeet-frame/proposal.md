## Why

`banc --labelled` (change `v2-labelled-bench`) scored V2 on the 35 clips the
user labelled by hand, and criterion 3 of Régie card whispy #1 failed:
WER 18.9 % against V1's 16.9 %, and « Yeah. » invented on noise. Parakeet
answered French in English on clips cut tight to their speech, and answered
« ... » on a quiet clip, which kept whisper from trying.

**Need, in one sentence:** carry over the V1 lessons those clips expose, so
V2 is not worse than V1 on the user's own speech.

## What Changes

- Parakeet frames every input with 0.25 s of digital silence (V1 fcf7861).
- The pipeline counts an answer without a letter or digit as empty, so the
  fallback tries and « ... » is never pasted.
- Default strategy `louder` → `padded`, the bench's new pick.

## Refusé

- **A `framed` strategy for every engine**: whisper then lost a lost speech
  clip (4/7); the frame is Parakeet's need only (whisper pads to 30 s itself).

## Coût

- Parakeet reads 0.5 s more per call; release-to-insert p95 0.32 s.
