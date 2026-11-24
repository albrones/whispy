## MODIFIED Requirements

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
