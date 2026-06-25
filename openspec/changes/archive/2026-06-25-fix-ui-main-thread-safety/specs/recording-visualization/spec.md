## ADDED Requirements

### Requirement: UI updates are marshaled to the main thread
UI updates triggered by engine callbacks that fire on background threads (event-tap, transcription worker) SHALL be marshaled to the main thread before mutating AppKit, so the app does not crash or corrupt UI state from off-main-thread access.

#### Scenario: Status update fires from a background thread
- **WHEN** an engine status callback fires on the event-tap or transcription-worker thread and updates the menu title
- **THEN** the AppKit mutation SHALL execute on the main thread (deferred via the main run loop if necessary)

### Requirement: Visualization tolerates a display-less session
Visualization SHALL not crash when no display is available.

#### Scenario: No screens available
- **WHEN** a visualization window is asked to show on a session with no screens
- **THEN** it SHALL bail safely without raising (no unguarded `screens()[0]` index)
