// The Omarchy panel's texts in English. fr.js has the same keys
// (tests/test_omarchy_panel_model.py fails otherwise); Model.lang() picks one.
var TEXTS = {
  "phase.ready": "Ready",
  "phase.recording": "Listening",
  "phase.transcribing": "Transcribing",
  "phase.loading": "Loading model",
  "phase.no_model": "Model not loaded",
  "phase.stopped": "Whispy stopped",
  "phase.yielded": "An older Whispy is running",
  "preset.right_option_hold": "Right Option (hold)",
  "preset.right_ctrl_hold": "Right Ctrl (hold)",
  "preset.f9_hold": "F9 (hold)",
  "preset.left_option_space_toggle": "Left Option + Space (toggle)",
  "start": "Start Whispy",
  "start.busy": "Starting Whispy…",
  "start.caption": "Runs systemctl --user start whispy2",
  "starting": "Starting",
  "stopping": "Stopping",
  "dictation_key": "Dictation key",
  "dictation_key.default": "Omarchy default",
  "model": "Model",
  "language": "Language",
  "language.value": "Detected automatically",
  "start_at_login": "Start at login",
  "update.caption": "Installs it, then restarts Whispy",
  "last_dictation": "LAST DICTATION",
  "last_dictation.none": "Nothing dictated yet",
  "last_dictation.copy": "Click or C to copy",
  "copied": "Copied",
  "error.key": "Could not change the key",
  "error.login": "Could not change Start at login",
  "error.service": "systemctl could not change Whispy"
}

if (typeof module !== "undefined") module.exports = { TEXTS: TEXTS }
