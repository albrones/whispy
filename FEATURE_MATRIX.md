# Whispy Feature Matrix

Single source of truth for **what works and how we know it**, on macOS and
Linux/X11. Run the whole thing with `make validate` (or the `/validate` skill).

## Maintenance rule (read before editing code)

Every bug fix or feature change MUST, in the same change:

1. **Update or add the row** below for the affected feature.
2. **Add a regression case at the lowest tier that can catch the defect:**
   - pure-logic defect → `unit-pure` test
   - real-seam defect (mic, model, injection, event tap) → `live-driven` assertion
   - human-only defect (physical keypress, visual confirm, menu/tray rendering) → `manual-ui` operator step

This keeps the validation system growing in lockstep with the code instead of
rotting. `make validate` flags rows whose **Verified by** target is missing.

Tiers are defined in `openspec/specs/TESTING-TIERS.md`.

## Verified-by reference grammar

- `path/to/test.py` or `path/to/test.py::Class::test` — a pytest target; the file must exist.
- `operator` — verified by the auto-generated operator checklist (only valid on `manual-ui` rows).
- `doctor` — verified by the preflight environment check.
- `TODO` — no verification yet; **counts as a gap** and is reported by the matrix linter.

## Matrix

| Feature | Platform(s) | Tier | Verified by | Notes |
|---------|-------------|------|-------------|-------|
| Config load / validate / persist | both | unit-pure | `tests/test_config_validation.py` | defaults, corrupt-file fallback, partial update |
| State machine transitions | both | unit-pure | `tests/test_state_machine.py` | idle→recording→transcribing→idle, guards |
| Text cleaning | both | unit-pure | `tests/test_text_cleaning.py` | whitespace normalization, custom-vocabulary near-miss correction |
| Silence gate (non-speech guard) | both | unit-pure | `tests/test_audio.py::TestAudioRms`, `::TestTranscribe` | RMS below threshold never reaches the model; fails open when unmeasurable |
| Speech gate (voiced-duration guard) | both | unit-pure | `tests/test_audio.py::TestSpeechGate`, `tests/test_segmentation.py::TestSpeechDuration` | non-speech above the RMS gate never reaches the model; one word in a long hold is not penalized; fails open without webrtcvad (rejection assertions skip there rather than fail) |
| Both gates against the real model | both | live-driven | `tests/test_non_speech_real.py` | pure silence and quiet-room noise across durations; loud white/brown/pink/hum/fan noise above the RMS gate; committed recordings still transcribe. Carries both markers, so `-m macos` and `-m linux` each run it |
| Gate thresholds vs. recorded audio | both | unit-pure | `tests/test_audio.py::TestSpeechGateAgainstCommittedAudio` | committed fixtures clear RMS by 5x and the speech gate by 3x; runs in the default tier, so ubuntu CI covers it too |
| Real speech clears the gate (synthesized) | macOS | live-driven | `tests/test_transcription_quality.py::TestSilenceGate`, `::TestShortDictation` | `say`-synthesized speech, sub-second words, and a word inside a 10s hold still transcribe |
| Audio duration detection | both | unit-pure | `tests/test_audio.py::TestAudioDurationDetection` | frames/rate; None for unreadable files |
| Engine + audio + FSM integration | both | unit-mocked | `tests/test_e2e.py::TestFullEngineAudioFSMIntegration` | mocked audio + ASR model |
| HTTP API endpoints | both | unit-mocked | `tests/test_api/` | status/config/last-transcription/start/stop |
| Event decode (keycode → trigger) | macOS | unit-pure | `tests/test_event_decode.py` | Fn keycode 63 mapping |
| Text injection logic (both modes) | both | unit-mocked | `tests/test_injection.py` | clipboard + keystroke, quote escaping |
| Injection waits for trigger release | both | unit-mocked | `tests/test_engine.py::TestInjectWaitsForTriggerRelease` | held modifier (e.g. Right Option) would mangle typed chars; bounded 10s wait |
| No double injection on rapid re-press | both | unit-mocked | `tests/test_engine.py::TestNoDoubleInjectionOnRapidRepress` | chunk buffer is consumed (swap-and-clear) by the worker, so a second stop_event never re-injects |
| Permissions detection | macOS | unit-mocked | `tests/test_permissions.py`, `doctor` | Input Monitoring / Accessibility / Mic |
| Linux adapters wiring | Linux | unit-mocked | `tests/test_linux_adapters.py` | pynput/pystray/xdotool selection |
| Doctor preflight report | both | unit-mocked | `tests/test_doctor.py`, `doctor` | injected checks |
| Real mic capture → valid WAV | macOS | live-driven | `tests/test_e2e_smoke.py::TestRealAudioCapture` | 16 kHz mono; UNVERIFIED w/o device |
| Real mic capture → valid WAV | Linux | live-driven | `tests/test_e2e_smoke_linux.py::TestRealAudioCapture` | 16 kHz mono; UNVERIFIED w/o device |
| Driven record→transcribe cycle (HTTP) | macOS | live-driven | `tests/test_e2e_smoke.py::TestLiveDriveCycle` | real daemon over HTTP; live mic, UNVERIFIED w/o speech |
| Driven record→transcribe cycle (HTTP) | Linux | live-driven | `tests/test_e2e_smoke_linux.py::TestLiveDriveCycle` | real daemon over HTTP; live mic, UNVERIFIED w/o speech |
| Silence yields empty transcription | both | live-driven | `tests/test_e2e_smoke.py::TestLiveDriveCycle`, `tests/test_e2e_smoke_linux.py::TestLiveDriveCycle` | fixture `silence.wav` via `/transcribe-file` |
| Transcription of known speech (fr) | both | live-driven | `tests/test_e2e_smoke.py::TestLiveDriveCycle`, `tests/test_e2e_smoke_linux.py::TestLiveDriveCycle` | fixture `fr_speech.wav`; expects tokens test+fini |
| Transcription of known speech (en) | both | live-driven | `tests/test_e2e_smoke.py::TestLiveDriveCycle`, `tests/test_e2e_smoke_linux.py::TestLiveDriveCycle` | fixture `en_speech.wav`; expects tokens testing+done |
| Language detected, not configured | both | live-driven | `tests/test_e2e_smoke.py::TestLiveDriveCycle`, `tests/test_e2e_smoke_linux.py::TestLiveDriveCycle` | fr/en fixtures each decode correctly with no language setting |
| Config change applies over HTTP | both | live-driven | `tests/test_e2e_smoke.py::TestLiveDriveCycle`, `tests/test_e2e_smoke_linux.py::TestLiveDriveCycle` | `/config` POST sets a value; `/config` GET reflects it |
| /transcribe-file endpoint (deterministic seam) | both | unit-mocked | `tests/test_api/` | transcribes given WAV with current config, no inject/delete |
| Streaming chunk transcription (HTTP) | both | live-driven | `tests/test_e2e_smoke.py::TestLiveDriveCycle`, `tests/test_e2e_smoke_linux.py::TestLiveDriveCycle` | fixture `fr_speech.wav` via `/stream-file`; expects tokens test+fini across chunks |
| Streaming segments on silence (≥2 chunks) | both | live-driven | `tests/test_e2e_smoke.py::TestLiveDriveCycle`, `tests/test_e2e_smoke_linux.py::TestLiveDriveCycle` | fr+silence+fr clip via `/stream-file` cut into ≥2 chunks |
| VAD speech segmentation detector | both | unit-pure | `tests/test_segmentation.py` | webrtcvad pause/max-length cuts, onset not clipped, energy fallback |
| Streaming types assembled text on release | both | unit-mocked | `tests/test_engine.py::TestStreamingChunkPipeline`, `tests/test_engine.py::TestStreamFileSeam` | chunks transcribed during recording, buffered, typed once on release (no mid-recording focus steal) |
| /stream-file endpoint (deterministic streaming seam) | both | unit-mocked | `tests/test_api/`, `tests/test_audio.py::TestSegmentPcm`, `tests/test_engine.py::TestStreamFileSeam` | replays WAV through live segmentation; returns ordered chunk texts, no inject/delete |
| Event tap arms with permission | macOS | live-driven | `tests/test_e2e_smoke.py::TestLiveEventTap` | CGEventTap; UNVERIFIED w/o Input Monitoring |
| pynput listener arms under X11 | Linux | live-driven | `tests/test_e2e_smoke_linux.py::TestLivePynputListener` | UNVERIFIED on Wayland / no perm |
| Clipboard round-trip (osascript) | macOS | live-driven | `tests/test_e2e_smoke.py::TestRealOsascriptClipboard` | UNVERIFIED w/o osascript |
| xdotool injection wires + runs | Linux | live-driven | `tests/test_e2e_smoke_linux.py::TestXdotoolInjection` | UNVERIFIED w/o xdotool / X11 |
| Push-to-talk → text in focused app | macOS | manual-ui | operator | hold trigger (Fn default), speak, release, confirm glyphs land |
| Trigger selectable from menu | macOS | manual-ui | operator | Settings → Trigger, pick a preset, hold the new key (live, no restart) |
| Push-to-talk → text in focused app | Linux | manual-ui | operator | hold Right Ctrl, speak, release, confirm glyphs land |
| Menu bar dropdown renders + reacts | macOS | manual-ui | operator | status dot, settings, model/lang checks |
| Tray menu renders + reacts | Linux | manual-ui | operator | pystray labels, toggles |
| Recording visualization (waveform/indicator) | both | manual-ui | operator | window appears while recording, animates |
| Copy-to-clipboard toggle pastes text | both | manual-ui | operator | enable in menu/tray, dictate, confirm Cmd/Ctrl+V pastes |
| Model selection change takes effect | both | manual-ui | operator | switch model in menu, confirm reload + transcription |
| Restart from menu relaunches daemon | macOS | manual-ui | operator | menu → Restart; daemon comes back on :9090 |
| Quit from menu stops daemon | both | manual-ui | operator | menu/tray → Quit; daemon process exits |
