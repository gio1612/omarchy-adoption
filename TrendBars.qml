import QtQuick
import qs.Commons

// Per-day keyboard-share bars for the trailing history window, with the
// oldest/newest day labels underneath.
//
// `bars` is [{day, kbFrac: 0..1|null}] from StatsFormat.keyboardTrendBars.
// A null kbFrac is a day with no navigation at all: it draws a short flat
// tick, never a zero-height bar, so "no data" stays distinguishable from
// "0% keyboard".
Column {
  id: root

  property var bars: []
  property string oldestLabel: ""
  property string newestLabel: "today"
  property string title: "Trend"
  property color foreground: Color.foreground
  property string fontFamily: Style.font.family
  property int barHeight: Style.space(28)

  spacing: Style.spacing.sm
  visible: !!bars && bars.length > 0

  Text {
    textFormat: Text.PlainText
    text: root.title
    color: Qt.darker(root.foreground, 1.5)
    font.family: root.fontFamily
    font.pixelSize: Style.font.caption
  }

  Row {
    id: barRow
    width: parent.width
    height: root.barHeight
    spacing: Style.spacing.sm

    // Sized to fill the available width rather than a fixed 12px, so the
    // strip lines up with the panel edges at any spacing scale or day count.
    readonly property int slotWidth: {
      var count = root.bars ? root.bars.length : 0
      if (count <= 0) return 0
      return Math.max(Style.space(4),
                      Math.floor((width - spacing * (count - 1)) / count))
    }

    Repeater {
      model: root.bars

      Rectangle {
        id: slot
        required property var modelData

        readonly property bool hasData: modelData.kbFrac !== null
                                        && modelData.kbFrac !== undefined

        width: barRow.slotWidth
        height: barRow.height
        radius: Style.space(2)
        color: Style.normalFill
        clip: true

        // no navigation recorded that day: a short flat "no data" tick
        Rectangle {
          visible: !slot.hasData
          anchors.centerIn: parent
          width: parent.width - Style.space(4)
          height: Style.space(2)
          radius: height / 2
          color: Util.alpha(root.foreground, 0.15)
        }

        // data day: full-height composition fill, bottom-up, mirroring the
        // live split bar's two-segment language
        Rectangle {
          visible: slot.hasData
          anchors.fill: parent
          color: Util.alpha(root.foreground, 0.28)
        }

        Rectangle {
          visible: slot.hasData
          anchors.bottom: parent.bottom
          width: parent.width
          height: slot.height * (slot.modelData.kbFrac || 0)
          color: Color.accent
          Behavior on height { NumberAnimation { duration: 150; easing.type: Easing.OutCubic } }
        }
      }
    }
  }

  Item {
    width: parent.width
    height: oldest.implicitHeight

    Text {
      id: oldest
      anchors.left: parent.left
      textFormat: Text.PlainText
      text: root.oldestLabel
      color: Qt.darker(root.foreground, 1.6)
      font.family: root.fontFamily
      font.pixelSize: Style.font.caption
    }

    Text {
      anchors.right: parent.right
      textFormat: Text.PlainText
      text: root.newestLabel
      color: Qt.darker(root.foreground, 1.6)
      font.family: root.fontFamily
      font.pixelSize: Style.font.caption
    }
  }
}
