import QtQuick
import Quickshell
import Quickshell.Wayland
import qs.Commons
import "Model.js" as Model

// The macOS recording pill (src/whispy/ui/waveform_window.py): bottom centre,
// eleven bars that follow the microphone while Whispy listens. A layer-shell
// overlay with no keyboard interactivity and an empty input region, so the
// window being dictated into keeps the focus and every click.
PanelWindow {
  id: pill

  required property var service
  // The output this bar widget lives on; the pill shows on the focused one only.
  property var targetScreen: null
  property bool onFocusedScreen: true

  readonly property bool shown: service.phase === "recording" && onFocusedScreen
  readonly property int barCount: 11
  readonly property real barWidth: 5
  readonly property real barGap: 6
  readonly property real barMinHeight: 5
  readonly property real barMaxHeight: 38

  // Smoothed toward the polled level each frame, as the macOS view does.
  property real amplitude: 0
  property real wavePhase: 0
  property double _lastTick: 0

  screen: targetScreen
  visible: shown || card.opacity > 0
  anchors.bottom: true
  margins.bottom: 40
  implicitWidth: 168
  implicitHeight: 52
  color: "transparent"
  exclusionMode: ExclusionMode.Ignore
  WlrLayershell.layer: WlrLayer.Overlay
  WlrLayershell.keyboardFocus: WlrKeyboardFocus.None
  WlrLayershell.namespace: "whispy-pill"
  mask: Region {}

  onShownChanged: if (shown) { amplitude = 0; _lastTick = 0 }

  Timer {
    interval: 33
    repeat: true
    running: pill.visible
    onTriggered: {
      var now = Date.now()
      var dt = pill._lastTick > 0 ? (now - pill._lastTick) / 1000 : interval / 1000
      pill._lastTick = now
      var target = Model.displayLevel(pill.service.level)
      pill.amplitude += (target - pill.amplitude) * Math.min(dt * 8, 1)
      pill.wavePhase += dt * 6
    }
  }

  Rectangle {
    id: card
    anchors.fill: parent
    radius: height / 2
    color: Qt.rgba(0.07, 0.07, 0.09, 0.92)
    opacity: pill.shown ? 1 : 0
    scale: pill.shown ? 1 : 0.96
    Behavior on opacity { NumberAnimation { duration: Style.duration(pill.shown ? 180 : 120); easing.type: Easing.OutCubic } }
    Behavior on scale {
      NumberAnimation { duration: Style.duration(180); easing.type: Easing.Bezier; easing.bezierCurve: Style.easeOut }
    }

    Row {
      anchors.centerIn: parent
      spacing: pill.barGap

      Repeater {
        model: pill.barCount
        Rectangle {
          required property int index
          anchors.verticalCenter: parent.verticalCenter
          width: pill.barWidth
          height: Model.barHeight(index, pill.barCount, pill.amplitude, pill.wavePhase, pill.barMinHeight, pill.barMaxHeight)
          radius: width / 2
          // Brand green, a little brighter with the level.
          color: Qt.rgba(Math.min(0.141 + 0.10 * pill.amplitude, 1),
                         Math.min(0.749 + 0.15 * pill.amplitude, 1),
                         Math.min(0.620 + 0.10 * pill.amplitude, 1), 0.95)
        }
      }
    }
  }
}
