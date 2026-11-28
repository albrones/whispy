import QtQuick
import Quickshell
import Quickshell.Io
import "Model.js" as Model
import "i18n/en.js" as En
import "i18n/fr.js" as Fr

// Whispy V2's state, input level and last dictation, read straight from its
// control socket (~/.whispy/v2/control.sock, a private Unix socket): no network
// port, no token, no process per read. One request per connection, one JSON
// line back: `status` (state, models, last problem, input level) and `last`.
//
// The update row (« Update available (X.Y.Z) », only while a release is
// offered) comes with `status`; a click sends its request (`update`) and the
// status is read every 500 ms while the row is transient.
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
//
// Whispy runs as the `systemd --user` unit whispy2.service (installed by
// scripts/bootstrap.sh): the power switch starts or stops it, Start at login
// enables or disables it.
Item {
  id: root

  readonly property string home: Quickshell.env("HOME")
  // WHISPY_V2_SOCKET overrides it, as for whispy2 itself.
  property string socketPath: Quickshell.env("WHISPY_V2_SOCKET") || (home + "/.whispy/v2/control.sock")
  readonly property string backend: home + "/.local/bin/omarchy-dictation-whispy"
  readonly property string configPath: (Quickshell.env("XDG_CONFIG_HOME") || (home + "/.config")) + "/whispy/config.json"
  readonly property string unit: "whispy2.service"
  // Replaced by tests, so they never reach a real service.
  property string serviceControl: "systemctl"

  property bool reachable: false
  property var status: null
  readonly property string phase: Model.phase(reachable, status)
  readonly property bool active: Model.isActive(phase)
  readonly property var update: Model.updateRow(reachable, status)

  property var config: ({})
  // The interface's language (Model.lang) and its texts, i18n/<lang>.js.
  readonly property string lang: Model.lang(reachable ? status : null, config,
    Quickshell.env("LC_ALL") || Quickshell.env("LC_MESSAGES") || Quickshell.env("LANG") || "")
  readonly property var t: lang === "fr" ? Fr.TEXTS : En.TEXTS
  property string lastText: ""
  property real level: 0
  property string message: ""
  property bool messageIsError: false
  property bool changingTrigger: triggerProcess.running
  // The switch asked systemd to start Whispy; cleared once the socket answers.
  property bool starting: false
  // The switch asked systemd to stop it; cleared once the socket stops answering.
  property bool stopping: false
  property bool startAtLogin: false

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

  // The update row's request: its reply is a word, not JSON; the next
  // status shows what changed.
  Ask {
    id: installUpdateAsk
    request: "update"
    onAnswered: function(data) { root.refresh() }
  }

  function runUpdate() {
    if (update && update.request === "update") installUpdateAsk.go()
  }

  function refresh() { statusAsk.go() }
  function fetchLast() { lastAsk.go() }

  function applyStatus(data) {
    var wasReachable = reachable
    var wasPhase = phase
    reachable = data !== null && typeof data === "object" && typeof data.state === "string"
    status = reachable ? data : null
    level = reachable && data.state === "recording" ? Number(data.level) || 0 : 0
    if (reachable) starting = false
    else stopping = false
    if (reachable && !wasReachable) fetchLast()
    if (wasPhase === "transcribing" && phase !== "transcribing") fetchLast()
  }

  // While listening, the status carries the pill's level: read 20 times a second.
  Timer {
    interval: root.phase === "recording" ? 50 : 500
    repeat: true
    running: root.active || root.starting || root.stopping || (root.update !== null && root.update.transient)
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
      if (exitCode !== 0) root.flash(last.replace(/^omarchy-dictation-whispy: /, "") || Model.text(root.t, "error.key"), true)
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
    command: [root.serviceControl, "--user", "is-enabled", root.unit]
    stdout: StdioCollector { id: loginStdout; waitForEnd: true }
    onExited: root.startAtLogin = String(loginStdout.text || "").trim() === "enabled"
  }

  function setStartAtLogin(on) {
    if (loginWriter.running) return
    startAtLogin = on
    loginWriter.command = [serviceControl, "--user", on ? "enable" : "disable", unit]
    loginWriter.running = true
  }

  Process {
    id: loginWriter
    onExited: function(exitCode) {
      if (exitCode !== 0) root.flash(Model.text(root.t, "error.login"), true)
      root.readStartAtLogin()
    }
  }

  function setRunning(on) {
    if (powerProcess.running) return
    starting = on
    stopping = !on
    // systemd refuses a burst of starts meant for a crashing service, not for
    // someone flipping the switch; clear that first.
    powerProcess.command = on
      ? ["sh", "-c", '"$0" --user reset-failed "$1" 2>/dev/null; exec "$0" --user start "$1"', serviceControl, unit]
      : [serviceControl, "--user", "stop", unit]
    powerProcess.running = true
    startDeadline.restart()
  }

  Process {
    id: powerProcess
    onExited: function(exitCode) {
      if (exitCode !== 0) {
        root.starting = false
        root.stopping = false
        root.flash(Model.text(root.t, "error.service"), true)
      }
      root.refresh()
    }
  }

  // A service that never answers releases the wait and shows where it is
  // (loading the models takes a few seconds; downloading them, minutes).
  Timer {
    id: startDeadline
    interval: 60000
    onTriggered: { root.starting = false; root.stopping = false; root.refresh() }
  }

  function copyLast() {
    if (lastText === "") return
    Quickshell.execDetached(["wl-copy", "--", lastText])
    flash(Model.text(t, "copied"), false)
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
