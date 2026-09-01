import QtQuick
import qs.Commons
import qs.Ui

import "StatsFormat.js" as Fmt

// The bar-widget's nested popup, loaded by BarWidget.qml's own Loader (per
// the official docs: "the manifest loads BarWidget.qml; its Loader loads
// Panel.qml... do not add a second manifest kind for this nested panel").
// Named StatsPanel.qml rather than literally "Panel.qml": this file's own
// directory also contains BarWidget.qml, which imports qs.Ui for the
// BarWidget base type -- qs.Ui itself exports a type named "Panel", so a
// sibling file also called Panel.qml would leave BarWidget.qml with two
// candidate meanings for the bare name "Panel".
//
// Extending Panel gives us `opened` (bound to an internal PanelController),
// open()/close()/toggle()/switchPanel() and `barForeground` for free;
// manageIpc:false disables Panel's own IpcHandler since BarWidget.qml's
// Loader already owns open/close for this popup.
//
// This file is composition and derivation only. Every visual piece lives in
// its own component (SplitBar, Sparkline, TrendBars, RecordsList,
// AuditLogSection) built on the shell's qs.Ui kit. The previous single-file
// version hand-rolled all of them out of bare Rectangles, which is how it
// ended up assigning `borderSpec` -- a BorderSurface property -- to a plain
// Rectangle, failing to load and taking the whole bar widget down with it.
Panel {
  id: root

  manageIpc: false

  required property Item anchorItem

  property string windowKey: "today"
  property string windowLabel: "Today"
  property bool connectedToDaemon: false
  property bool inputBlocked: false
  property var inputHealth: null
  property bool hasData: false
  property real wpmAvg: 0
  property real wpmLast: 0
  property int navKeyboardCount: 0
  property int navMouseCount: 0
  property real mouseWeight: 1.0
  property var navKeyboardPct: null
  property int cheatsheetCount: 0
  property int appLaunchKeybindCount: 0
  property int appLaunchPanelCount: 0
  property var appLaunchKeybindPct: null
  property var records: null
  property var history: null
  property bool loggingEnabled: false
  property var logLines: []
  property int logTotal: 0

  signal toggleLogging()
  signal refreshLog()

  // --- derived series -------------------------------------------------------
  //
  // Each of these is computed once when `history` / `records` changes and then
  // reused by every consumer. Calling the Fmt helpers inline in bindings (as
  // this file used to) allocated a fresh array on every re-evaluation, and
  // handing a fresh array to a Repeater rebuilds every delegate -- so a stats
  // push rebuilt the whole panel instead of updating a few numbers.

  readonly property var historySeries: Fmt.historySeries(history)
  readonly property var sparkPoints: Fmt.wpmSparkPoints(history)
  readonly property bool hasWpmTrend: Fmt.hasWpmTrend(history)
  readonly property var trendBars: Fmt.keyboardTrendBars(history)
  readonly property var recordCards: Fmt.recordCards(records)
  readonly property var cheatsheetTrend: Fmt.cheatsheetTrend(history)
  readonly property var appLaunchTrend: Fmt.appLaunchTrend(history)
  readonly property string oldestDayLabel:
    historySeries.length > 0 ? Fmt._shortDay(historySeries[0].day) : ""
  readonly property string trendTitle: historySeries.length + "-day trend"

  // "No input access" outranks "no data yet": the second is what the user
  // saw for as long as the first was true, with nothing pointing at the
  // actual cause.
  readonly property bool showEmptyState: connectedToDaemon && !hasData && !inputBlocked

  KeyboardPanel {
    id: keyboardPanel
    anchorItem: root.anchorItem
    bar: root.bar
    open: root.opened
    contentWidth: fittedContentWidth(Style.space(300))
    contentHeight: fittedContentHeight(header.implicitHeight
                                       + Style.spacing.lg
                                       + contentColumn.implicitHeight)
    focusTarget: keyCatcher

    PanelKeyCatcher {
      id: keyCatcher
      anchors.fill: parent
      onCloseRequested: root.close()

      // 2.0 Header row (all states). Pinned outside the scroll area so the
      // window pill stays visible while the body scrolls.
      Item {
        id: header
        anchors.top: parent.top
        anchors.left: parent.left
        anchors.right: parent.right
        height: Math.max(titleText.implicitHeight, windowPill.height)

        Text {
          id: titleText
          anchors.left: parent.left
          anchors.verticalCenter: parent.verticalCenter
          textFormat: Text.PlainText
          text: "Adoption Tracker"
          color: root.barForeground
          font.family: root.bar ? root.bar.fontFamily : Style.font.family
          font.bold: true
          font.pixelSize: Style.font.subtitle
        }

        BorderSurface {
          id: windowPill
          anchors.right: parent.right
          anchors.verticalCenter: parent.verticalCenter
          height: Style.space(20)
          width: pillLabel.implicitWidth + Style.spacing.huge
          radius: Style.cornerRadius > 0 ? height / 2 : 0
          color: root.connectedToDaemon ? Style.selectedAccentFill : Style.normalFill
          borderSpec: Border.flat(
            root.connectedToDaemon ? Color.accent : root.barForeground,
            Style.space(1))

          Text {
            id: pillLabel
            anchors.centerIn: parent
            textFormat: Text.PlainText
            text: root.windowLabel.toUpperCase()
            color: root.connectedToDaemon ? Color.accent : Util.alpha(root.barForeground, 0.6)
            font.family: root.bar ? root.bar.fontFamily : Style.font.family
            font.bold: true
            font.pixelSize: Style.font.caption
            font.letterSpacing: 1
          }
        }
      }

      // The body scrolls. With every section visible the content can exceed
      // the panel's available height, and KeyboardPanel simply clips at that
      // point -- previously the records and Debug Audit sections just vanished
      // off the bottom with no way to reach them.
      Flickable {
        id: body
        anchors.top: header.bottom
        anchors.topMargin: Style.spacing.lg
        anchors.left: parent.left
        anchors.right: parent.right
        anchors.bottom: parent.bottom
        contentWidth: width
        contentHeight: contentColumn.implicitHeight
        boundsBehavior: Flickable.StopAtBounds
        clip: true

        Column {
          id: contentColumn
          width: body.width
          spacing: Style.spacing.lg

          // 2.1 State: not connected
          Column {
            width: parent.width
            visible: !root.connectedToDaemon
            spacing: Style.spacing.lg
            topPadding: Style.spacing.xxl

            Text {
              anchors.horizontalCenter: parent.horizontalCenter
              textFormat: Text.PlainText
              text: "🔌"
              font.pixelSize: Style.font.heading
              opacity: 0.55
            }
            Text {
              width: parent.width
              horizontalAlignment: Text.AlignHCenter
              textFormat: Text.PlainText
              text: "Not connected"
              color: root.barForeground
              font.family: root.bar ? root.bar.fontFamily : Style.font.family
              font.bold: true
              font.pixelSize: Style.font.body
            }
            Text {
              width: parent.width
              horizontalAlignment: Text.AlignHCenter
              wrapMode: Text.WordWrap
              textFormat: Text.PlainText
              text: "Run the plugin's scripts/setup.sh once to start tracking (see its README)."
              color: Qt.darker(root.barForeground, 1.5)
              font.family: root.bar ? root.bar.fontFamily : Style.font.family
              font.pixelSize: Style.font.bodySmall
            }
            Rectangle {
              anchors.horizontalCenter: parent.horizontalCenter
              width: codeText.implicitWidth + Style.spacing.huge
              height: codeText.implicitHeight + Style.spacing.lg
              radius: Style.cornerRadius
              color: Style.normalFill
              Text {
                id: codeText
                anchors.centerIn: parent
                textFormat: Text.PlainText
                text: "scripts/setup.sh"
                color: root.barForeground
                font.family: "monospace"
                font.pixelSize: Style.font.bodySmall
              }
            }
          }

          // 2.1b State: connected, but locked out of /dev/input
          BorderSurface {
            width: parent.width
            visible: root.connectedToDaemon && root.inputBlocked
            height: visible ? inputWarnColumn.implicitHeight + Style.spacing.xxl : 0
            radius: Style.cornerRadius
            color: Util.alpha(Color.urgent, 0.12)
            borderSpec: Border.flat(Color.urgent, Style.space(1))

            Column {
              id: inputWarnColumn
              anchors.left: parent.left
              anchors.right: parent.right
              anchors.verticalCenter: parent.verticalCenter
              anchors.leftMargin: Style.spacing.lg
              anchors.rightMargin: Style.spacing.lg
              spacing: Style.spacing.sm

              Text {
                width: parent.width
                textFormat: Text.PlainText
                text: "⚠  No input access"
                color: Color.urgent
                font.family: root.bar ? root.bar.fontFamily : Style.font.family
                font.bold: true
                font.pixelSize: Style.font.bodySmall
              }
              Text {
                width: parent.width
                wrapMode: Text.WordWrap
                textFormat: Text.PlainText
                text: Fmt.formatInputWarning(root.inputHealth)
                color: root.barForeground
                font.family: root.bar ? root.bar.fontFamily : Style.font.family
                font.pixelSize: Style.font.caption
              }
              Text {
                width: parent.width
                wrapMode: Text.WrapAnywhere
                textFormat: Text.PlainText
                text: "sudo usermod -aG input $USER   # then log out and back in"
                color: Qt.darker(root.barForeground, 1.3)
                font.family: "monospace"
                font.pixelSize: Style.font.caption
              }
            }
          }

          // 2.2 State: connected, no data yet
          Column {
            width: parent.width
            visible: root.showEmptyState
            spacing: Style.spacing.md
            topPadding: Style.spacing.xxl

            Text {
              anchors.horizontalCenter: parent.horizontalCenter
              textFormat: Text.PlainText
              text: "⏳"
              font.pixelSize: Style.font.heading
              opacity: 0.55
            }
            Text {
              width: parent.width
              horizontalAlignment: Text.AlignHCenter
              wrapMode: Text.WordWrap
              textFormat: Text.PlainText
              text: "No data yet for " + root.windowLabel.toLowerCase() + "."
              color: Qt.darker(root.barForeground, 1.4)
              font.family: root.bar ? root.bar.fontFamily : Style.font.family
              font.pixelSize: Style.font.bodySmall
            }
          }

          // 2.3 State: connected, has data
          Column {
            width: parent.width
            visible: root.connectedToDaemon && root.hasData
            spacing: Style.spacing.lg

            // 2.3.1 WPM hero + sparkline
            PanelSectionHeader {
              text: "TYPING SPEED"
              foreground: root.barForeground
              fontFamily: root.bar ? root.bar.fontFamily : Style.font.family
            }

            Row {
              width: parent.width
              spacing: Style.spacing.lg

              Text {
                textFormat: Text.PlainText
                text: Math.round(root.wpmAvg)
                color: root.barForeground
                font.family: root.bar ? root.bar.fontFamily : Style.font.family
                font.bold: true
                font.pixelSize: Style.font.displayLarge
              }
              Column {
                anchors.bottom: parent.bottom
                anchors.bottomMargin: Style.spacing.sm
                spacing: 0
                Text {
                  textFormat: Text.PlainText
                  text: "WPM avg"
                  color: Qt.darker(root.barForeground, 1.4)
                  font.family: root.bar ? root.bar.fontFamily : Style.font.family
                  font.pixelSize: Style.font.caption
                }
                Text {
                  visible: root.wpmLast > 0
                  textFormat: Text.PlainText
                  text: "last burst " + Math.round(root.wpmLast)
                  color: Qt.darker(root.barForeground, 1.4)
                  font.family: root.bar ? root.bar.fontFamily : Style.font.family
                  font.pixelSize: Style.font.caption
                }
              }
            }

            Sparkline {
              width: parent.width
              visible: root.hasWpmTrend
              points: root.sparkPoints
            }

            // 2.3.2 Keyboard vs. mouse
            PanelSectionHeader {
              text: "KEYBOARD VS MOUSE"
              foreground: root.barForeground
              fontFamily: root.bar ? root.bar.fontFamily : Style.font.family
            }

            SplitBar {
              width: parent.width
              percent: root.navKeyboardPct
              leadingLabel: "KBD " + Math.round(root.navKeyboardPct || 0) + "%"
              trailingLabel: Math.round(100 - (root.navKeyboardPct || 0)) + "% MOUSE"
              emptyText: "No navigation recorded yet"
              caption: Fmt.formatNavCaption(root.navKeyboardCount, root.navMouseCount,
                                            root.mouseWeight)
              foreground: root.barForeground
              fontFamily: root.bar ? root.bar.fontFamily : Style.font.family
            }

            TrendBars {
              width: parent.width
              bars: root.trendBars
              title: root.trendTitle
              oldestLabel: root.oldestDayLabel
              foreground: root.barForeground
              fontFamily: root.bar ? root.bar.fontFamily : Style.font.family
            }

            // 2.3.3 Cheatsheet line + trend
            Column {
              width: parent.width
              spacing: 0

              Text {
                width: parent.width
                wrapMode: Text.WordWrap
                textFormat: Text.PlainText
                text: "SUPER+K cheatsheet: " + Fmt.formatCheatsheetCount(root.cheatsheetCount)
                color: Qt.darker(root.barForeground, 1.3)
                font.family: root.bar ? root.bar.fontFamily : Style.font.family
                font.pixelSize: Style.font.bodySmall
              }
              Text {
                width: parent.width
                wrapMode: Text.WordWrap
                visible: root.cheatsheetTrend !== null
                textFormat: Text.PlainText
                text: Fmt.formatCheatsheetTrendCaption(root.cheatsheetTrend)
                color: Qt.darker(root.barForeground, 1.6)
                font.family: root.bar ? root.bar.fontFamily : Style.font.family
                font.pixelSize: Style.font.caption
              }
            }

            // 2.3.4 App launches: keybind vs. panel
            PanelSectionHeader {
              text: "APP LAUNCHES"
              foreground: root.barForeground
              fontFamily: root.bar ? root.bar.fontFamily : Style.font.family
            }

            SplitBar {
              width: parent.width
              percent: root.appLaunchKeybindPct
              leadingLabel: "Keybind " + Math.round(root.appLaunchKeybindPct || 0) + "%"
              trailingLabel: Math.round(100 - (root.appLaunchKeybindPct || 0)) + "% Panel"
              emptyText: "No app launches recorded yet"
              valueFontSize: Style.font.bodySmall
              barHeight: Style.space(8)
              caption: Fmt.formatAppLaunchCaption(root.appLaunchKeybindCount,
                                                  root.appLaunchPanelCount)
              trendCaption: root.appLaunchTrend !== null
                ? Fmt.formatAppLaunchTrendCaption(root.appLaunchTrend) : ""
              foreground: root.barForeground
              fontFamily: root.bar ? root.bar.fontFamily : Style.font.family
            }
          }

          // 2.4 Records
          PanelSeparator {
            visible: recordsList.visible
            foreground: root.barForeground
          }

          RecordsList {
            id: recordsList
            width: parent.width
            visible: root.connectedToDaemon && root.recordCards.length > 0
            cards: root.recordCards
            foreground: root.barForeground
            fontFamily: root.bar ? root.bar.fontFamily : Style.font.family
          }

          // 2.5 Debug audit logging
          PanelSeparator {
            visible: auditSection.visible
            foreground: root.barForeground
          }

          AuditLogSection {
            id: auditSection
            width: parent.width
            visible: root.connectedToDaemon
            loggingEnabled: root.loggingEnabled
            lines: root.logLines
            totalLines: root.logTotal
            foreground: root.barForeground
            fontFamily: root.bar ? root.bar.fontFamily : Style.font.family
            onToggleRequested: root.toggleLogging()
            onRefreshRequested: root.refreshLog()
          }
        }
      }

      // Tail the audit log while it is actually on screen. 2s rather than 1s,
      // and gated on the panel being open, the section being visible, and
      // logging being enabled -- this timer used to run at 1Hz and rebuild the
      // whole log list on every tick.
      Timer {
        interval: 2000
        running: root.opened && root.connectedToDaemon && root.loggingEnabled
        repeat: true
        triggeredOnStart: true
        onTriggered: root.refreshLog()
      }
    }
  }
}
