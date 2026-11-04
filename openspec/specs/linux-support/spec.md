# linux-support Specification

## Purpose
The Linux adapter sets behind the platform ports. X11: a `pynput` global hotkey
listener, `xdotool` text injection and a `pystray` tray UI. Wayland: the
compositor's key binding drives the API, `wtype` text injection and desktop
notifications instead of a tray, plus the Omarchy dictation backend. These
adapters provide the same behavior contract as their macOS counterparts.

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

### Requirement: Advertised Linux install path is honest
The documented Linux install path SHALL actually install and start the daemon, OR the documentation SHALL NOT advertise an install path that does not function on Linux.

#### Scenario: User follows the Linux install instructions
- **WHEN** a Linux user runs the install path the docs advertise for Linux
- **THEN** either the daemon SHALL be installed and started (e.g. via a `systemd --user` unit), OR the docs SHALL clearly scope that path to macOS and present the supported Linux procedure — never silently no-op

### Requirement: Linux hotkey listener does not latch
The Linux hotkey listener SHALL reset its held-key state on start so a previously missed release does not permanently swallow the next press.

#### Scenario: Restart after a missed release
- **WHEN** the listener is (re)started while its internal held flag was left set
- **THEN** `start()` SHALL reset the held flag so the next press is detected

_Tier: unit-mocked — `tests/test_linux_adapters.py`._

### Requirement: Wayland session support
On Linux, Whispy SHALL detect a Wayland session (`XDG_SESSION_TYPE=wayland` or a non-empty `WAYLAND_DISPLAY`) and bind the Wayland adapter set: no in-process global key listener (the compositor's key binding drives `POST /start` and `POST /stop`), text injection through `wtype`, and no tray icon. Under an X11 session the X11 adapter set (pynput, xdotool, pystray) SHALL be bound unchanged.

#### Scenario: Wayland session binds the Wayland adapters
- **WHEN** Whispy starts on Linux under a Wayland session
- **THEN** it SHALL NOT start the pynput listener, SHALL inject through `wtype`, SHALL run without the pystray tray, and SHALL log that the trigger is the compositor's binding

_Tier: unit-mocked — `tests/test_linux_adapters.py` (session env patched)._

#### Scenario: X11 session is unchanged
- **WHEN** Whispy starts on Linux under an X11 session
- **THEN** it SHALL bind the pynput listener, the xdotool injector and the pystray tray

_Tier: unit-mocked — `tests/test_linux_adapters.py`._

#### Scenario: Keystroke mode types via wtype
- **WHEN** a transcription completes under Wayland with `copy_to_clipboard` disabled
- **THEN** the injector SHALL type the text with `wtype`, reading it from stdin

_Tier: unit-mocked — `tests/test_linux_adapters.py` (subprocess patched)._

#### Scenario: Clipboard mode copies then types
- **WHEN** a transcription completes under Wayland with `copy_to_clipboard` enabled and `wl-copy` installed
- **THEN** the injector SHALL put the text on the clipboard with `wl-copy` and type it with `wtype` (Ctrl+V is ignored by terminals, and `wtype` is independent of the keyboard layout)

_Tier: unit-mocked — `tests/test_linux_adapters.py`._

#### Scenario: wtype missing is reported
- **WHEN** the `wtype` binary is not available at startup under Wayland
- **THEN** the injector SHALL emit an actionable install hint

_Tier: unit-mocked — `tests/test_linux_adapters.py`._

#### Scenario: Errors surface as desktop notifications without a tray
- **WHEN** under Wayland the recording limit is reached, the model fails to load, or capture fails
- **THEN** Whispy SHALL post a desktop notification through `notify-send` (stderr when absent)

_Tier: unit-mocked — `tests/test_linux_adapters.py`._

### Requirement: Omarchy dictation backend
Whispy SHALL ship an Omarchy dictation adapter, `omarchy-dictation-whispy start|stop|toggle`, that drives the HTTP API with the per-install token. When Whispy does not answer, the adapter SHALL post the desktop notification « Whispy ne répond pas » and exit non-zero, so a dictation is never lost silently. The Linux installer SHALL link it into `~/.local/bin` when Omarchy's `omarchy-dictation` is present.

#### Scenario: Whispy is not running
- **WHEN** `omarchy-dictation-whispy start` runs and nothing answers on the API port
- **THEN** it SHALL post « Whispy ne répond pas » and exit non-zero

_Tier: unit-mocked — `tests/test_omarchy_adapter.py` (fake `notify-send` on PATH)._

#### Scenario: Push-to-talk through the compositor binding
- **WHEN** Omarchy's F9 binding calls `omarchy-dictation start` then `omarchy-dictation stop` with `whispy` selected
- **THEN** Whispy SHALL record between the two calls and type the transcript into the focused window

_Tier: manual-ui — Omarchy VM._

### Requirement: Login autostart under a Wayland compositor
On Linux, when the installing session has an active `graphical-session.target`, the `systemd --user` unit SHALL be wanted by and ordered after that target, so the daemon starts with the compositor's environment (`WAYLAND_DISPLAY`) after every login; otherwise it SHALL keep `default.target`.

#### Scenario: Reboot under Hyprland
- **WHEN** the machine reboots and the user logs into Hyprland
- **THEN** Whispy SHALL answer on `/status` without any manual start

_Tier: manual-ui — Omarchy VM._
