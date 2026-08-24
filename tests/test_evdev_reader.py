from evdev import ecodes as e

from evdev_reader import EvdevSource


class FakeEvent:
    def __init__(self, type_, code, value):
        self.type = type_
        self.code = code
        self.value = value


def make_source():
    calls = {"mouse": [], "typing": [], "kbd_nav": []}
    source = EvdevSource(
        nav_matcher=None,  # only mouse paths are exercised here
        on_typing_burst=calls["typing"].append,
        on_mouse_activity=lambda ts: calls["mouse"].append(ts),
        on_keyboard_nav_combo=lambda ts: calls["kbd_nav"].append(ts),
    )
    return source, calls


def test_button_press_counts_but_release_does_not():
    source, calls = make_source()
    source._handle_event(FakeEvent(e.EV_KEY, e.BTN_LEFT, 1))
    assert len(calls["mouse"]) == 1
    source._handle_event(FakeEvent(e.EV_KEY, e.BTN_LEFT, 0))
    assert len(calls["mouse"]) == 1  # release is not a second action


def test_pointer_motion_is_ignored():
    # deliberate: cursor movement must not pollute the keyboard/mouse split
    source, calls = make_source()
    for _ in range(100):
        source._handle_event(FakeEvent(e.EV_REL, e.REL_X, 20))
        source._handle_event(FakeEvent(e.EV_REL, e.REL_Y, -20))
    assert calls["mouse"] == []


def test_wheel_scroll_counts_as_activity():
    source, calls = make_source()
    source._handle_event(FakeEvent(e.EV_REL, e.REL_WHEEL, 1))
    source._handle_event(FakeEvent(e.EV_REL, e.REL_WHEEL, -1))
    source._handle_event(FakeEvent(e.EV_REL, e.REL_HWHEEL, 1))
    if hasattr(e, "REL_WHEEL_HI_RES"):
        source._handle_event(FakeEvent(e.EV_REL, e.REL_WHEEL_HI_RES, 120))
    assert len(calls["mouse"]) == 3 + (1 if hasattr(e, "REL_WHEEL_HI_RES") else 0)
