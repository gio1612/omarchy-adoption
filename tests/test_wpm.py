from evdev import ecodes as e
from wpm import TypingTracker, compute_wpm


def test_compute_wpm_basic():
    # 25 keystrokes in 10 seconds => 5 words in 10s => 30 wpm
    assert abs(compute_wpm(25, 10000) - 30.0) < 0.01


def test_burst_closes_on_idle_gap():
    tracker = TypingTracker(idle_gap_ms=2000, min_keystrokes=2, min_duration_ms=100)
    t = 1000.0
    assert tracker.on_key_event(e.KEY_H, 1, t, t) is None
    t += 0.2
    assert tracker.on_key_event(e.KEY_I, 1, t, t) is None
    t += 3.0  # gap exceeds idle_gap_ms
    closed = tracker.on_key_event(e.KEY_A, 1, t, t)
    assert closed is not None
    assert closed.keystroke_count == 2
    assert closed.duration_ms == 200


def test_shift_does_not_block_typing():
    tracker = TypingTracker(min_keystrokes=1, min_duration_ms=0)
    t = 0.0
    tracker.on_key_event(e.KEY_LEFTSHIFT, 1, t, t)
    assert tracker.on_key_event(e.KEY_H, 1, t + 0.05, t + 0.05) is None
    tracker.on_key_event(e.KEY_LEFTSHIFT, 0, t + 0.06, t + 0.06)
    closed = tracker.flush(t + 0.1)
    assert closed is not None
    assert closed.keystroke_count == 1


def test_ctrl_combo_excluded_from_typing():
    tracker = TypingTracker(min_keystrokes=1, min_duration_ms=0)
    t = 0.0
    tracker.on_key_event(e.KEY_LEFTCTRL, 1, t, t)
    assert tracker.on_key_event(e.KEY_C, 1, t + 0.01, t + 0.01) is None
    tracker.on_key_event(e.KEY_LEFTCTRL, 0, t + 0.02, t + 0.02)
    assert tracker.flush(t + 0.1) is None


def test_short_burst_discarded():
    tracker = TypingTracker(min_keystrokes=5, min_duration_ms=300)
    t = 0.0
    for _ in range(3):
        tracker.on_key_event(e.KEY_A, 1, t, t)
        t += 0.05
    assert tracker.flush(t) is None


def test_keyup_and_repeat_ignored():
    tracker = TypingTracker(min_keystrokes=1, min_duration_ms=0)
    t = 0.0
    assert tracker.on_key_event(e.KEY_A, 0, t, t) is None  # keyup, ignored
    assert tracker.on_key_event(e.KEY_A, 2, t, t) is None  # autorepeat, ignored
    assert tracker.flush(t) is None  # nothing counted
