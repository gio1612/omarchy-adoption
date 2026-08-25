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
  if (windowKey === "month") return "This month"
  if (windowKey === "all") return "All-time"
  return "Today"
}

function _shortDay(day) {
  if (!day) return ""
  var months = ["Jan", "Feb", "Mar", "Apr", "May", "Jun",
                "Jul", "Aug", "Sep", "Oct", "Nov", "Dec"]
  var parts = String(day).split("-")
  if (parts.length !== 3) return String(day)
  return months[Number(parts[1]) - 1] + " " + Number(parts[2])
}

function recordLines(records) {
  if (!records) return []
  var lines = []
  if (records.fastest_burst_wpm) {
    lines.push("Fastest burst: " + Math.round(records.fastest_burst_wpm.value)
               + " WPM · " + _shortDay(records.fastest_burst_wpm.day))
  }
  if (records.busiest_keystroke_day) {
    lines.push("Most keystrokes in a day: "
               + Number(records.busiest_keystroke_day.value).toLocaleString()
               + " · " + _shortDay(records.busiest_keystroke_day.day))
  }
  if (records.best_keyboard_day) {
    lines.push("Most keyboard-driven day: "
               + Math.round(records.best_keyboard_day.value) + "% keyboard · "
               + _shortDay(records.best_keyboard_day.day))
  }
  return lines
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
