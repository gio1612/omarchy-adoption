.pragma library

// Pure formatting helpers, no state. Shared by BarWidget.qml and StatsPanel.qml.

function formatCompactLabel(connected, hasData, wpmAvg, navKeyboardPct) {
  if (!connected) return "Adoption: offline"
  if (!hasData) return "No data yet"
  var wpm = Math.round(wpmAvg || 0)
  var navPart = "—"
  if (navKeyboardPct !== null && navKeyboardPct !== undefined) {
    navPart = "⌨" + Math.round(navKeyboardPct) + "%"
  }
  return navPart + " · " + wpm + "wpm"
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

function recordCards(records) {
  if (!records) return []
  var cards = []
  if (records.fastest_burst_wpm) {
    cards.push({
      icon: "⚡",
      label: "Fastest typing burst",
      value: Math.round(records.fastest_burst_wpm.value) + " WPM",
      day: _shortDay(records.fastest_burst_wpm.day),
    })
  }
  if (records.busiest_keystroke_day) {
    cards.push({
      icon: "🔥",
      label: "Busiest day",
      value: Number(records.busiest_keystroke_day.value).toLocaleString() + " keys",
      day: _shortDay(records.busiest_keystroke_day.day),
    })
  }
  if (records.best_keyboard_day) {
    cards.push({
      icon: "⌨",
      label: "Most keyboard-driven day",
      value: Math.round(records.best_keyboard_day.value) + "% kbd",
      day: _shortDay(records.best_keyboard_day.day),
    })
  }
  return cards
}

function formatNavCaption(navKeyboardCount, navMouseCount, mouseWeight) {
  var total = (navKeyboardCount || 0) + (navMouseCount || 0)
  if (total === 0) return "No navigation recorded yet"
  var caption = (navKeyboardCount || 0) + " keys · " + (navMouseCount || 0) + " clicks"
  if (mouseWeight && mouseWeight !== 1) {
    caption += " · mouse ×" + Number(mouseWeight).toFixed(1).replace(/\.0$/, "")
  }
  return caption
}

function formatCheatsheetCount(count) {
  count = count || 0
  return count + " " + (count === 1 ? "time" : "times")
}

function historySeries(history) {
  return (history && Array.isArray(history.series)) ? history.series : []
}

function hasWpmTrend(history) {
  var series = historySeries(history)
  var count = 0
  for (var i = 0; i < series.length; i++) {
    if (series[i].wpm_avg !== null && series[i].wpm_avg !== undefined) count++
  }
  return count >= 2
}

function wpmSparkPoints(history) {
  var series = historySeries(history)
  if (series.length === 0) return []

  var min = null, max = null
  for (var i = 0; i < series.length; i++) {
    var v = series[i].wpm_avg
    if (v === null || v === undefined) continue
    if (min === null || v < min) min = v
    if (max === null || v > max) max = v
  }

  var points = []
  var denom = Math.max(1, series.length - 1)
  for (var j = 0; j < series.length; j++) {
    var value = series[j].wpm_avg
    var x = j / denom
    var y
    if (value === null || value === undefined) {
      y = null
    } else if (min === max) {
      y = 0.5
    } else {
      y = (value - min) / (max - min)
    }
    points.push({ x: x, y: y })
  }
  return points
}

function keyboardTrendBars(history) {
  if (!history) return []
  var series = historySeries(history)
  var bars = []
  for (var i = 0; i < series.length; i++) {
    var day = series[i]
    bars.push({
      day: day.day,
      kbFrac: (day.nav_keyboard_pct !== null && day.nav_keyboard_pct !== undefined)
        ? day.nav_keyboard_pct / 100 : null,
    })
  }
  return bars
}

function cheatsheetTrend(history) {
  var series = historySeries(history)
  if (series.length < 4) return null

  var mid = Math.floor(series.length / 2)
  var older = series.slice(0, mid)
  var recent = series.slice(mid)

  var olderSum = 0
  for (var i = 0; i < older.length; i++) olderSum += (older[i].cheatsheet_count || 0)
  var recentSum = 0
  for (var j = 0; j < recent.length; j++) recentSum += (recent[j].cheatsheet_count || 0)

  if (olderSum === 0 && recentSum === 0) return null

  var direction = "flat"
  if (recentSum <= olderSum - 1 && recentSum < olderSum * 0.9) {
    direction = "down"
  } else if (recentSum >= olderSum + 1 && recentSum > olderSum * 1.1) {
    direction = "up"
  }

  return { direction: direction, olderSum: olderSum, recentSum: recentSum }
}

function formatCheatsheetTrendCaption(trend) {
  if (trend === null || trend === undefined) return ""
  if (trend.direction === "down") {
    return "↓ leaning on it less (" + trend.olderSum + " → " + trend.recentSum + ")"
  }
  if (trend.direction === "up") {
    return "↑ using it more (" + trend.olderSum + " → " + trend.recentSum + ")"
  }
  return "steady (" + trend.recentSum + " this period)"
}
