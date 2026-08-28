## 0. Preconditions

- [x] 0.1 Confirm `remove-adaptive-correction` has landed (it deletes `corrections.py` and the `hotwords` channel this change's `custom_vocabulary` rewrite neighbours). Done 2026-08-25 as `bbeb376`, suite green (640 passed, 1 skipped). Note: it landed on `chore/general-audit-hardening`, not `main` — `main` is 11 commits behind and never carried adaptive correction, so branching off `main` would have dropped the audit hardening, CI fixes, and website SEO work.
- [x] 0.2 Branch `feat/parakeet-asr-backend` off `bbeb376` (tip of `chore/general-audit-hardening`), not off `main`, for the reason in 0.1. Merging the hardening branch into `main` stays a separate decision.
- [x] 0.3 Purge the fp32 spike weights from the HF cache (`encoder-model.onnx.data`, `encoder-model.onnx`, `decoder_joint-model.onnx` = 2.41 GB). Done 2026-08-25: cache is 639 MB, int8 verified to still load and transcribe.

## 1. Swap the backend

- [x] 1.1 `pyproject.toml`: replace `faster-whisper` with `onnx-asr[cpu,hub]` in `dependencies`. Leave the platform-conditional deps alone.
- [x] 1.2 `src/whispy/core/engine.py`: replace `_load_model()` (`:83`) — load `nemo-parakeet-tdt-0.6b-v3` via `onnx_asr.load_model(..., quantization="int8", providers=["CPUExecutionProvider"])`. Comment the provider pin with the measured reason (CoreML: 2× latency, 6070 MB peak RSS on M1 Pro) and note that `onnx_asr` also accepts a local model directory if the upstream conversion repo disappears.
- [x] 1.3 `engine.py`: drop the `local_files_only=True` → online retry dance and the `cpu_threads` computation if `onnx_asr` exposes no equivalent; keep `load_model_async`'s retry-once + `_notify_model_load_failed` contract intact.
- [x] 1.4 `engine.py`: remove the `from faster_whisper import WhisperModel` import and the `WhisperModel` type annotations (`:83`, `:165`).
- [x] 1.5 `src/whispy/core/audio.py`: rewrite `AudioEngine.transcribe()` (`:460`) — signature keeps `audio_path`, `model`, `min_recording_duration`; drop `language`, `beam_size`, `best_of`, `auto_detect_min_duration`, `initial_prompt`. Body calls `model.recognize(audio_path)`, keeps the short-clip discard guard and the `except Exception → return None` isolation, drops the `strip_whisper_credit` call and the auto-detect warning block.
- [x] 1.6 `audio.py`: delete `strip_whisper_credit` (`:93`) and update the module docstring (`:4`) which names faster-whisper.
- [x] 1.7 `engine.py`: simplify the four transcription call sites (`:517`, `:584`, `:678`, `:730`) — remove the `vocab`/`initial_prompt` construction (`:514`, `:582`, `:675`, `:725`) and the dropped keyword arguments.
- [x] 1.8 Manual smoke (needs a human at the keyboard — everything reachable without one is verified): run the daemon from the venv, dictate a French sentence and an English one without changing config, confirm both inject correctly. Automated half done — `_load_model` + `AudioEngine.transcribe` verified against the committed fixtures: load 1.21s, fr 0.097s, en 0.090s, silence -> None. **Validated by the operator on 2026-08-28** against the rebuilt `/Applications/Whispy.app` (commit `f9ed081`).

## 2. Shrink the configuration

- [x] 2.1 `src/whispy/core/config.py`: delete `VALID_MODEL_SIZES` (`:12`), `MODEL_PRESETS` (`:37`), `SUPPORTED_LANGUAGES` (`:16`), and the `model_size`, `language`, `beam_size`, `best_of`, `auto_detect_min_duration` entries from `DEFAULT_CONFIG`.
- [x] 2.2 `config.py`: remove the model-size and language validation branches (`:120-126`) and their migration paths. Verify that a pre-existing config carrying the removed keys loads without raising and drops them on next save.
- [x] 2.3 `engine.py`: update `__all__` and the re-exports (`MODEL_PRESETS`, `SUPPORTED_LANGUAGES`) — grep for importers first; `menu_bar.py` and `tray.py` are the known consumers.
- [x] 2.4 `src/whispy/ui/menu_bar.py`: remove the Model and Language submenus and their callbacks.
- [x] 2.5 `src/whispy/platform/linux/tray.py`: same removal on the Linux tray.
- [x] 2.6 Grep `src/whispy/api/server.py` for `model_size`/`language` in status payloads or config endpoints; update or remove.

## 3. Rework custom vocabulary and text cleaning

- [x] 3.1 `src/whispy/core/text_cleaner.py`: delete the Whisper credit prefixes and the hallucination phrase list along with their matching logic; keep whitespace normalization.
- [x] 3.2 `text_cleaner.py`: add near-miss vocabulary correction using stdlib `difflib.get_close_matches` over `custom_vocabulary`, per output token, above a similarity cutoff. Start at 0.75; tune against `tests/fixtures/audio` plus the spike sentences and record the final value in the spec scenario.
- [x] 3.3 Wire the vocabulary through `clean_text` at the engine's cleaning step (the config value is already loaded; do not reintroduce a transcription-call parameter).
- [x] 3.4 Confirm the correction cannot inject a vocabulary term into text that contained no near match — that failure mode is the whole reason `initial_prompt` was dropped.

## 4. Update the tests

- [x] 4.1 `tests/conftest.py:139-140`: replace the `WhisperModel` mock fixture with a Parakeet-shaped mock exposing `recognize()`.
- [x] 4.2 `tests/test_audio.py`: update transcribe-path tests for the new signature; delete credit-stripping assertions.
- [x] 4.3 `tests/test_engine.py`: delete `test_vocabulary_builds_initial_prompt` and the sibling `initial_prompt` assertions (`:358-390`, `:746-748`); update model-load tests.
- [x] 4.4 `tests/test_language_detection.py`: delete the auto-detect-warning tests; keep and relocate the WAV duration tests (they cover `_get_audio_duration`, not language).
- [x] 4.5 `tests/test_text_cleaning.py`: delete credit/hallucination tests; add near-miss vocabulary-correction tests including the no-false-injection case from 3.4.
- [x] 4.6 `tests/test_config_validation.py`: drop cases for the removed keys; add a case proving a legacy config with `model_size`/`language` loads and validates.
- [x] 4.7 `tests/test_transcription_quality.py` rewritten against Parakeet with no language argument, plus new `TestCodeSwitching`, `TestSilenceGate`, `TestLongAudio`, `TestShortChunks`. 16/16 green. **This tier is what caught the silence-hallucination bug** — see task 9.
- [x] 4.8 `tests/test_menu_bar.py`: drop Model/Language submenu assertions.
- [x] 4.9 `tests/test_doctor.py` done (cache glob + a new guard that a stale Whisper snapshot does not count as cached). `tests/test_install_scripts.py` follows the `WHISPER_MODEL` removal in 5.2/5.4.
- [x] 4.10 `./.venv/bin/pytest` green; then `./.venv/bin/pytest -m macos` for the real-seam tier.

## 5. Installer, doctor, packaging

- [x] 5.1 `src/whispy/doctor.py:71`: change the cache check to the Parakeet ONNX snapshot (`models--istupakov--parakeet-tdt-0.6b-v3-onnx`); drop the `model_size` lookup and the `check_model` docstring's "Whisper".
- [x] 5.2 `install.sh`: update the banner (`:13`), remove `WHISPER_MODEL` handling and the config write-back (`:110-133`), and change the uninstall glob (`:69`) to the Parakeet snapshot. Keep the scoping guarantee — never delete the hub cache directory itself.
- [x] 5.3 `install.sh`: in the uninstall path, print the location of any leftover `models--Systran--faster-whisper-*` snapshots as safe to delete manually.
- [x] 5.4 `scripts/bootstrap.sh`: remove `WHISPER_MODEL` pass-through.
- [x] 5.5 `packaging/macos/setup_app.py:53`: drop `faster_whisper`, `ctranslate2`, `tokenizers`, `av`; add `onnx_asr`. Keep `onnxruntime`, `huggingface_hub`, `certifi`.
- [x] 5.6 `make app` built and signed (188 MB; `onnx_asr`/`onnxruntime` present, `faster_whisper`/`ctranslate2`/`tokenizers`/`av` gone). Launched `dist/Whispy.app` for real: it started, loaded the model (`model_loaded: true`), and migrated the *real* on-disk config — the removed keys dropped, the user's own `pause_ms`/`vad_aggressiveness` preserved. Note: a stale Whispy from 2026-08-18 was wedged on `:9090` (unrelated to this change) and had to be killed first, or `open` just reactivates it. Dictating with a held key still needs a human — see 1.8.

## 6. Documentation

- [x] 6.1 `README.md`: replace faster-whisper with Parakeet throughout; update the Configuration table to the reduced `DEFAULT_CONFIG`; state the 639 MB first-run download; list the 25 supported languages (or link the model card) rather than implying universality; describe `custom_vocabulary` honestly as near-miss correction; add the CC-BY-4.0 attribution.
- [x] 6.2 New `NOTICE` at the repo root crediting `nvidia/parakeet-tdt-0.6b-v3` (CC-BY-4.0) and the `istupakov/parakeet-tdt-0.6b-v3-onnx` conversion; note that weights are downloaded at runtime, not redistributed.
- [x] 6.3 `FEATURE_MATRIX.md`: update the transcription rows; drop model-size and language rows.
- [x] 6.4 `docs/SPECIFICATION.md` and `docs/transcription-quality-and-memory.md`: rewrite the Whisper-specific sections; the latter's premises about hallucination and hotwords no longer hold.
- [x] 6.5 `CHANGELOG.md`: one `2.0.0` entry — the backend swap, the breaking config and menu changes, the new download size, and the two silently-fixed bugs (`language="auto"` `ValueError`, long-audio truncation).
- [x] 6.6 `.github/ISSUE_TEMPLATE/bug_report.md`: drop the model-size question.
- [x] 6.7 Bump the version to `2.0.0` everywhere `ci-cd-pipeline`'s consistency requirement checks (`pyproject.toml`, and whatever `tests/` asserts).

## 7. Website

- [x] 7.1 `website/index.html:73`: the privacy copy names `faster-whisper`; change it to Parakeet and keep the local/no-cloud claim intact.
- [x] 7.2 `website/index.html`: remove the Model and Language rows from the animated menu-bar demo dropdown (they no longer exist in `menu_bar.py`); check the dropdown height/timing still animates correctly.
- [x] 7.3 `website/index.html`: add the model attribution (NVIDIA, CC-BY-4.0) near the existing licence statement.
- [x] 7.4 Update any feature card or copy implying a choice of model sizes or a language setting.
- [x] 7.5 `tests/test_website.py`: update the guards and add one asserting the page does not name faster-whisper.
- [x] 7.6 Verified structurally: every JS selector resolves against the markup and no `data-demo-*` hook is orphaned. A human still needs to watch the animation once — the demo's narrative changed from a language switch to a clipboard toggle.

## 8. Verify

- [x] 8.1 Full suite green: **636 passed, 1 skipped**. Lint + format clean.
- [x] 8.2 macOS real-seam tier green: **30 passed, 2 skipped** in 24s. Two findings while getting there: (a) the sweep appeared to hang for >10 min — it was port contention from a stale daemon holding `:9090`, not a code hang; on a clean port the live-drive cycle completes in 6.5s; (b) `tests/validation/harness.py` still drove `language` over HTTP and asserted it came back, which fails against a config that no longer has the key. Rewritten to drive `pause_ms` instead, and the per-language fixture checks now configure nothing — each clip must be recognized on the model's own detection.
- [x] 8.3 `doctor` reports `[ok] model: parakeet-tdt-0.6b-v3 (int8) cached`.
- [x] 8.4 `graphify update .` done — 3558 nodes, 8205 edges.

## 9. Silence gate (added during implementation)

Found by running the real-model tier, which had never been run before this change.
The proposal claimed Parakeet "returns an empty string for silence", generalized
from one 1.0 s fixture. It does not: it invents short fillers (`Yeah.`, `Okay.`,
`Mm-hmm.`, `No.`, `Thank you.`) on pure silence *and* on a realistic quiet-room
noise floor, non-monotonically in duration. Left unguarded, releasing the key on a
pause would type `Okay.` into the active field.

- [x] 9.1 Measure the failure: RMS vs output across durations (0.4–5.0 s) and noise floors (0.0005 / 0.002 / 0.01 of full scale). Every false positive ≤0.00065 RMS; real speech ≥0.147. Separation 220x.
- [x] 9.2 Add `SILENCE_RMS_THRESHOLD = 0.005` and `_get_audio_rms()` to `audio.py`; gate before the model in `AudioEngine.transcribe`. Fails **open** — an unmeasurable clip is transcribed, never silently dropped.
- [x] 9.3 Reject a phrase blocklist explicitly: it would have to contain `Okay.` and `No.`, which are legitimate one-word dictations, so filtering by text would delete real speech — the exact liability that justified deleting Whisper's list.
- [x] 9.4 Verify: 0 leaks across all 24 measured silence/noise clips, both speech fixtures still transcribe correctly.
- [x] 9.5 Tests: `test_audio.py::TestAudioRms` (5), `::TestTranscribe` gate cases (3), `test_transcription_quality.py::TestSilenceGate` (6, parameterized over durations and noise floors).
- [x] 9.6 Correct the artifacts the finding invalidated: `design.md` decision 7 + Correctness observations + a new risk entry, `specs/transcription-quality`, `specs/text-cleaning` (REMOVED reason), `specs/audio-capture` (2 new requirements), `proposal.md`, `CHANGELOG.md`, `docs/transcription-quality-and-memory.md`, `docs/SPECIFICATION.md`, `README.md`, `FEATURE_MATRIX.md`.
- [x] 9.7 Make the real-audio vocabulary test honest: it asserted recovery of "Whispy" from `open whispy now`, which came back as "oh we'll see no" — too distant for near-miss correction, i.e. asserting something the design explicitly does not promise. Now asserts cleaning never makes output worse; the correction itself is pinned deterministically in `test_text_cleaning.py`.

## 10. Phonetic vocabulary matching (added after user testing)

User reported the migration working well except on proper nouns, brand names and
anglicisms — "parakite" instead of "Parakeet" — and asked whether a larger model
would help. Measured both.

- [x] 10.1 Test the larger-model hypothesis: `nemo-canary-1b-v2` int8 vs parakeet-0.6b on the jargon fixtures, scoring surviving technical terms. **Rejected**: 62% vs 72%, 2.7x slower, 1.75x the RSS, 982 MB vs 639 MB — and it translates to English unless given an explicit `language`, reintroducing the setting decision 5 removes.
- [x] 10.2 Side result: passing `language` to Parakeet produces byte-identical output on all four clips. Decision 5 now confirmed on Parakeet itself, not inherited from the Whisper measurement.
- [x] 10.3 Diagnose the real cause: `parakite`~`Parakeet` is 0.750 on characters, just under the 0.80 cutoff; lowering the cutoff also admits `pense`~`OpenSpec` (0.769). The classes are not separable on spelling.
- [x] 10.4 Add `phonetic_key()` — accent stripping, interchangeable-consonant folding (c/k/q, s/z/x, v/f), vowel dropping after the first letter, double collapsing. ~15 lines stdlib, no Metaphone dependency. `parakite` and `parakeet` reduce to the same key; `pense` and `openspec` fall to 0.667.
- [x] 10.5 Ship the union rule (char >=0.80 OR phon >=0.90), not phonetics as a replacement: measured over 234 335 dictionary words, phonetics alone at 0.80 gives 1763 false corrections (0.752%) and would mangle "appreciate". The union gives 139 (0.059%) against 31 for spelling alone.
- [x] 10.6 Verify the shipped implementation reproduces the measurement exactly: 139/234 335, `parakite` -> `Parakeet`, and every French/English lookalike left alone.
- [x] 10.7 Tests: `TestPhoneticCorrection` (6), `TestPhoneticKey` (5), two tuning-constant guards. Suite 649 passed; `-m macos` 30 passed.
- [x] 10.8 Artifacts: design decision 6 extended + new decision 11 (model size, with the Canary table) + a new risk entry, `specs/text-cleaning` (2 new scenarios), `proposal.md`, `README.md`, `CHANGELOG.md`, `docs/transcription-quality-and-memory.md`.
- [x] 10.9 Purge the 982 MB canary weights from the HF cache.

## 11. Speech gate (added after an independent A/B re-measurement)

The migration's numbers were re-derived from scratch rather than trusted, with
`faster-whisper` reinstalled into a throwaway venv and both backends run over the
same synthesized clips. Most claims held. Two turned out to be stated backwards,
and one real gap surfaced: the silence gate only covers *near*-silence, so
non-speech that is merely loud still reached the model.

- [x] 11.1 Re-measure the migration claims independently: latency 6-16x and proportional to audio (0.035s at 0.5s, 0.075s at 2.2s) vs Whisper flat at 0.58-0.70s; WER 5.2% vs 17.2% at the pre-migration defaults, 3.4% with Whisper's language detection left on. Truncation reproduced under four decoder configs (beam 1/5, `vad_filter`, `condition_on_previous_text=False`): a 16.6s clip returns one sentence of eight. Forced-language mistranslation reproduced.
- [x] 11.2 Correct two claims that were stated backwards. Whisper does **not** behave better than Parakeet on non-speech: over 100 noise realizations per backend on identical files, `faster-whisper small` answered 52-100% with text (`you`, `Thank you.`), Parakeet 3%. And Parakeet's apparent weakness on short foreign words was a test artifact — an English `say` voice pronouncing French. With a matched voice it recognizes `oui`, `non`, `stop`, `d'accord`.
- [x] 11.3 Measure the real gap: noise at 0.010-0.035 normalized RMS clears the 0.005 silence gate, reaches the model, and comes back as a filler in 3 of 100 realizations.
- [x] 11.4 Reject a confidence gate with data. `with_timestamps()` exposes `logprobs`, but the populations overlap completely: an invented `Hello` on a mid-word cut scores -0.040 mean against -0.399 for a correctly recognized `Oui.`. Any threshold catching the invention discards real dictation first.
- [x] 11.5 Reject a voiced/silent **ratio** with data: one word inside a 10s trigger-hold is ~6% voiced and steady noise ~5%, so the metric orders the populations by at most 1.4x and flipped to overlap on a second draw. Absolute voiced duration separates them 2.7x (0.33s vs 0.12s across 125 noise realizations).
- [x] 11.6 Add `speech_duration_s()` to `segmentation.py` — reuses the `webrtcvad` the streaming segmenter already needs, no new dependency — and `_carries_speech()` + `MIN_SPEECH_DURATION_S = 0.20` to `audio.py`, gated after the RMS check. Fails **open** on every unmeasurable path (no VAD, unreadable file, unsupported width).
- [x] 11.7 Document the ceiling rather than hide it: past ~0.04 normalized RMS `webrtcvad` labels steady noise fully voiced and the gate is inert. Left to the model, which returned empty text for all 15 such clips. Raising the threshold is explicitly not the fix — it would reach real speech first.
- [x] 11.8 Verify: leak rate 3/100 -> 0/100, with real speech unaffected (1.62-2.85s voiced on phrases, 0.33-0.69s on one-word clips, 0.66s for a word buried in a 10s hold).
- [x] 11.9 Tests: `test_segmentation.py::TestSpeechDuration` (6), `test_audio.py::TestSpeechGate` (8), `test_transcription_quality.py::TestSilenceGate::test_loud_non_speech_above_the_rms_gate_is_discarded` (5 noise types, seeded), `::TestShortDictation` (5 words + the buried-word case). Suite 663 passed; `-m macos` 40 passed over four consecutive runs.
- [x] 11.10 Fix three flaky tests found on the way, two of them mine: `sox synth` draws fresh noise per call (now `-R`); `_find_voice("en")` returns the legacy novelty voice `Albert`, whose `okay` transcribes to nothing (now `_prefer_voice` with modern voices); `oui` synthesizes close enough to English `we` to fail ~half the draws (parameter removed, reason documented); and the synthetic `_speech_block` fixture reads only 18% voiced, so it cannot back a duration assertion (new `_voiced_block`, a harmonic stack).
- [x] 11.11 Version the measurement scripts in `scripts/asr-bench/` (with a README) rather than leaving them in a scratch directory — re-deriving them costs an hour, re-running them a minute. Absolute paths removed, duplicated helpers factored into `_bench.py`, outputs written outside the repo.
- [x] 11.12 Artifacts: `specs/audio-capture` (2 new requirements, 7 scenarios), `specs/transcription-quality` (requirement extended, 3 new scenarios), `CHANGELOG.md`, `README.md` (gate table + a "nothing was typed" FAQ pointing at the log lines), `docs/SPECIFICATION.md`, `docs/transcription-quality-and-memory.md`, `FEATURE_MATRIX.md`, `website/index.html`.
- [x] 11.13 Review finding — the speech gate was only ever exercised against the real model on macOS. `test_transcription_quality.py` skips at module level without `say`, so Linux had unit coverage of the gate and nothing else. The non-speech cases never needed `say` (they synthesize with `sox`, which exists on both), so they moved to `tests/test_non_speech_real.py`, carrying both markers: `-m macos` and `-m linux` each run it. The `linux` tier goes from 0 selected tests on this feature to 15.
- [x] 11.14 Review finding — `TestSpeechDuration` and the rejection assertions in `TestSpeechGate` required `webrtcvad` in hard, while the rest of the module degrades (the segmenter ships an energy fallback and `speech_duration_s` returns `None`). On a platform with no wheel they would have failed rather than skipped, on a configuration the code explicitly supports. Added `requires_vad` skip markers, verified by running the suite against a shim that makes `import webrtcvad` raise: 654 passed, 13 skipped, 0 failed.
- [x] 11.15 Review finding — both gate thresholds were calibrated on macOS against `say` synthesis and one microphone. Added `TestSpeechGateAgainstCommittedAudio`, which checks the margins against the committed *recordings* (RMS by 5x, voiced duration by 3x) and runs in the default tier, so ubuntu CI covers it. Documented at the constant what is still unmeasured: a real Linux microphone at a different capture gain, since webrtcvad's energy floor could swallow a very quiet input.
- [x] 11.16 Confirm the rest of the platform story rather than assume it: `webrtcvad-wheels` carries no platform marker and publishes manylinux x86_64 + aarch64 wheels for 3.10-3.12 (checked with `pip download --platform`); capture is 16 kHz mono int16 on both platforms, exactly what `_carries_speech` requires; `conftest.py` mocks only Quartz and rumps, so ubuntu CI exercises the real VAD; the diff touches no file under `hardware/`, `platform/` or `ui/`. Wayland is unaffected — the gate sits upstream of text injection, which is where Wayland's existing limitation lives.
- [x] 11.17 Review finding — the `test-macos-real-seam` job never installed `sox`, so both real-model modules skipped at import and the job was green on 14 of its 44 tests. Measured by hiding sox from PATH. It now installs sox and caches the 639 MB weights, running 29: the smoke seams plus the whole deterministic non-speech tier. `test_transcription_quality.py` stays excluded *explicitly* rather than by accident — it asserts on `say` output, which is not byte-stable between runs, so it remains a local tool.
- [x] 11.18 Drop the `sox` dependency from the real-model tests rather than install it in CI. Measured first, because the concern was data volume and the numbers said otherwise: the weights are already cached (`Cache hit`, 444 MB restored in ~10s, nothing downloaded) and `brew install sox` cost 6s of a 91s job. The reason to remove sox is not cost, it is that an external tool is one more thing to install, to differ between platforms, and to skip a whole module when absent. `test_non_speech_real.py` now synthesizes white/brown/pink/hum/fan noise with numpy, scaled to an exact target RMS instead of a `vol` multiplier, seeded so the draw is reproducible. Verified identical behaviour: same measured RMS, same 0.09s voiced duration, same empty model output, all six clips still blocked. The module now runs with sox absent from PATH, CI installs nothing, and the original blanket "CI must not install sox" guard is restored intact -- only the pinned exclusion of the `say`-dependent module remains alongside it.
