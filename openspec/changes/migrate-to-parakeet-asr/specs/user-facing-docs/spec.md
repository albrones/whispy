## MODIFIED Requirements

### Requirement: Complete config key reference
README.md's Configuration section SHALL document every key present in `DEFAULT_CONFIG`, and SHALL NOT document keys that no longer exist.

#### Scenario: Every DEFAULT_CONFIG key has a doc row
- **WHEN** a reader compares the keys in `DEFAULT_CONFIG` to the rows in README.md's Configuration table
- **THEN** every key (`copy_to_clipboard`, `start_at_login`, `min_recording_duration`, `custom_vocabulary`, `trigger`, `streaming_enabled`, `pause_ms`, `min_chunk_s`, `max_chunk_s`, `vad_aggressiveness`) has a corresponding row with a human-readable description

#### Scenario: Removed keys are absent from the table
- **WHEN** the Configuration table is read after the backend swap
- **THEN** it SHALL contain no row for `model_size`, `language`, `beam_size`, `best_of`, or `auto_detect_min_duration`

#### Scenario: Config completeness guard test passes
- **WHEN** `tests/test_docs.py` parses the README Configuration table and diffs its keys against `DEFAULT_CONFIG.keys()`
- **THEN** the two sets match exactly and the test passes

### Requirement: Documented defaults match code
User-facing documentation SHALL state configuration default values that match `DEFAULT_CONFIG` in `src/whispy/core/config.py`.

#### Scenario: Default-value guard test passes
- **WHEN** `tests/test_docs.py` checks a README-documented default against the corresponding `DEFAULT_CONFIG` entry
- **THEN** the two values are equal and the test passes

## ADDED Requirements

### Requirement: Docs name the actual transcription model
User-facing documentation SHALL name `nvidia/parakeet-tdt-0.6b-v3` as the transcription model and SHALL NOT refer to Whisper, faster-whisper, or a choice of model sizes. Documentation SHALL state the first-run download size and SHALL name the supported language set rather than implying universal language coverage.

#### Scenario: No stale backend references
- **WHEN** README.md, FEATURE_MATRIX.md, and `docs/` are read
- **THEN** they SHALL contain no claim that Whispy transcribes with Whisper or faster-whisper, and no reference to selecting a model size

#### Scenario: Download size and language coverage stated
- **WHEN** a reader looks for what the first run costs and which languages work
- **THEN** README.md SHALL state the model download size and SHALL name or link the supported languages

### Requirement: Model attribution is present
Because the model is licensed CC-BY-4.0 while Whispy is GPL-3.0, the repository SHALL carry attribution for `nvidia/parakeet-tdt-0.6b-v3` and for the ONNX conversion it loads. Attribution SHALL live in a `NOTICE` file at the repository root and SHALL also appear in README.md. The documentation SHALL make clear that model weights are downloaded at runtime and are not redistributed with Whispy.

#### Scenario: NOTICE credits the model
- **WHEN** the repository root is inspected
- **THEN** a `NOTICE` file SHALL credit NVIDIA for `parakeet-tdt-0.6b-v3` under CC-BY-4.0 and name the ONNX conversion used

#### Scenario: README repeats the attribution
- **WHEN** README.md's licence section is read
- **THEN** it SHALL state that Whispy is GPL-3.0, that the model is CC-BY-4.0, and that weights are fetched at runtime rather than bundled

### Requirement: Upgrade path for the orphaned Whisper cache
Documentation SHALL tell users upgrading from a Whisper-era install that the old model cache is no longer used and where it is, since the uninstaller no longer offers to remove it.

#### Scenario: Release notes name the stale cache
- **WHEN** a user reads the upgrade notes for this release
- **THEN** they SHALL find the path `~/.cache/huggingface/hub/models--Systran--faster-whisper-*` identified as safe to delete manually
