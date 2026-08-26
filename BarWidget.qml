import QtQuick
import Quickshell
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
    if (w.indexOf("month") >= 0) return "month"
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
  readonly property real mouseWeight: stats ? Number(stats.mouse_weight || 1.0) : 1.0
  readonly property var navKeyboardPct: stats ? stats.nav_keyboard_pct : null
  readonly property int cheatsheetCount: stats ? Number(stats.cheatsheet_count || 0) : 0

  readonly property string compactLabel: Fmt.formatCompactLabel(
    backend.connected, hasData, wpmAvg, navKeyboardPct)

  onWindowKeyChanged: backend.requestStats(windowKey)
  onOpenedChanged: if (opened) {
    backend.requestRecords()
    backend.requestHistory(14)
  }

  BackendClient {
    id: backend
    window: root.windowKey
  }

  implicitWidth: button.implicitWidth
  implicitHeight: button.implicitHeight

  // A bare MouseArea is not reliably clickable here: the bar's own
  // per-slot MouseArea (drag-to-reorder) sits on top of every widget and
  // only forwards presses to a target that exposes triggerPress() (either
  // self-registered via WidgetButton, or exposed on the slot's activeItem
  // directly) -- see Bar.qml's moduleClickTargetAt/pressModuleClickTarget.
  // Every other first- and third-party bar widget uses WidgetButton for
  // exactly this reason.
  WidgetButton {
    id: button
    anchors.fill: parent
    bar: root.bar
    text: root.compactLabel
    hasVisualContent: text !== ""

    onPressed: function(b) { if (b === Qt.LeftButton) root.toggle() }
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
        mouseWeight: root.mouseWeight
        navKeyboardPct: root.navKeyboardPct
        cheatsheetCount: root.cheatsheetCount
        records: backend.lastRecords
        history: backend.lastHistory
      }
    }
  }
}
