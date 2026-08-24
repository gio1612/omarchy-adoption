import json

from keybinds import parse_binds_json


def bind(modmask=64, key="LEFT", dispatcher="__lua", description="", **extra):
    entry = {"modmask": modmask, "key": key, "dispatcher": dispatcher,
             "description": description}
    entry.update(extra)
    return entry


def parse(entries):
    return parse_binds_json(json.dumps(entries))


def test_plain_hyprland_dispatcher_still_matches():
    allow = parse([bind(dispatcher="movefocus", key="LEFT")])
    assert (64, "LEFT") in allow


def test_omarchy_lua_nav_description_matches():
    allow = parse([
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
    allow = parse([
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
    assert parse([bind(modmask=0, dispatcher="workspace", key="1")]) == set()
    assert parse([bind(modmask=0, description="Switch to workspace 1")]) == set()


def test_keyless_omarchy_workspace_digits_are_synthesized():
    # Omarchy binds SUPER+1..9,0 via `code:N`, which hyprctl reports with an
    # empty key; the description still identifies them, so synthesize digits.
    allow = parse([
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
    allow = parse([
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
    assert parse_binds_json(raw) == set()


def test_invalid_json_returns_empty():
    assert parse_binds_json("not json at all") == set()
