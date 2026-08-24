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


async def fetch_nav_allowlist() -> set[tuple[int, str]]:
    """Runs `hyprctl binds -j` and returns the set of (modmask, KEY) pairs
    bound to a navigation dispatcher."""
    proc = await asyncio.create_subprocess_exec(
        "hyprctl", "binds", "-j",
        stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL)
    stdout, _ = await proc.communicate()
    return parse_binds_json(stdout.decode("utf-8", errors="replace"))


def parse_binds_json(raw: str) -> set[tuple[int, str]]:
    try:
        binds = json.loads(raw)
    except json.JSONDecodeError:
        return set()
    if not isinstance(binds, list):
        return set()

    allowlist: set[tuple[int, str]] = set()
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
        try:
            modmask = int(bind.get("modmask", 0))
        except (TypeError, ValueError):
            modmask = 0
        if modmask == 0:
            continue  # an un-modified nav bind can't be distinguished from typing

        if not key:
            if dispatcher == LUA_DISPATCHER and modmask and \
                    (match := _workspace_number(bind.get("description"))):
                keyless_workspace_binds.append((modmask, match))
            continue

        if dispatcher in NAV_DISPATCHERS:
            allowlist.add((modmask, key.upper()))
        elif dispatcher == LUA_DISPATCHER and _is_nav_description(bind.get("description")):
            allowlist.add((modmask, key.upper()))

    for modmask, workspace in keyless_workspace_binds:
        allowlist.add((modmask, str(workspace % 10)))  # workspace 10 -> "0"
    return allowlist


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
    modifier held -- a bare, unmodified keystroke never reaches here."""

    def __init__(self) -> None:
        self._allowlist: set[tuple[int, str]] = set()
        self._held_shift = False
        self._held_ctrl = False
        self._held_alt = False
        self._held_super = False

    def update_allowlist(self, allowlist: set[tuple[int, str]]) -> None:
        self._allowlist = {(mask, key.upper()) for mask, key in allowlist}

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
        modmask = self.current_modmask
        if modmask == 0:
            return False
        name = EVDEV_TO_HYPR_KEYNAME.get(code)
        if name is None:
            return False
        return (modmask, name) in self._allowlist
