// Pure logic of the Whispy bar widget, shared by the QML and its node test
// (tests/test_omarchy_panel_model.py). No Qt, no I/O.

// The dictation keys the panel offers, in the order of the backend's presets
// (omarchy-dictation-whispy) and of omarchy_trigger in docs/src/config-schema.json.
var PRESETS = [
  { value: "right_option_hold", label: "Right Option (hold)" },
  { value: "right_ctrl_hold", label: "Right Ctrl (hold)" },
  { value: "f9_hold", label: "F9 (hold)" },
  { value: "left_option_space_toggle", label: "Left Option + Space (toggle)" }
]

// The macOS menu bar's braille waveform (v2/whispy2/src/title_anim.rs):
// a calm frame at rest, a scrolling wave while Whispy works.
var IDLE_FRAME = "⣀⣤⣶⣤"
var WAVEROWS = [
  "⠖⠉⠉⠑", "⡠⠖⠉⠉", "⣠⡠⠖⠉", "⣄⣠⡠⠖", "⠢⣄⣠⡠", "⠙⠢⣄⣠", "⠉⠙⠢⣄", "⠊⠉⠙⠢",
  "⠜⠊⠉⠙", "⡤⠜⠊⠉", "⣀⡤⠜⠊", "⢤⣀⡤⠜", "⠣⢤⣀⡤", "⠑⠣⢤⣀", "⠉⠑⠣⢤", "⠋⠉⠑⠣"
]
var FRAME_INTERVAL_MS = 90

// Whispy reports the level as 10 x RMS; below the transcription silence gate
// (RMS 0.005, whispy-core) nothing is speech, so the wave is flat.
var SILENCE_LEVEL = 0.05
// The macOS pill's perceptual boost (v2/whispy2/src/pill_geometry.rs).
var LEVEL_GAMMA = 0.5
var LEVEL_GAIN = 2.0

function presetLabel(value) {
  for (var i = 0; i < PRESETS.length; i++) {
    if (PRESETS[i].value === value) return PRESETS[i].label
  }
  return ""
}

// What Whispy V2 is doing, from the last `status` answer of its control socket.
//   reachable: the socket answered; status: its JSON (or null), e.g.
//   {"state":"idle","models_loaded":true,"yielded":false,"last_problem":null,
//    "trigger_mode":"hold","level":0.000}
function phase(reachable, status) {
  if (!reachable || !status) return "stopped"
  if (status.state === "recording") return "recording"
  if (status.state === "transcribing" || status.state === "inserting") return "transcribing"
  if (status.state === "yielded") return "yielded"
  if (!status.models_loaded) return status.last_problem ? "no-model" : "loading"
  return "ready"
}

function phaseLabel(value) {
  if (value === "recording") return "Listening"
  if (value === "transcribing") return "Transcribing"
  if (value === "loading") return "Loading model"
  if (value === "no-model") return "Model not loaded"
  if (value === "stopped") return "Whispy stopped"
  if (value === "yielded") return "An older Whispy is running"
  return "Ready"
}

// The bar's tooltip: "Whispy · Listening", or "Whispy stopped".
function tooltip(value) {
  return value === "stopped" ? phaseLabel(value) : "Whispy · " + phaseLabel(value)
}

// Whispy is working: the bar animates and the status is read often.
function isActive(value) {
  return value === "recording" || value === "transcribing" || value === "loading"
}

function frame(value, tick) {
  return isActive(value) ? WAVEROWS[((tick % WAVEROWS.length) + WAVEROWS.length) % WAVEROWS.length] : IDLE_FRAME
}

// 0..1 bar amplitude from the engine's level: flat in silence, then the
// macOS boost so ordinary speech fills the bars.
function displayLevel(level) {
  var value = Number(level)
  if (!isFinite(value) || value <= SILENCE_LEVEL) return 0
  var above = Math.min(1, (value - SILENCE_LEVEL) / (1 - SILENCE_LEVEL))
  return Math.min(Math.pow(above, LEVEL_GAMMA) * LEVEL_GAIN, 1)
}

// Height of bar `index` of `count`, mirroring the macOS pill: a symmetric
// envelope, taller in the middle, with a per-bar wobble that only moves bars
// that already have sound behind them.
function barHeight(index, count, amplitude, phaseRadians, minHeight, maxHeight) {
  var half = (count - 1) / 2
  var envelope = 0.45 + 0.55 * (1 - Math.abs(index - half) / half)
  var wobble = 0.5 + 0.5 * Math.sin(phaseRadians + index * 0.9)
  var amount = amplitude * envelope * (0.6 + 0.4 * wobble)
  return minHeight + (maxHeight - minHeight) * amount
}

if (typeof module !== "undefined") {
  module.exports = {
    PRESETS: PRESETS,
    IDLE_FRAME: IDLE_FRAME,
    WAVEROWS: WAVEROWS,
    presetLabel: presetLabel,
    phase: phase,
    phaseLabel: phaseLabel,
    tooltip: tooltip,
    isActive: isActive,
    frame: frame,
    displayLevel: displayLevel,
    barHeight: barHeight
  }
}
