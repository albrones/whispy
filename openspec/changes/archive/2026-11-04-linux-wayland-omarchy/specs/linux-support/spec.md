## REMOVED Requirements

### Requirement: X11 session requirement
**Reason**: Wayland sessions are now supported (see "Wayland session support").
**Migration**: None; X11 sessions keep the same behavior.

### Requirement: Linux hotkey listener warns on Wayland and does not latch
**Reason**: Under Wayland the pynput listener is no longer started, so there is nothing to warn about; the latch reset is kept in "Linux hotkey listener does not latch".
**Migration**: None.

## ADDED Requirements

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
