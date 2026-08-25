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
