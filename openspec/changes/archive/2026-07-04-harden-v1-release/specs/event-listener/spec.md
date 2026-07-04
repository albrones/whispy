## ADDED Requirements

### Requirement: Event-tap failure guidance matches the current architecture
When `CGEventTapCreate` fails or the run loop does not start in time, the listener's stderr guidance SHALL name Whispy and the in-app Restart action (or `open -a Whispy`), and SHALL NOT reference `python3` or the pre-rebrand `com.whispy` LaunchAgent, since the shipped macOS install is a signed `.app` bundle with no LaunchAgent.

#### Scenario: Tap creation fails
- **WHEN** `CGEventTapCreate` returns `None`
- **THEN** the printed guidance SHALL tell the user to grant Input Monitoring to Whispy and restart via the menu's Restart item or `open -a Whispy`, not `python3` or `launchctl kickstart`

#### Scenario: Run loop start times out
- **WHEN** the run loop does not confirm startup within the timeout
- **THEN** the printed guidance SHALL name Whispy, not `python3`, as the process that may be missing Input Monitoring
