import QtQuick
import qs.Commons

// Two-segment composition bar for an A-vs-B percentage, with a headline row
// above it and a caption below. Used for both keyboard-vs-mouse navigation
// and keybind-vs-panel app launches, which were previously two near-identical
// 90-line blocks of hand-rolled Rectangles.
//
// `percent` is the A-share, 0..100, or null when there is nothing to show --
// in which case the bar is replaced by `emptyText` rather than drawn at 0%,
// so "no data" never reads as "0% keyboard".
Column {
  id: root

  property var percent: null
  property string leadingLabel: ""
  property string trailingLabel: ""
  property string emptyText: "Nothing recorded yet"
  property string caption: ""
  property string trendCaption: ""
  property color foreground: Color.foreground
  property string fontFamily: Style.font.family
  property int valueFontSize: Style.font.title
  property int barHeight: Style.space(14)

  readonly property bool hasValue: percent !== null && percent !== undefined
  readonly property real fraction: hasValue ? Math.max(0, Math.min(1, percent / 100)) : 0

  spacing: Style.spacing.sm

  Item {
    width: parent.width
    height: Math.max(leading.implicitHeight, empty.implicitHeight)

    Text {
      id: leading
      anchors.left: parent.left
      anchors.verticalCenter: parent.verticalCenter
      visible: root.hasValue
      textFormat: Text.PlainText
      text: root.leadingLabel
      color: Color.accent
      font.bold: true
      font.family: root.fontFamily
      font.pixelSize: root.valueFontSize
    }

    Text {
      anchors.right: parent.right
      anchors.verticalCenter: parent.verticalCenter
      visible: root.hasValue
      textFormat: Text.PlainText
      text: root.trailingLabel
      color: Qt.darker(root.foreground, 1.4)
      font.family: root.fontFamily
      font.pixelSize: root.valueFontSize
    }

    Text {
      id: empty
      anchors.centerIn: parent
      visible: !root.hasValue
      textFormat: Text.PlainText
      text: root.emptyText
      color: Qt.darker(root.foreground, 1.4)
      font.family: root.fontFamily
      font.pixelSize: Style.font.bodySmall
    }
  }

  Rectangle {
    id: track
    visible: root.hasValue
    width: parent.width
    height: root.barHeight
    radius: Style.cornerRadius > 0 ? height / 2 : 0
    color: Style.normalFill
    clip: true

    // The remainder is drawn as a full-width ground with the A-share on top,
    // so the two segments can never disagree about the total by a rounding
    // pixel the way two independently-sized rectangles did.
    Rectangle {
      anchors.fill: parent
      color: Util.alpha(root.foreground, 0.28)
    }

    Rectangle {
      width: track.width * root.fraction
      height: track.height
      color: Color.accent
      Behavior on width { NumberAnimation { duration: 200; easing.type: Easing.OutCubic } }
    }
  }

  Text {
    width: parent.width
    visible: root.caption !== ""
    textFormat: Text.PlainText
    text: root.caption
    wrapMode: Text.WordWrap
    color: Qt.darker(root.foreground, 1.5)
    font.family: root.fontFamily
    font.pixelSize: Style.font.caption
  }

  Text {
    width: parent.width
    visible: root.trendCaption !== ""
    textFormat: Text.PlainText
    text: root.trendCaption
    wrapMode: Text.WordWrap
    color: Qt.darker(root.foreground, 1.6)
    font.family: root.fontFamily
    font.pixelSize: Style.font.caption
  }
}
