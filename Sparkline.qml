import QtQuick
import qs.Commons

// WPM trend sparkline. `points` is a pre-normalized [{x: 0..1, y: 0..1|null}]
// series from StatsFormat.wpmSparkPoints -- a null y is a day with no typing,
// which breaks the line rather than interpolating across it.
//
// The caller owns the derivation and passes the finished array in. Calling
// the Fmt helper inline in this binding, as the old panel did, re-derived the
// whole series on every repaint trigger.
Canvas {
  id: root

  property var points: []
  property color lineColor: Color.accent
  property int strokeWidth: Style.space(2)
  property int dotRadius: Style.space(2)
  property int verticalPadding: Style.space(3)

  readonly property bool hasLine: !!points && points.length >= 2

  height: Style.space(32)

  onPointsChanged: requestPaint()
  onWidthChanged: requestPaint()
  onHeightChanged: requestPaint()
  onLineColorChanged: requestPaint()

  onPaint: {
    var ctx = getContext("2d")
    ctx.reset()
    var series = root.points
    if (!series || series.length < 2) return

    var w = width
    var h = height
    var pad = root.verticalPadding
    var span = h - 2 * pad

    function px(pt) { return pt.x * w }
    function py(pt) { return pad + span * (1 - pt.y) }

    ctx.lineWidth = root.strokeWidth
    ctx.strokeStyle = root.lineColor
    ctx.lineCap = "round"
    ctx.lineJoin = "round"
    ctx.beginPath()

    var started = false
    for (var i = 0; i < series.length; i++) {
      var pt = series[i]
      if (pt.y === null || pt.y === undefined) { started = false; continue }
      if (started) ctx.lineTo(px(pt), py(pt))
      else { ctx.moveTo(px(pt), py(pt)); started = true }
    }
    ctx.stroke()

    // Mark the most recent day that actually has a value.
    for (var j = series.length - 1; j >= 0; j--) {
      var last = series[j]
      if (last.y === null || last.y === undefined) continue
      ctx.beginPath()
      ctx.arc(px(last), py(last), root.dotRadius, 0, Math.PI * 2)
      ctx.fillStyle = root.lineColor
      ctx.fill()
      break
    }
  }
}
