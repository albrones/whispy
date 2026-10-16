## Purpose

Whispy V2's transcription core: turning the PCM of one dictation into the text to insert, with engines and a default configuration chosen by a reproducible bench run against V1 on the same clips.

## ADDED Requirements

### Requirement: A dictation's PCM becomes text through one call
The core SHALL take a whole dictation as 16 kHz mono samples and return the text to insert, empty when nothing was said, together with the engine that produced it. Audio files in any other format than 16 kHz mono 16-bit PCM SHALL be refused with an error naming the actual and the expected format.

#### Scenario: Speech becomes text
- **WHEN** the reference clip « à améliorer, je pense » is transcribed with the default configuration
- **THEN** the text SHALL read « À améliorer, je pense. » and name the engine that produced it

_Tier: bench — `v2/bench/REPORT.md`, reference table._

#### Scenario: A stereo or 44.1 kHz file is refused
- **WHEN** a WAV that is not 16 kHz mono 16-bit is read
- **THEN** reading SHALL fail with an error naming its channels, rate and sample format and the expected ones

_Tier: unit — `whispy-core` `audio`._

### Requirement: Silence and noise never produce text
Once gated, a clip whose loudest 0.5 s window is under RMS 0.005, or that carries less than 0.20 s of voiced frames, SHALL NOT reach an engine. Whisper output that whisper itself doubts (no-speech probability above 0.6, mean token log probability under −1) or that holds a non-Latin letter SHALL be dropped.

#### Scenario: Silence is not sent to an engine
- **WHEN** one second of digital silence is transcribed under any gated strategy
- **THEN** no engine SHALL be called and the text SHALL be empty

_Tier: unit — `whispy-core` `pipeline` (scripted engine)._

#### Scenario: The bench's non-speech clips stay empty
- **WHEN** the bench replays silence, white and brown noise and a 50 Hz hum through the default configuration
- **THEN** none of them SHALL come back with text

_Tier: bench — `v2/bench/REPORT.md`, « non-speech: invented » column._

### Requirement: One engine call never receives more than 20 seconds
A dictation longer than 20 s SHALL be split into pieces of at most 20 s, cut in the longest pause near the limit, covering every sample exactly once, and the piece texts SHALL be joined in order.

#### Scenario: A 65 s dictation is split
- **WHEN** 65 s of voiced audio is transcribed
- **THEN** the engine SHALL be called at least four times, never with more than 20 s, and the text SHALL hold one piece text per call in order

_Tier: unit — `whispy-core` `pipeline`, `split`._

#### Scenario: A 180 s dictation stays bounded in memory
- **WHEN** the bench transcribes a 180 s dictation in a fresh process with one engine loaded
- **THEN** its peak RSS and physical footprint SHALL be reported, and SHALL stay under 1.5 GB for Parakeet alone and for whisper alone

_Tier: bench — `v2/bench/REPORT.md`, memory table._

### Requirement: A second engine answers when the first hears nothing
When a fallback engine is configured and the primary engine returns empty text for a prepared piece, the fallback engine SHALL transcribe the same prepared piece and its text SHALL be used.

#### Scenario: Whisper recovers what Parakeet drops
- **WHEN** the primary engine returns nothing for a gated clip and the fallback returns « à améliorer, je pense »
- **THEN** the transcript SHALL be « à améliorer, je pense » and name the fallback engine

_Tier: unit — `whispy-core` `pipeline`._

### Requirement: Parakeet runs on the CPU only
The Parakeet engine SHALL run on the ONNX Runtime CPU provider, never CoreML: a 180 s clip under CoreML reached 25 GB and took the machine down in V1.

#### Scenario: Loading Parakeet registers no other provider
- **WHEN** the Parakeet engine is loaded
- **THEN** its sessions SHALL be created without any execution provider other than the CPU one

_Tier: review — `whispy-core/src/parakeet.rs`, `session`._

### Requirement: Model files are found, never downloaded
The core SHALL use the model files already on the Mac — Parakeet from the Hugging Face cache V1 filled, whisper small from `~/.whispy/models/` or `~/.jarvis/models/`, each overridable by an environment variable — and SHALL fail with the paths it looked at when one is missing, without any network call.

#### Scenario: A missing model names where it was looked for
- **WHEN** the whisper model is absent from every location
- **THEN** loading SHALL fail with an error listing those paths and the variable that overrides them

_Tier: review — `whispy-core/src/models.rs`._

### Requirement: The bench compares V2 with V1 and picks the default
`cargo run --release --bin banc` SHALL replay the lost clips of `~/.whispy/lost/`, the reference clips with a known text, their quiet copies and non-speech clips through every engine and strategy, alone and with the other engine as fallback, and through V1's own engine; it SHALL report per configuration the share of clips with text, the word error rate, latency p50 and p95 and the ~5 s sentence p95, write `v2/bench/REPORT.md` naming the pick, and exit non-zero when the pick differs from the core's default.

#### Scenario: The report names the default the core uses
- **WHEN** the bench runs on a Mac holding both models and V1's venv
- **THEN** `v2/bench/REPORT.md` SHALL name the picked configuration with its numbers, and the core's default configuration SHALL be that pick

_Tier: bench — `v2/bench/REPORT.md`, « Default engine and strategy »._

#### Scenario: Replaying V1 leaves V1 untouched
- **WHEN** the bench runs V1 on the same clips
- **THEN** no clip SHALL be added to or removed from `~/.whispy/lost/` and V1 SHALL run offline

_Tier: review — `v2/bench/v1_replay.py`, `banc/src/v1.rs`._
