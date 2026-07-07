## MODIFIED Requirements

### Requirement: Final tail flush on release

When the trigger key is released while streaming, the system SHALL flush and
transcribe the final (in-progress) chunk so no trailing speech is lost, and SHALL
return to the idle state after the tail chunk is handled. The on-release wait for
the chunk queue to drain SHALL be bounded by a timeout: if the queue does not
drain within the timeout (a stalled or blocked chunk), the system SHALL stop
waiting, inject whatever assembled text exists so far, and return the FSM to IDLE
rather than blocking indefinitely in TRANSCRIBING. A bounded-wait expiry SHALL be
logged.

#### Scenario: Trailing speech after the last pause is transcribed

- **WHEN** the user releases the trigger key with un-emitted speech in the current chunk
- **THEN** the system SHALL flush and transcribe that tail chunk, assemble it with the earlier chunks, and inject the text before returning to idle

#### Scenario: Stalled chunk drain does not wedge the FSM

- **WHEN** the on-release wait for the chunk queue to drain exceeds the timeout
- **THEN** the system SHALL stop waiting, inject the assembled text produced so far, log the expiry, and force the FSM back to IDLE
