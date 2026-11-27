import QtQuick
import Quickshell
import Quickshell.Io

// The Omarchy bar panel's Service.qml, alone under Quickshell (no Omarchy
// shell around it): it logs every change the icon, the pill and the panel
// would draw, and takes the panel's key pick, power switch and Start at login
// over Quickshell's own IPC. systemctl is a stand-in (fakes/systemctl) that
// runs whispy2 as the unit would.
ShellRoot {
  Service {
    id: sw
    serviceControl: "/tmp/fakes/systemctl"
    onPhaseChanged: console.info("panel: phase=" + phase)
    onLevelChanged: if (level > 0) console.info("panel: level=" + level.toFixed(3))
    onLastTextChanged: console.info("panel: last=[" + lastText + "]")
    onConfigChanged: console.info("panel: key=" + (config.omarchy_trigger || "none"))
    onMessageChanged: if (message !== "") console.info("panel: message=" + message)
    onStartingChanged: console.info("panel: starting=" + starting)
    onStoppingChanged: console.info("panel: stopping=" + stopping)
    onStartAtLoginChanged: console.info("panel: startAtLogin=" + startAtLogin)
  }

  IpcHandler {
    target: "whispy"
    function refresh(): string { sw.refresh(); return "ok" }
    function pick(preset: string): string { sw.setTrigger(preset); return "ok" }
    function state(): string { return sw.phase + " key=" + (sw.config.omarchy_trigger || "none") + " login=" + sw.startAtLogin }
    function power(on: bool): string { sw.setRunning(on); return "ok" }
    function login(on: bool): string { sw.setStartAtLogin(on); return "ok" }
    function readLogin(): string { sw.readStartAtLogin(); return "ok" }
  }
}
