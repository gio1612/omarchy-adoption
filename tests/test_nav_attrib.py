from nav_attrib import EpisodeCoalescer, NavAttributor


def test_attribute_prefers_more_recent_keyboard():
    attributor = NavAttributor(correlation_window_s=0.4)
    attributor.note_mouse_activity(10.0)
    attributor.note_keyboard_nav_combo(10.1)
    assert attributor.attribute(10.2) == "keyboard"


def test_attribute_prefers_more_recent_mouse():
    attributor = NavAttributor(correlation_window_s=0.4)
    attributor.note_keyboard_nav_combo(10.0)
    attributor.note_mouse_activity(10.1)
    assert attributor.attribute(10.2) == "mouse"


def test_attribute_outside_window_is_none():
    attributor = NavAttributor(correlation_window_s=0.4)
    attributor.note_keyboard_nav_combo(10.0)
    assert attributor.attribute(11.0) is None


def test_attribute_future_event_not_counted():
    attributor = NavAttributor(correlation_window_s=0.4)
    attributor.note_keyboard_nav_combo(10.5)
    # the nav combo happened *after* the episode -- can't have caused it
    assert attributor.attribute(10.0) is None


def test_attribute_with_no_signals_is_none():
    attributor = NavAttributor(correlation_window_s=0.4)
    assert attributor.attribute(10.0) is None


def test_episode_coalescer_merges_within_window():
    coalescer = EpisodeCoalescer(coalesce_window_s=0.08)
    assert coalescer.add_event(1.0) == 1.0
    assert coalescer.add_event(1.05) is None  # merged into the open episode
    assert coalescer.add_event(1.2) == 1.2  # outside the window -- new episode
