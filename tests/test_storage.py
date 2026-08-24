import os
import time

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
