## 1. Core (`whispy-core`)

- [x] 1.1 `Word` and `Transcriber::transcribe_timed` (provided, `None`); `Lazy` forwards it
- [x] 1.2 Parakeet timed words from the TDT frames; invariant test against `transcribe` and monotonic times on a reference clip (skipped when the model is missing)
- [x] 1.3 `Pipeline::transcribe_timed` (gates and louder copy, no trim, no padding, primary only)
- [x] 1.4 `stream::Streamer` (push, is_pass_due, pass, finish, committed) with the scenarios of `v2-transcription-core` as unit tests on a scripted timed engine

## 2. Pill caption (`whispy2`)

- [x] 2.1 `feedback::Caption` and `Feedback::caption` (default no-op)
- [x] 2.2 Wide pill geometry in `pill_geometry.rs`, unit-tested
- [x] 2.3 The macOS pill draws the caption (committed white, provisional faded, head truncation), cleared at each recording

## 3. App wiring (`whispy2`)

- [x] 3.1 `StreamAudio` / `FinishStream` / `DiscardStream` jobs; the worker coalesces and runs a pass when due
- [x] 3.2 Committed text typed, caption sent to the controller and to the pill while recording; one log line of counts per pass
- [x] 3.3 Deaf take, watchdog to the clipboard, failed insertion, lost clips and journal kept; controller tests for the streaming path and hold mode

## 4. Bench (`banc --streaming`)

- [x] 4.1 One block vs pieces vs rolling, on reference clips (two sentences back to back, one with a 1 s pause inside a sentence, the run-on clip) and the labelled speech clips ≥ 8 s, simulated at real-time pace
- [x] 4.2 WER, extra sentence ends, commit delay, stop latency, pass cost; exit 1 on a failed criterion; 180 s memory probe kept

## 4b. After the first manual tests (2026-11-24)

- [x] 4b.1 The pill shows the words in every dictation (hold mode, setting off); only « Type while speaking » types them live
- [x] 4b.2 The caption sits under the bars, which stay centred and in place

## 5. Delivery

- [x] 5.1 `v2/README.md` describes the new « Type while speaking »
- [ ] 5.2 v2/ gate green (`cargo test --release`, `cargo clippy --release --all-targets -- -D warnings`), bench criteria proven, `make v2-reinstall`, manual check in TextEdit
