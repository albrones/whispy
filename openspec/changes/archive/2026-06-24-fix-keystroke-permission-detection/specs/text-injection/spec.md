## ADDED Requirements

### Requirement: Keystroke permission failure is detected and surfaced
The injection engine SHALL detect when a synthetic keystroke is rejected by
the OS (on macOS, osascript error `1002` / errAEEventNotPermitted from
`System Events`) and SHALL surface it to the user with an actionable
remediation, rather than failing silently while the clipboard appears to work.
The detection SHALL apply to both the clipboard-paste path (the `Cmd+V`
keystroke) and the direct-keystroke path.

#### Scenario: Denied paste keystroke is surfaced
- **WHEN** the clipboard is set successfully but the paste keystroke is denied
  with osascript error `1002`
- **THEN** the engine SHALL log a warning identifying the permission failure
  and SHALL present a user-visible notification with remediation (grant
  Accessibility/Automation to the current bundle, or run `tccutil reset`)

#### Scenario: Denied direct keystroke is surfaced
- **WHEN** keystroke injection mode is active and the keystroke is denied with
  osascript error `1002`
- **THEN** the engine SHALL log a warning and present the same user-visible
  remediation rather than reporting success

_Tier: unit-mocked — `subprocess` return code + stderr patched to emit `1002`._

### Requirement: Startup probe validates the keystroke path
The startup permission check SHALL validate that synthetic keystrokes are
actually permitted, not merely that a benign Apple-event query succeeds. A
probe that only confirms a non-keystroke query (e.g. `System Events return
name`) SHALL NOT be reported as "Automation authorized" when the keystroke
path is still denied.

#### Scenario: Benign query passes but keystroke is denied
- **WHEN** the benign `return name` query to System Events succeeds but a
  keystroke probe is denied with `1002`
- **THEN** the startup check SHALL report the keystroke path as not authorized
  and SHALL emit the remediation hint, not a false "authorized"

#### Scenario: Keystroke path fully authorized
- **WHEN** both the query and the keystroke probe succeed
- **THEN** the startup check SHALL report keystroke injection as authorized

_Tier: unit-mocked — `subprocess.run` results patched per branch._
