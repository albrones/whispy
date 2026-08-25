## Why

Whispy transcribes push-to-talk dictation by cutting the recording into
silence-bounded chunks and running each one through `faster-whisper`. Whisper is
the wrong shape for that workload, and measurements on the real fixtures
(M1 Pro, `small` int8 vs `parakeet-tdt-0.6b-v3` int8 on `CPUExecutionProvider`)
show it costs correctness, not just speed:

- **Latency floor.** Whisper pads every input to a 30 s window, so a 0.5 s chunk
  costs 0.53 s and a 2.2 s chunk costs 0.63 s — regardless of content. Parakeet
  is proportional to real audio: 0.04 s and 0.075 s. On a 6–8 s dictation split
  into 1.5 s chunks, end-to-end goes from 2.5–7.9 s to 0.26–0.36 s.
- **Degenerate repetition loops.** On short chunks Whisper emits runaway output
  ("grand" ×100, "de la vidéo" ×60, "Macintosh" ×55). This is injected into the
  user's active text field. Parakeet's transducer decoder cannot loop this way
  and did not do so once across the whole fixture set.
- **Forced language is a liability.** With `language="fr"` (a supported config
  value) Whisper *translates* English speech: "the test is done" → "le test est
  fait". Parakeet auto-detects per utterance and handled FR→EN code-switching
  inside a single clip correctly, with no language parameter at all.
- **`initial_prompt` poisons the output.** The `custom_vocabulary` terms leak
  into transcriptions verbatim ("… sur la boitée. Orange principal, `int8,
  OpenSpec` Il faudra penser à …") — the same class of failure that got adaptive
  correction deleted (issue #8).
- **Silent truncation.** In the non-streaming path a 22 s recording transcribes
  to a single sentence; ~90% of the audio is dropped with no error.
- **Hallucination on silence** is why `strip_whisper_credit`, the hallucination
  phrase list, and `min_recording_duration` exist at all. Parakeet's failure on
  silence is far smaller — short fillers rather than long corpus artifacts, and
  never a repetition loop — but it is not zero, so an RMS gate replaces the
  phrase list rather than nothing replacing it.

The cost is bounded and known: +440 MB RSS (923 MB → 1366 MB), +173 MB on disk
(466 MB → 639 MB), 25 languages instead of 99, and weaker recognition of unusual
proper nouns now that the decoder cannot be biased. `onnxruntime`, `numpy`, and
`huggingface_hub` are already bundled in the `.app`, so the swap *removes* four
dependencies (`faster-whisper`, `ctranslate2`, `tokenizers`, `av`) and adds one
pure-Python package.

## What Changes

- **BREAKING (user-visible):** replace `faster-whisper` with
  `nvidia/parakeet-tdt-0.6b-v3` (int8 ONNX, via `onnx-asr`) as the only
  transcription backend. Whisper is removed, not kept behind a flag.
- **BREAKING (config):** drop `model_size`, `beam_size`, `best_of`, `language`,
  and `auto_detect_min_duration` from `DEFAULT_CONFIG`. Parakeet ships in one
  size, decodes greedily, and detects language itself. Existing config files
  keep working: unknown keys are dropped by the existing validation pass.
- **BREAKING (UI):** remove the "Model" and "Language" submenus from the macOS
  menu bar and the Linux tray. They no longer configure anything.
- Pin the execution provider to `CPUExecutionProvider`. The onnxruntime default
  on macOS enrols CoreML, which on an M1 Pro is 2× slower *and* peaks at
  6 070 MB RSS versus 1 366 MB. The pin is settled, not provisional: the CPU
  path already clears the latency budget by an order of magnitude.
- `custom_vocabulary` survives as post-hoc near-miss correction in
  `text_cleaner.py` (stdlib `difflib` + `unicodedata`, no new dependency) instead
  of decoder biasing. A token is corrected when its **spelling** or its **sound**
  matches a configured term — the phonetic path is what catches "parakite" for
  "Parakeet", which spelling similarity scores below the cutoff. Weaker than
  `initial_prompt` by construction, and no longer capable of leaking prompt text
  into output.
- Keep the 0.6b model rather than moving to a larger one: `canary-1b-v2` measured
  *worse* on technical vocabulary (62% of expected terms vs 72%) while costing
  2.7× the time and 1.75× the memory, and it translates to English unless given
  an explicit language.
- Delete the Whisper-specific text cleaning — credit/watermark prefixes and the
  hallucination phrase list — along with the model that emitted them, and add an
  **RMS silence gate** in its place. Parakeet does not hallucinate the way
  Whisper did, but the real-model tier showed it invents short fillers (`Yeah.`,
  `Okay.`, `Mm-hmm.`, `No.`, `Thank you.`) on near-silent audio, including a
  realistic quiet-room noise floor. Gating on energy rather than on text is what
  makes this safe: `Okay.` and `No.` are legitimate one-word dictations, so a
  blocklist would delete real speech. Measured separation is 220×.
- `WHISPER_MODEL` disappears from `install.sh`/`scripts/bootstrap.sh`; the
  uninstall cache glob becomes the Parakeet ONNX snapshot;
  `doctor.py`'s model check follows.
- `packaging/macos/setup_app.py`: drop `faster_whisper`, `ctranslate2`,
  `tokenizers`, `av`; add `onnx_asr`.
- Attribute the model: Parakeet is CC-BY-4.0, so README, the website, and a new
  `NOTICE` file SHALL credit NVIDIA. Whispy stays GPL-3.0; weights are
  downloaded at runtime, never redistributed.
- Documentation and site sync: README, FEATURE_MATRIX, docs/SPECIFICATION.md,
  CHANGELOG, `.github/ISSUE_TEMPLATE/bug_report.md`, and `website/index.html`
  (which names `faster-whisper` in the privacy copy and shows the Model and
  Language rows in the animated menu-bar demo).
- Version bump to `2.0.0` — the config schema and the menu both change.

## Capabilities

### New Capabilities

- `asr-backend`: which model runs, on which runtime, with which execution
  provider and quantization; where the weights are cached; how a missing model
  is obtained and how a load failure is reported.

### Removed Capabilities

<!-- none -->

### Modified Capabilities

- `core-engine`: configuration no longer carries model size, language, or
  decoding parameters; `custom_vocabulary` no longer reaches the transcription
  call; the model-load-failure contract now describes the Parakeet loader.
- `transcription-quality`: real-model scenarios run against Parakeet with no
  language argument; the `hotwords`/`initial_prompt` biasing scenarios are
  replaced by a post-hoc vocabulary-correction scenario; silence is stopped by
  an RMS gate before the model rather than filtered out of its output.
- `audio-capture`: the transcription call loses `language`, `beam_size`,
  `best_of`, `vad_filter`, `condition_on_previous_text`, `temperature`, and
  `initial_prompt`; the auto-detect-duration warning and the credit-stripping
  requirement go with them. The short-clip discard guard stays, rejustified, and
  an RMS silence gate plus its measurement helper are added.
- `streaming-transcription`: per-chunk guards lose the Whisper-specific
  parameters; chunk independence is now a property of the backend rather than a
  flag that must be passed.
- `text-cleaning`: remove credit-prefix stripping and the hallucination phrase
  list; add near-miss custom-vocabulary correction.
- `user-facing-docs`: the config key reference tracks the reduced
  `DEFAULT_CONFIG`; docs SHALL name Parakeet and carry the CC-BY-4.0
  attribution.
- `promotional-website`: privacy copy names Parakeet, not faster-whisper; the
  menu-bar demo drops Model and Language; the page carries model attribution.
- `macos-install`: uninstall removes the Parakeet ONNX snapshot, still scoped
  inside the shared HuggingFace hub cache.
- `ci-cd-pipeline`: the `WHISPER_MODEL` requirement is removed; the macOS
  real-seam tier loads Parakeet.

## Impact

- Code: `src/whispy/core/engine.py` (loader, four transcription call sites,
  config constants), `src/whispy/core/audio.py` (`transcribe`),
  `src/whispy/core/config.py` (`DEFAULT_CONFIG`, `MODEL_PRESETS`,
  `SUPPORTED_LANGUAGES`, `VALID_MODEL_SIZES`, validation),
  `src/whispy/core/text_cleaner.py`, `src/whispy/doctor.py`,
  `src/whispy/ui/menu_bar.py`, `src/whispy/platform/linux/tray.py`,
  `packaging/macos/setup_app.py`, `pyproject.toml`.
- Tests: `tests/conftest.py` (the `WhisperModel` mock), `test_audio.py`,
  `test_engine.py`, `test_language_detection.py`,
  `test_transcription_quality.py`, `test_text_cleaning.py`,
  `test_config_validation.py`, `test_doctor.py`, `test_docs.py`,
  `test_website.py`, `test_install_scripts.py`, `test_menu_bar.py`,
  `tests/validation/harness.py`.
- Docs/site: `README.md`, `FEATURE_MATRIX.md`, `CHANGELOG.md`,
  `docs/SPECIFICATION.md`, `docs/transcription-quality-and-memory.md`,
  `.github/ISSUE_TEMPLATE/bug_report.md`, `website/index.html`, new `NOTICE`.
- Installer: `install.sh`, `scripts/bootstrap.sh`.
- User data: on first run after upgrade the daemon downloads 639 MB. The old
  `models--Systran--faster-whisper-*` snapshots are orphaned; uninstall stops
  offering to remove them, so the upgrade path SHALL tell users where they are.
- Ordering: depends on `remove-adaptive-correction` landing first — it touches
  the same `custom_vocabulary` neighbourhood.
