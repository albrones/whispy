## MODIFIED Requirements

### Requirement: Uninstall offers scoped removal of user data
`install.sh --uninstall` SHALL, after removing the venv and any legacy LaunchAgent, offer to also remove the config directory (which includes the local API token), the log files, and the downloaded Parakeet model cache. The offer SHALL default to keeping the data and SHALL only prompt when running interactively (a TTY); a non-interactive invocation (e.g. `scripts/bootstrap.sh --uninstall` piped via `curl | bash`) SHALL keep the data without blocking on an unanswerable prompt. Model-cache removal SHALL be scoped to the Parakeet ONNX snapshots only, never the shared HuggingFace hub cache directory as a whole. Because a Whisper-era install may still hold `models--Systran--faster-whisper-*` snapshots that this uninstaller no longer manages, the uninstall output SHALL name that path as safe to delete manually rather than deleting it.

#### Scenario: Interactive uninstall offers to remove user data
- **WHEN** `install.sh --uninstall` runs with a TTY attached and the user answers "y"
- **THEN** it SHALL remove `~/.config/whispy`, `~/.whispy.log` (and rotated backups), `~/.whispy-error.log` (and rotated backups), and the Parakeet ONNX snapshots under the HuggingFace hub cache

#### Scenario: Default answer keeps the data
- **WHEN** the interactive prompt is presented and the user answers with anything other than "y"/"Y" (including just pressing Enter)
- **THEN** the config, logs, and model cache SHALL be left in place

#### Scenario: Non-interactive uninstall never blocks on the prompt
- **WHEN** `install.sh --uninstall` runs with no TTY on stdin (e.g. invoked from `scripts/bootstrap.sh` under `curl | bash`)
- **THEN** it SHALL skip the prompt entirely and keep the user data, without hanging

#### Scenario: Model-cache deletion never touches the shared hub cache
- **WHEN** the user opts to remove the model cache
- **THEN** only paths matching the Parakeet ONNX snapshot name inside `~/.cache/huggingface/hub` SHALL be removed, and the hub cache directory itself (which may hold other tools' cached models) SHALL NOT be deleted

#### Scenario: Stale Whisper cache is reported, not deleted
- **WHEN** the uninstaller runs on a machine upgraded from a Whisper-era install
- **THEN** it SHALL print the location of any `models--Systran--faster-whisper-*` snapshots as safe to delete manually, and SHALL NOT delete them itself
