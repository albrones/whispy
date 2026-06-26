## 1. Config

- [x] 1.1 Add `streaming_enabled`, `pause_ms`, `min_chunk_s`, `max_chunk_s`, `silence_factor` to `DEFAULT_CONFIG` in `core/config.py` with starting defaults (streaming off initially; pause_ms≈600, min_chunk_s≈0.4, max_chunk_s≈12, silence_factor≈2.5)
- [x] 1.2 Add type/range validation for each new key (fall back to default + warn on invalid)
- [x] 1.3 Add config migration so existing configs gain the new keys with defaults
- [x] 1.4 Tests in `test_config_validation.py`: defaults present, invalid values fall back, migration adds keys

## 2. Silence/length segmentation detector

- [x] 2.1 Implement a pure segmentation state machine (SPEAKING/SILENCE) driven by per-block level + elapsed time, with adaptive noise-floor threshold (`level < noise_floor × silence_factor`) and a `max_chunk_s` forced flush
- [x] 2.2 Suppress emission of chunks that never contained speech
- [x] 2.3 Unit-test the detector in isolation (feed synthetic level/time sequences): pause emits, max-length force-flushes, pure silence emits nothing, threshold adapts to noise floor

## 3. Capture-side PCM buffering + chunk emission

- [x] 3.1 In `core/audio.py`, when streaming is enabled, accumulate int16 frames for the current chunk and run the detector inside the capture callback (reusing the computed RMS), keeping detector work inside the callback's exception containment
- [x] 3.2 On a chunk boundary, write the accumulated audio to a unique 16 kHz mono WAV and hand it to the chunk pipeline
- [x] 3.3 Keep the legacy single-file capture path unchanged when streaming is disabled
- [x] 3.4 Add a tail-flush entry point used on stop to emit the final in-progress chunk
- [x] 3.5 Tests: streaming buffers/emits per boundary; non-streaming capture unchanged; detector error is contained, not raised

## 4. Chunk pipeline (engine, FSM-1)

- [x] 4.1 Add an ordered (FIFO) chunk queue and a single transcription/injection worker in `core/engine.py`, active during `RECORDING`
- [x] 4.2 Per chunk: apply `min_chunk_s`/`min_recording_duration` discard, transcribe with existing params (`vad_filter`, `temperature=0`, `condition_on_previous_text=False`, custom-vocabulary `initial_prompt`), strip credit/clean
- [x] 4.3 Inject each chunk's text in order, append-only, with inter-chunk spacing; clean up each chunk WAV after use
- [x] 4.4 Wire trigger-release to flush the tail chunk via the worker; route the tail flush through `TRANSCRIBING → IDLE` so `is_transcribing` denotes only the tail
- [x] 4.5 Ensure no new FSM state is added; `RECORDING` stays the sole recording owner
- [x] 4.6 Tests in `test_engine.py`: chunks inject in order; mid-recording chunks do not set `is_transcribing`; tail flush returns FSM to IDLE; empty/error chunk does not wedge the worker; chunks transcribed independently (no previous-text feedback)

## 5. Integration + validation

- [x] 5.1 End-to-end (mocked model) test: streaming enabled produces ordered incremental injections across multiple chunks; streaming disabled matches legacy single-block behaviour
- [x] 5.2 Manual/real-mic check: long dictation streams text incrementally and post-release wait is bounded to the last chunk
- [x] 5.3 Update `docs/transcription-quality-and-memory.md` (or a new doc) noting streaming, its config keys, and the `large-v3` RTF caveat
- [x] 5.4 Decide and set the first-release default for `streaming_enabled` (resolve the design Open Question)

## 6. Settings UI toggle

- [x] 6.1 Add a "Streaming transcription" checkbox to the menu-bar Settings section (mirrors the clipboard toggle); reflect `streaming_enabled` and refresh on appearance change
- [x] 6.2 Make `update_config` apply streaming changes at runtime: re-wire the audio engine and start/stop the chunk worker without a restart
- [x] 6.3 Add a deterministic streaming live-drive seam (`POST /stream-file` + `engine.stream_file` + `AudioEngine.segment_pcm`) and wire `run_streaming_checks` into the harness
- [x] 6.4 Tests: menu toggle persists the flag; runtime enable/disable wires audio + worker; `/stream-file` endpoint; `segment_pcm`/`stream_file` units; matrix rows added

## 7. Bug fixes found in end-to-end testing

- [x] 7.1 Fix onset clipping: segmenter never drops audio (`keep` always true) and seeds the noise floor low, so speech at recording start is not lost (verified: `fr_speech` streams to the full text, not a truncated one)
- [x] 7.2 Fix keystroke scrambling: chunk worker injects with `blocking=True`; add `blocking` param to both injectors (macOS osascript + Linux xdotool) so consecutive chunks type in order and the FSM completes only after typing
- [x] 7.3 Regression tests: onset-not-clipped (segmenter), ordered injection under latency (engine), blocking-inject inline (injection); re-run live-drive to confirm streaming text matches the whole-file path

## 8. Rework after real-mic testing (focus loss + garbled cuts)

- [x] 8.1 Replace the energy threshold with WebRTC VAD (`webrtcvad-wheels`) for gain-independent, mid-word-safe segmentation; energy gate fallback when the dep is absent. Config: `silence_factor` → `vad_aggressiveness`
- [x] 8.2 Add `streaming_inject_mode` ("on_release" default | "live"): on_release assembles chunks transcribed during recording and types once at release (fixes focus loss in full-screen apps); live types per chunk
- [x] 8.3 Fix `stream_file` passing the removed `silence_factor` to `segment_pcm` (crashed `/stream-file`); harden the endpoint to return 500 instead of dropping the connection
- [x] 8.4 Regression tests: VAD segmenter (frame alignment, onset, energy fallback), on_release accumulation, real-segmentation stream_file path (catches kwarg mismatch); re-run live-drive (streaming text matches whole-file, 2 clean chunks)

## 9. Drop live mode; streaming on by default

- [x] 9.1 Remove `streaming_inject_mode` / live injection: chunk worker only accumulates; FSM worker types the assembled text once on release. Drop the `blocking` inject param (revert both injectors to async-only) and the menu "Type while speaking" item
- [x] 9.2 Default `streaming_enabled` to true (menu + config); update validation/tests
- [x] 9.3 Update tests/docs/spec: remove live + blocking tests, assert on-release assembly, default-on

## 10. Remove streaming menu toggle; align settings checks

- [x] 10.1 Remove the "Streaming transcription" menu item (streaming is always on); keep `streaming_enabled` config-gated for the legacy fallback
- [x] 10.2 Render boolean settings toggles with a trailing check (`menu_theme.toggle_title`) so titles left-align with Model/Language; mirror on the website mockup (`dd-toggle`)
- [x] 10.3 Tests: toggle_title trailing-check units; drop the streaming-toggle menu test
