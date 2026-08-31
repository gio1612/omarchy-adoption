# Adoption Tracker — visualization design

Design spec for `BarWidget.qml` and `StatsPanel.qml`. Written for the
development agent that implements it; do not implement QML from this repo
under this task (see `.claude/agents/plugin-designer.md`). All tokens below
come from the installed shell — `/usr/share/omarchy/shell/Commons/Style.qml`
and `Color.qml` — read there for definitions not repeated here.

A companion HTML mockup (bar-strip label + all three panel states) was
published as an Artifact for visual sign-off before any QML changes land.

## Direction, in one paragraph

This plugin exists to answer one question at a glance: "am I actually using
the keyboard-driven workflow, or am I reaching for the mouse?" Everything
here is built around making the keyboard/mouse split *visible as a shape*,
not just as a fraction of an emoji-decorated sentence, while keeping the WPM
number simple (no color-coded speed bands — this plugin isn't a typing-test
scorer, it's an adoption tracker, so the number stays neutral). One accent
color is claimed as the "keyboard-forward" signal and reused consistently:
the keyboard segment of the split bar, the window pill, and record values.
Nothing else fights it. The bar-strip label stays plain text (no new icon
component) because the existing ⌨/🖱 glyphs already carry the icon job
inline, and `BarIconButton`/`OpticalGlyph` would mean swapping off
`WidgetButton`, which is exactly the type that was just fixed for
click-forwarding — not worth the regression risk for a label that's already
legible.

## Revision — trends, titles, minimalism

User feedback on the mockup, verbatim: *"On The panel show sparkcharts, and
bars, Titles, and minimalistic style, the grafics give more information that
plane numbers, play with the statistics that you can generate. The
information need to have meaning."* Read as five separate requirements: (1)
a sparkline *and* a bar chart — two distinct chart types, not one; (2) real
section titles; (3) stay minimal, not busy; (4) each chart must show more
than a single number would (trend/context, not a shape restating one
scalar); (5) survey what else the backend can generate and only use what
clears the "does this actually tell the user something true and useful" bar.

This is only satisfiable with real history, and today's daemon has none —
`get_stats` only returns pre-summed window totals and `get_records` only
all-time bests, neither is a per-day series. `daily_rollup` already has the
rows (one per calendar day, `typing_wpm_avg`, `nav_keyboard_count`,
`nav_mouse_count`, `cheatsheet_count`, …); it is just never queried as a
series today. So this revision starts with a new backend contract (see
below), then two charts, then a set of title/hierarchy changes to the
existing layout.

**Chart 1 — keyboard-adoption trend, a bar chart (§2.3.2).** One bar per
day, stacked composition (keyboard fraction vs. mouse fraction), 14 days.
This is the single most on-thesis chart possible for this plugin: the
README's whole premise is "am I trending toward keyboard-first workflow
over time," and today's panel only ever answers that for *one* day at a
time. It sits directly under the existing split bar (2.3.2) so "today's
snapshot" and "recent trend" of the *same* metric are visually adjacent —
not a second unrelated section fighting for attention.

**Chart 2 — WPM trend, a sparkline (§2.3.1).** A `Canvas` line, 14 days,
under the WPM hero number for the same "snapshot + its trend" pairing.
Line, not bars, because WPM is a continuous quantity (a rate), and a line
reads faster as "drifting up/down" than 14 discrete columns would; the
bar-chart slot is already spent on the keyboard split, which is genuinely
categorical (composition of two options per day) — using both chart forms
for what they're actually good at, rather than picking one style and
forcing both metrics into it, is the answer to "sparklines *and* bars."

**Considered and rejected** (the "does this clear the bar" test, made
explicit so the reasoning isn't lost):
- *SUPER+K cheatsheet trend as a full chart* — rejected as a chart, kept as
  a one-line trend annotation instead (§2.3.3). A declining trend here does
  mean something real ("leaning on the cheatsheet less because the binds
  are sinking in"), so it clears the *meaning* bar — but cheatsheet counts
  are low, bursty daily integers; a 14-bar chart of mostly 0s/1s/2s next to
  two real trend charts would read as visual noise, not insight, and would
  break the "minimalistic" instruction. A single trend arrow + before/after
  count gives the same insight far more cheaply.
- *Daily nav volume (total keyboard+mouse events/day)* — rejected outright.
  Raw activity volume isn't an adoption signal; a busy mouse day and a busy
  keyboard day would look identical on a volume chart. The composition
  chart (Chart 1) already isolates the one axis that actually matters here.
- *Daily burst count as its own chart* — rejected. The records leaderboard
  already surfaces the extremes ("busiest keystroke day"); a third
  chart plotting the same underlying activity as Chart 1/2 adds clutter
  without a new question answered.
- *Records "leaderboard" gets no chart treatment* — records are precisely
  single memorable events, not a series; charting one point per record
  would be exactly the "plain numbers wearing a shape" problem the feedback
  called out. Records stay cards (existing §2.4), unchanged by this
  revision.

**Titles.** The panel had exactly one title ("Best of the best") before
this revision; everything else was unlabeled. Rather than invent a new
heading style, this revision reuses the window pill's existing small-caps
"eyebrow" typography (bold, `Style.font.caption`, `letterSpacing: 1`,
muted color) as the one secondary-heading vocabulary, applied above the
WPM group ("TYPING SPEED") and the split/trend group ("KEYBOARD VS
MOUSE") — see §2.3.0 below. The cheatsheet line deliberately does *not*
get its own eyebrow: it's one sentence, and a heading over a single line
of text is decoration, not information, which is exactly what the feedback
warned against.

## Required data-plumbing change (not a visual change, but blocking)

`StatsPanel.qml` today receives `navKeyboardCount` / `navMouseCount` /
`mouseWeight` but **not** `navKeyboardPct`. Its own `Fmt.formatNavBreakdown`
then recomputes a percentage from the *raw* counts, ignoring `mouseWeight`
entirely — inconsistent with the bar-strip label, which correctly reads
`stats.nav_keyboard_pct` (the backend's *weighted* percentage) directly. Per
the README's calibration section, the weight is meant to affect the
displayed percentage — the split bar below is exactly "the displayed
percentage," so it must be driven by the weighted value, matching the bar
strip, not by a client-side recompute of raw counts.

Fix required in `BarWidget.qml`'s `StatsPanel` instantiation: add
`navKeyboardPct: root.navKeyboardPct` alongside the existing props. Add a
matching `property var navKeyboardPct: null` to `StatsPanel.qml`. The panel
uses this for the split-bar's *proportions and headline percentages*; raw
`navKeyboardCount`/`navMouseCount` are still shown as supporting text (counts
must stay unweighted per README).

### New: `history` command (daily trend series)

Neither chart above is buildable from `get_stats`/`get_records` as they
exist — both need one row per day, in order. New read-only method on
`Storage` (`backend/storage.py`), same file/class as `get_stats` and
`get_records`, same conventions (uses `_day_bounds`/`mouse_weight()`,
returns plain dicts, no schema change — pure `SELECT` over the existing
`daily_rollup` table):

```python
def get_daily_history(self, days: int = 14) -> dict:
    """Per-day trend series for the trailing `days` calendar days
    (including today), oldest first. Read-only projection over
    daily_rollup -- no new writes. Days with no daemon activity that day
    come back as zeroed/null rows rather than being omitted, so callers
    can always zip the series against a fixed-length day axis."""
    days = max(1, min(int(days) if days else 14, self.retention_days()))
    today = datetime.now().astimezone().date()
    day_keys = [(today - timedelta(days=i)).strftime("%Y-%m-%d")
                for i in range(days - 1, -1, -1)]  # oldest -> newest
    placeholders = ",".join("?" for _ in day_keys)
    rows = {r[0]: r for r in self._conn.execute(
        f"SELECT day, typing_wpm_avg, typing_burst_count, nav_keyboard_count, "
        f"nav_mouse_count, cheatsheet_count FROM daily_rollup "
        f"WHERE day IN ({placeholders})", day_keys).fetchall()}
    mouse_weight = self.mouse_weight()
    series = []
    for day in day_keys:
        row = rows.get(day)
        if row is None:
            series.append({
                "day": day, "wpm_avg": None, "burst_count": 0,
                "nav_keyboard": 0, "nav_mouse": 0, "nav_keyboard_pct": None,
                "cheatsheet_count": 0,
            })
            continue
        _, wpm_avg, burst_count, nav_kb, nav_mouse, cheatsheet_count = row
        denom = nav_kb + nav_mouse * mouse_weight
        series.append({
            "day": day,
            "wpm_avg": round(wpm_avg, 1) if wpm_avg is not None else None,
            "burst_count": burst_count,
            "nav_keyboard": nav_kb,
            "nav_mouse": nav_mouse,
            "nav_keyboard_pct": round(100 * nav_kb / denom, 1) if denom else None,
            "cheatsheet_count": cheatsheet_count,
        })
    return {"days": days, "mouse_weight": mouse_weight, "series": series}
```

`days` is clamped into `[1, retention_days()]` — never trust the request
value blindly, same posture as `set_mouse_weight`'s clamp. No minimum
burst/event count gates a day's value the way `RECORD_MIN_NAV_DAY` gates a
*record* — that threshold exists specifically to stop a 2-event day from
becoming a permanent "personal best"; a trend line isn't claiming a
superlative, it's just showing what happened, so every day's real value
(including noisy ones) belongs in the series as-is.

`daemon.py`'s `_process_message`, alongside the existing `elif command ==
"stats"` / `"records"` / `"set_mouse_weight"` chain:

```python
elif command == "history":
    try:
        days = int(message.get("days", 14))
    except (TypeError, ValueError):
        days = 14
    result = response(request_id, True, self.storage.get_daily_history(days))
```

Request shape: `{"v":1,"id":N,"command":"history","days":14}`. Response
`result` is exactly `get_daily_history`'s return value:
`{"days":14,"mouse_weight":1.0,"series":[{"day":"2026-08-13","wpm_avg":71.2,
"burst_count":4,"nav_keyboard":38,"nav_mouse":12,"nav_keyboard_pct":76.0,
"cheatsheet_count":1}, …]}`, oldest first. No push event for this command —
unlike `stats`, history isn't re-pushed on every flush (a 14-day trend
doesn't need sub-minute freshness); it's fetched once, matching how
`records` already behaves.

`BackendClient.qml` additions, mirroring `requestStats`/`lastStats`:

```qml
property var lastHistory: null
signal historyReceived(var history)

function requestHistory(days) {
  sendCommand("history", { days: days || 14 }, function(ok, result) {
    if (ok && result) {
      root.lastHistory = result
      root.historyReceived(result)
    }
  })
}
```

Wiring in `BarWidget.qml`: fetch once when the panel opens, same moment as
records (`onOpenedChanged: if (opened) { backend.requestRecords();
backend.requestHistory(14) }`), and pass through to the panel instance
alongside the other props: `history: backend.lastHistory`. Deliberately
**not** wired to `windowKey`/`onWindowKeyChanged` — the trend charts always
show a fixed trailing 14-day window regardless of which Today/week/
month/all-time window the header pill shows; those are two different
concepts ("what period are the headline numbers for" vs. "how did the
last two weeks trend") and conflating them would need a second visible
selector, which is explicitly out of scope (see below). `StatsPanel.qml`
gets a matching `property var history: null`.

## StatsFormat.js additions (new pure functions, alongside existing ones)

- `formatCompactLabel(connected, hasData, wpmAvg, navKeyboardPct)` — drop the
  `cheatsheetCount` parameter; compact label no longer shows it (see below).
- `recordCards(records)` — structured counterpart to `recordLines`, for the
  leaderboard card treatment. Returns an array of
  `{ icon, label, value, day }`, empty array if `records` is falsy:
  - `fastest_burst_wpm` → `{ icon: "⚡", label: "Fastest typing burst", value: Math.round(v) + " WPM", day: _shortDay(day) }`
  - `busiest_keystroke_day` → `{ icon: "🔥", label: "Busiest day", value: Number(v).toLocaleString() + " keys", day: _shortDay(day) }`
  - `best_keyboard_day` → `{ icon: "⌨", label: "Most keyboard-driven day", value: Math.round(v) + "% kbd", day: _shortDay(day) }`
  - Keep `_shortDay` and `recordLines` as-is (recordLines can stay, unused, or be removed — dev agent's call, `recordCards` replaces it in the panel).
- `formatNavCaption(navKeyboardCount, navMouseCount, mouseWeight)` — the
  small supporting line under the split bar. `total = navKeyboardCount +
  navMouseCount`; if `total === 0` return `"No navigation recorded yet"`;
  else `navKeyboardCount + " keys · " + navMouseCount + " clicks"`, and if
  `mouseWeight !== 1` append `" · mouse ×" + mouseWeight.toFixed(1).replace(/\.0$/, "")`.
- `historySeries(history)` — `history && Array.isArray(history.series) ?
  history.series : []`. Every function below builds on this.
- `hasWpmTrend(history)` — `true` iff `historySeries(history)` has at least
  two entries with non-null `wpm_avg`. A sparkline needs two points to draw
  a line at all; a single point would be a floating dot with no
  comparative meaning, so the sparkline hides entirely below this
  threshold rather than drawing something misleadingly definitive.
- `wpmSparkPoints(history)` — geometry for the Canvas sparkline. Returns an
  array, one entry per day of `historySeries(history)` (oldest first),
  each `{ x, y }`:
  - `x = index / Math.max(1, series.length - 1)` — 0 at the oldest day, 1
    at the newest.
  - `y` is that day's `wpm_avg`, min-max-normalized to `[0, 1]` **within
    this series only**, never against an absolute WPM scale — the hero
    number already shows the absolute value; the spark line's only job is
    the shape of change over the window (this keeps faith with the
    original design's "no color-coded speed bands" stance: the number
    stays neutral, and so does the line).
  - `y` is `null` for a day with `wpm_avg === null` (no typing that day) —
    the Canvas paint code breaks the line there instead of interpolating
    through a fabricated dip toward zero.
  - If every non-null value in the series is equal (flat trend, or exactly
    one non-null value), `y = 0.5` for all of them — a flat centered line,
    which honestly represents "no change" instead of dividing by a zero
    range.
  - Returns `[]` if `historySeries(history).length === 0`.
- `keyboardTrendBars(history)` — one entry per day, `{ day, kbFrac }`:
  `kbFrac = nav_keyboard_pct / 100` when that day's `nav_keyboard_pct` is
  non-null, else `kbFrac: null` (no navigation recorded that day — render
  as a flat "no data" tick, never a 0% or interpolated bar, exactly the
  null-handling the live split bar already uses in 2.3.2). Returns `[]` if
  `history` is falsy.
- `cheatsheetTrend(history)` — day-over-day-half comparison feeding the
  trend arrow next to the cheatsheet line (2.3.3). Returns `null` if
  `historySeries(history).length < 4` (too little sample either side of
  the split to say anything) **or** if both halves sum to zero (nothing
  happened — silence is more honest than announcing "steady at 0").
  Otherwise splits the series in half by index (`older` = first half,
  `recent` = second half; an odd length's extra day joins `recent`, i.e.
  `recent = series.slice(Math.floor(series.length / 2))`), sums
  `cheatsheet_count` in each half, and returns
  `{ direction, olderSum, recentSum }` where `direction` is:
  - `"down"` when `recentSum <= olderSum - 1 && recentSum < olderSum * 0.9`
  - `"up"` when `recentSum >= olderSum + 1 && recentSum > olderSum * 1.1`
  - `"flat"` otherwise.
- `formatCheatsheetTrendCaption(trend)` — `""` if `trend` is `null`.
  Otherwise: `"down"` → `"↓ leaning on it less (" + olderSum + " → " +
  recentSum + ")"`; `"up"` → `"↑ using it more (" + olderSum + " → " +
  recentSum + ")"`; `"flat"` → `"steady (" + recentSum + " this period)"`.

## 1. `BarWidget.qml` — compact bar-strip label

No component-tree change: keep `WidgetButton` (the click-forwarding fix
stays intact), keep `implicitWidth`/`implicitHeight` bound to the button.
Only the label text changes, via the `formatCompactLabel` signature above.

| State | `compactLabel` text |
|---|---|
| not connected | `Adoption: offline` |
| connected, no data | `No data yet` |
| connected, has data, no nav recorded in window | `— · 74wpm` |
| connected, has data, nav recorded | `⌨68% · 74wpm` |

Rationale: keyboard percentage leads (it's the hero metric — the thing this
plugin is *for*), WPM follows after a middle dot, cheatsheet count is
dropped from the compact label entirely (it's the least important of the
three metrics and the label was already the longest string on most bars —
"K:3" cost horizontal space for the least-glanced-at number; it still shows
in the panel). Round `wpmAvg` with `Math.round`, same as today.

## 2. `StatsPanel.qml` — full redesign

Base chrome is unchanged: still `Panel` → `KeyboardPanel` → `PanelKeyCatcher`
→ content. `contentWidth: Style.space(300)` stays (a hair narrow but
workable; do not widen without checking `fittedContentWidth` clamping on
narrow bars). `contentHeight` stays computed via
`fittedContentHeight(contentColumn.implicitHeight)`. Root `Column` spacing
and `anchors.margins: Style.spacing.popupPadding` stay as-is.

### 2.0 Header row (all states)

Replace the single `Text` title line with an `Item` (not a `Row`, so the
pill can anchor right while the title anchors left):

```
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
```

This surfaces the active window (Today/This week/This month/All-time)
without adding interactive chrome the widget doesn't support today — the
`window` setting is a plain `string` schema field edited from the plugin's
settings UI (confirmed in `manifest.json`), not a control the panel exposes;
the pill is read-only, dimmed (muted border/text, no accent) when not
connected since the window selection isn't doing anything meaningful yet.
`Border` and `Util` come for free once `import qs.Commons` is present (already
imported).

### 2.1 State: not connected

Replace the existing "Not connected" `Text` with a centered notice block,
`visible: !root.connectedToDaemon`:

```
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
```

Keep the privacy/no-content promise intact — this state never implies any
data exists, only that the daemon isn't reachable.

### 2.2 State: connected, no data yet

Replace the existing "No data yet for …" `Text` with, `visible:
root.connectedToDaemon && !root.hasData`:

```
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
```

Deliberately no skeleton/placeholder bar here: a 0/0 split bar has no
meaningful proportions to preview, and a fake filled bar would misrepresent
"no data" as "some data." A short empty-state message is more honest.

### 2.3 State: connected, has data — hero metrics

`visible: root.connectedToDaemon && root.hasData`, replacing the current
three-`Text` `Column`.

#### 2.3.0 Section-eyebrow convention

Both metric groups below get a small label reusing the header pill's own
typography (bold, `Style.font.caption`, `letterSpacing: 1`, muted) as the
one secondary-heading vocabulary in this panel — not a new heading style:

```
Text {
  text: "TYPING SPEED"   // or "KEYBOARD VS MOUSE"
  color: Util.alpha(root.barForeground, 0.55)
  font.family: root.bar ? root.bar.fontFamily : Style.font.family
  font.bold: true
  font.pixelSize: Style.font.caption
  font.letterSpacing: 1
  topPadding: Style.space(4)
}
```

#### 2.3.1 WPM hero + 14-day sparkline

**Eyebrow**: `"TYPING SPEED"` (per 2.3.0), directly above the hero `Row`.

**WPM hero** (own `Row`, `spacing: Style.space(8)`):

```
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
```

No color-coded speed bands (see rationale above) — the number stays
`root.barForeground`, not accent, so accent reads unambiguously as "keyboard
signal" everywhere else in the panel.

**WPM sparkline** (new — the "more than a plain number" chart for this
metric), directly under the hero `Row`, `visible:
Fmt.hasWpmTrend(root.history)` (hidden entirely, no placeholder box, when
fewer than two days of typing history exist yet — same "don't fake data"
posture as 2.2's empty state):

```
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
```

`Canvas` is plain `QtQuick`, already imported at the top of
`StatsPanel.qml` — no new import needed. The line always renders in
`Color.accent` (this chart is squarely part of the "keyboard-forward
signal" language the accent already carries elsewhere — WPM trend feeds
the same "am I improving at the keyboard-driven workflow" question). The
trailing dot marks the most recent day so the line has a clear "you are
here" endpoint, the same role the "last burst" caption plays next to the
hero number. Width spans the *full* content width (continuous line, no
per-day cells) — unlike the discrete bar chart below, there is no
minimum-legible-cell-width constraint to respect here.

#### 2.3.2 Keyboard/mouse split + 14-day trend

**Eyebrow**: `"KEYBOARD VS MOUSE"` (per 2.3.0), directly above the split
block below — replaces this block's previous bare `topPadding: Style.space(6)`
start (the eyebrow now supplies that top spacing).

**Keyboard/mouse split bar** — the one genuinely novel component. Exact
geometry:

```
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
      text: "⌨ " + Math.round(root.navKeyboardPct !== null ? root.navKeyboardPct : 0) + "%"
      visible: root.navKeyboardPct !== null
      color: Color.accent
      font.bold: true
      font.family: root.bar ? root.bar.fontFamily : Style.font.family
      font.pixelSize: Style.font.title
    }
    Text {
      anchors.right: parent.right
      text: (root.navKeyboardPct !== null ? Math.round(100 - root.navKeyboardPct) : 0) + "% 🖱"
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
```

The two inner `Rectangle`s are plain (not individually rounded) — the
container's `radius: height/2` + `clip: true` gives the pill shape, matching
how `PanelSlider.qml`'s track/fill pair is built. Keyboard segment is always
`Color.accent` (the one claimed accent use in this panel besides the window
pill and record values); mouse segment is `root.barForeground` at 28% alpha
— deliberately desaturated/neutral, not a second competing hue, so the bar
reads as "how much of this is the good/keyboard color" rather than a
two-way competition. When `navKeyboardPct` is `null` (has typing/cheatsheet
data but zero nav events yet), hide the bar and headline percentages, show
the "No navigation recorded yet" text instead — do not render a 0-width or
50/50 bar, which would misstate a state with no measurement.

**14-day keyboard trend** (new — the bar chart; sits directly under the
split bar so today's snapshot and its recent trend read as one group),
`visible: Fmt.keyboardTrendBars(root.history).length > 0`:

```
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

        // no navigation recorded that day: a short flat "no data" tick,
        // never a 0% or interpolated bar
        Rectangle {
          visible: modelData.kbFrac === null
          anchors.horizontalCenter: parent.horizontalCenter
          anchors.verticalCenter: parent.verticalCenter
          width: parent.width - Style.space(4)
          height: Style.space(2)
          radius: height / 2
          color: Util.alpha(root.barForeground, 0.15)
        }

        // data day: full-height composition fill, bottom-up, mirroring
        // the live split bar's two-segment language
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
```

`_shortDay` is exported from `StatsFormat.js` already (used by
`recordCards`); reuse it rather than duplicating date formatting. Cell
geometry is fixed (`Style.space(12)` wide, `Style.space(4)` gaps): 14 cells
= `14×12 + 13×4 = 220` space-units, comfortably under the ~272px usable
content width, deliberately **not** stretched to fill the row — a
day-cell has a minimum legible width, and stretching 14 cells across 272px
would make each day's composition harder to read, not easier. This is why
the bar row and the sparkline above it end up different widths: the
sparkline is continuous (no per-day cells to keep legible) while this
chart is discrete (14 fixed-width days), and forcing them to visually
align would be optimizing for symmetry over the readability of either
chart.

**Cheatsheet line + trend arrow** (2.3.3 — small, secondary, not a hero;
the base line is unchanged plain text, with a short trend caption appended
only when `cheatsheetTrend` has enough signal to say something; no eyebrow
title per 2.3's rationale — one sentence doesn't need a heading):

```
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
```

### 2.4 Records — "Best of the best" leaderboard card

`visible: root.connectedToDaemon && Fmt.recordCards(root.records).length > 0`
(unchanged visibility condition, just against the new structured helper):

```
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
```

Each record gets a filled row (`Style.normalFill`, `radius: Style.space(6)`)
instead of a bare bullet line — the "personal best" hook the README calls
out deserves to look like a small trophy card, not another sentence in the
same flat list as everything else. Value is bold + accent (same accent
language as the split bar's keyboard segment: "this number is the good
one"). No new interactivity — rows are inert, matching the plugin's
read-only nature.

## Summary of visible token usage

| Purpose | Token |
|---|---|
| Popup padding | `Style.spacing.popupPadding` (unchanged) |
| Section/row spacing | `Style.space(4..12)` per block above |
| Card/pill radius | `height / 2` (pills, split bar), `Style.space(6)` (record rows), `Style.space(4)` (code chip) |
| Card fill | `Style.normalFill` |
| Accent (keyboard signal) | `Color.accent` |
| Body text | `root.barForeground` |
| Muted/secondary text | `Util.alpha(root.barForeground, 0.55–0.7)` |
| Fonts | `Style.font.{caption,bodySmall,body,subtitle,title,displayLarge}` |
| Section eyebrow (new) | `Style.font.caption`, bold, `letterSpacing: 1`, `Util.alpha(root.barForeground, 0.55)` — reuses the window pill's typography |
| Sparkline stroke/dot (new) | `Color.accent`, `Style.space(2)` line width and dot radius |
| Trend-bar cell (new) | `Style.space(12)` wide × `Style.space(28)` tall, `Style.space(2)` radius, `Style.space(4)` gap; fill same accent/muted pair as the live split bar |

## Explicitly out of scope

- No dial/gauge (à la `SpeedTestOverlay`'s `SpeedDial`) — the popup card is
  ~272px of usable width after padding, far short of a 210px dial's comfort
  zone, and a big clean number reads faster at this size anyway.
- No new interactive controls (no in-panel window switcher, no
  click-to-cycle) — `window` is a settings-only field today; adding
  panel-side switching is a scope change to `manifest.json`'s schema and
  `BarWidget.qml`'s settings plumbing, not a visualization change.
- `BarWidget.qml`'s `WidgetButton` usage is unchanged — do not swap to
  `BarIconButton`/`OpticalGlyph`.
- No full chart for SUPER+K cheatsheet usage — a trend arrow + before/after
  count (2.3.3) carries the same meaning without a third chart's worth of
  visual weight; see the "Revision — trends, titles, minimalism" rationale
  above.
- No daily nav-volume chart (total keyboard+mouse events/day) — volume
  isn't an adoption signal; the composition chart (2.3.2) already isolates
  the axis that matters.
- No separate daily burst-count chart — the records leaderboard (2.4)
  already surfaces the relevant extreme ("busiest keystroke day"); a
  fourth chart over the same underlying activity wouldn't add a new
  question answered.
- No user-configurable trend window — the 14-day history request
  (`backend.requestHistory(14)`) is a fixed literal, not a setting;
  `manifest.json`'s schema is unchanged by this revision.
- No live-push updates for `history` — fetched once per panel open
  (`onOpenedChanged`), same cadence as `records`; unlike `stats`, the
  daemon does not re-push it on every flush.
- No chart/card treatment for records (2.4) — records are individual
  memorable events, not a series; charting one point per record would be
  exactly the "plain numbers wearing a shape" problem the feedback called
  out. They stay leaderboard cards, unchanged by this revision.

## App-launch: keybind vs. panel

New metric, spec-only addendum (companion to the "Revision — trends, titles,
minimalism" work above; same house style, same rigor). Answers a third
adoption question alongside "keyboard vs. mouse for navigation" and "typing
speed": **when the user opens an application, do they reach for a direct
keybind, or do they go through Omarchy's app panel (SUPER+SPACE / SUPER+ALT+
SPACE)?** A direct-bind habit is the deeper mastery signal this whole plugin
exists to encourage; the panel is the "still building muscle memory" path.
Same accent language applies: the keybind share is drawn in `Color.accent`
("the good direction"), the panel share in muted `barForeground` alpha —
identical grammar to the keyboard/mouse nav split, just a second axis.

### Ground truth this section is built on

Verified live on this machine (`hyprctl binds -j`) and against the installed
shell's own source, not assumed:

- Omarchy wraps every bind through a `__lua` dispatcher with an opaque
  `arg` handler index — same wrinkle `keybinds.py` already documents for
  nav. The only usable signal for a `__lua` bind is its human-readable
  `description`.
- App-launch binds are a long, open-ended, effectively-proper-noun list:
  `64 RETURN "Terminal"`, `65 RETURN "Browser"`, `65 F "File manager"`,
  `73 F "File manager (cwd)"`, `65 B "Browser"`, `73 B "Browser (private)"`,
  `65 N "Editor"`, `72 RETURN "Tmux"`, `68 RETURN "Herdr"`, `65 M "Music"`,
  `73 M "Music TUI"`, `65 D "Docker"`, `65 G "Signal"`, `65 O "Obsidian"`,
  `65 W "Omawrite"`, `65 SLASH "Passwords"`, `65 A "ChatGPT"`,
  `73 A "Grok"`, `65 C "Calendar"`, `65 E "Email"`, `73 E "New email"`,
  `65 Y "YouTube"`, `73 G "WhatsApp"`, `69 G "Google Messages"`,
  `65 P "Google Photos"`, `65 S "Google Maps"`, `65 X "X"`, `73 X "X Post"`.
  Unlike nav's fixed phrasing template ("Focus on left window"), these
  share no common sentence shape — they are literally the app's name — so
  a regex-pattern allowlist (nav's approach) doesn't apply; a **literal
  description allowlist** is the only workable signal (see decision 1).
- The two bar-real-estate app-entry points the user named are both real,
  distinct binds: `64 SPACE "Omarchy menu"` (SUPER+SPACE, a root menu —
  apps plus system actions like Lock/Power) and `72 SPACE "Apps menu"`
  (SUPER+ALT+SPACE, dedicated app launcher).
- Confirmed by reading `/usr/share/omarchy/shell/plugins/menu/Menu.qml`:
  Omarchy's app panel is a **Quickshell-native overlay**, not a separate
  Hyprland client window (no `walker`/`rofi`/`fuzzel` process, nothing in
  `hyprctl clients -j` for it). This matters directly for decision 2 below:
  there is no launcher window to filter out of `openwindow>>` correlation.
- `hypr_ipc.py`'s `_read_loop` already reads every socket2 line but only
  forwards `NAV_EVENT_PREFIXES` and `configreloaded>>`; `openwindow>>`
  lines (format `openwindow>>ADDRESS,WORKSPACE,CLASS,TITLE`) are read and
  silently dropped today. New plumbing is required to use them.

### Key design decisions

**1. Detection: a curated literal-description allowlist, not a pattern.**
Add `APP_LAUNCH_DESCRIPTIONS` (a `frozenset[str]`, exact strings from the
list above) and `PANEL_LAUNCH_DESCRIPTIONS = frozenset({"Omarchy menu",
"Apps menu"})` to `backend/keybinds.py`, parsed from live `hyprctl binds
-j` output exactly like `NAV_DESCRIPTION_PATTERNS` — same file, same
"live, not hardcoded modmask/key" philosophy, just literal-string matching
instead of regex (there is no shared phrase template to anchor a regex
to). Explicitly **not exhaustive by design**, mirroring `keybinds.py`'s own
docstring: this list is seeded from Omarchy's first-party default
`bindings.lua`, so a user's own custom app-launch bind in their personal
`~/.config/hypr/bindings.lua` is *not* tracked unless its description
happens to match one of these exact strings. A `__lua` bind whose
description matches neither `APP_LAUNCH_DESCRIPTIONS` nor
`PANEL_LAUNCH_DESCRIPTIONS` is simply never armed — it falls back to
unattributed, never guessed, same posture as nav. Utility/system-toggle
binds that also "open something" in a loose sense (Calculator, Weather,
Reminders, Screenshot, Background switcher, Theme menu, System menu,
Power menu, notification history, etc.) are **deliberately excluded** from
`APP_LAUNCH_DESCRIPTIONS` — this metric is about *applications*, not every
keybind that pops a window; drawing that line via a curated allowlist
(explicit inclusion) rather than a denylist (explicit exclusion) is safer
by construction, matching nav's existing allowlist philosophy: an
ambiguous new Omarchy bind added in a future release is unattributed by
default, not silently swept into either bucket.

**2. Attribution timing: correlate against a real `openwindow>>` event, not
the keypress alone.** Keypress-only counting is fine for the cheatsheet:
SUPER+K is a complete interaction -- the press itself renders the panel, so
the keypress *is* the invocation, counted straight off the evdev stream
against the live `hyprctl binds` allowlist (the cheatsheet's description
bucket). No Hyprland keybind is ever rewritten to do that. This does not
generalize to app launches, for two independent reasons, both decisive on
their own:
  - A bind wrapper that rewrites the tracked key doesn't scale: one wrapper
    per tracked app-launch bind (26+ binds, an open-ended, user-editable
    list) directly contradicts the "read live binds, don't hardcode a
    fixed script per key" philosophy this whole plugin already commits to
    for nav.
  - It cannot represent the panel bucket at all: pressing SUPER+SPACE or
    SUPER+ALT+SPACE only *opens the menu*. The actual launch happens an
    unbounded, variable number of seconds later, when the user picks an
    entry (mouse click or Enter after typing a filter) — an event this
    daemon has no keybind to intercept.

  Both problems point to the same fix: arm a channel on keypress, then
  wait for Hyprland's own `openwindow>>` event (fired only when a brand
  new top-level client is created — unlike `activewindow>>`, which also
  fires on ordinary focus switches between already-open windows) to
  confirm something was actually *launched*, not merely focused. This is
  strictly more honest than keypress-only counting: pressing an
  app-launch bind for an already-running app (which just focuses the
  existing window, no new client) correctly produces **no** count in
  either bucket — matching the metric's literal definition ("how many
  apps they *launch*"), and matching the existing "don't fabricate, hide
  rather than guess" posture applied elsewhere in this codebase. The
  trade-off: it needs new IPC plumbing (`hypr_ipc.py` forwarding
  `openwindow>>`) and a timing-correlation heuristic (§ below), with the
  same category of known/accepted imprecision `nav_attrib.py`'s docstring
  already documents for nav (an unrelated near-simultaneous window open
  can be misattributed) — an acceptable trade-off for a personal adoption
  metric, same standard this codebase already holds itself to.

**3. SUPER+SPACE and SUPER+ALT+SPACE: both included, one shared "panel"
bucket.** The user named both explicitly, so both are in scope per the
brief's own default. They are **not** split into two sub-buckets: there is
no meaningfully different user-facing story between "went through the root
menu" and "went through the dedicated launcher" — both represent "browsed
instead of using a direct shortcut," and a three-way keybind/root-menu/
apps-menu visualization would dilute the one binary story ("shortcut vs.
browse") this metric exists to tell, for no proportional payoff. The
concern that SUPER+SPACE is a *root* menu (Lock, Power, and other
non-app actions live there too, not just apps) is resolved by decision 2,
not by excluding the bind: picking "Lock screen" from that menu produces
no `openwindow>>` event, so it produces no panel-launch count at all —
the correlation step itself filters out the non-app-launch paths through
that menu, for free, without needing to special-case menu entries.

**4. Non-launch binds (nav, system toggles, unmatched `__lua` presses,
unmatched user binds) never arm either channel, ever.** They are simply
never fed to `note_keybind_press`/`note_panel_press` at all — not
misclassified, not counted as a third "other" bucket, not surfaced
anywhere. An `openwindow>>` event with no live armed channel (e.g. an app
spawns a second window on its own, or the user ran something from a
terminal, or clicked a dock/taskbar icon this plugin doesn't have) is
correctly attributed to neither bucket. Same "hide rather than fabricate"
posture as nav's unmatched combos.

### Backend data contract

#### `backend/keybinds.py`

Add the two new constants (exact set from "Ground truth" above):

```python
# Omarchy's first-party default app-launch bind descriptions (bindings.lua).
# Seeded from a live default install -- NOT exhaustive by design (a user's
# own custom app-launch bind in ~/.config/hypr/bindings.lua isn't tracked
# unless its description happens to match one of these exact strings). A
# __lua bind whose description matches neither this set nor
# PANEL_LAUNCH_DESCRIPTIONS is simply not allowlisted -- unattributed, not
# guessed, same posture as NAV_DESCRIPTION_PATTERNS above.
APP_LAUNCH_DESCRIPTIONS = frozenset({
    "Terminal", "Browser", "Browser (private)", "File manager",
    "File manager (cwd)", "Editor", "Tmux", "Herdr", "Music", "Music TUI",
    "Docker", "Signal", "Obsidian", "Omawrite", "Passwords", "ChatGPT",
    "Grok", "Calendar", "Email", "New email", "YouTube", "WhatsApp",
    "Google Messages", "Google Photos", "Google Maps", "X", "X Post",
})

# Omarchy's app-entry-point menu binds. Both included in one shared
# "panel" bucket -- see DESIGN.md "App-launch: keybind vs. panel", decision
# 3, for why SUPER+SPACE (a root menu, not exclusively an app launcher) is
# still included rather than excluded or split out.
PANEL_LAUNCH_DESCRIPTIONS = frozenset({"Omarchy menu", "Apps menu"})
```

Extend `parse_binds_json` to compute all three allowlists in the same
single pass over the JSON it already parses, returning a dict instead of a
bare set:

```python
def parse_binds_json(raw: str) -> dict[str, set[tuple[int, str]]]:
    """Returns {"nav": ..., "app_launch": ..., "panel_launch": ...}, each a
    set of (modmask, KEY) pairs. Breaking return-type change from the
    previous bare-set return -- update callers (daemon.py) and
    tests/test_keybinds.py accordingly."""
    result = {"nav": set(), "app_launch": set(), "panel_launch": set()}
    try:
        binds = json.loads(raw)
    except json.JSONDecodeError:
        return result
    if not isinstance(binds, list):
        return result

    keyless_workspace_binds: list[tuple[int, int]] = []
    for bind in binds:
        if not isinstance(bind, dict):
            continue
        dispatcher = str(bind.get("dispatcher", ""))
        key = str(bind.get("key", "")).strip()
        description = str(bind.get("description") or "").strip()
        try:
            modmask = int(bind.get("modmask", 0))
        except (TypeError, ValueError):
            modmask = 0
        if modmask == 0:
            continue

        if not key:
            if dispatcher == LUA_DISPATCHER and modmask and \
                    (match := _workspace_number(description)):
                keyless_workspace_binds.append((modmask, match))
            continue

        combo = (modmask, key.upper())
        if dispatcher in NAV_DISPATCHERS:
            result["nav"].add(combo)
        elif dispatcher == LUA_DISPATCHER and _is_nav_description(description):
            result["nav"].add(combo)
        elif dispatcher == LUA_DISPATCHER and description in APP_LAUNCH_DESCRIPTIONS:
            result["app_launch"].add(combo)
        elif dispatcher == LUA_DISPATCHER and description in PANEL_LAUNCH_DESCRIPTIONS:
            result["panel_launch"].add(combo)
        # first match wins, checked nav -> app_launch -> panel_launch;
        # defensive only -- the three sources are disjoint by construction.

    for modmask, workspace in keyless_workspace_binds:
        result["nav"].add((modmask, str(workspace % 10)))
    return result
```

Rename `fetch_nav_allowlist()` to `fetch_keybind_allowlists()` (same body,
just returns `parse_binds_json`'s dict directly) — the old name no longer
describes what it fetches.

Extend `NavComboMatcher` with two more allowlists and matcher methods,
reusing its existing shared modifier-state tracking rather than
duplicating it in a second class instance:

```python
class NavComboMatcher:
    def __init__(self) -> None:
        self._allowlist: set[tuple[int, str]] = set()
        self._app_launch_allowlist: set[tuple[int, str]] = set()
        self._panel_launch_allowlist: set[tuple[int, str]] = set()
        # ... existing _held_* fields unchanged ...

    def update_app_launch_allowlist(self, allowlist: set[tuple[int, str]]) -> None:
        self._app_launch_allowlist = {(mask, key.upper()) for mask, key in allowlist}

    def update_panel_launch_allowlist(self, allowlist: set[tuple[int, str]]) -> None:
        self._panel_launch_allowlist = {(mask, key.upper()) for mask, key in allowlist}

    def matches_app_launch(self, code: int) -> bool:
        return self._matches_against(self._app_launch_allowlist, code)

    def matches_panel_launch(self, code: int) -> bool:
        return self._matches_against(self._panel_launch_allowlist, code)

    def _matches_against(self, allowlist: set[tuple[int, str]], code: int) -> bool:
        modmask = self.current_modmask
        if modmask == 0:
            return False
        name = EVDEV_TO_HYPR_KEYNAME.get(code)
        if name is None:
            return False
        return (modmask, name) in allowlist
```

(Refactor the existing `matches()` to also call `_matches_against(self._allowlist,
code)` — same behavior, less duplication.) Update the class's module
docstring to note it now serves three purposes (nav / app-launch / panel-
launch detection), not just nav. Class name kept as `NavComboMatcher` to
minimize diff size — a rename is not required for this addendum.

#### `backend/hypr_ipc.py`

Add a fourth event channel. `openwindow>>` carries window class/title in
its payload, but this daemon **deliberately never parses that** — parsing
only "did this line arrive," never its contents, extends the existing "no
raw content, only aggregates" privacy stance to app identity too (see
"Considered and rejected" below):

```python
OPENWINDOW_EVENT_PREFIX = "openwindow>>"
```

`HyprSocketClient.__init__` gains a new required callback:

```python
def __init__(self, on_nav_event, on_config_reloaded, on_openwindow_event):
    ...
    self._on_openwindow_event = on_openwindow_event
```

`_read_loop` gains one more branch (order matters only for readability;
`openwindow>>` and `NAV_EVENT_PREFIXES` never overlap):

```python
if text.startswith(NAV_EVENT_PREFIXES):
    self._on_nav_event()
elif text.startswith(OPENWINDOW_EVENT_PREFIX):
    self._on_openwindow_event()
elif text.startswith("configreloaded>>"):
    await self._invoke_config_reloaded()
```

#### New file `backend/app_launch_attrib.py`

Mirrors `nav_attrib.py`'s structure, constants-as-tunables, and docstring
conventions. No `EpisodeCoalescer` equivalent is needed: nav needed one
because `activewindow>>`/`workspace>>` fire *together* for one user
action and must be merged before attribution; here there is exactly one
event type (`openwindow>>`), and single-shot arm consumption (an arm is
cleared the instant it's used to attribute one event) already stops a
second, near-simultaneous `openwindow>>` from the same app's own startup
(e.g. a splash window plus a main window) from being double-counted — the
second one simply finds no live armed channel and is correctly
unattributed.

```python
"""Keybind-vs-panel attribution for app launches, correlated against
Hyprland's own openwindow>> event.

Not an Omarchy-documented convention -- our own timing-correlation
heuristic, same category as nav_attrib.py's NavAttributor. Only ever
timestamps are tracked in memory; window class/title from the triggering
openwindow>> line is never read, let alone stored.

Known limitation (documented, not fixed): an openwindow>> that fires for
an unrelated reason while a channel is still armed (e.g. a notification's
own window, or a second app the user manually started from a terminal
during the panel's long arm window) can be misattributed. This is
inherent to timing correlation without dispatcher-identity ground truth,
same accepted trade-off nav_attrib.py already documents for a personal
adoption metric.
"""

from __future__ import annotations

# An app-launch keybind press is usually followed within a couple of
# seconds by its window appearing; bounded generously for slow-starting
# apps (Docker Desktop, Obsidian cold start) without risking correlation
# with a much later, unrelated launch.
KEYBIND_ARM_WINDOW_S = 3.0

# The panel bind only opens the menu -- the actual launch (click or Enter
# after typing a filter) can be many seconds later. Bounded generously so
# "still browsing the menu" stays armed, but finite so a stale arm can't
# attribute an unrelated launch minutes later.
PANEL_ARM_WINDOW_S = 12.0


class AppLaunchAttributor:
    """Attributes an openwindow>> event to 'keybind', 'panel', or None."""

    def __init__(self,
                 keybind_window_s: float = KEYBIND_ARM_WINDOW_S,
                 panel_window_s: float = PANEL_ARM_WINDOW_S):
        self._keybind_window = keybind_window_s
        self._panel_window = panel_window_s
        self._keybind_armed_ts: float | None = None
        self._panel_armed_ts: float | None = None

    def note_keybind_press(self, monotonic_ts: float) -> None:
        """Call only when the keydown's (modmask, key) matches
        keybinds.py's live app_launch allowlist."""
        self._keybind_armed_ts = monotonic_ts

    def note_panel_press(self, monotonic_ts: float) -> None:
        """Call only when the keydown's (modmask, key) matches keybinds.py's
        live panel_launch allowlist (SUPER+SPACE / SUPER+ALT+SPACE)."""
        self._panel_armed_ts = monotonic_ts

    def on_openwindow(self, monotonic_ts: float) -> str | None:
        keybind_ok = self._within_window(
            self._keybind_armed_ts, monotonic_ts, self._keybind_window)
        panel_ok = self._within_window(
            self._panel_armed_ts, monotonic_ts, self._panel_window)

        if keybind_ok and panel_ok:
            # Most-recent-arm-wins, same tie-break NavAttributor uses for
            # simultaneous keyboard/mouse signals.
            winner = ("keybind" if self._keybind_armed_ts > self._panel_armed_ts
                      else "panel")
        elif keybind_ok:
            winner = "keybind"
        elif panel_ok:
            winner = "panel"
        else:
            return None

        # Single-shot consumption: clear the arm that was just used so a
        # second, closely-following openwindow>> (e.g. a second window
        # from the same app's own startup) isn't double-counted.
        if winner == "keybind":
            self._keybind_armed_ts = None
        else:
            self._panel_armed_ts = None
        return winner

    @staticmethod
    def _within_window(armed_ts: float | None, now_ts: float, window_s: float) -> bool:
        if armed_ts is None:
            return False
        delta = now_ts - armed_ts
        return 0 <= delta <= window_s
```

#### `backend/evdev_reader.py`

`EvdevSource.__init__` gains two more required callbacks, alongside the
existing `on_mouse_activity`/`on_keyboard_nav_combo`:

```python
def __init__(self, nav_matcher, on_typing_burst, on_mouse_activity,
             on_keyboard_nav_combo, on_app_launch_keybind_combo,
             on_panel_launch_combo):
    ...
    self._on_app_launch_keybind_combo = on_app_launch_keybind_combo
    self._on_panel_launch_combo = on_panel_launch_combo
```

`_handle_key`, immediately alongside the existing nav-combo check
(independent `if`s, not `elif` -- defensively correct even though the
three allowlists are disjoint by construction):

```python
if value == 1 and not is_modifier:
    if self._nav_matcher.matches(code):
        self._on_keyboard_nav_combo(now)
    if self._nav_matcher.matches_app_launch(code):
        self._on_app_launch_keybind_combo(now)
    if self._nav_matcher.matches_panel_launch(code):
        self._on_panel_launch_combo(now)
```

#### `backend/storage.py`

New table, added via the existing idempotent `_SCHEMA` script (a *new*
table needs no migration):

```sql
CREATE TABLE IF NOT EXISTS app_launch_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    occurred_at INTEGER NOT NULL,
    method TEXT NOT NULL CHECK (method IN ('keybind','panel'))
);
CREATE INDEX IF NOT EXISTS idx_app_launch_events_occurred_at ON app_launch_events(occurred_at);
```

`daily_rollup` needs two new columns on an **existing** table, which
`CREATE TABLE IF NOT EXISTS` cannot add for installs upgrading from a
pre-addendum database — this needs an explicit, idempotent migration.
Add a `_migrate_schema()` method, called once from `__init__` right after
`executescript(_SCHEMA)`:

```python
def _migrate_schema(self) -> None:
    existing = {row[1] for row in
                self._conn.execute("PRAGMA table_info(daily_rollup)")}
    for column in ("app_launch_keybind_count", "app_launch_panel_count"):
        if column not in existing:
            self._conn.execute(
                f"ALTER TABLE daily_rollup ADD COLUMN {column} "
                f"INTEGER NOT NULL DEFAULT 0")
```

`_PendingWrites` gains `app_launch_events: list = field(default_factory=list)`;
`queue_app_launch_event(method, occurred_at)` mirrors `queue_nav_event`
exactly; `has_pending()`/`flush()` include it (insert into
`app_launch_events`, add `_day_key(occurred_at)` to `touched_days`, same
pattern as `nav_events`).

`_recompute_rollup(day)` gains two more `SELECT COUNT(*)` queries
(`method = 'keybind'` / `method = 'panel'` against `app_launch_events`,
same bounds as the existing nav queries) and includes both counts in the
`INSERT ... ON CONFLICT DO UPDATE` for `daily_rollup`.

`get_stats(window)` gains three fields, same shape as the nav split (no
`mouse_weight`-style calibration knob -- see "Considered and rejected"):

```python
app_launch_keybind, app_launch_panel = self._conn.execute(
    f"SELECT COALESCE(SUM(app_launch_keybind_count),0), "
    f"COALESCE(SUM(app_launch_panel_count),0) FROM daily_rollup "
    f"WHERE day IN ({placeholders})", days_or_all_clause).fetchone()
...
applaunch_denom = app_launch_keybind + app_launch_panel
return {
    ...,  # existing fields unchanged
    "app_launch_keybind": app_launch_keybind,
    "app_launch_panel": app_launch_panel,
    "app_launch_keybind_pct":
        round(100 * app_launch_keybind / applaunch_denom, 1) if applaunch_denom else None,
}
```

(Same pattern for both the `window == "all"` branch and the day-list
branch, mirroring how `nav_kb`/`nav_mouse` are already summed in both
branches.) `has_data` gains this metric to its `bool(...)` check:
`bool(burst_count or nav_total or cheatsheet_count or applaunch_denom)`.

`get_daily_history(days)` gains the same three fields per series entry
(query `daily_rollup`'s two new columns alongside the existing ones;
`None`/zeroed for a day with no `daily_rollup` row, exactly like every
other field in that method).

`get_records()` gains one new record, same shape and gating philosophy as
`best_keyboard_day` (a minimum daily volume so a 1-launch day can't top
the board by luck; the threshold is lower than nav's `RECORD_MIN_NAV_DAY
= 20` because app launches per day are naturally far fewer than nav
events):

```python
RECORD_MIN_APPLAUNCH_DAY = 5  # alongside RECORD_MIN_NAV_DAY

row = self._conn.execute(
    "SELECT day, app_launch_keybind_count, app_launch_panel_count FROM daily_rollup "
    "WHERE app_launch_keybind_count + app_launch_panel_count >= ? "
    "ORDER BY CAST(app_launch_keybind_count AS REAL) / "
    "(app_launch_keybind_count + app_launch_panel_count) DESC LIMIT 1",
    (RECORD_MIN_APPLAUNCH_DAY,)).fetchone()
if row:
    day, kb, panel = row
    records["best_keybind_launch_day"] = {
        "value": round(100 * kb / (kb + panel), 1), "day": day}
```

#### `backend/daemon.py`

```python
from app_launch_attrib import AppLaunchAttributor
from keybinds import NavComboMatcher, fetch_keybind_allowlists  # renamed import
```

`Daemon.__init__`:

```python
self.app_launch_attributor = AppLaunchAttributor()
self.evdev_source = EvdevSource(
    self.nav_matcher,
    on_typing_burst=self._on_typing_burst,
    on_mouse_activity=self.attributor.note_mouse_activity,
    on_keyboard_nav_combo=self.attributor.note_keyboard_nav_combo,
    on_app_launch_keybind_combo=self.app_launch_attributor.note_keybind_press,
    on_panel_launch_combo=self.app_launch_attributor.note_panel_press,
)
self.hypr_client = HyprSocketClient(
    on_nav_event=self._on_nav_event,
    on_config_reloaded=self._refresh_allowlist,
    on_openwindow_event=self._on_openwindow_event,
)
```

New handler, alongside `_on_nav_event`:

```python
def _on_openwindow_event(self) -> None:
    method = self.app_launch_attributor.on_openwindow(time.monotonic())
    if method is not None:
        self.storage.queue_app_launch_event(method, time.time())
```

`_refresh_allowlist` now fetches and distributes all three allowlists in
one `hyprctl binds -j` call (no extra subprocess spawn per config reload):

```python
async def _refresh_allowlist(self) -> None:
    try:
        allowlists = await fetch_keybind_allowlists()
        self.nav_matcher.update_allowlist(allowlists["nav"])
        self.nav_matcher.update_app_launch_allowlist(allowlists["app_launch"])
        self.nav_matcher.update_panel_launch_allowlist(allowlists["panel_launch"])
    except OSError:
        pass
```

No `protocol.py` change, and no new daemon command: `stats`, `history`,
and `records` already return `self.storage.get_stats/get_daily_history/
get_records()`'s full dict verbatim, so the new fields ride along
automatically once `storage.py` produces them — exactly how the existing
`history` command needed no protocol changes when it was added.

### Frontend wiring

#### `BackendClient.qml`

No changes needed — `lastStats`/`lastRecords`/`lastHistory` already carry
whatever the daemon returns; the new fields arrive automatically.

#### `BarWidget.qml`

Add three read-through properties alongside the existing `nav*`/`cheatsheetCount`
ones:

```qml
readonly property int appLaunchKeybindCount: stats ? Number(stats.app_launch_keybind || 0) : 0
readonly property int appLaunchPanelCount: stats ? Number(stats.app_launch_panel || 0) : 0
readonly property var appLaunchKeybindPct: stats ? stats.app_launch_keybind_pct : null
```

Pass through to the `StatsPanel` instantiation:

```qml
appLaunchKeybindCount: root.appLaunchKeybindCount
appLaunchPanelCount: root.appLaunchPanelCount
appLaunchKeybindPct: root.appLaunchKeybindPct
```

`compactLabel`/`formatCompactLabel` are **unchanged** — see "Bar-strip
label" below for why this metric does not appear there.

#### `StatsPanel.qml`

Add matching properties: `property int appLaunchKeybindCount: 0`,
`property int appLaunchPanelCount: 0`, `property var appLaunchKeybindPct: null`.
New section markup in § "2.3 State: connected, has data" below.

#### `StatsFormat.js` additions

```js
function formatAppLaunchCaption(keybindCount, panelCount) {
  var total = (keybindCount || 0) + (panelCount || 0)
  if (total === 0) return "No app launches recorded yet"
  return (keybindCount || 0) + " via keybind · " + (panelCount || 0) + " via panel"
}

function appLaunchTrend(history) {
  var series = historySeries(history)
  if (series.length < 4) return null

  var mid = Math.floor(series.length / 2)
  var older = series.slice(0, mid)
  var recent = series.slice(mid)

  function halfPct(half) {
    var kb = 0, total = 0
    for (var i = 0; i < half.length; i++) {
      kb += (half[i].app_launch_keybind || 0)
      total += (half[i].app_launch_keybind || 0) + (half[i].app_launch_panel || 0)
    }
    return total > 0 ? (100 * kb / total) : null
  }

  var olderPct = halfPct(older)
  var recentPct = halfPct(recent)
  if (olderPct === null || recentPct === null) return null

  var delta = recentPct - olderPct
  var direction = "flat"
  if (delta >= 5) direction = "up"
  else if (delta <= -5) direction = "down"
  return { direction: direction, olderPct: olderPct, recentPct: recentPct }
}

function formatAppLaunchTrendCaption(trend) {
  if (trend === null || trend === undefined) return ""
  var o = Math.round(trend.olderPct), r = Math.round(trend.recentPct)
  if (trend.direction === "up") return "↑ leaning on shortcuts more (" + o + "% → " + r + "%)"
  if (trend.direction === "down") return "↓ leaning on shortcuts less (" + o + "% → " + r + "%)"
  return "steady (~" + r + "% via shortcut)"
}
```

`appLaunchTrend` compares **percentage-point share**, not raw volume
(unlike `cheatsheetTrend`, which compares raw counts) — deliberately
different from the cheatsheet pattern: raw app-launch volume going up
just means "launched more apps today," which says nothing about
*adoption*; the keybind *share* of that volume is the actual signal. A
fixed 5-percentage-point threshold (rather than `cheatsheetTrend`'s
relative-ratio threshold) is the cleaner "meaningfully different" bar for
an already-bounded 0–100 quantity, consistent with how the live split
bar's own headline already reports whole percentage points.

`recordCards(records)` gains a fourth entry, appended after
`best_keyboard_day`:

```js
if (records.best_keybind_launch_day) {
  cards.push({
    icon: "🎯",
    label: "Most keybind-driven launch day",
    value: Math.round(records.best_keybind_launch_day.value) + "% via keybind",
    day: _shortDay(records.best_keybind_launch_day.day),
  })
}
```

### Bar-strip label — unchanged

Applying the same "does this clear the bar" scrutiny already used to drop
cheatsheet count from `formatCompactLabel` (§1 above): **no.** This
metric does not appear in the bar-strip label. The label already carries
two hero numbers (`⌨68% · 74wpm`) and is already the longest string on
most bars; a third fraction would either force truncation or crowd out
the two metrics this plugin is actually *for* (keyboard-vs-mouse nav,
typing speed). App-launch keybind-share is thematically adjacent to the
nav split but is a distinctly secondary signal — same tier as cheatsheet
count, which was already excluded for exactly this reason. It shows only
in the panel. See "Considered and rejected" for the specific alternative
layouts rejected here.

### 2.3.4 `StatsPanel.qml` — new panel section: "App launches"

Inserted after the existing 2.3.3 cheatsheet block, before 2.4 Records —
last item inside the "connected, has data" `Column`. Deliberately scaled
**down** from the hero split bar (2.3.2), not a duplicate of it: this is
a secondary metric (same tier as the cheatsheet line), so it gets a
compact mini split-bar plus a one-line trend caption, not a second
14-day bar chart — reusing the "hero gets the full chart budget, secondary
metrics get a cheap trend line" rule the "trends, titles, minimalism"
revision already established for the cheatsheet line, rather than
reopening that budget for a third chart.

**Eyebrow**: `"APP LAUNCHES"` (per 2.3.0's convention).

**Mini split-bar** (a smaller sibling of 2.3.2's split bar, not the same
component reused verbatim — the size difference itself communicates
"this one's secondary"). Exact geometry:

```qml
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
```

Geometry deltas from 2.3.2's hero split bar, precisely: headline text
`Style.font.bodySmall` (not `Style.font.title`), track height
`Style.space(8)` (not `Style.space(14)`), no 14-day trend chart under it
(one trend-caption `Text` instead). Track radius stays `height / 2`; fill
colors are identical to 2.3.2's (`Color.accent` / `Util.alpha(root.barForeground,
0.28)`) — same "accent = the good direction" grammar, deliberately not a
new hue, so a third color doesn't compete for attention. Labels are plain
words ("Keybind" / "Panel"), not the ⌨/🖱 glyphs 2.3.2 uses — those glyphs
represent input *devices* (a mouse click vs. a keystroke); this axis is a
*workflow path* (direct shortcut vs. browsing a menu), and either could in
principle be operated via keyboard-only interaction with the panel menu
itself, so reusing the device glyphs here would misrepresent what's being
measured. `appLaunchKeybindPct === null` (has other data but zero
attributed app-launch events yet) hides the bar and shows "No app
launches recorded yet" centered — same null-handling rule as 2.3.2, never
a fabricated 0-width or 50/50 bar.

### Records — leaderboard extension

No new component: `Fmt.recordCards(root.records)` already drives 2.4's
`Repeater` over the existing card `Rectangle`; the fourth card (🎯 "Most
keybind-driven launch day") slots in automatically once `recordCards`
returns it. No QML changes to 2.4 itself.

### Considered and rejected

- **Keypress-only, fire-and-forget attribution of app launches** —
  rejected; see decision 2 above. It only makes sense for interactions
  where the keypress *is* the tracked act (the cheatsheet, whose press
  renders the panel). For app launches the tracked event arrives after the
  keypress (a new client), and a per-key bind wrapper doesn't scale, so
  the panel bucket can't be represented that way at all.
- **Splitting SUPER+SPACE and SUPER+ALT+SPACE into two panel sub-
  buckets** — rejected; see decision 3. No distinct user-facing story,
  and a three-way split dilutes the one binary axis this metric answers.
- **A `mouse_weight`-style calibration knob for keybind vs. panel** —
  rejected. `mouse_weight` exists because "how much a mouse click should
  count against keyboard-first workflow" is a genuinely subjective
  calibration (README's own framing: some people navigate mostly by
  scroll wheel and don't want it to dominate). There's no analogous
  subjective judgment here: a keybind press either preceded the launch or
  it didn't. Weighting it would misrepresent an observed fact as an
  opinion, so raw unweighted percentage is the only correct treatment.
- **Per-app breakdown (which apps get launched via keybind vs. panel)** —
  rejected on privacy grounds, deliberately, even though `openwindow>>`'s
  payload carries window class/title for free. This plugin's stated
  privacy stance is "no raw content, only aggregates"; extending that
  posture to "no app identity either" keeps this metric in the same
  spirit as the rest of the plugin — an adoption *signal*, not an
  activity log of what was opened and when.
- **A second full 14-day bar chart for app launches (mirroring 2.3.2's
  keyboard-adoption chart)** — rejected. App-launch counts per day are
  low and bursty (a handful of launches, not the dozens-to-hundreds of nav
  events the existing chart aggregates), so 14 mostly-thin/near-empty
  bars would be visual noise, not insight — the same "does this clear the
  bar" test the "trends, titles, minimalism" revision already applied to
  reject a cheatsheet chart for the identical reason. The two-chart
  budget (sparkline + bar chart) established by that revision belongs to
  the two hero metrics (WPM, keyboard/mouse nav); this addendum doesn't
  reopen it. A mini split-bar (today's snapshot) plus a one-line trend
  caption is the proportionate treatment for a secondary metric.
- **Bar-strip inclusion, either as a third fraction or a compact glyph
  (e.g. `🎯62%`)** — rejected; see "Bar-strip label" above. Crowds the two
  hero numbers for a tertiary signal.
- **Correlating against `activewindow>>`/`activewindowv2>>` instead of
  `openwindow>>`** — rejected. Those events also fire on ordinary focus
  switches between already-open windows (that's precisely what nav
  attribution already uses them for), so they can't distinguish "a new
  app was actually launched" from "an existing window was focused."
  `openwindow>>` fires only when Hyprland creates a genuinely new
  top-level client — the one event that actually means "launch."
- **A generic "other/unattributed" third bucket surfaced in the UI** —
  rejected. Unmatched presses and unmatched `openwindow>>` events stay
  invisible, exactly like nav's unmatched combos — "hide rather than
  fabricate," not "show a bucket for everything we're unsure about."
- **Reusing the ⌨/🖱 glyphs from the nav split for this section's
  headline** — rejected; see 2.3.4's geometry notes. Those glyphs name
  input *devices*; this metric measures a *workflow path*, and reusing
  device glyphs here would misrepresent what's being counted (the panel
  can itself be operated entirely from the keyboard).

### Explicitly out of scope

- No per-app identity or breakdown, anywhere (privacy; see "Considered
  and rejected").
- No user-configurable `KEYBIND_ARM_WINDOW_S` / `PANEL_ARM_WINDOW_S` —
  fixed constants in `app_launch_attrib.py`, not exposed via
  `set_mouse_weight`-style commands or `manifest.json` schema.
- No calibration weight for this split (see "Considered and rejected").
- No bar-strip label change of any kind for this metric.
- No splitting the panel bucket by which bind (SUPER+SPACE vs. SUPER+
  ALT+SPACE) was pressed.
- No new `manifest.json` schema field — this addendum needs no new
  per-widget setting.
- No `README.md` edits performed as part of this design addendum — the
  README's "How it works," "Calibration," and "Stats windows & records"
  sections should gain a paragraph describing this metric as a follow-up
  once the dev agent implements it, but authoring that text is not part
  of this spec-only pass.
- No historical backfill for pre-upgrade installs — a database created
  before this addendum simply has zero `app_launch_events` rows for past
  days; the mini split-bar and trend caption show "no data" until new
  tracking accumulates, exactly how any other new metric's rollout is
  already handled elsewhere in this codebase (missing `daily_rollup` rows
  already come back null/zeroed, never fabricated).
- No live-push update specifically for this metric beyond what `stats`
  already does — `app_launch_keybind`/`app_launch_panel`/
  `app_launch_keybind_pct` ride along in the existing `stats_update` push
  and `history`/`records` fetch-once-per-open pattern; no new push
  cadence is introduced.

### Token usage — addendum

| Purpose | Token |
|---|---|
| Mini split-bar track height | `Style.space(8)` (vs. `Style.space(14)` for the hero split bar) |
| Mini split-bar headline text | `Style.font.bodySmall` (vs. `Style.font.title` for the hero split bar) |
| Mini split-bar fill colors | Same as 2.3.2: `Color.accent` (keybind) / `Util.alpha(root.barForeground, 0.28)` (panel) |
| Mini split-bar radius | `height / 2`, same grammar as every other pill/track in this panel |
| New record icon | `🎯` — distinct from the three already claimed (`⚡`,`🔥`,`⌨`) |
| Trend caption | `Style.font.caption`, `Util.alpha(root.barForeground, 0.5)` — identical treatment to the cheatsheet trend caption (2.3.3) |
