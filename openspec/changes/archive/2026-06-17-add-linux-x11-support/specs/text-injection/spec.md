## MODIFIED Requirements

### Requirement: Text Injection via System Services
The injection engine SHALL provide a mechanism to input transcribed text into the active application using system-level automation, **behind a `TextInjector` port with a per-OS adapter**: `osascript` on macOS and `xdotool` on Linux/X11. The injected result and the clipboard-vs-keystroke configuration contract SHALL be identical across adapters.

#### Scenario: Successful Text Injection
- **WHEN** a transcription is completed and text injection is enabled
- **THEN** the active platform's injector adapter SHALL inject the transcribed text into the currently focused application field

_Tier: platform-real — `subprocess` mocked on macOS; the real seam (osascript / xdotool) is not exercised in CI. Deferred to the per-OS smoke tier._

#### Scenario: Adapter selected by platform
- **WHEN** the engine injects text
- **THEN** it SHALL use the `osascript` adapter on macOS and the `xdotool` adapter on Linux, selected via the platform factory rather than a direct import

_Tier: unit-mocked — `sys.platform`/factory patched._
