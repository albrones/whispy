## ADDED Requirements

### Requirement: Injections are delivered in call order
Successive `inject()` (and `copy_only()`) calls on one injector adapter SHALL
deliver their text in the order the calls were made, and two injections SHALL
never run concurrently: the second SHALL start only after the first has
finished typing or pasting (including the clipboard restore step in clipboard
mode). `inject()` itself SHALL remain non-blocking for its caller. This applies
identically to the macOS and Linux adapters.

#### Scenario: Two rapid injections keep their order
- **WHEN** `inject("A")` is called and `inject("B")` is called before the first has finished
- **THEN** every keystroke or paste of "A" SHALL complete before any of "B" begins

#### Scenario: Caller is not blocked
- **WHEN** an injection is in progress and a caller invokes `inject()` again
- **THEN** the call SHALL return immediately and the new text SHALL be delivered after the one in progress

#### Scenario: A failed injection does not block later ones
- **WHEN** an injection fails (non-zero exit, timeout, or permission denial) and another injection is queued behind it
- **THEN** the queued injection SHALL still run, and the failure SHALL be classified and surfaced exactly as it is today

_Tier: unit-mocked — `test_injection.py` / `test_linux_adapters.py` with a slow first `subprocess` step._
