import evdev_reader as mod
from evdev import ecodes as e
from evdev_reader import EvdevSource
from keybinds import NavComboMatcher


class FakeEvent:
    def __init__(self, type_, code, value):
        self.type = type_
        self.code = code
        self.value = value


def make_source():
    calls = {"mouse": [], "typing": [], "kbd_nav": [], "app_launch": [], "panel_launch": [],
             "cheatsheet": []}
    source = EvdevSource(
        nav_matcher=NavComboMatcher(),  # required by the key-modifier path
        on_typing_burst=calls["typing"].append,
        on_mouse_activity=lambda ts: calls["mouse"].append(ts),
        on_keyboard_nav_combo=lambda ts: calls["kbd_nav"].append(ts),
        on_app_launch_keybind_combo=lambda ts: calls["app_launch"].append(ts),
        on_panel_launch_combo=lambda ts: calls["panel_launch"].append(ts),
        on_cheatsheet_combo=lambda ts: calls["cheatsheet"].append(ts),
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


def make_source_with_matcher():
    calls = {"mouse": [], "typing": [], "kbd_nav": [], "app_launch": [], "panel_launch": [],
             "cheatsheet": []}
    matcher = NavComboMatcher()
    matcher.update_allowlist({(64, "LEFT")})
    matcher.update_app_launch_allowlist({(64, "RETURN")})
    matcher.update_panel_launch_allowlist({(64, "SPACE")})
    matcher.update_cheatsheet_allowlist({(64, "K")})
    source = EvdevSource(
        nav_matcher=matcher,
        on_typing_burst=calls["typing"].append,
        on_mouse_activity=lambda ts: calls["mouse"].append(ts),
        on_keyboard_nav_combo=lambda ts: calls["kbd_nav"].append(ts),
        on_app_launch_keybind_combo=lambda ts: calls["app_launch"].append(ts),
        on_panel_launch_combo=lambda ts: calls["panel_launch"].append(ts),
        on_cheatsheet_combo=lambda ts: calls["cheatsheet"].append(ts),
    )
    return source, calls


def test_app_launch_keybind_combo_fires_app_launch_callback():
    source, calls = make_source_with_matcher()
    source._handle_event(FakeEvent(e.EV_KEY, e.KEY_LEFTMETA, 1))
    source._handle_event(FakeEvent(e.EV_KEY, e.KEY_ENTER, 1))
    assert len(calls["app_launch"]) == 1
    assert calls["kbd_nav"] == []
    assert calls["panel_launch"] == []


def test_panel_launch_combo_fires_panel_launch_callback():
    source, calls = make_source_with_matcher()
    source._handle_event(FakeEvent(e.EV_KEY, e.KEY_LEFTMETA, 1))
    source._handle_event(FakeEvent(e.EV_KEY, e.KEY_SPACE, 1))
    assert len(calls["panel_launch"]) == 1
    assert calls["app_launch"] == []
    assert calls["kbd_nav"] == []


def test_nav_combo_does_not_arm_app_launch_or_panel_channels():
    source, calls = make_source_with_matcher()
    source._handle_event(FakeEvent(e.EV_KEY, e.KEY_LEFTMETA, 1))
    source._handle_event(FakeEvent(e.EV_KEY, e.KEY_LEFT, 1))
    assert len(calls["kbd_nav"]) == 1
    assert calls["app_launch"] == []
    assert calls["panel_launch"] == []
    assert calls["cheatsheet"] == []


def test_super_k_fires_cheatsheet_callback_only():
    source, calls = make_source_with_matcher()
    source._handle_event(FakeEvent(e.EV_KEY, e.KEY_LEFTMETA, 1))
    source._handle_event(FakeEvent(e.EV_KEY, e.KEY_K, 1))
    assert len(calls["cheatsheet"]) == 1
    assert calls["kbd_nav"] == []
    assert calls["app_launch"] == []
    assert calls["panel_launch"] == []


def test_cheatsheet_requires_super_held():
    source, calls = make_source_with_matcher()
    # bare K while typing -- no modifier held, never counts as a cheatsheet
    source._handle_event(FakeEvent(e.EV_KEY, e.KEY_K, 1))
    assert calls["cheatsheet"] == []


def test_cheatsheet_auto_repeat_is_excluded():
    source, calls = make_source_with_matcher()
    source._handle_event(FakeEvent(e.EV_KEY, e.KEY_LEFTMETA, 1))
    source._handle_event(FakeEvent(e.EV_KEY, e.KEY_K, 1))
    source._handle_event(FakeEvent(e.EV_KEY, e.KEY_K, 2))  # hold auto-repeat
    assert len(calls["cheatsheet"]) == 1


# ---------------------------------------------------------------------------
# Trackpad (multitouch / protocol B) two-finger scroll detection
# ---------------------------------------------------------------------------

# A two-finger scroll is delivered as >=2 concurrently active ABS_MT slots
# whose (slot, tracking_id, position) coordinates move together. The detector
# looks for >=2 active fingerprints whose accumulated movement crosses the
# SCROLL_THRESHOLD -- that is a deliberate scroll gesture, distinct from a
# single-finger cursor drag (which is excluded, like REL_X/REL_Y).


def _scenario_source():
    calls = {"mouse": [], "typing": [], "kbd_nav": [], "app_launch": [],
             "panel_launch": [], "cheatsheet": []}
    source = mod.EvdevSource(
        nav_matcher=None,
        on_typing_burst=calls["typing"].append,
        on_mouse_activity=lambda ts: calls["mouse"].append(ts),
        on_keyboard_nav_combo=lambda ts: calls["kbd_nav"].append(ts),
        on_app_launch_keybind_combo=lambda ts: calls["app_launch"].append(ts),
        on_panel_launch_combo=lambda ts: calls["panel_launch"].append(ts),
        on_cheatsheet_combo=lambda ts: calls["cheatsheet"].append(ts),
    )
    return source, calls


def _feed_abs(source, path, events):
    # Real devices are enrolled by EvdevSource._discover after a capability
    # check; driving _handle_event directly means doing that enrollment here.
    source.register_trackpad(path)
    for type_, code, value in events:
        source._handle_event(FakeEvent(type_, code, value), path)


def _two_finger_scroll(source, path, from_y=100, to_y=300, steps=5):
    """Touch down two fingers, drag them both down `to_y-from_y` units."""
    S, T, Y = mod._ABS_MT_SLOT, mod._ABS_MT_TRACKING_ID, mod._ABS_MT_POSITION_Y
    X = mod._ABS_MT_POSITION_X
    events = []
    # slot 0 finger 1 down
    events += [(e.EV_ABS, S, 0), (e.EV_ABS, T, 100), (e.EV_ABS, X, 10), (e.EV_ABS, Y, from_y)]
    # slot 1 finger 2 down
    events += [(e.EV_ABS, S, 1), (e.EV_ABS, T, 200), (e.EV_ABS, X, 30), (e.EV_ABS, Y, from_y)]
    # drag both fingers down in steps
    for i in range(1, steps + 1):
        y = from_y + int((to_y - from_y) * i / steps)
        events += [(e.EV_ABS, S, 0), (e.EV_ABS, Y, y)]
        events += [(e.EV_ABS, S, 1), (e.EV_ABS, Y, y)]
    _feed_abs(source, path, events)


def test_two_finger_trackpad_scroll_counts_as_mouse_activity():
    source, calls = _scenario_source()
    # EP is just an opaque path label; the detector is per-device.
    _two_finger_scroll(source, "/dev/input/eventX", from_y=100, to_y=400, steps=8)
    assert len(calls["mouse"]) >= 1


def test_single_finger_trackpad_drag_does_not_count():
    source, calls = _scenario_source()
    S, T, Y = mod._ABS_MT_SLOT, mod._ABS_MT_TRACKING_ID, mod._ABS_MT_POSITION_Y
    X = mod._ABS_MT_POSITION_X
    events = [
        (e.EV_ABS, S, 0), (e.EV_ABS, T, 100), (e.EV_ABS, X, 10), (e.EV_ABS, Y, 100),
    ]
    for y in range(110, 501, 10):
        events.append((e.EV_ABS, S, 0))
        events.append((e.EV_ABS, Y, y))
    _feed_abs(source, "/dev/input/eventY", events)
    # single finger moving the cursor is NOT navigation, matching REL_X/REL_Y
    assert calls["mouse"] == []


def test_trackpad_scroll_requires_two_active_fingers_not_lift_offset():
    source, calls = _scenario_source()
    S, T, Y = mod._ABS_MT_SLOT, mod._ABS_MT_TRACKING_ID, mod._ABS_MT_POSITION_Y
    X = mod._ABS_MT_POSITION_X
    # two fingers down, huge initial offset positions (hardware may deliver a
    # big first delta) -- must not fire because only one finger moved at a time
    events = [
        (e.EV_ABS, S, 0), (e.EV_ABS, T, 100), (e.EV_ABS, X, 10), (e.EV_ABS, Y, 100),
        (e.EV_ABS, S, 1), (e.EV_ABS, T, 200), (e.EV_ABS, X, 30), (e.EV_ABS, Y, 50),
    ]
    _feed_abs(source, "/dev/input/eventZ", events)
    assert calls["mouse"] == []


# ---------------------------------------------------------------------------
# Audit logging
# ---------------------------------------------------------------------------


def test_logging_disabled_by_default_no_lines_emitted():
    calls = {"mouse": [], "typing": [], "kbd_nav": [], "app_launch": [],
             "panel_launch": [], "cheatsheet": []}
    logged = []
    source = mod.EvdevSource(
        nav_matcher=None,
        on_typing_burst=calls["typing"].append,
        on_mouse_activity=lambda ts: calls["mouse"].append(ts),
        on_keyboard_nav_combo=lambda ts: calls["kbd_nav"].append(ts),
        on_app_launch_keybind_combo=lambda ts: calls["app_launch"].append(ts),
        on_panel_launch_combo=lambda ts: calls["panel_launch"].append(ts),
        on_cheatsheet_combo=lambda ts: calls["cheatsheet"].append(ts),
        logging_enabled=False,
        on_log=logged.append,
    )
    source._handle_event(FakeEvent(e.EV_KEY, e.BTN_LEFT, 1), "/dev/input/eventA")
    source._handle_event(FakeEvent(e.EV_REL, e.REL_WHEEL, -1), "/dev/input/eventA")
    assert logged == []


def test_logging_reports_mouse_click_wheel_and_trackpad():
    calls = {"mouse": [], "typing": [], "kbd_nav": [], "app_launch": [],
             "panel_launch": [], "cheatsheet": []}
    logged = []
    source = mod.EvdevSource(
        nav_matcher=None,
        on_typing_burst=calls["typing"].append,
        on_mouse_activity=lambda ts: calls["mouse"].append(ts),
        on_keyboard_nav_combo=lambda ts: calls["kbd_nav"].append(ts),
        on_app_launch_keybind_combo=lambda ts: calls["app_launch"].append(ts),
        on_panel_launch_combo=lambda ts: calls["panel_launch"].append(ts),
        on_cheatsheet_combo=lambda ts: calls["cheatsheet"].append(ts),
        logging_enabled=True,
        on_log=logged.append,
    )
    source._handle_event(FakeEvent(e.EV_KEY, e.BTN_LEFT, 1), "/dev/input/eventCmd")
    assert any("mouse:click" in line for line in logged)
    source._handle_event(FakeEvent(e.EV_REL, e.REL_WHEEL, -1), "/dev/input/eventCmd")
    assert any("mouse:wheel" in line for line in logged)
    _two_finger_scroll(source, "/dev/input/eventPad", from_y=100, to_y=400, steps=8)
    assert any("trackpad-scroll" in line for line in logged)


def test_logging_reports_keyboard_keystrokes():
    calls = {"mouse": [], "typing": [], "kbd_nav": [], "app_launch": [],
             "panel_launch": [], "cheatsheet": []}
    logged = []
    matcher = NavComboMatcher()
    source = mod.EvdevSource(
        nav_matcher=matcher,
        on_typing_burst=calls["typing"].append,
        on_mouse_activity=lambda ts: calls["mouse"].append(ts),
        on_keyboard_nav_combo=lambda ts: calls["kbd_nav"].append(ts),
        on_app_launch_keybind_combo=lambda ts: calls["app_launch"].append(ts),
        on_panel_launch_combo=lambda ts: calls["panel_launch"].append(ts),
        on_cheatsheet_combo=lambda ts: calls["cheatsheet"].append(ts),
        logging_enabled=True,
        on_log=logged.append,
    )
    source._handle_event(FakeEvent(e.EV_KEY, e.KEY_A, 1), "/dev/input/eventKB")
    source._handle_event(FakeEvent(e.EV_KEY, e.KEY_A, 0), "/dev/input/eventKB")
    assert any("key" in line for line in logged)
    assert not any("mouse:click" in line for line in logged)


# ---------------------------------------------------------------------------
# Trackpad enrollment is explicit
# ---------------------------------------------------------------------------

def test_abs_events_from_an_unregistered_device_are_ignored():
    """Regression: _handle_event used to create a scroll detector for ANY
    device that emitted an EV_ABS event, which quietly enrolled graphics
    tablets, joysticks and lid switches as trackpads. Only devices whose
    capabilities advertise ABS_MT_POSITION_X are enrolled now."""
    source, calls = _scenario_source()
    S, T, Y = mod._ABS_MT_SLOT, mod._ABS_MT_TRACKING_ID, mod._ABS_MT_POSITION_Y
    X = mod._ABS_MT_POSITION_X
    events = [
        (e.EV_ABS, S, 0), (e.EV_ABS, T, 100), (e.EV_ABS, X, 10), (e.EV_ABS, Y, 100),
        (e.EV_ABS, S, 1), (e.EV_ABS, T, 200), (e.EV_ABS, X, 30), (e.EV_ABS, Y, 100),
    ]
    for y in range(120, 601, 20):
        events += [(e.EV_ABS, S, 0), (e.EV_ABS, Y, y),
                   (e.EV_ABS, S, 1), (e.EV_ABS, Y, y)]

    # NOT registered as a trackpad
    for type_, code, value in events:
        source._handle_event(FakeEvent(type_, code, value), "/dev/input/eventTablet")

    assert calls["mouse"] == []
    assert "/dev/input/eventTablet" not in source._trackpads


def test_register_trackpad_is_idempotent():
    source, _ = _scenario_source()
    first = source.register_trackpad("/dev/input/eventTP")
    assert source.register_trackpad("/dev/input/eventTP") is first


def test_health_starts_empty_and_counts_registered_devices():
    source, _ = _scenario_source()
    assert source.health() == {"readable": 0, "blocked": 0, "total": 0, "keyboards": 0}


def test_keyboard_probe_keys_are_real_codes():
    """A typo here would silently classify every keyboard as 'not a keyboard'
    and make the input-access warning fire on a perfectly healthy system."""
    for code in mod._KEYBOARD_PROBE_KEYS:
        assert isinstance(code, int) and code > 0
    assert e.KEY_A in mod._KEYBOARD_PROBE_KEYS
    assert e.KEY_SPACE in mod._KEYBOARD_PROBE_KEYS
