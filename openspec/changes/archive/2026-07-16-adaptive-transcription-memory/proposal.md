## Why

Whispy's transcription accuracy degrades on user-specific vocabulary — proper nouns, brand names, jargon. Example: "Whispy" is consistently transcribed as "Wispy" because faster-whisper has no memory of past corrections. Users must manually edit `custom_vocabulary` in config JSON, which is friction most won't tolerate. The app should learn from its user over time, reducing correction needs with each dictation session.

## What Changes

- **Correction detection via macOS Accessibility API**: after text injection, snapshot the focused text field's value. On the next Fn press, read the field again and diff the injected region to detect user corrections.
- **Persistent correction store**: corrections accumulate in `~/.config/whispy/corrections.json` with occurrence/correction counts and confidence scores.
- **Hotwords integration**: wire the unused faster-whisper `hotwords` parameter — feed learned vocabulary from the correction store to bias the model before transcription.
- **Post-transcription replacement**: high-confidence corrections (user fixed the same error ≥3 times) are applied as deterministic find-and-replace after transcription, as a safety net when model biasing isn't enough.
- **Menu bar visibility**: expose learned corrections in the menu bar UI so users can view, edit, or remove entries.

## Capabilities

### New Capabilities
- `correction-detection`: Snapshot text fields via AXUIElement on inject, diff on next Fn press, extract user corrections automatically with zero user effort.
- `correction-store`: Persistent JSON storage for correction mappings with occurrence tracking, confidence scores, and activation thresholds.
- `adaptive-vocabulary`: Feed correction store into faster-whisper's `hotwords` param and apply post-transcription replacements for high-confidence entries.

### Modified Capabilities
- `transcription-quality`: Custom vocabulary requirement expands — hotwords parameter used alongside initial_prompt; post-transcription replacement layer added.
- `text-cleaning`: Pipeline gains a new correction-replacement step after existing credit stripping.

## Impact

- **New code**: `src/whispy/core/corrections.py` (store + diffing), AX text-field reading in `src/whispy/hardware/`
- **Modified code**: `src/whispy/core/engine.py` (snapshot on inject, diff on Fn press, hotwords wiring), `src/whispy/core/audio.py` (hotwords param passthrough), `src/whispy/ui/menu_app.py` (corrections submenu)
- **New dependency**: potentially `pyobjc-framework-Cocoa` for AXUIElement text reading (may work with existing `ApplicationServices`)
- **Config**: new file `~/.config/whispy/corrections.json`, no changes to existing `config.json` schema
- **Permissions**: no new permissions — Accessibility (already required for text injection) covers AXUIElement reading
