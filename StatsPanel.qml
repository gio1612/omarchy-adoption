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
  property var navKeyboardPct: null
  property int cheatsheetCount: 0
  property int appLaunchKeybindCount: 0
  property int appLaunchPanelCount: 0
  property var appLaunchKeybindPct: null
  property var records: null
  property var history: null
  property bool loggingEnabled: false
  property var logLines: []

  signal toggleLogging()
  signal refreshLog()

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
        spacing: Style.space(8)

        // 2.0 Header row (all states)
        Item {
          width: parent.width
          height: Math.max(titleText.implicitHeight, windowPill.height)

          Text {
            id: titleText
            anchors.left: parent.left
            anchors.verticalCenter: parent.verticalCenter
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
            width: pillLabel.implicitWidth + Style.space(16)
            radius: height / 2
            color: root.connectedToDaemon ? Style.selectedAccentFill : Style.normalFill
            borderSpec: Border.flat(root.connectedToDaemon ? Color.accent : root.barForeground, Style.space(1))

            Text {
              id: pillLabel
              anchors.centerIn: parent
              text: root.windowLabel.toUpperCase()
              color: root.connectedToDaemon ? Color.accent : Util.alpha(root.barForeground, 0.6)
              font.family: root.bar ? root.bar.fontFamily : Style.font.family
              font.bold: true
              font.pixelSize: Style.font.caption
              font.letterSpacing: 1
            }
          }
        }

        // 2.1 State: not connected
        Column {
          width: parent.width
          visible: !root.connectedToDaemon
          spacing: Style.space(8)
          topPadding: Style.space(12)

          Text {
            anchors.horizontalCenter: parent.horizontalCenter
            text: "🔌"
            font.pixelSize: Style.font.heading
            opacity: 0.55
          }
          Text {
            width: parent.width
            horizontalAlignment: Text.AlignHCenter
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
            text: "Run scripts/setup.sh once to start tracking (see this plugin's README)."
            color: Util.alpha(root.barForeground, 0.65)
            font.family: root.bar ? root.bar.fontFamily : Style.font.family
            font.pixelSize: Style.font.bodySmall
          }
          Rectangle {
            anchors.horizontalCenter: parent.horizontalCenter
            width: codeText.implicitWidth + Style.space(16)
            height: codeText.implicitHeight + Style.space(8)
            radius: Style.space(4)
            color: Style.normalFill
            Text {
              id: codeText
              anchors.centerIn: parent
              text: "scripts/setup.sh"
              color: root.barForeground
              font.family: root.bar ? root.bar.fontFamily : Style.font.family
              font.pixelSize: Style.font.bodySmall
            }
          }
        }

        // 2.2 State: connected, no data yet
        Column {
          width: parent.width
          visible: root.connectedToDaemon && !root.hasData
          spacing: Style.space(6)
          topPadding: Style.space(12)

          Text {
            anchors.horizontalCenter: parent.horizontalCenter
            text: "⏳"
            font.pixelSize: Style.font.heading
            opacity: 0.55
          }
          Text {
            width: parent.width
            horizontalAlignment: Text.AlignHCenter
            wrapMode: Text.WordWrap
            text: "No data yet for " + root.windowLabel.toLowerCase() + "."
            color: Util.alpha(root.barForeground, 0.7)
            font.family: root.bar ? root.bar.fontFamily : Style.font.family
            font.pixelSize: Style.font.bodySmall
          }
        }

        // 2.3 State: connected, has data -- hero metrics
        Column {
          width: parent.width
          visible: root.connectedToDaemon && root.hasData
          spacing: Style.space(8)

          // 2.3.1 WPM hero + 14-day sparkline
          Text {
            text: "TYPING SPEED"
            color: Util.alpha(root.barForeground, 0.55)
            font.family: root.bar ? root.bar.fontFamily : Style.font.family
            font.bold: true
            font.pixelSize: Style.font.caption
            font.letterSpacing: 1
            topPadding: Style.space(4)
          }

          Row {
            width: parent.width
            spacing: Style.space(8)

            Text {
              text: Math.round(root.wpmAvg)
              color: root.barForeground
              font.family: root.bar ? root.bar.fontFamily : Style.font.family
              font.bold: true
              font.pixelSize: Style.font.displayLarge
            }
            Column {
              anchors.bottom: parent.bottom
              anchors.bottomMargin: Style.space(4)
              spacing: 0
              Text {
                text: "WPM avg"
                color: Util.alpha(root.barForeground, 0.6)
                font.family: root.bar ? root.bar.fontFamily : Style.font.family
                font.pixelSize: Style.font.caption
              }
              Text {
                visible: root.wpmLast > 0
                text: "last burst " + Math.round(root.wpmLast)
                color: Util.alpha(root.barForeground, 0.6)
                font.family: root.bar ? root.bar.fontFamily : Style.font.family
                font.pixelSize: Style.font.caption
              }
            }
          }

          Canvas {
            id: wpmSpark
            width: parent.width
            height: Style.space(32)
            visible: Fmt.hasWpmTrend(root.history)
            property var points: Fmt.wpmSparkPoints(root.history)

            onPointsChanged: requestPaint()
            onWidthChanged: requestPaint()

            onPaint: {
              var ctx = getContext("2d")
              ctx.reset()
              if (!points || points.length < 2) return
              var w = width, h = height
              var pad = Style.space(3)
              ctx.lineWidth = Style.space(2)
              ctx.strokeStyle = Color.accent
              ctx.lineCap = "round"
              ctx.lineJoin = "round"
              ctx.beginPath()
              var started = false
              for (var i = 0; i < points.length; i++) {
                var pt = points[i]
                if (pt.y === null) { started = false; continue }
                var px = pt.x * w
                var py = pad + (h - 2 * pad) * (1 - pt.y)
                if (!started) { ctx.moveTo(px, py); started = true }
                else ctx.lineTo(px, py)
              }
              ctx.stroke()

              for (var j = points.length - 1; j >= 0; j--) {
                if (points[j].y !== null) {
                  var lx = points[j].x * w
                  var ly = pad + (h - 2 * pad) * (1 - points[j].y)
                  ctx.beginPath()
                  ctx.arc(lx, ly, Style.space(2), 0, Math.PI * 2)
                  ctx.fillStyle = Color.accent
                  ctx.fill()
                  break
                }
              }
            }
          }

          // 2.3.2 Keyboard/mouse split + 14-day trend
          Text {
            text: "KEYBOARD VS MOUSE"
            color: Util.alpha(root.barForeground, 0.55)
            font.family: root.bar ? root.bar.fontFamily : Style.font.family
            font.bold: true
            font.pixelSize: Style.font.caption
            font.letterSpacing: 1
            topPadding: Style.space(4)
          }

          Column {
            width: parent.width
            spacing: Style.space(4)

            // percentage headline row
            Item {
              width: parent.width
              height: kbPct.implicitHeight
              Text {
                id: kbPct
                anchors.left: parent.left
                text: "KBD " + Math.round(root.navKeyboardPct !== null ? root.navKeyboardPct : 0) + "%"
                visible: root.navKeyboardPct !== null
                color: Color.accent
                font.bold: true
                font.family: root.bar ? root.bar.fontFamily : Style.font.family
                font.pixelSize: Style.font.title
              }
              Text {
                anchors.right: parent.right
                text: (root.navKeyboardPct !== null ? Math.round(100 - root.navKeyboardPct) : 0) + "% MOUSE"
                visible: root.navKeyboardPct !== null
                color: Util.alpha(root.barForeground, 0.6)
                font.family: root.bar ? root.bar.fontFamily : Style.font.family
                font.pixelSize: Style.font.title
              }
              Text {
                anchors.centerIn: parent
                visible: root.navKeyboardPct === null
                text: "No navigation recorded yet"
                color: Util.alpha(root.barForeground, 0.6)
                font.family: root.bar ? root.bar.fontFamily : Style.font.family
                font.pixelSize: Style.font.bodySmall
              }
            }

            // the bar itself
            Rectangle {
              id: splitTrack
              visible: root.navKeyboardPct !== null
              width: parent.width
              height: Style.space(14)
              radius: height / 2
              color: Style.normalFill
              clip: true

              Rectangle {
                width: parent.width * (root.navKeyboardPct / 100)
                height: parent.height
                color: Color.accent
                Behavior on width { NumberAnimation { duration: 200; easing.type: Easing.OutCubic } }
              }
              Rectangle {
                anchors.right: parent.right
                width: parent.width * (1 - root.navKeyboardPct / 100)
                height: parent.height
                color: Util.alpha(root.barForeground, 0.28)
                Behavior on width { NumberAnimation { duration: 200; easing.type: Easing.OutCubic } }
              }
            }

            Text {
              width: parent.width
              text: Fmt.formatNavCaption(root.navKeyboardCount, root.navMouseCount, root.mouseWeight)
              color: Util.alpha(root.barForeground, 0.55)
              font.family: root.bar ? root.bar.fontFamily : Style.font.family
              font.pixelSize: Style.font.caption
            }
          }

          Column {
            width: parent.width
            spacing: Style.space(4)
            topPadding: Style.space(8)
            visible: Fmt.keyboardTrendBars(root.history).length > 0

            Text {
              text: "14-day trend"
              color: Util.alpha(root.barForeground, 0.55)
              font.family: root.bar ? root.bar.fontFamily : Style.font.family
              font.pixelSize: Style.font.caption
            }

            Row {
              width: parent.width
              height: Style.space(28)
              spacing: Style.space(4)

              Repeater {
                model: Fmt.keyboardTrendBars(root.history)
                Rectangle {
                  required property var modelData
                  width: Style.space(12)
                  height: parent.height
                  radius: Style.space(2)
                  color: Style.normalFill
                  clip: true

                  // no navigation recorded that day: a short flat "no data"
                  // tick, never a 0% or interpolated bar
                  Rectangle {
                    visible: modelData.kbFrac === null
                    anchors.horizontalCenter: parent.horizontalCenter
                    anchors.verticalCenter: parent.verticalCenter
                    width: parent.width - Style.space(4)
                    height: Style.space(2)
                    radius: height / 2
                    color: Util.alpha(root.barForeground, 0.15)
                  }

                  // data day: full-height composition fill, bottom-up,
                  // mirroring the live split bar's two-segment language
                  Rectangle {
                    visible: modelData.kbFrac !== null
                    anchors.bottom: parent.bottom
                    width: parent.width
                    height: parent.height
                    color: Util.alpha(root.barForeground, 0.28)
                  }
                  Rectangle {
                    visible: modelData.kbFrac !== null
                    anchors.bottom: parent.bottom
                    width: parent.width
                    height: parent.height * (modelData.kbFrac || 0)
                    color: Color.accent
                    Behavior on height { NumberAnimation { duration: 150; easing.type: Easing.OutCubic } }
                  }
                }
              }
            }

            Item {
              width: parent.width
              height: oldestLabel.implicitHeight
              Text {
                id: oldestLabel
                anchors.left: parent.left
                text: Fmt._shortDay(Fmt.historySeries(root.history)[0]
                        ? Fmt.historySeries(root.history)[0].day : "")
                color: Util.alpha(root.barForeground, 0.5)
                font.family: root.bar ? root.bar.fontFamily : Style.font.family
                font.pixelSize: Style.font.caption
              }
              Text {
                anchors.right: parent.right
                text: "today"
                color: Util.alpha(root.barForeground, 0.5)
                font.family: root.bar ? root.bar.fontFamily : Style.font.family
                font.pixelSize: Style.font.caption
              }
            }
          }

          // 2.3.3 Cheatsheet line + trend arrow
          Column {
            width: parent.width
            spacing: 0
            topPadding: Style.space(4)

            Text {
              width: parent.width
              text: "SUPER+K cheatsheet: " + Fmt.formatCheatsheetCount(root.cheatsheetCount)
              color: Util.alpha(root.barForeground, 0.7)
              font.family: root.bar ? root.bar.fontFamily : Style.font.family
              font.pixelSize: Style.font.bodySmall
            }
            Text {
              width: parent.width
              visible: Fmt.cheatsheetTrend(root.history) !== null
              text: Fmt.formatCheatsheetTrendCaption(Fmt.cheatsheetTrend(root.history))
              color: Util.alpha(root.barForeground, 0.5)
              font.family: root.bar ? root.bar.fontFamily : Style.font.family
              font.pixelSize: Style.font.caption
            }
          }

          // 2.3.4 App launches: keybind vs. panel mini split-bar
          Column {
            width: parent.width
            spacing: Style.space(8)
            topPadding: Style.space(4)

            Text {
              text: "APP LAUNCHES"
              color: Util.alpha(root.barForeground, 0.55)
              font.family: root.bar ? root.bar.fontFamily : Style.font.family
              font.bold: true
              font.pixelSize: Style.font.caption
              font.letterSpacing: 1
            }

            Column {
              width: parent.width
              spacing: Style.space(4)

              Item {
                width: parent.width
                height: kbLaunchPct.implicitHeight
                Text {
                  id: kbLaunchPct
                  anchors.left: parent.left
                  text: "Keybind " + Math.round(root.appLaunchKeybindPct !== null ? root.appLaunchKeybindPct : 0) + "%"
                  visible: root.appLaunchKeybindPct !== null
                  color: Color.accent
                  font.bold: true
                  font.family: root.bar ? root.bar.fontFamily : Style.font.family
                  font.pixelSize: Style.font.bodySmall
                }
                Text {
                  anchors.right: parent.right
                  text: (root.appLaunchKeybindPct !== null ? Math.round(100 - root.appLaunchKeybindPct) : 0) + "% Panel"
                  visible: root.appLaunchKeybindPct !== null
                  color: Util.alpha(root.barForeground, 0.6)
                  font.family: root.bar ? root.bar.fontFamily : Style.font.family
                  font.pixelSize: Style.font.bodySmall
                }
                Text {
                  anchors.centerIn: parent
                  visible: root.appLaunchKeybindPct === null
                  text: "No app launches recorded yet"
                  color: Util.alpha(root.barForeground, 0.6)
                  font.family: root.bar ? root.bar.fontFamily : Style.font.family
                  font.pixelSize: Style.font.bodySmall
                }
              }

              Rectangle {
                visible: root.appLaunchKeybindPct !== null
                width: parent.width
                height: Style.space(8)
                radius: height / 2
                color: Style.normalFill
                clip: true

                Rectangle {
                  width: parent.width * (root.appLaunchKeybindPct / 100)
                  height: parent.height
                  color: Color.accent
                  Behavior on width { NumberAnimation { duration: 200; easing.type: Easing.OutCubic } }
                }
                Rectangle {
                  anchors.right: parent.right
                  width: parent.width * (1 - root.appLaunchKeybindPct / 100)
                  height: parent.height
                  color: Util.alpha(root.barForeground, 0.28)
                  Behavior on width { NumberAnimation { duration: 200; easing.type: Easing.OutCubic } }
                }
              }

              Text {
                width: parent.width
                text: Fmt.formatAppLaunchCaption(root.appLaunchKeybindCount, root.appLaunchPanelCount)
                color: Util.alpha(root.barForeground, 0.55)
                font.family: root.bar ? root.bar.fontFamily : Style.font.family
                font.pixelSize: Style.font.caption
              }
              Text {
                width: parent.width
                visible: Fmt.appLaunchTrend(root.history) !== null
                text: Fmt.formatAppLaunchTrendCaption(Fmt.appLaunchTrend(root.history))
                color: Util.alpha(root.barForeground, 0.5)
                font.family: root.bar ? root.bar.fontFamily : Style.font.family
                font.pixelSize: Style.font.caption
              }
            }
          }
        }

        // 2.4 Records -- "Best of the best" leaderboard card
        Column {
          width: parent.width
          visible: root.connectedToDaemon && Fmt.recordCards(root.records).length > 0
          spacing: Style.space(6)
          topPadding: Style.space(8)

          Text {
            text: "Best of the best"
            color: root.barForeground
            font.family: root.bar ? root.bar.fontFamily : Style.font.family
            font.bold: true
            font.pixelSize: Style.font.subtitle
          }

          Repeater {
            model: Fmt.recordCards(root.records)
            Rectangle {
              required property var modelData
              width: parent.width
              height: rowIcon.implicitHeight + Style.space(12)
              radius: Style.space(6)
              color: Style.normalFill

              Text {
                id: rowIcon
                anchors.left: parent.left
                anchors.leftMargin: Style.space(8)
                anchors.verticalCenter: parent.verticalCenter
                text: modelData.icon
                font.pixelSize: Style.font.title
              }
              Column {
                anchors.left: rowIcon.right
                anchors.leftMargin: Style.space(8)
                anchors.right: rowValue.left
                anchors.rightMargin: Style.space(8)
                anchors.verticalCenter: parent.verticalCenter
                spacing: 0
                Text {
                  width: parent.width
                  text: modelData.label
                  color: root.barForeground
                  font.family: root.bar ? root.bar.fontFamily : Style.font.family
                  font.pixelSize: Style.font.bodySmall
                  elide: Text.ElideRight
                }
                Text {
                  text: modelData.day
                  color: Util.alpha(root.barForeground, 0.55)
                  font.family: root.bar ? root.bar.fontFamily : Style.font.family
                  font.pixelSize: Style.font.caption
                }
              }
              Text {
                id: rowValue
                anchors.right: parent.right
                anchors.rightMargin: Style.space(8)
                anchors.verticalCenter: parent.verticalCenter
                text: modelData.value
                color: Color.accent
                font.bold: true
                font.family: root.bar ? root.bar.fontFamily : Style.font.family
                font.pixelSize: Style.font.bodySmall
              }
            }
          }
        }

        // 2.5 Debug audit logging -- toggle to enable/disable, and a small
        // live view of the daemon's in-memory classification log.
        Column {
          width: parent.width
          visible: root.connectedToDaemon
          spacing: Style.space(8)
          topPadding: Style.space(12)

          Text {
            text: "DEBUG AUDIT"
            color: Util.alpha(root.barForeground, 0.55)
            font.family: root.bar ? root.bar.fontFamily : Style.font.family
            font.bold: true
            font.pixelSize: Style.font.caption
            font.letterSpacing: 1
          }

          Row {
            width: parent.width
            spacing: Style.space(8)
            anchors.horizontalCenter: parent.horizontalCenter

            Rectangle {
              id: logToggle
              width: Style.space(64)
              height: Style.space(24)
              radius: height / 2
              color: root.loggingEnabled ? Color.accent : Style.normalFill
              borderSpec: Border.flat(
                root.loggingEnabled ? Color.accent : Util.alpha(root.barForeground, 0.3),
                Style.space(1))

              Rectangle {
                width: parent.height - Style.space(6)
                height: parent.height - Style.space(6)
                radius: width / 2
                color: root.loggingEnabled ? Util.alpha(root.barForeground, 1.0) : Util.alpha(root.barForeground, 0.7)
                x: root.loggingEnabled ? parent.width - width - Style.space(3) : Style.space(3)
                anchors.verticalCenter: parent.verticalCenter
                Behavior on x { NumberAnimation { duration: 150; easing.type: Easing.OutCubic } }
              }

              MouseArea {
                anchors.fill: parent
                onClicked: root.toggleLogging()
              }
            }

            Text {
              text: root.loggingEnabled ? "Logging ON" : "Logging OFF"
              color: root.barForeground
              font.family: root.bar ? root.bar.fontFamily : Style.font.family
              font.pixelSize: Style.font.bodySmall
              anchors.verticalCenter: logToggle.verticalCenter
            }
          }

          // live log view
          Column {
            width: parent.width
            visible: root.loggingEnabled
            spacing: Style.space(6)

            Text {
              width: parent.width
              wrapMode: Text.WordWrap
              text: "Input activity is being recorded in memory (not persisted). Scroll devices, clicks, wheels and trackpad scrolls appear here."
              color: Util.alpha(root.barForeground, 0.6)
              font.family: root.bar ? root.bar.fontFamily : Style.font.family
              font.pixelSize: Style.font.caption
            }

            Rectangle {
              width: parent.width
              height: Math.min(root.logLines.length * Style.space(16), Style.space(180))
              radius: Style.space(6)
              color: Style.normalFill
              clip: true

              Flickable {
                id: logFlick
                anchors.fill: parent
                contentHeight: logCol.implicitHeight
                clip: true

                Column {
                  id: logCol
                  width: parent.width
                  spacing: Style.space(2)
                  Repeater {
                    model: root.logLines
                    Text {
                      width: parent.width
                      wrapMode: Text.WrapAnywhere
                      text: modelData
                      color: Util.alpha(root.barForeground, 0.85)
                      font.family: "monospace"
                      font.pixelSize: Style.font.caption
                    }
                  }
                }
              }
            }

            Row {
              width: parent.width
              spacing: Style.space(8)

              Rectangle {
                width: refreshText.implicitWidth + Style.space(16)
                height: refreshText.implicitHeight + Style.space(6)
                radius: Style.space(4)
                color: Style.normalFill
                borderSpec: Border.flat(Util.alpha(root.barForeground, 0.3), Style.space(1))
                Text {
                  id: refreshText
                  anchors.centerIn: parent
                  text: "Refresh log"
                  color: root.barForeground
                  font.family: root.bar ? root.bar.fontFamily : Style.font.family
                  font.pixelSize: Style.font.bodySmall
                }
                MouseArea {
                  anchors.fill: parent
                  onClicked: root.refreshLog()
                }
              }
              Text {
                text: root.logLines.length + " lines"
                color: Util.alpha(root.barForeground, 0.55)
                font.family: root.bar ? root.bar.fontFamily : Style.font.family
                font.pixelSize: Style.font.caption
                anchors.verticalCenter: parent.verticalCenter
              }
            }
          }

          // auto-refresh the log view while the panel is open and logging is on
          Timer {
            interval: 1000
            running: root.connectedToDaemon && root.loggingEnabled && root.opened
            repeat: true
            triggeredOnStart: true
            onTriggered: root.refreshLog()
          }
        }
      }
    }
  }
}
