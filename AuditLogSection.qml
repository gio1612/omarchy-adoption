import QtQuick
import qs.Commons
import qs.Ui

// Debug Audit: a toggle that turns on the daemon's in-memory classification
// log, plus a live tail of it. The log is never persisted and carries only
// classification labels -- no key codes, no coordinates.
//
// Performance note, because this section is what made the shell hitch:
// the old version polled the daemon once a second, got the whole 400-line
// ring back, assigned it to a `property var` bound to a Repeater inside an
// unvirtualized Column, and so destroyed and rebuilt up to 400 Text items
// every second on the UI thread. Now the daemon returns a bounded tail, the
// client skips the assignment when nothing changed, the poll is slower, and
// this is a ListView -- which only instantiates the delegates on screen.
Column {
  id: root

  property bool loggingEnabled: false
  property var lines: []
  property int totalLines: 0
  property color foreground: Color.foreground
  property string fontFamily: Style.font.family
  property int maxHeight: Style.space(180)

  signal toggleRequested()
  signal refreshRequested()

  spacing: Style.spacing.lg

  PanelSectionHeader {
    text: "DEBUG AUDIT"
    foreground: root.foreground
    fontFamily: root.fontFamily
  }

  Row {
    width: parent.width
    spacing: Style.spacing.lg

    ToggleSwitch {
      id: logToggle
      checked: root.loggingEnabled
      foreground: root.foreground
      anchors.verticalCenter: parent.verticalCenter
      onToggled: root.toggleRequested()
    }

    Text {
      anchors.verticalCenter: parent.verticalCenter
      textFormat: Text.PlainText
      text: root.loggingEnabled ? "Logging ON" : "Logging OFF"
      color: root.foreground
      font.family: root.fontFamily
      font.pixelSize: Style.font.bodySmall
    }
  }

  Column {
    width: parent.width
    visible: root.loggingEnabled
    spacing: Style.spacing.md

    Text {
      width: parent.width
      wrapMode: Text.WordWrap
      textFormat: Text.PlainText
      text: "Input activity is being classified in memory (never written to disk). "
            + "Clicks, wheel ticks and two-finger trackpad scrolls appear here."
      color: Qt.darker(root.foreground, 1.5)
      font.family: root.fontFamily
      font.pixelSize: Style.font.caption
    }

    Rectangle {
      width: parent.width
      height: Math.min(Math.max(logList.contentHeight, Style.space(24)), root.maxHeight)
      radius: Style.cornerRadius
      color: Style.normalFill
      clip: true

      ListView {
        id: logList
        anchors.fill: parent
        anchors.margins: Style.spacing.sm
        model: root.lines
        spacing: Style.spacing.xxs
        clip: true
        // Non-interactive on purpose: this lives inside the panel's own
        // Flickable, and two nested flickables fight over the same drag.
        // The view pins itself to the newest line instead of scrolling.
        interactive: false
        reuseItems: true

        onCountChanged: positionViewAtEnd()
        Component.onCompleted: positionViewAtEnd()

        delegate: Text {
          required property string modelData
          width: ListView.view.width
          textFormat: Text.PlainText
          text: modelData
          wrapMode: Text.WrapAnywhere
          color: Util.alpha(root.foreground, 0.85)
          font.family: "monospace"
          font.pixelSize: Style.font.caption
        }
      }
    }

    Row {
      width: parent.width
      spacing: Style.spacing.lg

      Button {
        text: "Refresh log"
        bordered: true
        foreground: root.foreground
        fontFamily: root.fontFamily
        fontSize: Style.font.bodySmall
        onClicked: root.refreshRequested()
      }

      Text {
        anchors.verticalCenter: parent.verticalCenter
        textFormat: Text.PlainText
        text: root.totalLines > root.lines.length
          ? (root.lines.length + " of " + root.totalLines + " lines")
          : (root.lines.length + " lines")
        color: Qt.darker(root.foreground, 1.5)
        font.family: root.fontFamily
        font.pixelSize: Style.font.caption
      }
    }
  }
}
