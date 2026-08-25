import QtQuick
import Quickshell
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
// candidate meanings for the bare name "Panel" (the qs.Ui type vs. this
// local file). Renaming this file sidesteps that ambiguity entirely; nothing
// about the manifest or plugin kinds changes (this file was never a declared
// entryPoint to begin with -- it's only ever instantiated by BarWidget.qml's
// own Loader).
//
// Confirmed against the real Panel/KeyboardPanel/PanelKeyCatcher base-type
// sources in basecamp/omarchy's shell/Ui/ (the shell's own official code,
// not a third-party plugin): extending Panel gives us `opened` (bound to an
// internal PanelController), open()/close()/toggle()/switchPanel() and
// `barForeground` for free; manageIpc:false disables Panel's own IpcHandler
// since BarWidget.qml's Loader already owns open/close for this popup.
Panel {
  id: root

  manageIpc: false

  required property Item anchorItem

  property string windowKey: "today"
  property string windowLabel: "Today"
  property bool connectedToDaemon: false
  property bool hasData: false
  property real wpmAvg: 0
  property real wpmLast: 0
  property int navKeyboardCount: 0
  property int navMouseCount: 0
  property real mouseWeight: 1.0
  property int cheatsheetCount: 0
  property var records: null

  KeyboardPanel {
    id: keyboardPanel
    anchorItem: root.anchorItem
    bar: root.bar
    open: root.opened
    contentWidth: Style.space(300)
    contentHeight: fittedContentHeight(contentColumn.implicitHeight)
    focusTarget: keyCatcher

    PanelKeyCatcher {
      id: keyCatcher
      anchors.fill: parent
      onCloseRequested: root.close()

      Column {
        id: contentColumn
        anchors.fill: parent
        anchors.margins: Style.spacing.popupPadding
        spacing: Style.space(8)

        Text {
          width: parent.width
          text: "Adoption Tracker — " + root.windowLabel
          color: root.barForeground
          font.family: root.bar ? root.bar.fontFamily : Style.font.family
          font.bold: true
          font.pixelSize: Style.font.subtitle
        }

        Text {
          width: parent.width
          visible: !root.connectedToDaemon
          text: "Not connected. Run scripts/setup.sh once to start tracking (see this plugin's README)."
          color: root.barForeground
          font.family: root.bar ? root.bar.fontFamily : Style.font.family
          wrapMode: Text.WordWrap
        }

        Text {
          width: parent.width
          visible: root.connectedToDaemon && !root.hasData
          text: "No data yet for " + root.windowLabel.toLowerCase() + "."
          color: root.barForeground
          font.family: root.bar ? root.bar.fontFamily : Style.font.family
        }

        Column {
          width: parent.width
          visible: root.connectedToDaemon && root.hasData
          spacing: Style.space(4)

          Text {
            width: parent.width
            text: "Typing: " + Fmt.formatWpm(root.wpmAvg, root.wpmLast)
            color: root.barForeground
            font.family: root.bar ? root.bar.fontFamily : Style.font.family
            wrapMode: Text.WordWrap
          }
          Text {
            width: parent.width
            text: "Navigation: " + Fmt.formatNavBreakdown(root.navKeyboardCount, root.navMouseCount, root.mouseWeight)
            color: root.barForeground
            font.family: root.bar ? root.bar.fontFamily : Style.font.family
            wrapMode: Text.WordWrap
          }
          Text {
            width: parent.width
            text: "SUPER+K cheatsheet: " + Fmt.formatCheatsheetCount(root.cheatsheetCount)
            color: root.barForeground
            font.family: root.bar ? root.bar.fontFamily : Style.font.family
            wrapMode: Text.WordWrap
          }
        }

        Column {
          width: parent.width
          visible: root.connectedToDaemon && Fmt.recordLines(root.records).length > 0
          spacing: Style.space(4)

          Text {
            width: parent.width
            text: "Best of the best"
            color: root.barForeground
            font.family: root.bar ? root.bar.fontFamily : Style.font.family
            font.bold: true
          }
          Repeater {
            model: Fmt.recordLines(root.records)
            Text {
              required property string modelData
              width: parent.width
              text: modelData
              color: root.barForeground
              font.family: root.bar ? root.bar.fontFamily : Style.font.family
              wrapMode: Text.WordWrap
            }
          }
        }
      }
    }
  }
}
