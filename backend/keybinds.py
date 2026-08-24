"""Live nav-dispatcher keybind allowlist, built from `hyprctl binds -j`.

Not an Omarchy-documented convention -- we parse Hyprland's own JSON bind dump
so mouse-vs-keyboard attribution stays correct if the user rebinds things in
their own ~/.config/hypr/bindings.lua, rather than hardcoding default binds.
"""

from __future__ import annotations

import asyncio
import json

from evdev import ecodes as e

NAV_DISPATCHERS = frozenset({
    "workspace", "movetoworkspace", "movetoworkspacesilent",
    "movefocus", "focuswindow", "focusmonitor", "focusurgentorlast",
    "cyclenext", "changegroupactive",
})

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
    for bind in binds:
        if not isinstance(bind, dict):
            continue
        dispatcher = str(bind.get("dispatcher", ""))
        if dispatcher not in NAV_DISPATCHERS:
            continue
        key = str(bind.get("key", "")).strip()
        if not key:
            continue
        try:
            modmask = int(bind.get("modmask", 0))
        except (TypeError, ValueError):
            modmask = 0
        if modmask == 0:
            continue  # an un-modified nav bind can't be distinguished from typing
        allowlist.add((modmask, key.upper()))
    return allowlist


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
