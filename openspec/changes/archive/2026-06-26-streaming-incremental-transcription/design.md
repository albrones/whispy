## Context

Whispy captures audio via a `sounddevice` (PortAudio) callback that streams int16
frames into a single WAV file (`core/audio.py`). On trigger release, the engine's
single-shot transcription worker reads the whole WAV and runs
`faster_whisper.WhisperModel.transcribe` once, then injects the joined text via
`osascript` keystrokes/clipboard (`core/engine.py`, `hardware/injection.py`).

Two measured facts shape this design:

- **RTF ≈ 0.15** on the default `small` int8 model, ≈ 0.18–0.37 on `medium`
  (10-core Mac). Whisper transcribes several times faster than real time, so
  per-chunk transcription comfortably keeps pace with live speech.
- **UI coupling is shallow.** No consumer treats `is_recording`/`is_transcribing`
  as a hard mutual-exclusion invariant: `menu_bar` only uses them as display
  priorities (checking `is_recording` before `is_transcribing`) and gates the
  waveform on recording start/stop. So transcription can run during `RECORDING`
  without breaking the UI.

Constraints:

- **Injection is append-only.** Keystroke/clipboard injection cannot retract
  already-typed text without backspaces. The design must commit only text it will
  not revise — which is why we cut on silence (clean boundaries), not a sliding
  window.
- **Existing anti-hallucination stance.** `condition_on_previous_text=False`,
  `temperature=0`, `vad_filter=True`, `min_recording_duration` discard, and credit
  stripping must be preserved and applied per chunk.

## Goals / Non-Goals

**Goals:**
- Move transcription off the post-release critical path: post-release wait
  becomes the last-chunk-only wait (~1–2 s) instead of whole-recording (~9 s on
  60 s of speech).
- Surface recognized text incrementally as the user speaks.
- Cut at natural (silent) boundaries to avoid mid-word splits, plus a max-length
  safety flush so run-on speech without pauses still streams.
- Zero behaviour change when streaming is disabled; no new runtime dependency.

**Non-Goals:**
- Sliding-window streaming ASR with text revision/backspacing (fights append-only
  injection; out of scope).
- Neural VAD for live segmentation (silero is offline/file-oriented; energy is
  enough for v1). `webrtcvad` is a possible future upgrade, not this change.
- Cross-chunk context priming (deliberately retains independent chunks).
- Tuning the model itself or changing the default model size.

## Decisions

> **Amendment (post real-mic testing).** Real-mic use exposed two failures the
> deterministic seam missed: the energy threshold (D1) mis-cut mid-word (gain-
> dependent → garbled fragments), and `live` injection mid-recording stole focus
> in full-screen Spaces. Resolution: D1's energy detector is **superseded by
> WebRTC VAD** (`webrtcvad-wheels`, gain-independent; energy gate as fallback),
> `silence_factor` is replaced by `vad_aggressiveness`, and a new
> `streaming_inject_mode` (`on_release` default | `live`) controls injection
> timing — `on_release` types once at release and removes the focus disruption.
> The rest of D1–D5 (max-length flush, in-memory buffering, FSM-1, ordered
> queue, config-gating) stands.

### D1 — Silence + max-length segmentation (energy-based — superseded by VAD)

Run a small state machine over the int16 blocks the capture callback already
receives. Reuse the per-block RMS already computed for the waveform level.

```
SPEAKING ──(level < thresh for ≥ pause_ms)──► emit chunk ──► SILENCE
SILENCE  ──(level > thresh)─────────────────► SPEAKING (start new chunk)
any      ──(current chunk audio ≥ max_chunk_s)─► emit chunk (forced flush)
```

- A chunk that never contained speech is **not** emitted (pure silence between
  phrases produces nothing → no hallucination, fewer empty transcribes).
- **Adaptive threshold**: track the noise floor (a slow running minimum / EMA of
  low levels) and define silence as `level < noise_floor × silence_factor`. This
  avoids asking the user to hand-tune an absolute threshold across different mics
  and rooms.

**Why energy over webrtcvad/silero:** zero new dependency, the RMS signal already
exists, and cuts only need to be *roughly* at pauses — the per-chunk
`min_recording_duration` guard and VAD filter inside `transcribe` clean up the
edges. Alternatives considered: `webrtcvad` (more robust to noise, but a new C
dep — deferred), silero (excellent but offline/file-oriented, wrong tool for live
framing).

### D2 — In-memory PCM buffering, per-chunk WAV at flush

Accumulate raw int16 frames for the current chunk in memory. On emit, write a
self-contained WAV (same 16 kHz mono format) to a unique temp path and enqueue
it. Rationale: `WhisperModel.transcribe` consumes a path/array; a per-chunk file
keeps the existing transcribe call and per-recording isolation
(unique-path) pattern intact, and lets the existing cleanup delete each chunk
after use. The legacy whole-file capture path is retained for
`streaming_enabled=false`.

### D3 — FSM-1: chunk transcription runs outside the state machine

The state machine keeps `IDLE → RECORDING → TRANSCRIBING → IDLE` and the
invariant that `RECORDING` is the sole owner of the recording lifecycle. Chunk
transcription/injection runs in a separate pipeline that is active **during**
`RECORDING`, not modeled as an FSM state. The trigger-release path transitions to
`TRANSCRIBING` only for the final tail flush, so `is_transcribing` keeps its
current meaning and existing consumers are untouched.

Alternative considered — **FSM-2** (composite `RECORDING_TRANSCRIBING` state or
orthogonal flags): conceptually cleaner but touches every FSM reader (UI, API
status, tests) for no behavioural gain here. Rejected for v1.

### D4 — Ordered chunk queue + single injector

A FIFO queue feeds a single transcription/injection worker so chunks are typed in
order (concurrent workers would interleave text). Each chunk: per-chunk
`min_recording_duration` discard → `transcribe` (existing params, `initial_prompt`
from custom vocabulary) → credit/clean → append-inject with inter-chunk spacing
(leading space when the previous chunk emitted text, so words don't concatenate).
Chunks stay independent — the previous chunk's text is not fed back as
`initial_prompt`/`condition_on_previous_text` (preserves the anti-snowball stance).

### D5 — Config-gated, all defaulted

New keys with validation + migration in `config.py`: `streaming_enabled`,
`pause_ms` (≈ 600 ms), `min_chunk_s` (≈ 0.4 s), `max_chunk_s` (≈ 12–15 s),
`silence_factor` (≈ 2–3). When `streaming_enabled` is false the legacy path runs
verbatim, giving an instant rollback switch.

## Risks / Trade-offs

- **`large-v3` RTF approaching 1.0 under concurrent capture** → the chunk queue
  could grow during recording. Mitigation: `max_chunk_s` bounds chunk size; queue
  depth is observable; degradation is graceful (text lags, never lost). Document
  that streaming is tuned for `small`/`medium`.
- **Punctuation/capitalization at chunk joins** (independent chunks) → each chunk
  may start capitalized / lack trailing punctuation. Mitigation: accept as a
  known trade-off of append-only streaming; inter-chunk spacing only. Not worth
  cross-chunk priming, which reintroduces hallucination risk.
- **Onset clipping** (resolved) → an early design dropped "leading silence" and
  seeded the noise floor from the first block, which ate the start of speech when
  a recording began without a silent lead-in (verified: `fr_speech` streamed to
  "le test est fini" instead of "Test 1-2-3, le test est fini"). Fix: the
  segmenter never drops audio (`keep` is always true) and the noise floor is
  seeded low, so the onset is always detected and buffered. The per-chunk VAD
  filter trims real silence.
- **Concurrent injection scrambles keystrokes** (resolved) → injection is
  normally fire-and-forget (one `osascript`/`xdotool` worker thread per call).
  Streaming injects many chunks, so concurrent injections raced and interleaved
  keystrokes, and `queue.join()` completed before typing finished. Fix: the chunk
  worker injects with `blocking=True`, running injection inline so chunks type in
  order and the FSM leaves TRANSCRIBING only once typing is done.
- **Very noisy room** → with the low-seeded floor, ambient above the minimum
  threshold can read as speech, so pause-cutting degrades to the `max_chunk_s`
  forced flush. Bounded and never lossy (VAD trims); acceptable for a dictation
  tool where not losing words dominates.
- **Focus changes mid-dictation** → incremental injection types into whatever is
  focused at emit time; a focus switch scatters partial text. Same failure exists
  today (smaller window). Mitigation: documented; no behavioural guard in v1.
- **Adaptive threshold mis-tracks in very noisy/very quiet rooms** → over- or
  under-segmentation. Mitigation: `silence_factor` and `pause_ms` are
  user-tunable; `max_chunk_s` guarantees forward progress regardless.
- **Tiny silence-bounded blips** → handled by the per-chunk `min_chunk_s` /
  `min_recording_duration` discard reused from the existing guard.

## Migration Plan

- Ship `streaming_enabled` defaulting to a chosen value (recommend **true** once
  validated, **false** initially behind config). Config migration adds the new
  keys with defaults; existing configs keep working.
- Rollback: set `streaming_enabled=false` → legacy record-then-transcribe path,
  no code revert needed.

## Open Questions

- Default for `streaming_enabled` at first release: on by default, or opt-in for
  one release while validating segmentation quality on real mics?
- Exact default `pause_ms` / `silence_factor` — pick starting values, then tune
  against a few real recordings (fast/slow speakers, noisy room).
