import QtQuick
import QtQuick.Controls
import QtQuick.Layouts
import Quickshell
import Quickshell.Hyprland
import Quickshell.Io
import qs.Commons
import qs.Commons as Commons
import qs.Ui
import "Model.js" as Model

// Whispy in the Omarchy bar: the macOS menu bar's waveform as the icon, a
// panel with its settings, and the recording pill. See Service.qml for how and
// when it talks to the daemon.
Panel {
  id: root
  moduleName: "whispy"
  ipcTarget: "whispy"
  manageIpc: false

  // "" is the main page; "trigger" drills the panel into the key choices.
  property string page: ""
  property int rowIndex: 0
  property bool cursorActive: false
  property int tick: 0

  readonly property color foreground: bar ? bar.foreground : Commons.Color.foreground
  readonly property color urgent: bar ? bar.urgent : Commons.Color.urgent
  readonly property color dim: Qt.darker(foreground, 1.55)
  readonly property string fontFamily: bar ? bar.fontFamily : Style.font.family
  readonly property color brandGreen: "#24bf9e"

  readonly property string phase: sw.phase
  readonly property bool running: sw.reachable
  readonly property color barIconColor: phase === "stopped" ? Qt.darker(barForeground, 1.55)
    : phase === "recording" ? brandGreen : barForeground

  readonly property var rows: running
    ? ["power", "trigger", "clipboard", "login"].concat(sw.lastText !== "" ? ["last"] : [])
    : ["power", "start"]
  readonly property string currentRow: cursorActive && page === "" ? rows[Math.min(rowIndex, rows.length - 1)] : ""
  readonly property var pageOptions: page === "trigger" ? Model.PRESETS : []

  function openPage(id, byPointer) {
    page = id
    var index = 0
    for (var i = 0; i < pageOptions.length; i++) if (pageOptions[i].value === sw.config.omarchy_trigger) index = i
    rowIndex = index
    if (byPointer) cursorActive = false
  }

  function leavePage(byPointer) {
    var from = page
    page = ""
    rowIndex = Math.max(0, rows.indexOf(from))
    if (byPointer) cursorActive = false
  }

  function choose(value, byPointer) {
    sw.setTrigger(value)
    leavePage(byPointer)
  }

  function activate(id) {
    if (id === "power" || id === "start") sw.setRunning(!sw.reachable && !sw.starting)
    else if (id === "trigger") openPage("trigger")
    else if (id === "clipboard") sw.setConfig("copy_to_clipboard", !sw.config.copy_to_clipboard)
    else if (id === "login") sw.setStartAtLogin(!sw.startAtLogin)
    else if (id === "last") sw.copyLast()
  }

  function moveCursor(dx, dy) {
    cursorActive = true
    if (page !== "") {
      if (dx < 0) { leavePage(); return }
      if (dy === 0) return
      rowIndex = Math.max(-1, Math.min(pageOptions.length - 1, rowIndex + dy))
      return
    }
    if (dx > 0 && currentRow === "trigger") { openPage("trigger"); return }
    if (dy === 0) return
    rowIndex = Math.max(0, Math.min(rows.length - 1, rowIndex + dy))
  }

  function setRowCursor(id) {
    cursorActive = true
    rowIndex = Math.max(0, rows.indexOf(id))
  }

  function activateCursor() {
    if (page === "") { activate(currentRow); return }
    if (rowIndex < 0) leavePage()
    else if (rowIndex < pageOptions.length) choose(pageOptions[rowIndex].value)
  }

  function togglePanel() {
    if (root.opened) root.close()
    else root.open()
  }

  onOpenedChanged: if (opened) {
    page = ""
    cursorActive = false
    rowIndex = 0
    sw.refresh()
    sw.fetchConfig()
    sw.fetchLast()
    sw.readStartAtLogin()
    Qt.callLater(function() { keyCatcher.forceActiveFocus() })
  }

  Service { id: sw }
  property alias service: sw

  // The dictation backend nudges the widget, so the icon follows a dictation
  // without polling: `omarchy-shell whispy refresh|transcribing`.
  IpcHandler {
    target: root.ipcTarget
    function open(): void { root.open() }
    function close(): void { root.close() }
    function toggle(): void { root.togglePanel() }
    function refresh(): string { sw.refresh(); return "ok" }
    function transcribing(): string { sw.markTranscribing(); sw.refresh(); return "ok" }
    function state(): string { return root.phase }
  }

  // The waveform scrolls only while Whispy works; at rest nothing ticks.
  Timer {
    interval: 90
    repeat: true
    running: Model.isActive(root.phase)
    onTriggered: root.tick += 1
  }

  Pill {
    service: sw
    targetScreen: root.QsWindow.window ? root.QsWindow.window.screen : null
    onFocusedScreen: {
      var monitor = Hyprland.focusedMonitor
      return !targetScreen || !monitor || String(monitor.name) === String(targetScreen.name)
    }
  }

  implicitWidth: button.implicitWidth
  implicitHeight: button.implicitHeight

  TextMetrics {
    id: frameMetrics
    font.family: root.fontFamily
    font.pixelSize: Style.bar.iconFont
    text: Model.IDLE_FRAME
  }

  BarIconButton {
    id: button
    anchors.fill: parent
    bar: root.bar
    iconComponent: Component { Item {} }
    fixedWidth: vertical ? -1 : Math.ceil(frameMetrics.advanceWidth) + Style.space(14)
    tooltipText: Model.tooltip(root.phase)

    Text {
      anchors.centerIn: parent
      textFormat: Text.PlainText
      text: Model.frame(root.phase, root.tick)
      color: root.barIconColor
      font.family: root.fontFamily
      font.pixelSize: Style.bar.iconFont
      scale: button.pressScale
    }

    onPressed: function(buttonCode) { root.togglePanel() }
  }

  KeyboardPanel {
    id: panel
    anchorItem: button
    owner: root
    bar: root.bar
    open: root.opened
    focusTarget: keyCatcher
    contentWidth: panel.fittedContentWidth(Style.space(340))
    contentHeight: panel.fittedContentHeight(column.implicitHeight, Style.space(560))

    PanelKeyCatcher {
      id: keyCatcher
      anchors.fill: parent
      onMoveRequested: function(dx, dy) {
        if (!root.cursorActive) { root.cursorActive = true; return }
        root.moveCursor(dx, dy)
      }
      onActivateRequested: if (root.cursorActive) root.activateCursor()
      onCloseRequested: root.page !== "" ? root.leavePage() : root.close()
      onTabRequested: function(direction) { root.switchPanel(direction) }
      onTextKey: function(t) { if (t.toLowerCase() === "c") sw.copyLast() }

      Column {
        id: column
        x: Style.space(2)
        width: parent.width - Style.space(4)
        spacing: Style.space(12)

        Hero { width: parent.width }

        PanelSeparator { foreground: root.foreground }

        // ---- Whispy stopped -------------------------------------------------

        ActionRow {
          visible: root.page === "" && !root.running
          rowId: "start"
          label: sw.starting ? "Starting Whispy…" : "Start Whispy"
          caption: "Runs systemctl --user start whispy"
        }

        // ---- Settings -------------------------------------------------------

        Column {
          visible: root.page === "" && root.running
          width: parent.width
          spacing: Style.space(6)

          SettingRow {
            rowId: "trigger"
            label: "Dictation key"
            value: Model.presetLabel(sw.config.omarchy_trigger) || "Omarchy default"
            chevron: true
          }
          // Parakeet ships in one size and finds the language itself (as on
          // macOS, where the menu has neither): these say so, and set nothing.
          SettingRow { label: "Model"; value: "Parakeet TDT 0.6B v3" }
          SettingRow { label: "Language"; value: "Detected automatically" }
          SwitchRow {
            rowId: "clipboard"
            label: "Copy to clipboard"
            caption: "Also leave the text on the clipboard"
            checked: sw.config.copy_to_clipboard === true
          }
          SwitchRow {
            rowId: "login"
            label: "Start at login"
            caption: "systemctl --user enable whispy"
            checked: sw.startAtLogin
          }
        }

        PanelSeparator {
          visible: root.page === "" && root.running
          foreground: root.foreground
        }

        LastDictation {
          visible: root.page === "" && root.running
          width: parent.width
        }

        // ---- Key choices ----------------------------------------------------

        Column {
          visible: root.page === "trigger"
          width: parent.width
          spacing: Style.space(2)

          BackRow { width: parent.width }

          Repeater {
            model: root.pageOptions
            OptionRow {
              required property var modelData
              required property int index
              width: parent.width
              option: modelData
              optionIndex: index
            }
          }
        }
      }
    }
  }

  // ---- Components -----------------------------------------------------------

  component Hero: Item {
    id: heroRoot
    implicitHeight: Math.max(heroGlyph.implicitHeight, heroLabels.implicitHeight, powerSwitch.implicitHeight)

    Text {
      id: heroGlyph
      anchors.left: parent.left
      anchors.verticalCenter: parent.verticalCenter
      textFormat: Text.PlainText
      text: Model.frame(root.phase, root.tick)
      color: root.phase === "recording" ? root.brandGreen : root.foreground
      opacity: root.running ? 1 : 0.5
      font.family: root.fontFamily
      font.pixelSize: Style.font.title
    }

    ToggleSwitch {
      id: powerSwitch
      checked: root.running || sw.starting
      busy: sw.starting
      hasCursor: root.currentRow === "power"
      foreground: root.foreground
      anchors.right: parent.right
      anchors.verticalCenter: parent.verticalCenter
      onHovered: function(on) { if (on) root.setRowCursor("power") }
      onToggled: root.activate("power")
    }

    Column {
      id: heroLabels
      anchors.left: heroGlyph.right
      anchors.leftMargin: Style.space(14)
      anchors.right: powerSwitch.left
      anchors.rightMargin: Style.space(12)
      anchors.verticalCenter: parent.verticalCenter
      spacing: Style.space(2)

      Text {
        textFormat: Text.PlainText
        text: "Whispy"
        color: root.foreground
        font.family: root.fontFamily
        font.pixelSize: Style.font.subtitle
        font.bold: true
      }

      Text {
        textFormat: Text.PlainText
        width: parent.width
        text: (sw.message !== "" ? sw.message
          : sw.starting ? "Starting" : Model.phaseLabel(root.phase)).toUpperCase()
        color: sw.message !== "" && sw.messageIsError ? root.urgent : Qt.darker(root.foreground, 1.4)
        font.family: root.fontFamily
        font.pixelSize: Style.font.caption
        font.bold: true
        font.letterSpacing: 1.2
        elide: Text.ElideRight
      }
    }
  }

  // "Dictation key      Right Option (hold)  ›"; without a rowId, information only.
  component SettingRow: CursorSurface {
    id: settingRow
    property string rowId: ""
    property string label: ""
    property string value: ""
    property bool chevron: false

    width: parent ? parent.width : implicitWidth
    hasCursor: rowId !== "" && root.currentRow === rowId
    foreground: root.foreground
    implicitHeight: settingContent.implicitHeight + Style.spacing.rowPaddingX

    MouseArea {
      anchors.fill: parent
      enabled: settingRow.rowId !== ""
      hoverEnabled: true
      cursorShape: Qt.PointingHandCursor
      onEntered: root.setRowCursor(settingRow.rowId)
      onClicked: root.openPage(settingRow.rowId, true)
    }

    RowLayout {
      id: settingContent
      anchors.left: parent.left
      anchors.right: parent.right
      anchors.verticalCenter: parent.verticalCenter
      anchors.leftMargin: Style.space(10)
      anchors.rightMargin: Style.space(10)
      spacing: Style.space(8)

      Text {
        textFormat: Text.PlainText
        text: settingRow.label
        color: root.foreground
        font.family: root.fontFamily
        font.pixelSize: Style.font.body
      }

      Text {
        textFormat: Text.PlainText
        Layout.fillWidth: true
        horizontalAlignment: Text.AlignRight
        text: settingRow.value
        color: root.dim
        font.family: root.fontFamily
        font.pixelSize: Style.font.body
        elide: Text.ElideRight
      }

      Text {
        textFormat: Text.PlainText
        visible: settingRow.chevron
        text: "›"
        color: root.foreground
        font.family: root.fontFamily
        font.pixelSize: Style.font.body
      }
    }
  }

  component SwitchRow: CursorSurface {
    id: switchRow
    property string rowId: ""
    property string label: ""
    property string caption: ""
    property bool checked: false

    width: parent ? parent.width : implicitWidth
    hasCursor: root.currentRow === rowId
    foreground: root.foreground
    implicitHeight: switchContent.implicitHeight + Style.spacing.rowPaddingX

    MouseArea {
      anchors.fill: parent
      hoverEnabled: true
      cursorShape: Qt.PointingHandCursor
      onEntered: root.setRowCursor(switchRow.rowId)
      onClicked: root.activate(switchRow.rowId)
    }

    RowLayout {
      id: switchContent
      anchors.left: parent.left
      anchors.right: parent.right
      anchors.verticalCenter: parent.verticalCenter
      anchors.leftMargin: Style.space(10)
      anchors.rightMargin: Style.space(10)
      spacing: Style.space(8)

      ColumnLayout {
        Layout.fillWidth: true
        spacing: Style.space(1)

        Text {
          textFormat: Text.PlainText
          Layout.fillWidth: true
          text: switchRow.label
          color: root.foreground
          font.family: root.fontFamily
          font.pixelSize: Style.font.body
          elide: Text.ElideRight
        }

        Text {
          textFormat: Text.PlainText
          Layout.fillWidth: true
          visible: switchRow.caption !== ""
          text: switchRow.caption
          color: root.dim
          font.family: root.fontFamily
          font.pixelSize: Style.font.caption
          elide: Text.ElideRight
        }
      }

      ToggleSwitch {
        checked: switchRow.checked
        interactive: false
        foreground: root.foreground
        Layout.alignment: Qt.AlignVCenter
      }
    }
  }

  component ActionRow: CursorSurface {
    id: actionRow
    property string rowId: ""
    property string label: ""
    property string caption: ""

    width: parent ? parent.width : implicitWidth
    hasCursor: root.currentRow === rowId
    foreground: root.foreground
    implicitHeight: actionContent.implicitHeight + Style.spacing.rowPaddingX

    MouseArea {
      anchors.fill: parent
      hoverEnabled: true
      cursorShape: Qt.PointingHandCursor
      onEntered: root.setRowCursor(actionRow.rowId)
      onClicked: root.activate(actionRow.rowId)
    }

    ColumnLayout {
      id: actionContent
      anchors.left: parent.left
      anchors.right: parent.right
      anchors.verticalCenter: parent.verticalCenter
      anchors.leftMargin: Style.space(10)
      anchors.rightMargin: Style.space(10)
      spacing: Style.space(1)

      Text {
        textFormat: Text.PlainText
        Layout.fillWidth: true
        text: actionRow.label
        color: root.foreground
        font.family: root.fontFamily
        font.pixelSize: Style.font.body
        font.bold: true
        elide: Text.ElideRight
      }

      Text {
        textFormat: Text.PlainText
        Layout.fillWidth: true
        visible: actionRow.caption !== ""
        text: actionRow.caption
        color: root.dim
        font.family: root.fontFamily
        font.pixelSize: Style.font.caption
        elide: Text.ElideRight
      }
    }
  }

  component LastDictation: CursorSurface {
    id: lastRow
    hasCursor: root.currentRow === "last"
    foreground: root.foreground
    implicitHeight: lastContent.implicitHeight + Style.spacing.rowPaddingX * 2

    MouseArea {
      anchors.fill: parent
      enabled: sw.lastText !== ""
      hoverEnabled: true
      cursorShape: Qt.PointingHandCursor
      onEntered: root.setRowCursor("last")
      onClicked: sw.copyLast()
    }

    ColumnLayout {
      id: lastContent
      anchors.left: parent.left
      anchors.right: parent.right
      anchors.verticalCenter: parent.verticalCenter
      anchors.leftMargin: Style.space(10)
      anchors.rightMargin: Style.space(10)
      spacing: Style.space(4)

      Text {
        textFormat: Text.PlainText
        text: "LAST DICTATION"
        color: root.dim
        font.family: root.fontFamily
        font.pixelSize: Style.font.caption
        font.bold: true
        font.letterSpacing: 1.2
      }

      Text {
        textFormat: Text.PlainText
        Layout.fillWidth: true
        text: sw.lastText !== "" ? sw.lastText : "Nothing dictated yet"
        color: sw.lastText !== "" ? root.foreground : root.dim
        font.family: root.fontFamily
        font.pixelSize: Style.font.body
        wrapMode: Text.WordWrap
        maximumLineCount: 4
        elide: Text.ElideRight
      }

      Text {
        textFormat: Text.PlainText
        visible: sw.lastText !== ""
        text: "Click or C to copy"
        opacity: lastRow.hasCursor ? 1 : 0
        color: root.dim
        font.family: root.fontFamily
        font.pixelSize: Style.font.caption
      }
    }
  }

  component BackRow: CursorSurface {
    id: backRow
    hasCursor: root.cursorActive && root.page !== "" && root.rowIndex < 0
    foreground: root.foreground
    implicitHeight: backContent.implicitHeight + Style.spacing.rowPaddingX

    MouseArea {
      anchors.fill: parent
      hoverEnabled: true
      cursorShape: Qt.PointingHandCursor
      onEntered: { root.cursorActive = true; root.rowIndex = -1 }
      onClicked: root.leavePage(true)
    }

    RowLayout {
      id: backContent
      anchors.left: parent.left
      anchors.right: parent.right
      anchors.verticalCenter: parent.verticalCenter
      anchors.leftMargin: Style.space(10)
      anchors.rightMargin: Style.space(10)
      spacing: Style.space(8)

      Text {
        textFormat: Text.PlainText
        text: "‹"
        color: root.foreground
        font.family: root.fontFamily
        font.pixelSize: Style.font.body
      }

      Text {
        textFormat: Text.PlainText
        Layout.fillWidth: true
        text: "Dictation key"
        color: root.foreground
        font.family: root.fontFamily
        font.pixelSize: Style.font.body
        font.bold: true
      }
    }
  }

  component OptionRow: CursorSurface {
    id: optionRow
    property var option: null
    property int optionIndex: 0
    readonly property bool selected: option !== null && option.value === sw.config.omarchy_trigger

    hasCursor: root.cursorActive && root.page !== "" && root.rowIndex === optionIndex
    foreground: root.foreground
    implicitHeight: optionLabel.implicitHeight + Style.spacing.rowPaddingX

    MouseArea {
      anchors.fill: parent
      hoverEnabled: true
      cursorShape: Qt.PointingHandCursor
      onEntered: { root.cursorActive = true; root.rowIndex = optionRow.optionIndex }
      onClicked: root.choose(optionRow.option.value, true)
    }

    RowLayout {
      anchors.left: parent.left
      anchors.right: parent.right
      anchors.verticalCenter: parent.verticalCenter
      anchors.leftMargin: Style.space(10)
      anchors.rightMargin: Style.space(10)
      spacing: Style.space(8)

      Text {
        textFormat: Text.PlainText
        Layout.preferredWidth: Style.space(14)
        text: optionRow.selected ? "✓" : ""
        color: root.foreground
        font.family: root.fontFamily
        font.pixelSize: Style.font.body
      }

      Text {
        id: optionLabel
        textFormat: Text.PlainText
        Layout.fillWidth: true
        text: optionRow.option ? optionRow.option.label : ""
        color: root.foreground
        font.family: root.fontFamily
        font.pixelSize: Style.font.body
        font.bold: optionRow.selected
        elide: Text.ElideRight
      }
    }
  }
}
