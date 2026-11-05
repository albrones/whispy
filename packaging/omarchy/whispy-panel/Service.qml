import QtQuick
import Quickshell
import Quickshell.Io
import "Model.js" as Model

// Whispy's state and settings, read and written through its loopback HTTP API
// (the same one the dictation keys drive). Requests go through QML's own
// XMLHttpRequest, so a poll costs one loopback request and no process.
//
// When it asks: once when the shell starts, on a nudge from the dictation
// backend (start, stop, or Whispy not answering), when the panel opens, every
// 500 ms while Whispy works (listening, transcribing, loading, starting), and
// 20 times a second for the input level while the pill shows. At rest it asks
// nothing: a daemon that dies unattended shows as stopped at the next key
// press or panel open.
Item {
  id: root

  property string api: "http://127.0.0.1:9090"
  readonly property string home: Quickshell.env("HOME")
  readonly property string backend: home + "/.local/bin/omarchy-dictation-whispy"
  // Replaced by tests, so they never reach a real service.
  property string serviceControl: "systemctl"

  property bool reachable: false
  property var status: null
  // The backend says /stop is running; the API answers nothing else until it ends.
  property bool transcribingHint: false
  readonly property string phase: Model.phase(reachable, status, transcribingHint)
  readonly property bool active: Model.isActive(phase)

  property var config: ({})
  property string lastText: ""
  property real level: 0
  property bool startAtLogin: false
  // Asked systemd to start Whispy; held until its API answers.
  property bool starting: false
  property string message: ""
  property bool messageIsError: false
  property bool changingTrigger: triggerProcess.running

  FileView {
    id: tokenFile
    path: root.home + "/.config/whispy/config.token"
    blockLoading: true
    watchChanges: true
    onFileChanged: reload()
  }

  function request(method, path, body, done) {
    var xhr = new XMLHttpRequest()
    xhr.onreadystatechange = function() {
      if (xhr.readyState !== XMLHttpRequest.DONE) return
      var data = null
      try { data = JSON.parse(xhr.responseText) } catch (e) {}
      done(xhr.status, data)
    }
    xhr.open(method, api + path)
    xhr.setRequestHeader("Authorization", "Bearer " + String(tokenFile.text() || "").trim())
    if (body === undefined) {
      xhr.send()
    } else {
      xhr.setRequestHeader("Content-Type", "application/json")
      xhr.send(JSON.stringify(body))
    }
  }

  // ---- Status ---------------------------------------------------------------

  property bool _statusInFlight: false
  property bool _refreshAgain: false

  function refresh() {
    if (_statusInFlight) { _refreshAgain = true; return }
    _statusInFlight = true
    request("GET", "/status", undefined, function(code, data) {
      root._statusInFlight = false
      root.applyStatus(code === 200 ? data : null)
      if (root._refreshAgain) { root._refreshAgain = false; root.refresh() }
    })
  }

  function applyStatus(data) {
    var wasReachable = reachable
    var wasPhase = phase
    reachable = data !== null
    status = data
    if (reachable) starting = false
    if (!reachable || (!data.is_recording && !data.is_transcribing)) transcribingHint = false
    if (reachable && !wasReachable) { fetchConfig(); fetchLast() }
    if (wasPhase === "transcribing" && phase !== "transcribing") fetchLast()
  }

  // From the dictation backend, just before its blocking /stop.
  function markTranscribing() {
    transcribingHint = true
    hintDeadline.restart()
  }

  Timer {
    id: hintDeadline
    interval: 65000
    onTriggered: { root.transcribingHint = false; root.refresh() }
  }

  Timer {
    interval: 500
    repeat: true
    running: root.active || root.starting
    onTriggered: root.refresh()
  }

  // ---- Input level, for the pill --------------------------------------------

  property bool _levelInFlight: false

  Timer {
    interval: 50
    repeat: true
    running: root.phase === "recording"
    onTriggered: {
      if (root._levelInFlight) return
      root._levelInFlight = true
      root.request("GET", "/level", undefined, function(code, data) {
        root._levelInFlight = false
        root.level = code === 200 && data ? Number(data.level) || 0 : 0
      })
    }
    onRunningChanged: if (!running) root.level = 0
  }

  // ---- Settings -------------------------------------------------------------

  function fetchConfig() {
    request("GET", "/config", undefined, function(code, data) {
      if (code === 200 && data) root.config = data
    })
  }

  function fetchLast() {
    request("GET", "/last-transcription", undefined, function(code, data) {
      if (code === 200 && data) root.lastText = data.text ? String(data.text) : ""
    })
  }

  // Drawn at once, then replaced by what the daemon saved.
  function setConfig(key, value) {
    var next = Object.assign({}, config)
    next[key] = value
    config = next
    var body = {}
    body[key] = value
    request("POST", "/config", body, function(code, data) {
      if (code === 200 && data && data.config) root.config = data.config
      else { root.flash("Could not save the setting", true); root.fetchConfig() }
    })
  }

  // The backend saves the preset, writes ~/.config/whispy/shortcuts.lua and
  // reloads Hyprland: the new key works at once, and at every login after.
  function setTrigger(preset) {
    if (triggerProcess.running || preset === config.omarchy_trigger) return
    var next = Object.assign({}, config)
    next.omarchy_trigger = preset
    config = next
    triggerProcess.command = [backend, "trigger", preset]
    triggerProcess.running = true
  }

  Process {
    id: triggerProcess
    stderr: StdioCollector { id: triggerStderr; waitForEnd: true }
    onExited: function(exitCode) {
      var last = String(triggerStderr.text || "").trim().split("\n").pop()
      if (exitCode !== 0) root.flash(last.replace(/^omarchy-dictation-whispy: /, "") || "Could not change the key", true)
      else if (last.indexOf("Warning: ") === 0) root.flash(last.slice(9), false)
      root.fetchConfig()
    }
  }

  // ---- The service ----------------------------------------------------------

  function readStartAtLogin() {
    loginReader.running = true
  }

  Process {
    id: loginReader
    command: [root.serviceControl, "--user", "is-enabled", "whispy"]
    stdout: StdioCollector { id: loginStdout; waitForEnd: true }
    onExited: root.startAtLogin = String(loginStdout.text || "").trim() === "enabled"
  }

  function setStartAtLogin(on) {
    if (loginWriter.running) return
    startAtLogin = on
    loginWriter.command = [serviceControl, "--user", on ? "enable" : "disable", "whispy"]
    loginWriter.running = true
  }

  Process {
    id: loginWriter
    onExited: function(exitCode) {
      if (exitCode !== 0) root.flash("Could not change Start at login", true)
      root.readStartAtLogin()
    }
  }

  function setRunning(on) {
    if (powerProcess.running) return
    starting = on
    // systemd refuses a burst of starts meant for a crashing service, not for
    // someone flipping the switch; clear that first.
    powerProcess.command = on
      ? ["sh", "-c", '"$0" --user reset-failed whispy 2>/dev/null; exec "$0" --user start whispy', serviceControl]
      : [serviceControl, "--user", "stop", "whispy"]
    powerProcess.running = true
    if (on) startDeadline.restart()
  }

  Process {
    id: powerProcess
    onExited: function(exitCode) {
      if (exitCode !== 0) { root.starting = false; root.flash("systemctl could not change Whispy", true) }
      root.refresh()
    }
  }

  // A service that never answers releases the wait and shows where it is.
  Timer {
    id: startDeadline
    interval: 60000
    onTriggered: { root.starting = false; root.refresh() }
  }

  function copyLast() {
    if (lastText === "") return
    Quickshell.execDetached(["wl-copy", "--", lastText])
    flash("Copied", false)
  }

  function flash(text, isError) {
    message = text
    messageIsError = isError === true
    messageTimer.restart()
  }

  Timer {
    id: messageTimer
    interval: 4000
    onTriggered: root.message = ""
  }

  Component.onCompleted: refresh()
}
