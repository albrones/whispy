import QtQuick
import Quickshell
import Quickshell.Io
import "Model.js" as Model

// Whispy V2's state, input level and last dictation, read straight from its
// control socket (~/.whispy/v2/control.sock, a private Unix socket): no network
// port, no token, no process per read. One request per connection, one JSON
// line back: `status` (state, models, last problem, input level) and `last`.
//
// When it asks: once when the shell starts, on a nudge from the dictation
// backend (`omarchy-shell whispy refresh` after a start or stop, or when
// Whispy does not answer), when the panel opens, every 500 ms while Whispy
// works (transcribing, loading), and 20 times a second while it listens, for
// the pill's level. At rest it asks nothing: a Whispy that quits unattended
// shows as stopped at the next key press or panel open.
//
// The dictation key is saved in ~/.config/whispy/config.json by the backend
// (`omarchy-dictation-whispy trigger`); the panel reads it from the file.
Item {
  id: root

  readonly property string home: Quickshell.env("HOME")
  // WHISPY_V2_SOCKET overrides it, as for whispy2 itself.
  property string socketPath: Quickshell.env("WHISPY_V2_SOCKET") || (home + "/.whispy/v2/control.sock")
  readonly property string backend: home + "/.local/bin/omarchy-dictation-whispy"
  readonly property string configPath: (Quickshell.env("XDG_CONFIG_HOME") || (home + "/.config")) + "/whispy/config.json"

  property bool reachable: false
  property var status: null
  readonly property string phase: Model.phase(reachable, status)
  readonly property bool active: Model.isActive(phase)

  property var config: ({})
  property string lastText: ""
  property real level: 0
  property string message: ""
  property bool messageIsError: false
  property bool changingTrigger: triggerProcess.running

  // ---- The control socket ---------------------------------------------------

  // A socket that asks one request per connection and hands back the parsed
  // reply line, or null when nothing answers. Asks again once if a read was
  // wanted while one was in flight.
  component Ask: Socket {
    id: ask
    required property string request
    signal answered(var data)
    property bool _again: false
    property bool _replied: false

    path: root.socketPath

    function go() {
      if (connected) { _again = true; return }
      _replied = false
      connected = true
    }

    onConnectedChanged: {
      if (connected) {
        write(request + "\n")
        flush()
        return
      }
      // The reply line closes the connection; no reply means no Whispy.
      if (!_replied) answered(null)
      if (_again) { _again = false; Qt.callLater(go) }
    }

    onError: function() {
      if (!_replied) { _replied = true; answered(null) }
      connected = false
    }

    parser: SplitParser {
      onRead: function(line) {
        if (ask._replied) return
        ask._replied = true
        var data = null
        try { data = JSON.parse(line) } catch (e) {}
        ask.answered(data)
        ask.connected = false
      }
    }
  }

  Ask {
    id: statusAsk
    request: "status"
    onAnswered: function(data) { root.applyStatus(data) }
  }

  Ask {
    id: lastAsk
    request: "last"
    onAnswered: function(data) { if (data) root.lastText = data.text ? String(data.text) : "" }
  }

  function refresh() { statusAsk.go() }
  function fetchLast() { lastAsk.go() }

  function applyStatus(data) {
    var wasReachable = reachable
    var wasPhase = phase
    reachable = data !== null && typeof data === "object" && typeof data.state === "string"
    status = reachable ? data : null
    level = reachable && data.state === "recording" ? Number(data.level) || 0 : 0
    if (reachable && !wasReachable) fetchLast()
    if (wasPhase === "transcribing" && phase !== "transcribing") fetchLast()
  }

  // While listening, the status carries the pill's level: read 20 times a second.
  Timer {
    interval: root.phase === "recording" ? 50 : 500
    repeat: true
    running: root.active
    onTriggered: root.refresh()
  }

  // ---- Settings -------------------------------------------------------------

  FileView {
    id: configFile
    path: root.configPath
    watchChanges: true
    printErrors: false
    onFileChanged: reload()
    onLoaded: root.readConfig()
    onLoadFailed: root.config = ({})
  }

  function readConfig() {
    try {
      var data = JSON.parse(configFile.text())
      root.config = data && typeof data === "object" ? data : ({})
    } catch (e) {
      root.config = ({})
    }
  }

  function fetchConfig() { configFile.reload() }

  // The backend saves the preset, writes ~/.config/whispy/shortcuts.lua and
  // reloads Hyprland: the new key works at once, and at every login after.
  // It needs no running Whispy.
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
