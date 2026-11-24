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
pub struct Streamer { /* window = left context + open audio, previous hypothesis, timings */ }
pub struct Update { pub typed: String, pub provisional: String, pub stats: PassStats } // stats: counts only
pub struct Finish { pub typed: String, pub engine: Option<&'static str>, pub lost: Option<Vec<f32>> }
impl Streamer {
    pub fn new() -> Self;
    pub fn push(&mut self, samples: &[f32]);   // 16 kHz mono, as the microphone gives it
    pub fn is_pass_due(&self) -> bool;
    pub fn pass(&mut self, pipeline: &mut Pipeline) -> Result<Update, Error>;
    pub fn finish(self, pipeline: &mut Pipeline) -> Result<Finish, Error>;
    pub fn rest(&self) -> &[f32];              // the open audio
    pub fn committed(&self) -> &str;
}
```

Constants (tuned on the bench): `PASS_EVERY_S = 0.6`, `LOOKAHEAD_S = 1.5`, `LOOKAHEAD_WORDS = 3`, `MIN_COMMIT_WORDS = 4`, `COMMIT_PAUSE_S = 2.0`, `LEFT_CONTEXT_S = 5.0`, `BOUNDARY_MARGIN_S = 0.15`, `MAX_WINDOW_S = 20.0` (= `split::MAX_PIECE_S`; the overflow fires two passes before it), `LEADING_SILENCE_KEPT_S = 0.5`.

**Revised after the first bench run (2026-11-24).** The first version committed whole sentences once two passes agreed on their final period with one word of speech after it, cut run-ons at 15 s, and restarted every window cold at the cut. On the reference clips it matched one block; on the user's 11 labelled dictations it did worse than the pieces (WER 16.3 % vs 15.0 %, 9 extra sentence ends vs 1, commit delay p95 16 s). The rule below gives, on the same clips: WER 14.5 % (one block 14.0 %, pieces 15.0 %), no extra sentence end (pieces 1), commit delay median 1.9 s / p95 3.7 s, stop p95 0.6 s, pass cost 0.36, 111 pastes (a per-word version without batching made 277). Read side by side, the extra periods came from deciding with too little right context (« comportement. Déjà » where one block has « comportement, déjà ») and the misheard words from cold restarts after a cut (« ça aurait ‖ c'était ‖ beaucoup »). The commit rule is now per word, with right context and left context:

`is_pass_due`: at least `PASS_EVERY_S` of audio pushed since the last pass, and either some of it is voiced (WebRTC VAD, one `VoiceDetector` kept across pushes) or the last hypothesis is not empty. Silence after everything is committed costs nothing.

`pass`, with W the window (left context C, then the open audio) and P the previous open hypothesis (times relative to W's start):

0. If P is empty and the open audio holds a run of at least `COMMIT_PAUSE_S` unvoiced frames followed by speech, the open audio up to `LEADING_SILENCE_KEPT_S` before that speech is closed: released with no engine call when it holds no voiced frame, else transcribed by the full default pipeline (fallback included: quiet speech the timed pass heard nothing in) and committed. The context goes too: what follows a long pause is heard on its own. A long thinking pause never pushes the next sentence into an overflow.
1. If the open audio holds no voiced frame and P is empty, keep only the last `LEADING_SILENCE_KEPT_S` (no engine call).
2. Overflow: past `MAX_WINDOW_S − 2 × PASS_EVERY_S`, the open audio goes through `Pipeline::transcribe` (fallback included) and is committed whole; W and P are cleared.
3. H = `pipeline.transcribe_timed(W)`; the words whose middle falls in C are dropped (typed already). `None` (no timings) is no stable word, so only the overflow commits.
4. `stable` = the longest common prefix of H and P, word texts compared exactly (punctuation and case included).
5. Commit: the largest `i < stable` that the model has heard far enough past — `W_s − H[i].end_s ≥ LOOKAHEAD_S` and at least `LOOKAHEAD_WORDS` words after it in H, or `≥ COMMIT_PAUSE_S` of audio when it is the last word — and that is worth a paste: at least `MIN_COMMIT_WORDS` words, or ending on punctuation, or the last word. A period at a thinking pause stays provisional until the model has heard three words past it (a pause fills the seconds, not the words), or 2 s of silence.
6. On a commit at `i`: typed = join(H[0..=i]); the boundary is `H[i].end_s + BOUNDARY_MARGIN_S` (capped at the middle of the gap to `H[i+1]`), not the middle of the gap: speech the pass has not transcribed yet may sit in that gap and must stay open (the bench lost « Euh... ça aurait » between « ça. » and « été » that way). The window then starts about `LEFT_CONTEXT_S` before the boundary, in a gap between words (`context_start`), and C = start..boundary. P = H[i+1..] shifted to the new start.

Joining: each commit after the first is preceded by a space. After a typed `.`, `?` or `!` (not an ellipsis) the next text starts with a capital: that period may come from an earlier pass than the text, which did not hear it (« donc bon. pensez »). A text heard without context (after an overflow or a long pause) that follows a committed text ending mid-sentence has its first letter lowered unless its first word is an acronym (`join::lowercase_first`); in context, the model's own case stands (a proper noun mid-sentence keeps its capital).

`finish`: when there is a context, the window goes through `transcribe_timed` once more and the open words are typed (heard in context); otherwise, or when that hears nothing, the open audio goes through `Pipeline::transcribe` (gates, padding, fallback, 20 s split). `Finish::lost` carries the open audio when the gates call it speech and no text came back, for the app's lost clips.

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

- Last words cut at a quick stop (reported once in manual testing, not reproduced). Two remedies were measured on the bench and rejected: keeping the fuller of the in-context and the stand-alone transcription of the end (6 extra periods, WER 14.7 %, stop p95 1.03 s), and 0.5 s of silence after the window for the stop's pass (3 extra periods, stop p95 0.93 s). Without the audio of the failing dictation there is nothing to fix against; keeping each dictation's audio locally is the next step.

- Pass cost: about one Parakeet call per 0.6 s on a window up to 15–20 s. Measured by the bench (criterion 3); `PASS_EVERY_S` is the knob.
- A sentence reaches the field only when the next one starts or after a 2 s pause: slower than today's pieces, by design; the pill carries the instant feedback.
- Parakeet's times are frame-accurate (80 ms) and the cut sits in the middle of an inter-word gap, so a word is not split; a forced commit starts the next window mid-sentence without left context, as the 20 s split already does.
- `LiveSplitter` and `PieceJoiner` remain only as the bench baseline; delete them once the trial settles.
