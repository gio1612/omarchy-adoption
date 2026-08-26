"""SQLite storage for the Omarchy Adoption Tracker daemon.

Not an Omarchy-documented convention -- our own schema. Only ever stores
derived aggregates (WPM values, event-type counts, timestamps); raw keycodes
or content are never written here.
"""

from __future__ import annotations

import sqlite3
import time
from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone

SCHEMA_VERSION = 1
DEFAULT_RETENTION_DAYS = 90
# Calibration knob for the keyboard/mouse split: each mouse nav event counts
# as `mouse_weight` keyboard events when computing nav_keyboard_pct. 1.0 =
# raw counts; >1 treats a mouse action as a bigger "keyboard avoidance";
# <1 discounts mouse actions.
DEFAULT_MOUSE_WEIGHT = 1.0
MOUSE_WEIGHT_MIN, MOUSE_WEIGHT_MAX = 0.1, 10.0
# A day needs at least this many raw nav events before its keyboard split can
# become the "best keyboard day" record -- otherwise a 2-event day tops the
# board by luck.
RECORD_MIN_NAV_DAY = 20

_SCHEMA = """
CREATE TABLE IF NOT EXISTS typing_bursts (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    ended_at INTEGER NOT NULL,
    duration_ms INTEGER NOT NULL,
    keystroke_count INTEGER NOT NULL,
    wpm REAL NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_typing_bursts_ended_at ON typing_bursts(ended_at);

CREATE TABLE IF NOT EXISTS nav_events (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    occurred_at INTEGER NOT NULL,
    method TEXT NOT NULL CHECK (method IN ('keyboard','mouse'))
);
CREATE INDEX IF NOT EXISTS idx_nav_events_occurred_at ON nav_events(occurred_at);

CREATE TABLE IF NOT EXISTS cheatsheet_invocations (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    occurred_at INTEGER NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_cheatsheet_occurred_at ON cheatsheet_invocations(occurred_at);

CREATE TABLE IF NOT EXISTS daily_rollup (
    day TEXT PRIMARY KEY,
    typing_burst_count INTEGER NOT NULL DEFAULT 0,
    typing_keystroke_total INTEGER NOT NULL DEFAULT 0,
    typing_wpm_avg REAL,
    typing_wpm_max REAL,
    nav_keyboard_count INTEGER NOT NULL DEFAULT 0,
    nav_mouse_count INTEGER NOT NULL DEFAULT 0,
    cheatsheet_count INTEGER NOT NULL DEFAULT 0,
    updated_at INTEGER NOT NULL
);

CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT
);
"""


def _day_key(wall_ts: float) -> str:
    return datetime.fromtimestamp(wall_ts, tz=timezone.utc).astimezone().strftime("%Y-%m-%d")


def _day_bounds(day: str) -> tuple[float, float]:
    """Local-midnight-to-local-midnight epoch bounds for a 'YYYY-MM-DD' day."""
    start = datetime.strptime(day, "%Y-%m-%d").astimezone().timestamp()
    return start, start + 86400


@dataclass
class _PendingWrites:
    typing_bursts: list = field(default_factory=list)
    nav_events: list = field(default_factory=list)
    cheatsheet_invocations: list = field(default_factory=list)


class Storage:
    def __init__(self, db_path: str):
        self._conn = sqlite3.connect(db_path, isolation_level=None)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._conn.execute("PRAGMA busy_timeout=2000")
        self._conn.executescript(_SCHEMA)
        self._ensure_meta("schema_version", str(SCHEMA_VERSION))
        self._ensure_meta("retention_days", str(DEFAULT_RETENTION_DAYS))
        self._ensure_meta("mouse_weight", str(DEFAULT_MOUSE_WEIGHT))
        self._pending = _PendingWrites()

    def close(self) -> None:
        self._conn.close()

    def _ensure_meta(self, key: str, default_value: str) -> None:
        cur = self._conn.execute("SELECT value FROM meta WHERE key = ?", (key,))
        if cur.fetchone() is None:
            self._conn.execute(
                "INSERT INTO meta(key, value) VALUES (?, ?)", (key, default_value))

    def retention_days(self) -> int:
        cur = self._conn.execute("SELECT value FROM meta WHERE key = 'retention_days'")
        row = cur.fetchone()
        return int(row[0]) if row else DEFAULT_RETENTION_DAYS

    def mouse_weight(self) -> float:
        """Calibration weight applied to mouse nav events in the split."""
        cur = self._conn.execute("SELECT value FROM meta WHERE key = 'mouse_weight'")
        row = cur.fetchone()
        try:
            weight = float(row[0]) if row else DEFAULT_MOUSE_WEIGHT
        except (TypeError, ValueError):
            weight = DEFAULT_MOUSE_WEIGHT
        return min(max(weight, MOUSE_WEIGHT_MIN), MOUSE_WEIGHT_MAX)

    def set_mouse_weight(self, weight: float) -> float:
        """Persist a new calibration weight; returns the clamped value used."""
        try:
            weight = float(weight)
        except (TypeError, ValueError):
            raise ValueError(f"mouse_weight must be a number, got {weight!r}")
        clamped = min(max(weight, MOUSE_WEIGHT_MIN), MOUSE_WEIGHT_MAX)
        self._conn.execute(
            "INSERT INTO meta(key, value) VALUES ('mouse_weight', ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (str(clamped),))
        return clamped

    # -- queueing: the daemon appends here as events happen, and calls
    # flush() on a ~2s timer so writes are batched rather than per-event. --

    def queue_typing_burst(self, burst) -> None:
        self._pending.typing_bursts.append(burst)

    def queue_nav_event(self, method: str, occurred_at: float) -> None:
        self._pending.nav_events.append((method, occurred_at))

    def queue_cheatsheet_invocation(self, occurred_at: float) -> None:
        self._pending.cheatsheet_invocations.append(occurred_at)

    def has_pending(self) -> bool:
        p = self._pending
        return bool(p.typing_bursts or p.nav_events or p.cheatsheet_invocations)

    def flush(self) -> bool:
        """Writes all queued rows in one transaction, refreshing daily_rollup
        for every day touched. Returns True if anything was written."""
        pending, self._pending = self._pending, _PendingWrites()
        if not (pending.typing_bursts or pending.nav_events
                or pending.cheatsheet_invocations):
            return False

        touched_days: set[str] = set()
        self._conn.execute("BEGIN")
        try:
            for burst in pending.typing_bursts:
                self._conn.execute(
                    "INSERT INTO typing_bursts(ended_at, duration_ms, "
                    "keystroke_count, wpm) VALUES (?, ?, ?, ?)",
                    (int(burst.ended_at), burst.duration_ms,
                     burst.keystroke_count, burst.wpm))
                touched_days.add(_day_key(burst.ended_at))

            for method, occurred_at in pending.nav_events:
                self._conn.execute(
                    "INSERT INTO nav_events(occurred_at, method) VALUES (?, ?)",
                    (int(occurred_at), method))
                touched_days.add(_day_key(occurred_at))

            for occurred_at in pending.cheatsheet_invocations:
                self._conn.execute(
                    "INSERT INTO cheatsheet_invocations(occurred_at) VALUES (?)",
                    (int(occurred_at),))
                touched_days.add(_day_key(occurred_at))

            for day in touched_days:
                self._recompute_rollup(day)
            self._conn.execute("COMMIT")
        except Exception:
            self._conn.execute("ROLLBACK")
            raise
        return True

    def _recompute_rollup(self, day: str) -> None:
        start, end = _day_bounds(day)
        burst_count, keystroke_total, wpm_avg, wpm_max = self._conn.execute(
            "SELECT COUNT(*), COALESCE(SUM(keystroke_count),0), AVG(wpm), MAX(wpm) "
            "FROM typing_bursts WHERE ended_at >= ? AND ended_at < ?",
            (start, end)).fetchone()

        nav_kb = self._conn.execute(
            "SELECT COUNT(*) FROM nav_events WHERE occurred_at >= ? AND occurred_at < ? "
            "AND method = 'keyboard'", (start, end)).fetchone()[0]
        nav_mouse = self._conn.execute(
            "SELECT COUNT(*) FROM nav_events WHERE occurred_at >= ? AND occurred_at < ? "
            "AND method = 'mouse'", (start, end)).fetchone()[0]
        cheatsheet_count = self._conn.execute(
            "SELECT COUNT(*) FROM cheatsheet_invocations "
            "WHERE occurred_at >= ? AND occurred_at < ?", (start, end)).fetchone()[0]

        self._conn.execute(
            "INSERT INTO daily_rollup(day, typing_burst_count, typing_keystroke_total, "
            "typing_wpm_avg, typing_wpm_max, nav_keyboard_count, nav_mouse_count, "
            "cheatsheet_count, updated_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?) "
            "ON CONFLICT(day) DO UPDATE SET "
            "typing_burst_count=excluded.typing_burst_count, "
            "typing_keystroke_total=excluded.typing_keystroke_total, "
            "typing_wpm_avg=excluded.typing_wpm_avg, "
            "typing_wpm_max=excluded.typing_wpm_max, "
            "nav_keyboard_count=excluded.nav_keyboard_count, "
            "nav_mouse_count=excluded.nav_mouse_count, "
            "cheatsheet_count=excluded.cheatsheet_count, "
            "updated_at=excluded.updated_at",
            (day, burst_count, keystroke_total, wpm_avg, wpm_max,
             nav_kb, nav_mouse, cheatsheet_count, int(time.time())))

    def _window_days(self, window: str) -> list[str]:
        today = datetime.now().astimezone().date()
        if window == "today":
            return [today.strftime("%Y-%m-%d")]
        span = 30 if window == "month" else 7
        return [(today - timedelta(days=i)).strftime("%Y-%m-%d")
                for i in range(span)]

    def get_stats(self, window: str) -> dict:
        window = window if window in ("today", "week", "month", "all") else "today"

        if window == "all":
            burst_count, nav_kb, nav_mouse, cheatsheet_count = self._conn.execute(
                "SELECT COALESCE(SUM(typing_burst_count),0), "
                "COALESCE(SUM(nav_keyboard_count),0), COALESCE(SUM(nav_mouse_count),0), "
                "COALESCE(SUM(cheatsheet_count),0) FROM daily_rollup").fetchone()
            wpm_avg = self._conn.execute("SELECT AVG(wpm) FROM typing_bursts").fetchone()[0]
            last_row = self._conn.execute(
                "SELECT wpm FROM typing_bursts ORDER BY ended_at DESC LIMIT 1").fetchone()
            wpm_last = last_row[0] if last_row else None
        else:
            days = self._window_days(window)
            placeholders = ",".join("?" for _ in days)
            burst_count, nav_kb, nav_mouse, cheatsheet_count = self._conn.execute(
                f"SELECT COALESCE(SUM(typing_burst_count),0), "
                f"COALESCE(SUM(nav_keyboard_count),0), COALESCE(SUM(nav_mouse_count),0), "
                f"COALESCE(SUM(cheatsheet_count),0) FROM daily_rollup "
                f"WHERE day IN ({placeholders})", days).fetchone()
            start, _ = _day_bounds(min(days))
            _, end = _day_bounds(max(days))
            wpm_avg = self._conn.execute(
                "SELECT AVG(wpm) FROM typing_bursts WHERE ended_at >= ? AND ended_at < ?",
                (start, end)).fetchone()[0]
            last_row = self._conn.execute(
                "SELECT wpm FROM typing_bursts WHERE ended_at >= ? AND ended_at < ? "
                "ORDER BY ended_at DESC LIMIT 1", (start, end)).fetchone()
            wpm_last = last_row[0] if last_row else None

        nav_total = nav_kb + nav_mouse
        has_data = bool(burst_count or nav_total or cheatsheet_count)
        mouse_weight = self.mouse_weight()
        nav_denominator = nav_kb + nav_mouse * mouse_weight
        return {
            "has_data": has_data,
            "window": window,
            "wpm_avg": round(wpm_avg, 1) if wpm_avg is not None else None,
            "wpm_last": round(wpm_last, 1) if wpm_last is not None else None,
            "wpm_burst_count": burst_count,
            "nav_keyboard": nav_kb,
            "nav_mouse": nav_mouse,
            "mouse_weight": mouse_weight,
            "nav_keyboard_pct":
                round(100 * nav_kb / nav_denominator, 1) if nav_denominator else None,
            "cheatsheet_count": cheatsheet_count,
        }

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

    def prune_old_data(self, retention_days: int | None = None) -> None:
        retention_days = retention_days if retention_days is not None else self.retention_days()
        cutoff = time.time() - retention_days * 86400
        self._conn.execute("DELETE FROM typing_bursts WHERE ended_at < ?", (cutoff,))
        self._conn.execute("DELETE FROM nav_events WHERE occurred_at < ?", (cutoff,))
        self._conn.execute(
            "DELETE FROM cheatsheet_invocations WHERE occurred_at < ?", (cutoff,))
        self._conn.execute("VACUUM")

    def get_records(self) -> dict:
        """All-time personal bests ('best of the best' KPIs). Daily stats
        reset by construction -- these survive so a great day is never lost.
        Computed on demand; the dataset (90-day retention) stays tiny."""
        records: dict[str, dict] = {}

        row = self._conn.execute(
            "SELECT wpm, ended_at FROM typing_bursts ORDER BY wpm DESC LIMIT 1"
        ).fetchone()
        if row:
            records["fastest_burst_wpm"] = {
                "value": round(row[0], 1), "day": _day_key(row[1])}

        row = self._conn.execute(
            "SELECT day, typing_keystroke_total FROM daily_rollup "
            "WHERE typing_keystroke_total > 0 "
            "ORDER BY typing_keystroke_total DESC LIMIT 1").fetchone()
        if row:
            records["busiest_keystroke_day"] = {
                "value": row[1], "day": row[0]}

        row = self._conn.execute(
            "SELECT day, nav_keyboard_count, nav_mouse_count FROM daily_rollup "
            "WHERE nav_keyboard_count + nav_mouse_count >= ? "
            "ORDER BY CAST(nav_keyboard_count AS REAL) / "
            "(nav_keyboard_count + nav_mouse_count) DESC LIMIT 1",
            (RECORD_MIN_NAV_DAY,)).fetchone()
        if row:
            day, kb, mouse = row
            records["best_keyboard_day"] = {
                "value": round(100 * kb / (kb + mouse), 1), "day": day}

        return records
