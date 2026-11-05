// Pure logic of the Whispy bar widget, shared by the QML and its node test
// (tests/test_omarchy_panel_model.py). No Qt, no I/O.

// The dictation keys the panel offers, in the order of
// OMARCHY_TRIGGER_PRESETS (src/whispy/core/config.py).
var PRESETS = [
  { value: "right_option_hold", label: "Right Option (hold)" },
  { value: "right_ctrl_hold", label: "Right Ctrl (hold)" },
  { value: "f9_hold", label: "F9 (hold)" },
  { value: "left_option_space_toggle", label: "Left Option + Space (toggle)" }
]

// The macOS menu bar's braille waveform (src/whispy/ui/unicode_anim.py):
// a calm frame at rest, a scrolling wave while Whispy works.
var IDLE_FRAME = "⣀⣤⣶⣤"
var WAVEROWS = [
  "⠖⠉⠉⠑", "⡠⠖⠉⠉", "⣠⡠⠖⠉", "⣄⣠⡠⠖", "⠢⣄⣠⡠", "⠙⠢⣄⣠", "⠉⠙⠢⣄", "⠊⠉⠙⠢",
  "⠜⠊⠉⠙", "⡤⠜⠊⠉", "⣀⡤⠜⠊", "⢤⣀⡤⠜", "⠣⢤⣀⡤", "⠑⠣⢤⣀", "⠉⠑⠣⢤", "⠋⠉⠑⠣"
]
var FRAME_INTERVAL_MS = 90

// The engine reports level = 10 x RMS; below the transcription silence gate
// (RMS 0.005, src/whispy/core/audio.py) nothing is speech, so the wave is flat.
var SILENCE_LEVEL = 0.05
// The macOS pill's perceptual boost (waveform_window.py: LEVEL_GAMMA, LEVEL_GAIN).
var LEVEL_GAMMA = 0.5
var LEVEL_GAIN = 2.0

function presetLabel(value) {
  for (var i = 0; i < PRESETS.length; i++) {
    if (PRESETS[i].value === value) return PRESETS[i].label
  }
  return ""
}

// What Whispy is doing, from the last /status answer.
//   reachable: the API answered; status: its JSON (or null);
//   transcribingHint: the dictation backend said /stop is running, during
//   which the API answers nothing else.
function phase(reachable, status, transcribingHint) {
  if (!reachable || !status) return "stopped"
  if (status.is_recording && !transcribingHint) return "recording"
  if (status.is_transcribing || transcribingHint) return "transcribing"
  if (status.model_loading) return "loading"
  if (!status.model_loaded) return "no-model"
  return "ready"
}

function phaseLabel(value) {
  if (value === "recording") return "Listening"
  if (value === "transcribing") return "Transcribing"
  if (value === "loading") return "Loading model"
  if (value === "no-model") return "Model not loaded"
  if (value === "stopped") return "Whispy stopped"
  return "Ready"
}

// The bar's tooltip: "Whispy · Listening", or "Whispy stopped".
function tooltip(value) {
  return value === "stopped" ? phaseLabel(value) : "Whispy · " + phaseLabel(value)
}

// Whispy is working: the bar animates and /status is read often.
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
