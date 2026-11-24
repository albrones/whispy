## Context

Today (`controller.rs`, `LiveDictation`): `split::LiveSplitter` cuts at a 0.6 s pause after 0.7 s of speech, or by 8 s; each piece goes through `Pipeline::transcribe` alone and is pasted; `join::PieceJoiner` withholds a period only for 8 s cuts. Decisions are irreversible and taken with the least context.

This is the « LocalAgreement » policy of whisper_streaming (Macháček et al., 2023) and NVIDIA's buffered inference for Parakeet: re-transcribe a growing window, commit what two passes agree on, and release audio only at a committed boundary.

## Goals / Non-Goals

**Goals:** text typed during the dictation has the quality of one-block transcription; the user sees the words within about a second (in the pill); the stop is near-instant.

**Non-Goals:** erasing or retyping text in the frontmost app (display A, later); a streaming-native model; changes to hold mode, to the whole-dictation path, or to V1.

## Decisions

### Timed words (`whispy-core`)

```rust
pub struct Word { pub text: String, pub start_s: f32, pub end_s: f32 }

pub trait Transcriber: Send {
    fn name(&self) -> &'static str;
    fn transcribe(&mut self, samples: &[f32]) -> Result<String, Error>;
    /// Words with their time in `samples`; `None` when the engine has no timings.
    fn transcribe_timed(&mut self, _samples: &[f32]) -> Result<Option<Vec<Word>>, Error> { Ok(None) }
}
```

- Parakeet: `decode` records the encoder frame `t` of every emitted token. One encoder frame is 8 mel hops of 10 ms = 80 ms (checked against `frames.len()` for the padded input). Times are in the caller's `samples`, so the `FRAME_S` silence Parakeet adds in front is subtracted, and every time is clamped to `0..=duration`. A word's start is its first token's frame; its end is its last token's frame plus that token's TDT duration (at least one frame).
- Invariant: the words' texts joined by single spaces equal `transcribe()`'s text for the same input. Words are split from the detokenized text while keeping a per-character frame, so punctuation stays attached to its word exactly as `detokenize` prints it.
- `Lazy` forwards `transcribe_timed` to the engine it wraps. Whisper keeps the default (`None`).
- `Pipeline::transcribe_timed(&mut self, window) -> Result<Option<Vec<Word>>, Error>`: same gates as `Strategy::prepare` (peak RMS under `SILENCE_RMS_THRESHOLD`, or `vad::speech_span` not carrying speech → `Some(vec![])`), then the louder copy, but **no trim and no padding**, so word times stay window times; the primary engine only (no fallback); words without a letter or digit are dropped (as `worded`).

### Rolling re-transcription (`whispy-core/src/stream.rs`)

```rust
pub struct Streamer { /* open window audio, previous hypothesis, join state, timings */ }
pub struct Update {
    /// Text to append to the field now, already joined (leading space included); empty most passes.
    pub typed: String,
    /// The hypothesis after the committed text, words joined by spaces.
    pub provisional: String,
    pub stats: PassStats, // window_s, took_s, words, stable, committed words, forced: bool — counts only
}
impl Streamer {
    pub fn new() -> Self;
    pub fn push(&mut self, samples: &[f32]);        // 16 kHz mono, as the microphone gives it
    pub fn is_pass_due(&self) -> bool;
    pub fn pass(&mut self, pipeline: &mut Pipeline) -> Result<Update, Error>;
    pub fn finish(self, pipeline: &mut Pipeline) -> Result<String, Error>; // text to append at the stop
    pub fn committed(&self) -> &str;                // everything typed so far
}
```

Constants (tunable from the bench): `PASS_EVERY_S = 0.6`, `COMMIT_PAUSE_S = 2.0`, `FORCE_COMMIT_S = 15.0`, `MAX_WINDOW_S = 20.0` (= `split::MAX_PIECE_S`), `LEADING_SILENCE_KEPT_S = 0.5`.

`is_pass_due`: at least `PASS_EVERY_S` of audio pushed since the last pass, and either some of it is voiced (WebRTC VAD, one `VoiceDetector` kept across pushes) or the last hypothesis is not empty. Silence after everything is committed costs nothing.

`pass`, with W the open window and P the previous hypothesis (times relative to W's start):

1. If W holds no voiced frame and P is empty, keep only its last `LEADING_SILENCE_KEPT_S` and return (no engine call).
2. If W is longer than `MAX_WINDOW_S`: **overflow commit**. Run `Pipeline::transcribe(W)` (the full default pipeline, fallback included), commit its whole text as a forced commit, clear W and P.
3. H = `pipeline.transcribe_timed(W)`; `None` (no timings) is treated as no stable words, so only the overflow commit can apply.
4. `stable` = the length of the longest common prefix of H and P, comparing word texts exactly (punctuation and case included).
5. Sentence commit: the largest `i < stable` whose text ends with `.`, `?`, `!` or `…`, and either `i + 1 < H.len()` (speech follows) or `W_s - H[i].end_s ≥ COMMIT_PAUSE_S`. A thinking pause shorter than 2 s therefore never commits a sentence end: the period stays provisional until the speaker goes on and the model, seeing the continuation, keeps or drops it.
6. Else, if `W_s ≥ FORCE_COMMIT_S`: forced commit at the `i < stable` with `i + 1 < H.len()` whose gap `H[i+1].start_s - H[i].end_s` is the largest (ties: the latest).
7. On a commit at `i`: typed = join(H[0..=i]); the cut is the middle of the gap to `H[i+1]` when it exists, else `H[i].end_s + 0.3 s` (capped at W's end); the audio before the cut is released; P = H[i+1..] shifted by the cut. Without a commit, P = H.

Joining: the first commit of a dictation is typed as is; each next one is preceded by a space; after a forced (mid-sentence) commit, the next text's first letter is lowered unless its first word is an acronym (`join::lowercase_first`, made `pub(crate)`).

`finish`: the open window goes through `Pipeline::transcribe` (gates, padding, fallback, 20 s split), joined by the same rule; if it is empty and the last commit was forced, a `.` closes the dictation.

### App wiring (`whispy2`)

- `Recorder` decides `is_streaming` at `StartCapture` (toggle mode and the setting on, as today). At each level beat while streaming it sends `Job::StreamAudio(capture.take_recorded())` (nothing when empty); the stop sends `Job::FinishStream { dictation, delivery }` with the rest of the audio; a discard sends `Job::DiscardStream`.
- The worker coalesces: after a `StreamAudio`, it drains every job already queued with `try_recv`, pushing `StreamAudio` samples and holding the first other job for the next turn. It runs a pass only when `is_pass_due()` and no other job is held, so a stop never waits behind a pass it did not need.
- After a pass: a non-empty `typed` goes to the inserter (`Delivery::Paste`) with today's failure handling; the worker sends `Input::Caption(Caption { committed: tail, provisional })` to the controller, which forwards it to `Feedback::caption` only while the phase is `Recording`. Each pass logs one line of counts, never text.
- `LiveDictation` keeps its other duties: deaf-take checks, the 5-minute watchdog's whole text to the clipboard, a failed insertion making the stop insert the whole text, lost clips, the journal entry.

### Caption in the pill (display B)

```rust
// feedback.rs
#[derive(Debug, Clone, PartialEq, Default)]
pub struct Caption { pub committed: String, pub provisional: String }
trait Feedback { /* … */ fn caption(&mut self, _caption: &Caption) {} }
```

The first non-empty caption widens the pill from 168 to `CAPTION_PILL_WIDTH` = 560 pt, recentred bottom-centre; the bars keep their place in the first 168 pt and a single line of text fills the rest (16 pt right padding), system font 14 pt, vertically centred. Committed words are white at 0.95 alpha, provisional words white at 0.5 alpha. A text too long is truncated at its head (« … »), so the latest words are always visible. The width stays fixed for the rest of the recording (no jitter) and is back to 168 at the next recording.

## Risks / Trade-offs

- Pass cost: about one Parakeet call per 0.6 s on a window up to 15–20 s. Measured by the bench (criterion 3); `PASS_EVERY_S` is the knob.
- A sentence reaches the field only when the next one starts or after a 2 s pause: slower than today's pieces, by design; the pill carries the instant feedback.
- Parakeet's times are frame-accurate (80 ms) and the cut sits in the middle of an inter-word gap, so a word is not split; a forced commit starts the next window mid-sentence without left context, as the 20 s split already does.
- `LiveSplitter` and `PieceJoiner` remain only as the bench baseline; delete them once the trial settles.
