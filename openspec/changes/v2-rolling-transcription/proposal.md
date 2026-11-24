## Why

V2's « Type while speaking » cuts the recording at every 0.6 s pause (or at 8 s) and transcribes each piece as its own model call. Each call punctuates its piece as a full sentence, so a thinking pause becomes a period; the first words of a piece have no context and are misheard or dropped; and a piece, once typed, can never be corrected. The user dictates prompts with it and the text arrives grammatically noisy (2026-11-24).

Transcribing the whole dictation at the stop gives better text, and in V2 it is no longer slow (journal: median 1.9 s, worst 11 s for dictations over 20 s; Parakeet transcribes 180 s in 5.4 s). That speed lets V2 re-transcribe the sentence in progress about once a second instead of guessing where to cut.

## What Changes

- In toggle mode with `type_while_speaking` on, V2 no longer cuts at pauses. It keeps the sentence in progress open and re-transcribes all of it about once a second. A word is stable when two passes in a row agree on it. A sentence is committed (typed into the frontmost app) once it is stable up to the end punctuation the model put there, and either more speech follows it or 2 s of silence do. Its audio is then released at the time Parakeet gives for its last word.
- Parakeet returns words with their start and end time in the audio, read from the TDT decoder's frame index (no new model).
- A run-on stretch with no sentence end is committed at its longest stable pause after 15 s. Its audio never reaches the engine in calls longer than 20 s.
- The stopping press transcribes the open sentence with the full default pipeline (gates, padding, whisper fallback), as a whole dictation is today.
- The recording pill shows the words as they are heard: it widens into a one-line caption, with committed words in white and the not-yet-committed words in grey, the latest words always visible. Nothing in the frontmost app is ever erased or retyped (display « B »; in-field correction « A » is a later, separate change).
- Each re-transcription pass logs counts only (window length, pass time, words, committed words): the log still holds no dictated text.
- `banc --streaming` compares three ways on the same audio: one block, the previous pieces cut at pauses, and the rolling re-transcription. It reports word error rate, extra sentence ends, commit delay, stop latency and pass cost.

Hold mode, and toggle mode with the setting off, are unchanged.

## Capabilities

### New Capabilities
<!-- none -->

### Modified Capabilities
- `v2-transcription-core`: timed words from Parakeet; rolling re-transcription with committed sentences.
- `v2-menu-bar-app`: « Type while speaking » commits sentences instead of pause-cut pieces; the pill shows a live caption.

## Acceptance criteria

1. On the bench (`banc --streaming`), the rolling text's WER is no worse than one-block WER + 1 point and no worse than the pieces' WER, on the reference clips and on the user's labelled speech clips of 8 s or more.
2. On the same clips, the rolling text has fewer extra sentence ends than the pieces (an extra sentence end is one more `.`, `?`, `!` than the one-block text has).
3. Commit delay (from a word's end in the audio to the moment it is typed) p95 ≤ 3 s; stop latency (stopping press to last text) p95 ≤ 1 s; mean pass cost ≤ 50 % of the audio time.
4. In toggle mode with the setting on, a sentence is typed into TextEdit before the stopping press while the pill shows the words being said, grey until committed [manual].
5. Hold mode and the setting off are unchanged; the v2/ gate is green; a 180 s dictation stays under 1.5 GB.

## Impact

- `v2/whispy-core`: new `stream` module; `Transcriber` gains timed words (provided method, Parakeet implements it); `Pipeline` gains a timed pass. `split::LiveSplitter` and `join::PieceJoiner` stay for the bench baseline only.
- `v2/whispy2`: controller and worker (streaming jobs, pass coalescing, caption input); `Feedback` gains `caption`; the macOS pill draws the caption.
- `v2/banc`: `--streaming` rewritten.
- `objc2-app-kit` may gain features for text drawing; no new crate.
- V1, the website and the user docs describe V1 and are unaffected; `v2/README.md` is updated.
