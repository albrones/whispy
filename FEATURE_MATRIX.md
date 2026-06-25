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
| Config live-reload (model swap) | both | unit-mocked | `tests/test_e2e.py::TestEngineLifecycle` | `needs_reload` flag triggers async model load |
| State machine transitions | both | unit-pure | `tests/test_state_machine.py` | idle→recording→transcribing→idle, guards |
| Text cleaning | both | unit-pure | `tests/test_text_cleaning.py` | trailing space, casing, filler |
| Language detection / selection | both | unit-mocked | `tests/test_language_detection.py` | fr/en, auto-detect min duration |
| Engine + audio + FSM integration | both | unit-mocked | `tests/test_e2e.py::TestFullEngineAudioFSMIntegration` | mocked audio/whisper |
| HTTP API endpoints | both | unit-mocked | `tests/test_api/` | status/config/last-transcription/start/stop |
| Event decode (keycode → trigger) | macOS | unit-pure | `tests/test_event_decode.py` | Fn keycode 63 mapping |
| Text injection logic (both modes) | both | unit-mocked | `tests/test_injection.py` | clipboard + keystroke, quote escaping |
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
| Language selection honored | both | live-driven | `tests/test_e2e_smoke.py::TestLiveDriveCycle`, `tests/test_e2e_smoke_linux.py::TestLiveDriveCycle` | fr/en fixtures decode in the configured language |
| Config change applies over HTTP | both | live-driven | `tests/test_e2e_smoke.py::TestLiveDriveCycle`, `tests/test_e2e_smoke_linux.py::TestLiveDriveCycle` | `/config` sets language; `/config` GET reflects it |
| /transcribe-file endpoint (deterministic seam) | both | unit-mocked | `tests/test_api/` | transcribes given WAV with current config, no inject/delete |
| Event tap arms with permission | macOS | live-driven | `tests/test_e2e_smoke.py::TestLiveEventTap` | CGEventTap; UNVERIFIED w/o Input Monitoring |
| pynput listener arms under X11 | Linux | live-driven | `tests/test_e2e_smoke_linux.py::TestLivePynputListener` | UNVERIFIED on Wayland / no perm |
| Clipboard round-trip (osascript) | macOS | live-driven | `tests/test_e2e_smoke.py::TestRealOsascriptClipboard` | UNVERIFIED w/o osascript |
| xdotool injection wires + runs | Linux | live-driven | `tests/test_e2e_smoke_linux.py::TestXdotoolInjection` | UNVERIFIED w/o xdotool / X11 |
| Push-to-talk → text in focused app | macOS | manual-ui | operator | hold Fn, speak, release, confirm glyphs land |
| Push-to-talk → text in focused app | Linux | manual-ui | operator | hold Right Ctrl, speak, release, confirm glyphs land |
| Menu bar dropdown renders + reacts | macOS | manual-ui | operator | status dot, settings, model/lang checks |
| Tray menu renders + reacts | Linux | manual-ui | operator | pystray labels, toggles |
| Recording visualization (waveform/indicator) | both | manual-ui | operator | window appears while recording, animates |
| Copy-to-clipboard toggle pastes text | both | manual-ui | operator | enable in menu/tray, dictate, confirm Cmd/Ctrl+V pastes |
| Model selection change takes effect | both | manual-ui | operator | switch model in menu, confirm reload + transcription |
| Restart from menu relaunches daemon | macOS | manual-ui | operator | menu → Restart; daemon comes back on :9090 |
| Quit from menu stops daemon | both | manual-ui | operator | menu/tray → Quit; daemon process exits |
