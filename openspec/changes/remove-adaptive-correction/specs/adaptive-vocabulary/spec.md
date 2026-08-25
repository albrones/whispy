## REMOVED Requirements

### Requirement: Hotwords from correction store
**Reason**: Adaptive correction is deleted — the correction store no longer exists, so there is no learned vocabulary to feed `hotwords`. The feature was permanently gated off (`ADAPTIVE_LEARNING_ENABLED = False`) after its alignment mislearned pairs and poisoned recognition.
**Migration**: Manual vocabulary biasing via `initial_prompt` (`transcription-quality`) is unaffected. Reimplementation is tracked in the GitHub issue created by this change.

### Requirement: Post-transcription replacement for high-confidence corrections
**Reason**: Same removal — no correction store, no replacements to apply.
**Migration**: None; behavior was already inert behind the disabled flag.
