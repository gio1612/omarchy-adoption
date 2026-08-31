import os
import time
from datetime import datetime, timedelta

import pytest

from storage import Storage
from wpm import TypingBurst


def make_storage(tmp_path):
    return Storage(os.path.join(str(tmp_path), "test.db"))


def test_empty_stats_has_no_data(tmp_path):
    store = make_storage(tmp_path)
    stats = store.get_stats("today")
    assert stats["has_data"] is False
    assert stats["wpm_avg"] is None
    store.close()


def test_flush_returns_false_when_nothing_queued(tmp_path):
    store = make_storage(tmp_path)
    assert store.flush() is False
    store.close()


def test_typing_burst_flush_and_stats(tmp_path):
    store = make_storage(tmp_path)
    now = time.time()
    burst = TypingBurst(ended_at=now, duration_ms=10000, keystroke_count=50, wpm=60.0)
    store.queue_typing_burst(burst)
    assert store.flush() is True
    stats = store.get_stats("today")
    assert stats["has_data"] is True
    assert stats["wpm_avg"] == 60.0
    assert stats["wpm_last"] == 60.0
    assert stats["wpm_burst_count"] == 1
    store.close()


def test_nav_events_ratio(tmp_path):
    store = make_storage(tmp_path)
    now = time.time()
    store.queue_nav_event("keyboard", now)
    store.queue_nav_event("keyboard", now)
    store.queue_nav_event("mouse", now)
    store.flush()
    stats = store.get_stats("today")
    assert stats["nav_keyboard"] == 2
    assert stats["nav_mouse"] == 1
    assert stats["nav_keyboard_pct"] == pytest.approx(66.7, rel=0.01)
    assert stats["mouse_weight"] == 1.0
    store.close()


def test_mouse_weight_persists_and_clamps(tmp_path):
    store = make_storage(tmp_path)
    assert store.mouse_weight() == 1.0
    assert store.set_mouse_weight(2.5) == 2.5
    assert store.mouse_weight() == 2.5
    # out-of-range values clamp instead of being rejected silently or stored raw
    assert store.set_mouse_weight(99) == 10.0
    assert store.set_mouse_weight(0.01) == 0.1
    with pytest.raises(ValueError):
        store.set_mouse_weight("not-a-number")
    # clamped-but-valid value survives a reopen
    store.close()
    reopened = make_storage(tmp_path)
    reopened.set_mouse_weight(2.5)
    reopened.close()
    final = make_storage(tmp_path)
    assert final.mouse_weight() == 2.5
    final.close()


def test_logging_enabled_defaults_off_and_persists(tmp_path):
    store = make_storage(tmp_path)
    assert store.logging_enabled() is False
    assert store.set_logging_enabled(True) is True
    assert store.logging_enabled() is True
    assert store.set_logging_enabled(0) is False
    assert store.logging_enabled() is False
    # true value survives a reopen
    store.set_logging_enabled(True)
    store.close()
    reopened = make_storage(tmp_path)
    assert reopened.logging_enabled() is True
    reopened.close()


def test_weighted_nav_split(tmp_path):
    # weight 2.0: the single mouse event counts double against the keyboard
    store = make_storage(tmp_path)
    now = time.time()
    store.queue_nav_event("keyboard", now)
    store.queue_nav_event("keyboard", now)
    store.queue_nav_event("mouse", now)
    store.flush()
    store.set_mouse_weight(2.0)

    weighted = store.get_stats("today")
    assert weighted["mouse_weight"] == 2.0
    # pct = 2 / (2 + 1*2) = 50%, vs 66.7% unweighted
    assert weighted["nav_keyboard_pct"] == 50.0

    store.set_mouse_weight(0.5)
    discounted = store.get_stats("today")
    # pct = 2 / (2 + 1*0.5) = 80%
    assert discounted["nav_keyboard_pct"] == 80.0
    store.close()


def test_cheatsheet_count(tmp_path):
    store = make_storage(tmp_path)
    now = time.time()
    store.queue_cheatsheet_invocation(now)
    store.queue_cheatsheet_invocation(now)
    store.flush()
    stats = store.get_stats("today")
    assert stats["cheatsheet_count"] == 2
    store.close()


def test_prune_old_data_removes_raw_rows_but_keeps_rollup(tmp_path):
    # daily_rollup is kept forever by design -- only the raw per-event tables
    # are subject to retention, so long-term aggregate history survives even
    # after the detailed rows age out.
    store = make_storage(tmp_path)
    old_ts = time.time() - 200 * 86400
    store.queue_cheatsheet_invocation(old_ts)
    store.flush()
    store.prune_old_data(retention_days=90)

    raw_count = store._conn.execute(
        "SELECT COUNT(*) FROM cheatsheet_invocations").fetchone()[0]
    assert raw_count == 0

    stats = store.get_stats("all")
    assert stats["cheatsheet_count"] == 1
    store.close()


def test_all_window_aggregates_across_days(tmp_path):
    store = make_storage(tmp_path)
    now = time.time()
    old_ts = now - 10 * 86400
    store.queue_typing_burst(TypingBurst(ended_at=old_ts, duration_ms=5000,
                                          keystroke_count=25, wpm=30.0))
    store.queue_typing_burst(TypingBurst(ended_at=now, duration_ms=5000,
                                          keystroke_count=25, wpm=50.0))
    store.flush()
    all_stats = store.get_stats("all")
    assert all_stats["wpm_burst_count"] == 2
    today_stats = store.get_stats("today")
    assert today_stats["wpm_burst_count"] == 1
    store.close()


def test_month_window_covers_30_days(tmp_path):
    store = make_storage(tmp_path)
    now = time.time()
    in_month = now - 10 * 86400
    out_of_month = now - 45 * 86400
    for ts in (in_month, out_of_month):
        store.queue_cheatsheet_invocation(ts)
    store.flush()
    assert store.get_stats("month")["cheatsheet_count"] == 1
    assert store.get_stats("week")["cheatsheet_count"] == 0
    assert store.get_stats("all")["cheatsheet_count"] == 2
    # month window really spans 30 distinct days
    assert len(store._window_days("month")) == 30
    store.close()


def test_records_empty_database(tmp_path):
    store = make_storage(tmp_path)
    assert store.get_records() == {}
    store.close()


def test_records_personal_bests(tmp_path):
    store = make_storage(tmp_path)

    def ts_for(day_ago, hour=12):
        d = datetime.now().astimezone() - timedelta(days=day_ago)
        return d.replace(hour=hour, minute=0, second=0, microsecond=0).timestamp()

    # typing: a 40 WPM day and a later record 80 WPM burst
    store.queue_typing_burst(TypingBurst(ended_at=ts_for(5), duration_ms=10000,
                                         keystroke_count=100, wpm=40.0))
    store.queue_typing_burst(TypingBurst(ended_at=ts_for(1), duration_ms=10000,
                                          keystroke_count=200, wpm=80.0))
    # nav: yesterday is keyboard-heavy with enough volume; two days ago is
    # higher-pct but under the volume threshold -- must NOT win the record
    store.queue_nav_event("mouse", ts_for(5, 9))
    for _ in range(19):
        store.queue_nav_event("keyboard", ts_for(5, 10))
    for _ in range(30):
        store.queue_nav_event("keyboard", ts_for(1, 9))
    store.queue_nav_event("mouse", ts_for(1, 10))
    store.flush()

    records = store.get_records()
    assert records["fastest_burst_wpm"]["value"] == 80.0
    assert records["fastest_burst_wpm"]["day"] == _day_str(1)

    busiest = records["busiest_keystroke_day"]
    assert busiest["value"] == 200
    assert busiest["day"] == _day_str(1)

    best_kb = records["best_keyboard_day"]
    # only the >=20-event day qualifies: 30/31 keyboard
    assert best_kb["value"] == pytest.approx(96.8, rel=0.01)
    assert best_kb["day"] == _day_str(1)
    store.close()


def _day_str(days_ago):
    return (datetime.now().astimezone() - timedelta(days=days_ago)).strftime("%Y-%m-%d")


def test_daily_history_empty_db_returns_zeroed_series(tmp_path):
    store = make_storage(tmp_path)
    history = store.get_daily_history(14)
    assert history["days"] == 14
    assert history["mouse_weight"] == 1.0
    assert len(history["series"]) == 14
    # oldest first, today last
    assert history["series"][-1]["day"] == _day_str(0)
    assert history["series"][0]["day"] == _day_str(13)
    for day in history["series"]:
        assert day["wpm_avg"] is None
        assert day["burst_count"] == 0
        assert day["nav_keyboard"] == 0
        assert day["nav_mouse"] == 0
        assert day["nav_keyboard_pct"] is None
        assert day["cheatsheet_count"] == 0
    store.close()


def test_daily_history_clamps_days_into_retention(tmp_path):
    store = make_storage(tmp_path)
    # 0 is falsy, same "not really specified" bucket as None -- defaults to 14
    assert len(store.get_daily_history(0)["series"]) == 14
    assert len(store.get_daily_history(-5)["series"]) == 1
    assert len(store.get_daily_history(9999)["series"]) == store.retention_days()
    assert store.get_daily_history(None)["days"] == 14
    store.close()


def test_daily_history_reflects_touched_days(tmp_path):
    store = make_storage(tmp_path)

    def ts_for(day_ago, hour=12):
        d = datetime.now().astimezone() - timedelta(days=day_ago)
        return d.replace(hour=hour, minute=0, second=0, microsecond=0).timestamp()

    store.queue_typing_burst(TypingBurst(ended_at=ts_for(2), duration_ms=10000,
                                          keystroke_count=100, wpm=72.0))
    store.queue_nav_event("keyboard", ts_for(2, 9))
    store.queue_nav_event("keyboard", ts_for(2, 9))
    store.queue_nav_event("mouse", ts_for(2, 9))
    store.queue_cheatsheet_invocation(ts_for(2))
    store.flush()

    history = store.get_daily_history(14)
    by_day = {row["day"]: row for row in history["series"]}
    today_row = by_day[_day_str(2)]
    assert today_row["wpm_avg"] == 72.0
    assert today_row["burst_count"] == 1
    assert today_row["nav_keyboard"] == 2
    assert today_row["nav_mouse"] == 1
    assert today_row["nav_keyboard_pct"] == pytest.approx(66.7, rel=0.01)
    assert today_row["cheatsheet_count"] == 1

    # an untouched day in the window stays a zeroed/null row
    untouched = by_day[_day_str(5)]
    assert untouched["wpm_avg"] is None
    assert untouched["nav_keyboard_pct"] is None
    store.close()


def test_daily_history_uses_mouse_weight(tmp_path):
    store = make_storage(tmp_path)
    now = time.time()
    store.queue_nav_event("keyboard", now)
    store.queue_nav_event("keyboard", now)
    store.queue_nav_event("mouse", now)
    store.flush()
    store.set_mouse_weight(2.0)

    history = store.get_daily_history(7)
    assert history["mouse_weight"] == 2.0
    today_row = history["series"][-1]
    # pct = 2 / (2 + 1*2) = 50%, matching get_stats' weighted calculation
    assert today_row["nav_keyboard_pct"] == 50.0
    store.close()


def test_daily_history_no_nav_events_leaves_pct_null(tmp_path):
    store = make_storage(tmp_path)
    store.queue_cheatsheet_invocation(time.time())
    store.flush()
    history = store.get_daily_history(3)
    today_row = history["series"][-1]
    assert today_row["nav_keyboard"] == 0
    assert today_row["nav_mouse"] == 0
    assert today_row["nav_keyboard_pct"] is None
    assert today_row["cheatsheet_count"] == 1
    store.close()


def test_app_launch_events_ratio(tmp_path):
    store = make_storage(tmp_path)
    now = time.time()
    store.queue_app_launch_event("keybind", now)
    store.queue_app_launch_event("keybind", now)
    store.queue_app_launch_event("panel", now)
    store.flush()
    stats = store.get_stats("today")
    assert stats["app_launch_keybind"] == 2
    assert stats["app_launch_panel"] == 1
    assert stats["app_launch_keybind_pct"] == pytest.approx(66.7, rel=0.01)
    store.close()


def test_app_launch_no_events_leaves_pct_null(tmp_path):
    store = make_storage(tmp_path)
    stats = store.get_stats("today")
    assert stats["app_launch_keybind"] == 0
    assert stats["app_launch_panel"] == 0
    assert stats["app_launch_keybind_pct"] is None
    store.close()


def test_app_launch_events_contribute_to_has_data(tmp_path):
    store = make_storage(tmp_path)
    assert store.get_stats("today")["has_data"] is False
    store.queue_app_launch_event("keybind", time.time())
    store.flush()
    assert store.get_stats("today")["has_data"] is True
    store.close()


def test_app_launch_not_weighted_by_mouse_weight(tmp_path):
    # app-launch split has no calibration knob -- mouse_weight must not
    # affect it, unlike the nav split.
    store = make_storage(tmp_path)
    now = time.time()
    store.queue_app_launch_event("keybind", now)
    store.queue_app_launch_event("panel", now)
    store.flush()
    store.set_mouse_weight(5.0)
    stats = store.get_stats("today")
    assert stats["app_launch_keybind_pct"] == 50.0
    store.close()


def test_daily_history_app_launch_fields(tmp_path):
    store = make_storage(tmp_path)
    now = time.time()
    store.queue_app_launch_event("keybind", now)
    store.queue_app_launch_event("keybind", now)
    store.queue_app_launch_event("panel", now)
    store.flush()

    history = store.get_daily_history(7)
    today_row = history["series"][-1]
    assert today_row["app_launch_keybind"] == 2
    assert today_row["app_launch_panel"] == 1
    store.close()


def test_daily_history_app_launch_zeroed_for_untouched_day(tmp_path):
    store = make_storage(tmp_path)
    history = store.get_daily_history(3)
    for day in history["series"]:
        assert day["app_launch_keybind"] == 0
        assert day["app_launch_panel"] == 0
    store.close()


def test_records_empty_has_no_best_keybind_launch_day(tmp_path):
    store = make_storage(tmp_path)
    assert store.get_records() == {}
    store.close()


def test_records_best_keybind_launch_day_requires_minimum_volume(tmp_path):
    store = make_storage(tmp_path)

    def ts_for(day_ago, hour=12):
        d = datetime.now().astimezone() - timedelta(days=day_ago)
        return d.replace(hour=hour, minute=0, second=0, microsecond=0).timestamp()

    # two days ago: 100% keybind but under the RECORD_MIN_APPLAUNCH_DAY=5
    # volume threshold -- must NOT win the record
    store.queue_app_launch_event("keybind", ts_for(2))
    store.queue_app_launch_event("keybind", ts_for(2))
    # yesterday: enough volume (5), 80% keybind -- wins
    for _ in range(4):
        store.queue_app_launch_event("keybind", ts_for(1))
    store.queue_app_launch_event("panel", ts_for(1))
    store.flush()

    records = store.get_records()
    best = records["best_keybind_launch_day"]
    assert best["value"] == 80.0
    assert best["day"] == _day_str(1)
    store.close()


def test_prune_old_data_removes_old_app_launch_events(tmp_path):
    store = make_storage(tmp_path)
    old_ts = time.time() - 200 * 86400
    store.queue_app_launch_event("keybind", old_ts)
    store.flush()
    store.prune_old_data(retention_days=90)

    raw_count = store._conn.execute(
        "SELECT COUNT(*) FROM app_launch_events").fetchone()[0]
    assert raw_count == 0
    # daily_rollup aggregate survives pruning, same as every other metric
    stats = store.get_stats("all")
    assert stats["app_launch_keybind"] == 1
    store.close()


def test_migrate_schema_adds_app_launch_columns_to_existing_db(tmp_path):
    # simulate a pre-addendum database: create the schema without the two
    # new daily_rollup columns, then reopen with Storage and confirm the
    # idempotent migration adds them without data loss.
    import sqlite3

    db_path = os.path.join(str(tmp_path), "legacy.db")
    conn = sqlite3.connect(db_path)
    conn.execute("""
        CREATE TABLE daily_rollup (
            day TEXT PRIMARY KEY,
            typing_burst_count INTEGER NOT NULL DEFAULT 0,
            typing_keystroke_total INTEGER NOT NULL DEFAULT 0,
            typing_wpm_avg REAL,
            typing_wpm_max REAL,
            nav_keyboard_count INTEGER NOT NULL DEFAULT 0,
            nav_mouse_count INTEGER NOT NULL DEFAULT 0,
            cheatsheet_count INTEGER NOT NULL DEFAULT 0,
            updated_at INTEGER NOT NULL
        )
    """)
    conn.execute(
        "INSERT INTO daily_rollup(day, updated_at) VALUES ('2020-01-01', 0)")
    conn.commit()
    conn.close()

    store = Storage(db_path)
    columns = {row[1] for row in
               store._conn.execute("PRAGMA table_info(daily_rollup)")}
    assert "app_launch_keybind_count" in columns
    assert "app_launch_panel_count" in columns
    row = store._conn.execute(
        "SELECT app_launch_keybind_count, app_launch_panel_count "
        "FROM daily_rollup WHERE day = '2020-01-01'").fetchone()
    assert row == (0, 0)
    store.close()

    # reopening again is a no-op (idempotent, no error)
    reopened = Storage(db_path)
    reopened.close()
