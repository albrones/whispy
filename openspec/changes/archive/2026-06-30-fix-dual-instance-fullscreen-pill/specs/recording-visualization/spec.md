## ADDED Requirements

### Requirement: Pill appears above the active full-screen Space on every recording

The floating waveform pill SHALL appear above the currently active Space — including another application's full-screen Space — on every recording start, not only on the process's first show. Its Space-joining collection behavior and window level SHALL be (re)applied and its position resolved against the active Space each time it is shown.

#### Scenario: Pill shows over a full-screen app

- **WHEN** another application is frontmost in a full-screen Space and recording begins
- **THEN** the pill appears floating above that full-screen Space, near the bottom center of the active screen

#### Scenario: Pill shows reliably on repeated recordings without restart

- **WHEN** the daemon has already shown and hidden the pill at least once and recording begins again while a full-screen app is frontmost
- **THEN** the pill appears above the full-screen Space without requiring the daemon to be restarted

#### Scenario: Pill stays click-through and non-activating over full screen

- **WHEN** the pill is visible over a full-screen app
- **THEN** mouse events pass through to the underlying app and the pill does not steal focus or exit the app's full-screen Space
