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
