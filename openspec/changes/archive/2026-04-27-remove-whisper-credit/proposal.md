## Why

When the user presses and releases the Fn key without speaking, Whisper sometimes outputs a French credit line ("Sous-titres réalisés par Whisper" or "Sous-titres réalisées par") as a watermark in the transcription. This credit appears as unwanted text injected into the active text field, degrading the user experience.

## What Changes

- Add a `strip_whisper_credit()` function that removes Whisper watermark prefixes from transcribed text in both French and English
- Apply the cleaning function in `AudioEngine.transcribe()` before returning the result
- Add unit tests for the credit stripping function
- Update the core-engine spec to document the new text cleaning requirement

## Capabilities

### New Capabilities
- `text-cleaning`: Stripping Whisper watermark/credit prefixes from transcription output

### Modified Capabilities
- `core-engine`: Adds requirement for automatic credit removal in transcription pipeline

## Impact

- **Code**: `src/whispy/core/audio.py` — new cleaning function applied in `transcribe()`
- **Code**: `src/whispy/core/engine.py` — no behavioral change, but text passes through cleaning before injection
- **Tests**: New unit tests for `strip_whisper_credit()`
- **Specs**: New `text-cleaning` spec, modified `core-engine` spec
