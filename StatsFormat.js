.pragma library

// Pure formatting helpers, no state. Shared by BarWidget.qml and Panel.qml.

function formatCompactLabel(connected, hasData, wpmAvg, navKeyboardPct, cheatsheetCount) {
  if (!connected) return "Adoption Tracker: not connected"
  if (!hasData) return "No data yet today"
  var wpm = Math.round(wpmAvg || 0)
  var navPart = "—"
  if (navKeyboardPct !== null && navKeyboardPct !== undefined) {
    var kb = Math.round(navKeyboardPct)
    navPart = "⌨" + kb + "%/🖱" + (100 - kb) + "%"
  }
  return wpm + " WPM · " + navPart + " · K:" + (cheatsheetCount || 0)
}

function formatWindowLabel(windowKey) {
  if (windowKey === "week") return "This week"
  if (windowKey === "all") return "All-time"
  return "Today"
}

function formatNavBreakdown(navKeyboardCount, navMouseCount, mouseWeight) {
  var total = (navKeyboardCount || 0) + (navMouseCount || 0)
  if (total === 0) return "No navigation recorded yet"
  var pct = Math.round(100 * navKeyboardCount / total)
  var label = navKeyboardCount + " keyboard / " + navMouseCount + " mouse (" + pct + "% keyboard)"
  if (mouseWeight && mouseWeight !== 1) {
    label += " · mouse ×" + Number(mouseWeight).toFixed(1).replace(/\.0$/, "")
  }
  return label
}

function formatWpm(wpmAvg, wpmLast) {
  if (!wpmAvg && !wpmLast) return "No typing recorded yet"
  return "avg " + Math.round(wpmAvg) + " WPM · last burst " + Math.round(wpmLast) + " WPM"
}

function formatCheatsheetCount(count) {
  count = count || 0
  return count + " " + (count === 1 ? "time" : "times")
}
