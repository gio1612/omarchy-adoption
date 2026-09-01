import QtQuick
import qs.Commons
import qs.Ui

// "Best of the best" leaderboard: one card per all-time personal best.
// `cards` is [{icon, label, value, day}] from StatsFormat.recordCards --
// already filtered, so an empty array means there is nothing to show and the
// whole section hides itself.
Column {
  id: root

  property var cards: []
  property string title: "Best of the best"
  property color foreground: Color.foreground
  property string fontFamily: Style.font.family

  spacing: Style.spacing.md
  visible: !!cards && cards.length > 0

  Text {
    textFormat: Text.PlainText
    text: root.title
    color: root.foreground
    font.family: root.fontFamily
    font.bold: true
    font.pixelSize: Style.font.subtitle
  }

  Repeater {
    model: root.cards

    BorderSurface {
      id: card
      required property var modelData

      width: root.width
      height: Math.max(Style.spacing.controlHeight,
                       icon.implicitHeight + Style.spacing.xxl)
      radius: Style.cornerRadius
      color: Style.normalFill
      borderSpec: Border.none()

      Text {
        id: icon
        anchors.left: parent.left
        anchors.leftMargin: Style.spacing.lg
        anchors.verticalCenter: parent.verticalCenter
        textFormat: Text.PlainText
        text: card.modelData.icon
        font.pixelSize: Style.font.icon
      }

      Text {
        id: value
        anchors.right: parent.right
        anchors.rightMargin: Style.spacing.lg
        anchors.verticalCenter: parent.verticalCenter
        textFormat: Text.PlainText
        text: card.modelData.value
        color: Color.accent
        font.bold: true
        font.family: root.fontFamily
        font.pixelSize: Style.font.bodySmall
      }

      Column {
        anchors.left: icon.right
        anchors.leftMargin: Style.spacing.lg
        anchors.right: value.left
        anchors.rightMargin: Style.spacing.lg
        anchors.verticalCenter: parent.verticalCenter
        spacing: 0

        Text {
          width: parent.width
          textFormat: Text.PlainText
          text: card.modelData.label
          color: root.foreground
          font.family: root.fontFamily
          font.pixelSize: Style.font.bodySmall
          elide: Text.ElideRight
        }

        Text {
          width: parent.width
          textFormat: Text.PlainText
          text: card.modelData.day
          color: Qt.darker(root.foreground, 1.5)
          font.family: root.fontFamily
          font.pixelSize: Style.font.caption
          elide: Text.ElideRight
        }
      }
    }
  }
}
