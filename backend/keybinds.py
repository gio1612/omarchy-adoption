"""Live nav-dispatcher keybind allowlist, built from `hyprctl binds -j`.

Not an Omarchy-documented convention -- we parse Hyprland's own JSON bind dump
so mouse-vs-keyboard attribution stays correct if the user rebinds things in
their own ~/.config/hypr/bindings.lua, rather than hardcoding default binds.

Omarchy wrinkle: its lua config binds EVERYTHING through the `__lua`
dispatcher (`hyprctl binds -j` shows dispatcher="__lua", arg="<n>" -- a
handler index that hides the real dispatcher). So for __lua binds we match on
the human-readable `description` field instead, which Omarchy populates with
phrases like "Focus on left window". A __lua bind whose description matches no
pattern is simply not allowlisted -- it falls back to "unattributed" rather
than guessing.
"""

from __future__ import annotations

import asyncio
import json
import re

from evdev import ecodes as e

NAV_DISPATCHERS = frozenset({
    "workspace", "movetoworkspace", "movetoworkspacesilent",
    "movefocus", "focuswindow", "focusmonitor", "focusurgentorlast",
    "cyclenext", "changegroupactive",
})

LUA_DISPATCHER = "__lua"

# Description phrases used by Omarchy's own bindings.lua for nav dispatchers.
# Kept anchored and narrow: a false "nav" here would misattribute real typing,
# while a miss just costs us one unattributed episode.
NAV_DESCRIPTION_PATTERNS = tuple(re.compile(p) for p in (
    r"^Focus on (left|right|above|below) window$",   # movefocus
    r"^Focus on (next|previous) monitor$",           # focusmonitor
    r"^Focus on (next|previous) window$",            # cyclenext
    r"^(Next|Previous) workspace$",                  # workspace cycling
    r"^Former workspace$",                           # focusurgentorlast-style
    r"^Switch to workspace \d+$",                    # workspace
    r"^Move window( silently)? to workspace \d+$",   # movetoworkspace(silent)
    r"^Move grouped window focus (left|right)$",     # changegroupactive
))

# Omarchy's first-party default app-launch bind descriptions (bindings.lua).
# Seeded from a live default install -- NOT exhaustive by design (a user's
# own custom app-launch bind in ~/.config/hypr/bindings.lua isn't tracked
# unless its description happens to match one of these exact strings). A
# __lua bind whose description matches neither this set nor
# PANEL_LAUNCH_DESCRIPTIONS is simply not allowlisted -- unattributed, not
# guessed, same posture as NAV_DESCRIPTION_PATTERNS above.
APP_LAUNCH_DESCRIPTIONS = frozenset({
    "Terminal", "Browser", "Browser (private)", "File manager",
    "File manager (cwd)", "Editor", "Tmux", "Herdr", "Music", "Music TUI",
    "Docker", "Signal", "Obsidian", "Omawrite", "Passwords", "ChatGPT",
    "Grok", "Calendar", "Email", "New email", "YouTube", "WhatsApp",
    "Google Messages", "Google Photos", "Google Maps", "X", "X Post",
})

# Omarchy's app-entry-point menu binds. Both included in one shared
# "panel" bucket -- see DESIGN.md "App-launch: keybind vs. panel", decision
# 3, for why SUPER+SPACE (a root menu, not exclusively an app launcher) is
# still included rather than excluded or split out.
PANEL_LAUNCH_DESCRIPTIONS = frozenset({"Omarchy menu", "Apps menu"})

# Omarchy's first-party keybindings cheatsheet bind (SUPER+K, description
# "Keybindings", `omarchy-menu-keybindings`). Matched on its exact description
# with the same "live, not hardcoded" posture as the other allowlists: a user
# who rebinds or re-describes SUPER+K simply drops off the cheatsheet
# allowlist instead of being guessed.
CHEATSHEET_DESCRIPTIONS = frozenset({"Keybindings"})

# Hyprland's own modmask bit values (SHIFT=1, CAPS=2, CTRL=4, ALT=8,
# NUMLOCK=16, MOD3=32, SUPER=64, MOD5=128) -- confirmed against this
# machine's live `hyprctl binds -j` output (SUPER+K -> modmask 64,
# SUPER+ALT+K -> 72, SUPER+CTRL+K -> 68).
MOD_BIT_SHIFT = 1
MOD_BIT_CTRL = 4
MOD_BIT_ALT = 8
MOD_BIT_SUPER = 64

# evdev key code -> Hyprland "key" name. Best-effort: Hyprland's key names
# roughly follow X11 keysym names, which evdev codes don't directly carry. A
# code missing from this table simply never matches the allowlist -- it falls
# back to "unattributed" rather than guessing.
_LETTER_NAMES = {getattr(e, f"KEY_{c}"): c for c in "ABCDEFGHIJKLMNOPQRSTUVWXYZ"}
_DIGIT_NAMES = {getattr(e, f"KEY_{d}"): d for d in "0123456789"}
_SPECIAL_NAMES = {
    e.KEY_SPACE: "SPACE",
    e.KEY_ENTER: "RETURN",
    e.KEY_ESC: "ESCAPE",
    e.KEY_TAB: "TAB",
    e.KEY_BACKSPACE: "BACKSPACE",
    e.KEY_COMMA: "COMMA",
    e.KEY_DOT: "PERIOD",
    e.KEY_SLASH: "SLASH",
    e.KEY_UP: "UP",
    e.KEY_DOWN: "DOWN",
    e.KEY_LEFT: "LEFT",
    e.KEY_RIGHT: "RIGHT",
}
EVDEV_TO_HYPR_KEYNAME: dict[int, str] = {**_LETTER_NAMES, **_DIGIT_NAMES, **_SPECIAL_NAMES}


async def fetch_keybind_allowlists() -> dict[str, set[tuple[int, str]]]:
    """Runs `hyprctl binds -j` once and returns all four live allowlists
    (nav / app-launch / panel-launch / cheatsheet), each a set of
    (modmask, KEY) pairs."""
    proc = await asyncio.create_subprocess_exec(
        "hyprctl", "binds", "-j",
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
    stdout, _ = await proc.communicate()
    return parse_binds_json(stdout.decode("utf-8", errors="replace"))


def parse_binds_json(raw: str) -> dict[str, set[tuple[int, str]]]:
    """Returns {"nav": ..., "app_launch": ..., "panel_launch": ...,
    "cheatsheet": ...}, each a set of (modmask, KEY) pairs. Breaking
    return-type change from the previous bare-set return -- update callers
    (daemon.py) and tests/test_keybinds.py accordingly."""
    result: dict[str, set[tuple[int, str]]] = {
        "nav": set(), "app_launch": set(), "panel_launch": set(),
        "cheatsheet": set()}
    try:
        binds = json.loads(raw)
    except json.JSONDecodeError:
        return result
    if not isinstance(binds, list):
        return result

    # Keyless __lua nav binds (Omarchy's workspace digits come through as
    # `code:N`, which `hyprctl binds -j` reports with an empty key). Their
    # descriptions still identify them, and their layout is fixed by Omarchy,
    # so we synthesize the digit key instead of losing the single most common
    # keyboard navigation there is.
    keyless_workspace_binds: list[tuple[int, int]] = []
    for bind in binds:
        if not isinstance(bind, dict):
            continue
        dispatcher = str(bind.get("dispatcher", ""))
        key = str(bind.get("key", "")).strip()
        description = str(bind.get("description") or "").strip()
        try:
            modmask = int(bind.get("modmask", 0))
        except (TypeError, ValueError):
            modmask = 0
        if modmask == 0:
            continue  # an un-modified bind can't be distinguished from typing

        if not key:
            if dispatcher == LUA_DISPATCHER and modmask and \
                    (match := _workspace_number(description)):
                keyless_workspace_binds.append((modmask, match))
            continue

        combo = (modmask, key.upper())
        if dispatcher in NAV_DISPATCHERS:
            result["nav"].add(combo)
        elif dispatcher == LUA_DISPATCHER and _is_nav_description(description):
            result["nav"].add(combo)
        elif dispatcher == LUA_DISPATCHER and description in APP_LAUNCH_DESCRIPTIONS:
            result["app_launch"].add(combo)
        elif dispatcher == LUA_DISPATCHER and description in PANEL_LAUNCH_DESCRIPTIONS:
            result["panel_launch"].add(combo)
        elif dispatcher == LUA_DISPATCHER and description in CHEATSHEET_DESCRIPTIONS:
            result["cheatsheet"].add(combo)
        # first match wins, checked nav -> app_launch -> panel_launch ->
        # cheatsheet; defensive only -- the four sources are disjoint by
        # construction.

    for modmask, workspace in keyless_workspace_binds:
        result["nav"].add((modmask, str(workspace % 10)))  # workspace 10 -> "0"
    return result


_WORKSPACE_NUMBER_RE = re.compile(
    r"^(?:Switch to|Move window(?: silently)? to) workspace (\d+)$")


def _workspace_number(description) -> int | None:
    text = str(description or "").strip()
    match = _WORKSPACE_NUMBER_RE.match(text)
    if not match:
        return None
    workspace = int(match.group(1))
    return workspace if 1 <= workspace <= 10 else None


def _is_nav_description(description) -> bool:
    text = str(description or "").strip()
    if not text:
        return False
    return any(pattern.match(text) for pattern in NAV_DESCRIPTION_PATTERNS)


class NavComboMatcher:
    """Tracks held-modifier state and checks a keydown against the live
    nav-dispatcher allowlist. Only ever consulted for combos with at least one
    modifier held -- a bare, unmodified keystroke never reaches here.

    Now serves four purposes -- nav / app-launch / panel-launch / cheatsheet
    detection -- all sharing the same held-modifier state tracking, since only
    one modifier-state machine is needed regardless of how many allowlists are
    checked against it. Class name kept as NavComboMatcher to minimize diff
    size; a rename is not required for the app-launch/cheatsheet addenda."""

    def __init__(self) -> None:
        self._allowlist: set[tuple[int, str]] = set()
        self._app_launch_allowlist: set[tuple[int, str]] = set()
        self._panel_launch_allowlist: set[tuple[int, str]] = set()
        self._cheatsheet_allowlist: set[tuple[int, str]] = set()
        self._held_shift = False
        self._held_ctrl = False
        self._held_alt = False
        self._held_super = False

    def update_allowlist(self, allowlist: set[tuple[int, str]]) -> None:
        self._allowlist = {(mask, key.upper()) for mask, key in allowlist}

    def update_app_launch_allowlist(self, allowlist: set[tuple[int, str]]) -> None:
        self._app_launch_allowlist = {(mask, key.upper()) for mask, key in allowlist}

    def update_panel_launch_allowlist(self, allowlist: set[tuple[int, str]]) -> None:
        self._panel_launch_allowlist = {(mask, key.upper()) for mask, key in allowlist}

    def update_cheatsheet_allowlist(self, allowlist: set[tuple[int, str]]) -> None:
        self._cheatsheet_allowlist = {(mask, key.upper()) for mask, key in allowlist}

    def on_modifier_event(self, code: int, pressed: bool) -> bool:
        """Feed KEY_LEFT/RIGHT{SHIFT,CTRL,ALT,META} down/up events. Returns
        True if this code was a tracked modifier (caller can skip it for
        other classification)."""
        if code in (e.KEY_LEFTSHIFT, e.KEY_RIGHTSHIFT):
            self._held_shift = pressed
        elif code in (e.KEY_LEFTCTRL, e.KEY_RIGHTCTRL):
            self._held_ctrl = pressed
        elif code in (e.KEY_LEFTALT, e.KEY_RIGHTALT):
            self._held_alt = pressed
        elif code in (e.KEY_LEFTMETA, e.KEY_RIGHTMETA):
            self._held_super = pressed
        else:
            return False
        return True

    @property
    def current_modmask(self) -> int:
        mask = 0
        if self._held_shift:
            mask |= MOD_BIT_SHIFT
        if self._held_ctrl:
            mask |= MOD_BIT_CTRL
        if self._held_alt:
            mask |= MOD_BIT_ALT
        if self._held_super:
            mask |= MOD_BIT_SUPER
        return mask

    def matches(self, code: int) -> bool:
        return self._matches_against(self._allowlist, code)

    def matches_app_launch(self, code: int) -> bool:
        return self._matches_against(self._app_launch_allowlist, code)

    def matches_panel_launch(self, code: int) -> bool:
        return self._matches_against(self._panel_launch_allowlist, code)

    def matches_cheatsheet(self, code: int) -> bool:
        return self._matches_against(self._cheatsheet_allowlist, code)

    def _matches_against(self, allowlist: set[tuple[int, str]], code: int) -> bool:
        modmask = self.current_modmask
        if modmask == 0:
            return False
        name = EVDEV_TO_HYPR_KEYNAME.get(code)
        if name is None:
            return False
        return (modmask, name) in allowlist
