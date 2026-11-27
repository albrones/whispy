# linux-support Specification

## Purpose
Whispy on Linux: Whispy V2 (`whispy2`, see `v2-linux-app`), installed by
`scripts/bootstrap.sh` as a `systemd --user` unit (see `v2-linux-install`).
X11: Right Ctrl through XInput 2 and a tray icon. Wayland: the compositor's key
binding drives the control socket. On Omarchy: the dictation backend, the bar
widget and the recording pill. Requirements that described the Python V1
(`pynput`, `xdotool`, `pystray`, the HTTP API) went with it; V1 is kept at the
git tag `v1`.

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
On Linux under X11, the status/menu surface SHALL be provided via `pystray` by default, exposing the same control actions as the macOS menu (status, settings, quit). The macOS overlay windows SHALL NOT be required on Linux; recording state SHALL be conveyed through the tray. The tray SHALL NOT block dictation: when it cannot start, Whispy SHALL keep running with notification-only feedback and SHALL notify the user once. When the `tray_icon` config key is false, Whispy SHALL NOT start the tray and SHALL use notification-only feedback.

#### Scenario: Tray reflects recording state
- **WHEN** the engine transitions between idle and recording on Linux
- **THEN** the pystray tray SHALL reflect the state change (icon and/or menu) without requiring an overlay window

_Tier: linux-real — needs a live tray host; deferred to a Linux smoke run._

#### Scenario: A tray that cannot start does not stop Whispy
- **WHEN** the tray fails to start under X11 (pystray import fails or the icon loop raises)
- **THEN** Whispy SHALL log the reason, post one desktop notification, keep running with notification-only feedback, and exit cleanly on `quit()`

_Tier: unit-mocked — `tests/test_linux_adapters.py`._

#### Scenario: The tray is switched off in config
- **WHEN** `tray_icon` is false and Whispy starts under X11
- **THEN** the notification-only tray SHALL be used and the pystray tray SHALL NOT be started

_Tier: unit-mocked — `tests/test_linux_adapters.py`._

#### Scenario: The tray is on by default
- **WHEN** `tray_icon` is unset and Whispy starts under X11
- **THEN** the pystray tray SHALL be used

_Tier: unit-mocked — `tests/test_linux_adapters.py`._

### Requirement: Advertised Linux install path is honest
The documented Linux install path SHALL actually install and start the daemon, OR the documentation SHALL NOT advertise an install path that does not function on Linux.

#### Scenario: User follows the Linux install instructions
- **WHEN** a Linux user runs the install path the docs advertise for Linux
- **THEN** either the daemon SHALL be installed and started (e.g. via a `systemd --user` unit), OR the docs SHALL clearly scope that path to macOS and present the supported Linux procedure — never silently no-op

_Tier: live — `v2/whispy2/linux-e2e/install.sh` (the one-liner on a fresh Debian with systemd)._

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
Whispy SHALL ship an Omarchy dictation adapter, `omarchy-dictation-whispy start|stop|toggle`, that drives Whispy V2 through its control socket (`whispy2 send start|stop|toggle`), with no network port and no token; Whispy V1 need not be installed. `whispy2` SHALL be found through `WHISPY2_BIN`, then `PATH`, then `~/.local/bin`. When Whispy does not answer, refuses, or is not installed, the adapter SHALL post the desktop notification « Whispy is not answering » and exit non-zero, so a dictation is never lost silently. The Linux installer SHALL link it into `~/.local/bin` when Omarchy's `omarchy-dictation` is present.

#### Scenario: Whispy is not running
- **WHEN** `omarchy-dictation-whispy start` runs and no V2 answers on the socket
- **THEN** it SHALL post « Whispy is not answering » and exit non-zero

_Tier: unit-mocked — `tests/test_omarchy_adapter.py` (fake `whispy2` and `notify-send` on PATH)._

#### Scenario: Push-to-talk through the compositor binding
- **WHEN** Omarchy's dictation binding calls `omarchy-dictation start` then `omarchy-dictation stop` with `whispy` selected and only V2 installed
- **THEN** V2 SHALL record between the two calls and type the transcript into the focused window

_Tier: live — `v2/whispy2/linux-e2e/omarchy.sh` (sway headless, the adapter driving the real socket); manual-ui — Hyprland on Omarchy._

### Requirement: Login autostart under a Wayland compositor
On Linux, when the installing session has an active `graphical-session.target`, the `systemd --user` unit SHALL be wanted by and ordered after that target, so the daemon starts with the compositor's environment (`WAYLAND_DISPLAY`) after every login; otherwise it SHALL keep `default.target`.

#### Scenario: Reboot under Hyprland
- **WHEN** the machine reboots and the user logs into Hyprland
- **THEN** Whispy SHALL answer `status` on its control socket without any manual start

_Tier: manual-ui — Omarchy VM._

### Requirement: Omarchy dictation key presets
`omarchy-dictation-whispy trigger <preset>` SHALL accept exactly the `omarchy_trigger` presets (`right_option_hold`, `right_ctrl_hold`, `f9_hold`, `left_option_space_toggle`), save the preset as `omarchy_trigger` in `~/.config/whispy/config.json` (keeping every other key; the file V1 and V2 share), write `~/.config/whispy/shortcuts.lua` binding only the chosen key, and reload Hyprland. It SHALL need no running Whispy. Hold presets SHALL be non-consuming; the toggle preset calls `omarchy-dictation toggle`, which V2 answers in either trigger mode.

#### Scenario: A preset is chosen
- **WHEN** `trigger right_ctrl_hold` runs
- **THEN** the config SHALL hold `omarchy_trigger: right_ctrl_hold` and its other keys unchanged, the file SHALL bind Right Ctrl push-to-talk and no other preset key, and `hyprctl reload` SHALL run

_Tier: unit-mocked — `tests/test_omarchy_adapter.py` (fake `hyprctl`); live — `hyprctl binds` on Omarchy._

#### Scenario: Unknown preset or unreadable config
- **WHEN** the preset is unknown, or `config.json` is not valid JSON
- **THEN** the script SHALL exit non-zero and leave the config, the binding file and Hyprland untouched

_Tier: unit-mocked — `tests/test_omarchy_adapter.py`._

#### Scenario: Install restores the saved key
- **WHEN** `install.sh` runs on Omarchy (`omarchy-dictation-whispy shortcuts`)
- **THEN** `~/.config/whispy/shortcuts.lua` SHALL be written for the preset saved in `config.json`, or `right_option_hold` without one, with no daemon needed

_Tier: unit-mocked — `tests/test_omarchy_adapter.py`._

#### Scenario: The chosen key dictates
- **WHEN** Right Ctrl is chosen in the panel and held, then Right Option is held
- **THEN** Right Ctrl SHALL dictate with V2 and Right Option SHALL NOT, also after logging in again

_Tier: live — `v2/whispy2/linux-e2e/omarchy.sh` (the panel's picker, then the generated binding's command); manual-ui — Hyprland on Omarchy._

### Requirement: Omarchy bar widget
On Omarchy, the installer SHALL link a bar widget (`whispy.panel`) and place it in the right section of the bar. The widget SHALL read Whispy V2's control socket directly (Quickshell's `Socket`, `status` and `last`), with no network port, no token and no process per read. Its icon SHALL show Whispy's state with the macOS braille waveform; a click SHALL open a panel with a power switch, the dictation key, model and language (information only), Start at login, and the last dictation (click to copy). The power switch (and a « Start Whispy » row while it is stopped) SHALL start or stop the `systemd --user` unit `whispy2.service`; Start at login SHALL enable or disable it and show `systemctl --user is-enabled`. The dictation key SHALL be read from `config.json`; the key and Start at login SHALL be changeable while Whispy is stopped. At rest the widget SHALL NOT poll: it reads `status` when the shell starts, when the panel opens, when the dictation backend nudges it, every 500 ms while Whispy transcribes or loads, and every 50 ms while it listens.

#### Scenario: State logic
- **WHEN** the socket does not answer, or `status` says recording, transcribing or inserting, yielded, models not loaded (with or without a problem), or idle
- **THEN** the widget state SHALL be stopped, recording, transcribing, yielded, loading or no-model, or ready respectively

_Tier: unit-pure — `tests/test_omarchy_panel_model.py` (node); live — `v2/whispy2/linux-e2e/omarchy.sh` (the real `Service.qml` under Quickshell against a running V2)._

#### Scenario: Whispy stopped
- **WHEN** V2 is not running and the panel is opened
- **THEN** the icon SHALL be greyed and the panel SHALL read « Whispy stopped »

#### Scenario: Start and stop from the panel
- **WHEN** the power switch or « Start Whispy » is activated while Whispy is stopped, or the switch while it runs
- **THEN** the panel SHALL run `systemctl --user start whispy2.service` (after `reset-failed`), or `systemctl --user stop whispy2.service`, show « Starting » until the socket answers (60 s at most), and say so if `systemctl` fails

#### Scenario: Start at login from the panel
- **WHEN** Start at login is toggled
- **THEN** the panel SHALL run `systemctl --user enable` or `disable whispy2.service`, then read `is-enabled` back

_Tier: unit — `tests/test_omarchy_panel_model.py` (the commands); manual-ui — Omarchy._

_Tier: live — `v2/whispy2/linux-e2e/omarchy.sh`; manual-ui — Omarchy._

#### Scenario: A dictation drives the icon
- **WHEN** the dictation key is held, then released
- **THEN** the icon SHALL show listening, then transcribing, then ready, and the last dictation SHALL show its text

_Tier: live — `v2/whispy2/linux-e2e/omarchy.sh`; manual-ui — Omarchy._

### Requirement: Omarchy recording pill
While recording, the bar widget SHALL show a pill at the bottom centre of the focused monitor: a layer-shell overlay with no keyboard interactivity and an empty input region, so the focused window keeps the focus. Its bars SHALL follow the `level` of V2's socket `status`, read only while recording, and SHALL stay flat at or below the transcription silence gate.

#### Scenario: Flat in silence, moving with speech
- **WHEN** the level is at or below 0.05, or above it
- **THEN** the bars SHALL be at their minimum height, or grow with the level, taller in the middle

_Tier: unit-pure — `tests/test_omarchy_panel_model.py` (node); live — `v2/whispy2/linux-e2e/omarchy.sh` (levels read during a dictation)._

#### Scenario: Focus is kept
- **WHEN** a dictation runs into a focused window
- **THEN** the pill SHALL appear and the text SHALL land in that window, which stays focused

_Tier: manual-ui — Omarchy VM._
