// Pure logic of the Whispy bar widget, shared by the QML and its node test
// (tests/test_omarchy_panel_model.py). No Qt, no I/O.

// The dictation keys the panel offers, in the order of the backend's presets
// (omarchy-dictation-whispy) and of omarchy_trigger in docs/src/config-schema.json.
// Their labels are the texts "preset.<value>" of i18n/<lang>.js.
var PRESETS = [
  { value: "right_option_hold" },
  { value: "right_ctrl_hold" },
  { value: "f9_hold" },
  { value: "left_option_space_toggle" }
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

// The panel's language, "en" or "fr": Whispy's own when it answers (its
// `status` carries `lang`, so a choice in its menu shows here too), else the
// `language` it would force (config.json), else the session's locale
// (LC_ALL, LC_MESSAGES, LANG: French for fr*, English for any other).
function lang(status, config, localeTag) {
  if (status && (status.lang === "fr" || status.lang === "en")) return status.lang
  var forced = config ? config.language : null
  if (forced === "fr" || forced === "en") return forced
  return /^fr([-_.@]|$)/i.test(String(localeTag || "")) ? "fr" : "en"
}

// The text `key` from `t` (a TEXTS table of i18n/), the key itself if missing.
function text(t, key) {
  return t && typeof t[key] === "string" ? t[key] : key
}

// The dictation keys with their labels in `t`.
function presets(t) {
  return PRESETS.map(function(preset) {
    return { value: preset.value, label: text(t, "preset." + preset.value) }
  })
}

function presetLabel(value, t) {
  for (var i = 0; i < PRESETS.length; i++) {
    if (PRESETS[i].value === value) return text(t, "preset." + value)
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

function phaseLabel(value, t) {
  if (value === "recording") return text(t, "phase.recording")
  if (value === "transcribing") return text(t, "phase.transcribing")
  if (value === "loading") return text(t, "phase.loading")
  if (value === "no-model") return text(t, "phase.no_model")
  if (value === "stopped") return text(t, "phase.stopped")
  if (value === "yielded") return text(t, "phase.yielded")
  return text(t, "phase.ready")
}

// The update row of the `status` answer (v2/whispy2/src/update.rs), e.g.
//   {"title":"Update available (2.5.0)","action":"update","transient":false}
// as { title, request, transient }: `request` is the socket request a click
// sends ("update", or "" while the install runs), and `transient` asks the
// panel to read the status again until it settles. null when Whispy is up to
// date (the status has no `update`), stopped, or too old to report one.
function updateRow(reachable, status) {
  if (!reachable || !status || !status.update || typeof status.update.title !== "string") return null
  var update = status.update
  var request = update.action === "update" ? "update" : ""
  return { title: update.title, request: request, transient: update.transient === true }
}

// The bar's tooltip: "Whispy · Listening", or "Whispy stopped".
function tooltip(value, t) {
  return value === "stopped" ? phaseLabel(value, t) : "Whispy · " + phaseLabel(value, t)
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
    lang: lang,
    text: text,
    presets: presets,
    presetLabel: presetLabel,
    phase: phase,
    phaseLabel: phaseLabel,
    updateRow: updateRow,
    tooltip: tooltip,
    isActive: isActive,
    frame: frame,
    displayLevel: displayLevel,
    barHeight: barHeight
  }
}
