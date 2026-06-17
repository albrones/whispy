# linux-support Specification

## Purpose
The Linux/X11 adapter set behind the platform ports: a `pynput` global hotkey
listener, `xdotool` text injection, a `pystray` tray UI, and the X11-session
requirement that Whispy v1 enforces at startup. These adapters provide the same
behavior contract as their macOS counterparts.

Scenario test tiers follow the convention in `../TESTING-TIERS.md`.

## Requirements
### Requirement: Linux X11 hotkey listening
On Linux, the hotkey listener SHALL detect the configured trigger key globally under an X11 session using `pynput`, emitting press and release events to the engine. When the global listen cannot be established, it SHALL degrade gracefully and emit an actionable message to stderr rather than crash.

#### Scenario: Configured trigger drives recording on X11
- **WHEN** the user presses and releases the configured trigger key under an X11 session
- **THEN** the listener SHALL emit a press event (start recording) on press and a release event (stop recording) on release

_Tier: linux-real — requires a live X11 session; not verifiable in CI._

#### Scenario: Listen failure degrades with a hint
- **WHEN** the global key listen cannot be established
- **THEN** the listener SHALL print an actionable message and SHALL NOT crash the daemon

_Tier: linux-real — deferred to a Linux smoke run._

### Requirement: Linux text injection
On Linux, the text injector SHALL inject transcribed text into the focused application via `xdotool`, honoring the same `copy_to_clipboard` configuration as macOS: clipboard-paste mode SHALL set the clipboard and synthesize paste, and keystroke mode SHALL type the text directly. Empty text SHALL be a no-op.

#### Scenario: Clipboard mode pastes via xdotool
- **WHEN** `copy_to_clipboard` is enabled and a transcription completes on Linux
- **THEN** the injector SHALL set the clipboard to the text and synthesize a paste into the focused application

_Tier: linux-real — needs a live X11 session and focused app; deferred to a Linux smoke run._

#### Scenario: Keystroke mode types via xdotool
- **WHEN** `copy_to_clipboard` is disabled and a transcription completes on Linux
- **THEN** the injector SHALL type the text directly via `xdotool` keystrokes

_Tier: linux-real — deferred to a Linux smoke run._

#### Scenario: xdotool missing is reported
- **WHEN** the `xdotool` binary is not available at startup
- **THEN** the Linux injector SHALL emit an actionable install hint rather than fail silently at injection time

_Tier: unit-mocked — binary probe patched._

### Requirement: Linux tray UI
On Linux, the status/menu surface SHALL be provided via `pystray`, exposing the same control actions as the macOS menu (status, settings, quit). The macOS overlay windows SHALL NOT be required on Linux; recording state SHALL be conveyed through the tray.

#### Scenario: Tray reflects recording state
- **WHEN** the engine transitions between idle and recording on Linux
- **THEN** the pystray tray SHALL reflect the state change (icon and/or menu) without requiring an overlay window

_Tier: linux-real — needs a live tray host; deferred to a Linux smoke run._

### Requirement: X11 session requirement
On Linux, Whispy v1 SHALL require an X11 session. At startup it SHALL detect a Wayland session (e.g. via `XDG_SESSION_TYPE`/`WAYLAND_DISPLAY`) and SHALL emit a clear message that an X11 session is required for v1, rather than failing opaquely when global hotkeys or injection do not work.

#### Scenario: Wayland session is detected and reported
- **WHEN** Whispy starts under a Wayland session on Linux
- **THEN** it SHALL emit a message stating that an X11 session is required in v1

_Tier: unit-mocked — session env vars patched._

#### Scenario: X11 session proceeds normally
- **WHEN** Whispy starts under an X11 session on Linux
- **THEN** it SHALL proceed without the Wayland warning

_Tier: unit-mocked — session env vars patched._
