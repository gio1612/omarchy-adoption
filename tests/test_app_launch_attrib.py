from app_launch_attrib import AppLaunchAttributor


def test_openwindow_attributes_to_keybind_within_window():
    attributor = AppLaunchAttributor(keybind_window_s=3.0, panel_window_s=12.0)
    attributor.note_keybind_press(10.0)
    assert attributor.on_openwindow(11.5) == "keybind"


def test_openwindow_attributes_to_panel_within_window():
    attributor = AppLaunchAttributor(keybind_window_s=3.0, panel_window_s=12.0)
    attributor.note_panel_press(10.0)
    assert attributor.on_openwindow(20.0) == "panel"


def test_openwindow_outside_keybind_window_is_none():
    attributor = AppLaunchAttributor(keybind_window_s=3.0, panel_window_s=12.0)
    attributor.note_keybind_press(10.0)
    assert attributor.on_openwindow(14.0) is None


def test_openwindow_outside_panel_window_is_none():
    attributor = AppLaunchAttributor(keybind_window_s=3.0, panel_window_s=12.0)
    attributor.note_panel_press(10.0)
    assert attributor.on_openwindow(23.0) is None


def test_openwindow_future_press_not_counted():
    attributor = AppLaunchAttributor(keybind_window_s=3.0, panel_window_s=12.0)
    attributor.note_keybind_press(10.5)
    # the keybind press happened *after* the openwindow event -- can't have caused it
    assert attributor.on_openwindow(10.0) is None


def test_openwindow_with_no_armed_channel_is_none():
    attributor = AppLaunchAttributor()
    assert attributor.on_openwindow(10.0) is None


def test_openwindow_prefers_most_recent_arm_when_both_within_window():
    attributor = AppLaunchAttributor(keybind_window_s=3.0, panel_window_s=12.0)
    attributor.note_panel_press(9.0)
    attributor.note_keybind_press(10.0)
    assert attributor.on_openwindow(10.5) == "keybind"

    attributor2 = AppLaunchAttributor(keybind_window_s=3.0, panel_window_s=12.0)
    attributor2.note_keybind_press(9.0)
    attributor2.note_panel_press(10.0)
    assert attributor2.on_openwindow(10.5) == "panel"


def test_single_shot_consumption_clears_only_the_winning_arm():
    attributor = AppLaunchAttributor(keybind_window_s=3.0, panel_window_s=12.0)
    attributor.note_keybind_press(10.0)
    attributor.note_panel_press(10.0)
    # a tie (equal timestamps) is not ">" so panel wins; only panel's arm
    # is consumed, keybind's arm stays live
    assert attributor.on_openwindow(10.5) == "panel"
    # a second openwindow>> shortly after (e.g. a splash window) finds the
    # still-live keybind arm and is attributed to it
    assert attributor.on_openwindow(10.6) == "keybind"
    # keybind arm was single-shot consumed by the previous call too
    assert attributor.on_openwindow(10.7) is None


def test_single_shot_consumption_prevents_double_count_for_same_channel():
    attributor = AppLaunchAttributor(keybind_window_s=3.0, panel_window_s=12.0)
    attributor.note_keybind_press(10.0)
    assert attributor.on_openwindow(10.5) == "keybind"
    # a second, closely-following openwindow>> from the same app's own
    # startup finds no live armed channel -- correctly unattributed
    assert attributor.on_openwindow(10.6) is None
