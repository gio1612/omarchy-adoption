import QtQuick
import Quickshell
import qs.Commons
import qs.Ui

import "StatsFormat.js" as Fmt

// kind: "bar-widget". `opened`, `popoutSwitchClosing`, open()/close()/
// toggle()/closeForPopoutSwitch() are NOT part of the BarWidget base type
// (confirmed against shell/Ui/BarWidget.qml, which only provides bar,
// moduleName, settings, vertical, barSize, broadcast(), setting()) -- the
// official docs require plugin authors to implement them, forwarding to the
// loaded StatsPanel so "opened" stays in sync ("panel opens once but not
// again" if this forwarding is skipped).
BarWidget {
  id: root

  moduleName: "io.github.gio1612.omarchy-adoption"

  readonly property bool opened: panelLoader.item ? panelLoader.item.opened : false
  property bool popoutSwitchClosing: false

  function open() { if (panelLoader.item) panelLoader.item.open() }
  function close() { if (panelLoader.item) panelLoader.item.close() }
  function toggle() { root.opened ? root.close() : root.open() }
  function closeForPopoutSwitch() {
    if (panelLoader.item) panelLoader.item.closeForPopoutSwitch()
  }

  readonly property string windowLabel: String(root.setting("window", "Today"))
  readonly property string windowKey: {
    var w = windowLabel.toLowerCase()
    if (w.indexOf("week") >= 0) return "week"
    if (w.indexOf("all") >= 0) return "all"
    return "today"
  }

  readonly property var stats: backend.lastStats
  readonly property bool hasData: !!(stats && stats.has_data)
  readonly property real wpmAvg: (stats && stats.wpm_avg !== null && stats.wpm_avg !== undefined)
    ? Number(stats.wpm_avg) : 0
  readonly property real wpmLast: (stats && stats.wpm_last !== null && stats.wpm_last !== undefined)
    ? Number(stats.wpm_last) : 0
  readonly property int navKeyboardCount: stats ? Number(stats.nav_keyboard || 0) : 0
  readonly property int navMouseCount: stats ? Number(stats.nav_mouse || 0) : 0
  readonly property var navKeyboardPct: stats ? stats.nav_keyboard_pct : null
  readonly property int cheatsheetCount: stats ? Number(stats.cheatsheet_count || 0) : 0

  readonly property string compactLabel: Fmt.formatCompactLabel(
    backend.connected, hasData, wpmAvg, navKeyboardPct, cheatsheetCount)

  onWindowKeyChanged: backend.requestStats(windowKey)

  BackendClient {
    id: backend
    window: root.windowKey
  }

  implicitWidth: label.implicitWidth + Style.space(16)
  implicitHeight: root.barSize

  Text {
    id: label
    anchors.centerIn: parent
    text: root.compactLabel
    color: root.bar ? root.bar.barForeground : Color.foreground
    font.family: root.bar ? root.bar.fontFamily : Style.font.family
    font.pixelSize: Style.font.body
    elide: Text.ElideRight
  }

  MouseArea {
    anchors.fill: parent
    onClicked: root.toggle()
  }

  Loader {
    id: panelLoader
    active: true
    sourceComponent: Component {
      StatsPanel {
        anchorItem: root
        bar: root.bar
        moduleName: root.moduleName
        windowKey: root.windowKey
        windowLabel: root.windowLabel
        connectedToDaemon: backend.connected
        hasData: root.hasData
        wpmAvg: root.wpmAvg
        wpmLast: root.wpmLast
        navKeyboardCount: root.navKeyboardCount
        navMouseCount: root.navMouseCount
        cheatsheetCount: root.cheatsheetCount
      }
    }
  }
}
