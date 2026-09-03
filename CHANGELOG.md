# Changelog V1 — Whispy

## [2.0.0]

### Changed

- **BREAKING — transcription now runs on NVIDIA Parakeet TDT 0.6b v3.**
  `faster-whisper` is removed, not kept behind a flag. The model is loaded as
  int8 ONNX through `onnx-asr`, pinned to `CPUExecutionProvider`. Measured on an
  Apple M1 Pro against the committed fixtures: a 0.5 s chunk goes from 0.529 s to
  0.037 s, a 2.2 s clip from 0.628 s to 0.075 s, and a 6–8 s dictation split into
  1.5 s chunks from 2.5–7.9 s to 0.26–0.36 s. Costs: resident memory rises from
  ~923 MB to ~1366 MB, the download from 466 MB to 639 MB, and language coverage
  drops from 99 languages to 25 European ones.
- **BREAKING — five config keys are gone**: `model_size`, `language`,
  `beam_size`, `best_of`, `auto_detect_min_duration`. Parakeet ships in one size,
  decodes greedily, and detects language itself, so none of them configured
  anything any more. Existing config files keep loading — unknown keys were
  already dropped by validation — and lose the stale keys on the next save.
- **BREAKING — the Model and Language submenus are gone** from the macOS menu bar
  and the Linux tray, along with the `WHISPER_MODEL` environment variable in
  `install.sh` / `scripts/bootstrap.sh`.
- `custom_vocabulary` now corrects near misses *after* transcription instead of
  biasing the decoder through `initial_prompt`. A word is corrected when its
  **spelling** or its **pronunciation** matches one of your terms — so `wispy`
  becomes `Whispy` and `parakite` becomes `Parakeet`, the latter being a case
  spelling similarity alone scores too low to catch. Stdlib only (character
  cutoff 0.80, phonetic cutoff 0.90, tokens under 4 characters skipped).
  Measured false-correction rate: 139 of 234 335 dictionary words (0.059%).
  Weaker than decoder biasing on distant misrenderings, but it can no longer
  leak vocabulary terms into text you did not say — which the prompt
  demonstrably did. **Put proper nouns, brand names and anglicisms here**; it is
  the intended fix for them.
- `POST /config` no longer triggers a model reload; no setting selects a model.

### Fixed

- **French dictation could come back partly in English.** Not a
  language-detection failure: streaming transcribes every chunk as an
  independent model call, and the guard meant to stop over-short chunks
  measured the wrong quantity. It compared *total buffered* seconds against
  `min_chunk_s` (0.4 s), but the same condition already required 0.6 s of
  silence, so at the shipped defaults the guard could never bind — a single
  short word followed by a pause became a chunk of its own, and the
  multilingual transducer resolved it into another language. Measured through
  the production transcription gates: an isolated "oui" chunk of 1.11 s total
  but **0.39 s voiced** came back as `We` in 5 of 5 realizations, and "bref"
  (0.51 s, all voiced) as `Dress.` in 6 of 6, while the same speech inside the
  19.45 s dictation was correct on every word. Prepending 0.5 s of preceding
  speech — 1.61 s total, **0.72 s voiced** — fixed it 5/5, so elapsed duration
  is not the discriminator and voiced duration is. The guard now measures
  voiced seconds, exposed as the new `min_speech_s` key (default 0.7, between
  the two measured regimes); a chunk holding less simply is not emitted at a
  pause, so the short word rides along with its neighbour. `max_chunk_s` still
  force-flushes and the tail flush is unchanged, so no audio is held
  indefinitely and a dictation of one short word is still transcribed. The
  default comes from synthesized speech with a single voice, which is why it is
  a config key: a real microphone or room may move where VAD counts a frame as
  voiced.
- **The five-minute recording limit no longer discards your text.** The
  watchdog that stops a recording at `RECORDING_MAX_S` used to recover by
  clearing `_chunk_texts`, silently throwing away everything transcribed so
  far — a backstop written back when "no push-to-talk hold lasts minutes," an
  assumption toggle mode below breaks. It now stops the recording gracefully,
  assembles the transcript, copies it to the clipboard, and shows a
  notification instead of typing into a field that may no longer be focused
  after five minutes.
- **Long recordings were silently truncated.** In the non-streaming path a
  22-second recording transcribed to a single sentence, dropping roughly 90% of
  the audio with no error and no log line. If you ever dictated a long passage
  and found most of it missing, this was why.
- **A configured language could mistranslate.** With `language="fr"` set — a
  supported value — English speech was transcribed *into French* rather than
  recognized ("the test is done" → "le test est fait").
- **Short chunks could produce runaway repetition.** Streaming chunks of ~1.5 s
  could make the decoder loop, injecting text like `"grand"` repeated a hundred
  times into the active field. The transducer architecture cannot fail this way.
- `AudioEngine.transcribe` had a `language="auto"` default that raised
  `ValueError`, unreachable only because config validation restricted the value
  to `fr`/`en`.

### Added

- **Toggle trigger mode.** A new `trigger_mode` config key — `"hold"` (default,
  push-to-talk, unchanged) or `"toggle"` — lets a trigger press start
  dictation and the next press stop it, so recording can outlive the key
  press. Exposed as a **Toggle mode** checkbox in the menu bar / tray
  Settings, and composable with any trigger.
- **Two new trigger presets**, `⌃⌥⌘E` and `⌃⌥⌘F` (Control+Option+Command plus a
  letter). They are labelled by their keys, nothing more — the macOS event tap
  is listen-only and cannot consume the event, so a combination the focused
  app also binds would fire that app's own shortcut too; the Hyper tier is the
  only multi-key combination left unbound by convention.
- **Silence gate.** Near-silent audio is now discarded before it reaches the
  model. Parakeet is far better behaved than Whisper on non-speech — no corpus
  artifacts, no repetition loops — but it does invent short fillers (`Yeah.`,
  `Okay.`, `Mm-hmm.`, `No.`, `Thank you.`) on silence and on a realistic
  quiet-room noise floor, which would otherwise be typed into the active field.
  The gate measures energy, not text, because `Okay.` and `No.` are legitimate
  one-word dictations. Every observed false positive measured ≤0.00065
  normalized RMS against ≥0.147 for real speech, so the 0.005 threshold has a
  220× margin, and it fails open — an unmeasurable clip is still transcribed.
- **Speech gate.** Non-speech that is merely *loud* clears the silence gate — a
  noisy room, a fan, mains hum all measure 0.010–0.035 normalized RMS against the
  0.005 threshold — and reached the model, which answered roughly 3% of
  realizations with a filler (3 of 100 measured). A clip now also needs 0.20 s of
  WebRTC-VAD voiced frames, which took that to 0 of 100 with no effect on real
  speech. Reuses the `webrtcvad` dependency the streaming segmenter already
  pulls, and fails open like the silence gate. Deliberately an absolute duration
  and not a voiced/silent ratio: one word inside a 10 s key-hold is 6% voiced,
  the same ratio as steady noise, while its voiced duration (0.66 s) is
  unmistakable. Known ceiling — past ~0.04 RMS the VAD labels steady noise
  voiced, so louder rooms are still the model's problem.

  Platform-neutral: `webrtcvad-wheels` carries no platform marker and publishes
  manylinux x86_64/aarch64 wheels, the gate sits in the shared core, and the
  capture format is the same 16 kHz mono int16 on both. Wayland is unaffected —
  the gate runs upstream of text injection, which is where Wayland's existing
  limitation lives.

### Removed

- Whisper watermark/credit stripping and the hallucination phrase blocklist in
  `text_cleaner.py`. Those phrases had a single emitter and it is gone; the
  replacement failure mode is handled by the silence gate above instead.
- Dependencies `faster-whisper`, `ctranslate2`, `tokenizers`, and `av`, including
  from the macOS `.app` bundle. `onnx-asr` replaces them and adds no native
  dependency the bundle did not already carry.

### Notes for upgraders

- First run after upgrading downloads the new model (639 MB).
- The old cache at `~/.cache/huggingface/hub/models--Systran--faster-whisper-*`
  is no longer used. `./install.sh --uninstall` points at it but will not delete
  another era's data — remove it by hand to reclaim the space.
- The model is licensed CC-BY-4.0 (© NVIDIA); Whispy stays GPLv3. Weights are
  fetched at runtime and never redistributed. See `NOTICE`.

## [Unreleased]

### Added
- **Trigger key selection from the menu (macOS).** The **Settings → Trigger**
  menu lets you pick the push-to-talk key from presets (Fn, Right Command,
  Right Option, F13); the change applies live, with no restart.
- Module `src/whispy/core/config.py`: config validation and migration.
- Module `src/whispy/core/text_cleaner.py`: text cleaning.
- Error-handling tests (`test_error_handling.py`): missing sox, unavailable
  microphone, engine without a model.
- Automatic config migration (versioning via `_version`).
- Validation of config values.

### Changed
- **macOS install consolidated on `Whispy.app`.** A single command
  (`curl … | bash`) detects the OS: on macOS it builds and installs the
  signed `Whispy.app` bundle into `/Applications`; Linux/X11 keeps venv +
  `systemd --user`. `install.sh` no longer creates a LaunchAgent on macOS
  (autostart is the in-app "Start at login" toggle). Existing installs have
  their `com.whispy` LaunchAgent removed automatically (ending the
  double-daemon-on-`:9090` issue).
- Extracted `load_config`/`save_config` from `engine.py` into `config.py`.
- Unified model loading (`_load_model_async` + `_load_model_on_device` →
  `_load_model_async`).
- Clarified the active visualization (indicator by default).
- Improved logging of FSM transitions.
- Fixed hanging tests (mocked the `afplay` subprocess).

### Removed
- **Homebrew formula.** `packaging/homebrew/whispy.rb`, the tap bump in
  `release.yml`, the `HOMEBREW_TAP_TOKEN` secret, `docs/homebrew.md` and its
  test. (A *Cask* — the correct tool for a GUI app — remains a future option,
  blocked on notarization.)
- `whispy_legacy.py` (redundant with `whispy_daemon.py`).

### Fixed
- **Ghost checkmark in the menu.** An unchecked row kept its green checkmark
  (AppKit's `attributedTitle` takes priority over `.title`); also affected
  Model/Language and the clipboard toggle.
- **Bug: freeze at recording start.** `_wait_for_recording_ready` never
  unblocked the main thread when sox failed or timed out (missing
  `ready.set()`) — the daemon could freeze. `ready.set()` is now guaranteed
  via `finally`.
- **Audio visualization replaced.** The old ferrofluid visualization never
  rendered (the renderer targeted nonexistent APIs:
  `NSApplication.mainScreen`, `NSApplication.graphicsContext`, a mix of
  NSBezierPath/CGContext). Replaced with a simple, reliable **waveform**
  indicator (`ui/waveform_window.py`): a pill centered at the bottom of the
  screen with bars reacting to the mic, rendered with NSBezierPath/NSColor.
  Rewired into the menu bar lifecycle.
- Fixed 21 broken/blocking tests (event tap callback signature, FSM recovery
  behavior, ferrofluid wiring, API fixture that hung on transcription).
- Cleaned up duplicate keycodes in `event_tap.py` (`51` mapped both `m` and
  `backspace`, `f13`-`f20` were duplicated).

### Tooling & quality
- Diagnostic command `python whispy_daemon.py --doctor` (`make doctor`):
  checks sox, the model, the 3 macOS permissions, and the daemon status.
- Migrated linting to **Ruff** (lint + format); removed flake8.
- `Makefile`, `.pre-commit-config.yaml`, dev dependency `ruff`.
- CI: Python 3.10/3.11/3.12 matrix, `ruff check` + `ruff format --check`.

### Open source
- `CONTRIBUTING.md`, `CODE_OF_CONDUCT.md`, issue and PR templates.
- Real repository URLs (`albrones/whispy`); placeholders removed.
- `graphify-out/` removed from version control (generated artifact, ~7.6 MB)
  and ignored.
- Documentation moved under `docs/`; model storage documented.

### Documentation
- `AGENTS.md` updated with the actual project structure.
- `SPECIFICATION.md`: obsolete sections marked.
- README.md: up-to-date install instructions.

## [Cross-platform] — macOS + Linux/X11 (2026-06-17)

### Added
- **Linux (X11) support.** Whispy now runs on macOS **and** Linux/X11.
- **Ports-and-adapters layer** (`src/whispy/platform/`): `Protocol`
  interfaces for the OS-coupled seams (hotkey, injection, audio, tray) bound
  at runtime by `platform.detect()`.
- **Linux/X11 adapters**: hotkey via `pynput`, text injection via `xdotool`
  (+ `xclip`/`xsel`), tray via `pystray`. X11 session detection.
- **Configurable trigger key** (push-to-talk): default **Fn** on macOS,
  **Right Ctrl** on Linux; decoding by key match in addition to the Fn flag.
- **Cross-platform doctor**: checks the audio backend, `xdotool` (Linux),
  the model, platform permissions, and daemon status.

### Changed
- **Cross-platform audio backend.** Capture via `sounddevice` (PortAudio)
  instead of the `sox` subprocess, unified across macOS and Linux.
- **Per-OS dependencies** via PEP 508 environment markers:
  `pyobjc-framework-Quartz`/`rumps` on macOS, `pynput`/`pystray`/`Pillow` on
  Linux; `sox` removed.
- **macOS-only overlay.** On Linux in v1, state is exposed via the tray
  (no floating window).

### Documentation
- Promotional website and living docs (README, ROADMAP) updated: Whispy is
  no longer presented as macOS-only.

**Not covered (deferred):** Wayland, Windows, native Linux packaging, Linux
overlay.

## V1 Exit Criteria

- [x] All tests pass (297 passed, 0 failures, 0 hangs)
- [x] `install.sh` checks sox, permissions, LaunchAgent
- [x] Daemon starts and stops cleanly
- [x] Recording → transcription → injection works
- [x] Default config works without a config file
- [x] README.md up to date with install instructions
- [x] macOS permissions documented
- [x] CHANGELOG.md for V1
- [x] CI configured (GitHub Actions: Ruff lint + tests on Python 3.10–3.12)
