## REMOVED Requirements

### Requirement: Apply learned corrections after cleaning
**Reason**: Adaptive correction is deleted; there is no correction store to apply entries from. The step was already a no-op behind `ADAPTIVE_LEARNING_ENABLED = False`.
**Migration**: None; credit stripping and the rest of the cleaning pipeline are unchanged.
