## REMOVED Requirements

### Requirement: Snapshot focused field after injection
**Reason**: Correction detection is deleted (`src/whispy/hardware/ax_reader.py` existed only for this). The detection heuristic mislearned from ordinary continued dictation and was permanently disabled.
**Migration**: None; the snapshot was already skipped behind the disabled flag. Reimplementation requirements live in the tracking issue.

### Requirement: Detect corrections on next Fn press
**Reason**: Same removal — the trigger-worker no longer performs correction detection on press (see the `core-engine` delta in this change).
**Migration**: None; behavior was already inert.
