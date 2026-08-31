import json

from evdev import ecodes as e

from keybinds import NavComboMatcher, parse_binds_json


def bind(modmask=64, key="LEFT", dispatcher="__lua", description="", **extra):
    entry = {"modmask": modmask, "key": key, "dispatcher": dispatcher,
             "description": description}
    entry.update(extra)
    return entry


def parse(entries):
    return parse_binds_json(json.dumps(entries))


def parse_nav(entries):
    return parse(entries)["nav"]


def test_plain_hyprland_dispatcher_still_matches():
    allow = parse_nav([bind(dispatcher="movefocus", key="LEFT")])
    assert (64, "LEFT") in allow


def test_omarchy_lua_nav_description_matches():
    allow = parse_nav([
        bind(description="Focus on left window"),
        bind(description="Focus on right window", key="RIGHT"),
        bind(key="UP", description="Focus on above window"),
        bind(key="DOWN", description="Focus on below window"),
        bind(key="1", description="Switch to workspace 1"),
        bind(key="TAB", description="Next workspace"),
        bind(key="TAB", modmask=68, description="Former workspace"),
        bind(key="TAB", modmask=8, description="Focus on next window"),
        bind(key="TAB", modmask=12, description="Focus on next monitor"),
        bind(key="1", modmask=65, description="Move window to workspace 1"),
        bind(key="1", modmask=73, description="Move window silently to workspace 1"),
        bind(key="LEFT", modmask=68, description="Move grouped window focus left"),
    ])
    assert len(allow) == 12
    assert (64, "LEFT") in allow
    assert (64, "1") in allow


def test_omarchy_lua_non_nav_description_excluded():
    # the bulk of Omarchy binds are non-nav; none may leak into the allowlist
    allow = parse_nav([
        bind(key="K", description="Keybindings"),
        bind(key="W", description="Close window"),
        bind(key="T", description="Toggle window floating/tiling"),
        bind(key="C", description="Universal copy"),
        bind(key="XF86AudioRaiseVolume", description="Volume up"),
        bind(key="G", description="Toggle window grouping"),
        bind(key="L", description="Toggle workspace layout"),  # layout, not nav
        bind(key="SLASH", description="Monitor scaling up"),
        bind(key="LEFT", modmask=72, description="Move window to group on left"),
    ])
    assert allow == set()


def test_unmodified_nav_bind_never_allowlisted():
    # a bare key can't be told apart from normal typing -- must stay excluded
    assert parse_nav([bind(modmask=0, dispatcher="workspace", key="1")]) == set()
    assert parse_nav([bind(modmask=0, description="Switch to workspace 1")]) == set()


def test_keyless_omarchy_workspace_digits_are_synthesized():
    # Omarchy binds SUPER+1..9,0 via `code:N`, which hyprctl reports with an
    # empty key; the description still identifies them, so synthesize digits.
    allow = parse_nav([
        bind(key="", description="Switch to workspace 1"),
        bind(key="", description="Switch to workspace 10"),
        bind(key="", modmask=65, description="Move window to workspace 3"),
        bind(key="", modmask=73, description="Move window silently to workspace 7"),
    ])
    assert (64, "1") in allow
    assert (64, "0") in allow   # workspace 10 -> "0"
    assert (65, "3") in allow
    assert (73, "7") in allow


def test_keyless_non_workspace_nav_stays_out():
    allow = parse_nav([
        bind(key="", description="Switch to group window 1"),
        bind(key="", description="Focus on left window"),
        bind(key="", description="Switch to workspace 11"),  # out of range
        bind(key="", modmask=0, description="Switch to workspace 4"),
    ])
    assert allow == set()


def test_empty_key_and_garbage_skipped():
    # Omarchy's "Switch to group window N" binds carry no usable key at all
    raw = json.dumps([
        {"modmask": 72, "key": "", "keycode": 0, "dispatcher": "__lua",
         "description": "Switch to group window 1"},
        "not-a-dict",
        {**bind(), "modmask": "not-an-int"},
    ])
    result = parse_binds_json(raw)
    assert result == {
        "nav": set(), "app_launch": set(), "panel_launch": set(), "cheatsheet": set()}


def test_invalid_json_returns_empty():
    result = parse_binds_json("not json at all")
    assert result == {
        "nav": set(), "app_launch": set(), "panel_launch": set(), "cheatsheet": set()}


def test_non_list_json_returns_empty():
    result = parse_binds_json(json.dumps({"not": "a list"}))
    assert result == {
        "nav": set(), "app_launch": set(), "panel_launch": set(), "cheatsheet": set()}


def test_app_launch_description_allowlisted():
    allow = parse([
        bind(key="RETURN", description="Terminal"),
        bind(key="RETURN", modmask=65, description="Browser"),
        bind(key="F", modmask=73, description="File manager (cwd)"),
    ])
    assert allow["app_launch"] == {(64, "RETURN"), (65, "RETURN"), (73, "F")}
    assert allow["nav"] == set()
    assert allow["panel_launch"] == set()


def test_panel_launch_descriptions_allowlisted():
    allow = parse([
        bind(key="SPACE", description="Omarchy menu"),
        bind(key="SPACE", modmask=72, description="Apps menu"),
    ])
    assert allow["panel_launch"] == {(64, "SPACE"), (72, "SPACE")}
    assert allow["app_launch"] == set()
    assert allow["nav"] == set()


def test_unmatched_lua_description_stays_unattributed_everywhere():
    allow = parse([
        bind(key="R", description="Calculator"),
        bind(key="B", description="Weather"),
    ])
    assert allow == {
        "nav": set(), "app_launch": set(), "panel_launch": set(), "cheatsheet": set()}


def test_three_allowlists_computed_in_one_pass():
    allow = parse([
        bind(key="LEFT", description="Focus on left window"),
        bind(key="RETURN", description="Terminal"),
        bind(key="SPACE", description="Omarchy menu"),
        bind(key="K", description="Keybindings"),
    ])
    assert allow["nav"] == {(64, "LEFT")}
    assert allow["app_launch"] == {(64, "RETURN")}
    assert allow["panel_launch"] == {(64, "SPACE")}
    assert allow["cheatsheet"] == {(64, "K")}


def test_cheatsheet_description_allowlisted():
    allow = parse([
        bind(key="K", description="Keybindings"),
        bind(key="K", modmask=72, description="Keybindings"),
    ])
    assert allow["cheatsheet"] == {(64, "K"), (72, "K")}
    assert allow["nav"] == set()
    assert allow["app_launch"] == set()
    assert allow["panel_launch"] == set()


def test_cheatsheet_key_follows_the_live_bind():
    # allowlist follows whatever combo carries the "Keybindings" description
    assert parse([bind(key="X", description="Keybindings")])["cheatsheet"] == {(64, "X")}
    assert parse([bind(modmask=0, key="K", description="Keybindings")])["cheatsheet"] == set()


def test_cheatsheet_wrong_description_stays_out():
    allow = parse([
        bind(key="K", description="Calculator"),
        bind(key="K", modmask=64, description="Terminal"),
    ])
    assert allow["cheatsheet"] == set()


def _held_super(matcher):
    matcher.on_modifier_event(e.KEY_LEFTMETA, pressed=True)


def test_matcher_matches_app_launch_allowlist():
    matcher = NavComboMatcher()
    matcher.update_app_launch_allowlist({(64, "RETURN")})
    _held_super(matcher)
    assert matcher.matches_app_launch(e.KEY_ENTER) is True
    assert matcher.matches_panel_launch(e.KEY_ENTER) is False
    assert matcher.matches(e.KEY_ENTER) is False


def test_matcher_matches_panel_launch_allowlist():
    matcher = NavComboMatcher()
    matcher.update_panel_launch_allowlist({(64, "SPACE")})
    _held_super(matcher)
    assert matcher.matches_panel_launch(e.KEY_SPACE) is True
    assert matcher.matches_app_launch(e.KEY_SPACE) is False


def test_matcher_app_launch_requires_modifier():
    matcher = NavComboMatcher()
    matcher.update_app_launch_allowlist({(64, "RETURN")})
    # no modifier held -- current_modmask is 0, never matches
    assert matcher.matches_app_launch(e.KEY_ENTER) is False


def test_matcher_three_allowlists_are_independent():
    matcher = NavComboMatcher()
    matcher.update_allowlist({(64, "LEFT")})
    matcher.update_app_launch_allowlist({(64, "RETURN")})
    matcher.update_panel_launch_allowlist({(64, "SPACE")})
    _held_super(matcher)
    assert matcher.matches(e.KEY_LEFT) is True
    assert matcher.matches_app_launch(e.KEY_LEFT) is False
    assert matcher.matches_panel_launch(e.KEY_LEFT) is False


def test_matcher_matches_cheatsheet_allowlist():
    matcher = NavComboMatcher()
    matcher.update_cheatsheet_allowlist({(64, "K")})
    _held_super(matcher)
    assert matcher.matches_cheatsheet(e.KEY_K) is True
    assert matcher.matches(e.KEY_K) is False
    assert matcher.matches_panel_launch(e.KEY_K) is False


def test_matcher_cheatsheet_channel_is_independent_from_others():
    matcher = NavComboMatcher()
    matcher.update_allowlist({(64, "LEFT")})
    matcher.update_panel_launch_allowlist({(64, "SPACE")})
    matcher.update_cheatsheet_allowlist({(64, "K")})
    _held_super(matcher)
    assert matcher.matches(e.KEY_LEFT) is True
    assert matcher.matches_cheatsheet(e.KEY_LEFT) is False
    assert matcher.matches_cheatsheet(e.KEY_SPACE) is False
    assert matcher.matches(e.KEY_K) is False
