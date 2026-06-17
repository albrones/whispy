## ADDED Requirements

### Requirement: Platform port interfaces
The OS-coupled seams SHALL be expressed as structural port interfaces (`typing.Protocol`): `HotkeyListener`, `TextInjector`, `AudioRecorder`, `TrayUI`, and `Notifier`. The core engine SHALL depend only on these ports and SHALL NOT import any platform-specific module directly. Existing macOS implementations SHALL satisfy the ports without behavior change.

#### Scenario: Engine depends only on ports
- **WHEN** the engine is constructed
- **THEN** it SHALL receive its hotkey listener, text injector, audio recorder, tray UI, and notifier as port-typed collaborators rather than constructing platform classes itself

_Tier: unit-pure — port wiring verifiable without a live OS seam._

#### Scenario: macOS adapter satisfies the ports
- **WHEN** the macOS adapter set is bound to the ports
- **THEN** the existing CGEventTap listener, osascript injector, and rumps tray SHALL conform to the port shapes with their current behavior unchanged

_Tier: macos-real — real-seam behavior unchanged; covered by existing macOS tier._

### Requirement: Runtime platform detection
A `platform.detect()` factory SHALL select and bind the adapter set for the current operating system based on `sys.platform`. On an unsupported platform it SHALL raise a clear, actionable error rather than fail opaquely.

#### Scenario: macOS selected on Darwin
- **WHEN** `detect()` runs on `darwin`
- **THEN** it SHALL return the macOS adapter set (CGEventTap, osascript, rumps, afplay)

_Tier: unit-mocked — `sys.platform` patched._

#### Scenario: Linux selected on Linux
- **WHEN** `detect()` runs on `linux`
- **THEN** it SHALL return the Linux adapter set (pynput, xdotool, pystray)

_Tier: unit-mocked — `sys.platform` patched._

#### Scenario: Unsupported platform rejected
- **WHEN** `detect()` runs on a platform with no adapter set (e.g. `win32` in v1)
- **THEN** it SHALL raise an error naming the platform and the supported set rather than return a partial binding

_Tier: unit-mocked — `sys.platform` patched._
