import QtQuick
import Quickshell
import Quickshell.Io

// The Omarchy bar panel's Service.qml, alone under Quickshell (no Omarchy
// shell around it): it logs every change the icon, the pill and the panel
// would draw, and takes the panel's key pick over Quickshell's own IPC.
ShellRoot {
  Service {
    id: sw
    onPhaseChanged: console.info("panel: phase=" + phase)
    onLevelChanged: if (level > 0) console.info("panel: level=" + level.toFixed(3))
    onLastTextChanged: console.info("panel: last=[" + lastText + "]")
    onConfigChanged: console.info("panel: key=" + (config.omarchy_trigger || "none"))
    onMessageChanged: if (message !== "") console.info("panel: message=" + message)
  }

  IpcHandler {
    target: "whispy"
    function refresh(): string { sw.refresh(); return "ok" }
    function pick(preset: string): string { sw.setTrigger(preset); return "ok" }
    function state(): string { return sw.phase + " key=" + (sw.config.omarchy_trigger || "none") }
  }
}
