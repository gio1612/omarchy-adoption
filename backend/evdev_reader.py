"""Evdev device discovery and raw keyboard/mouse event classification.

Rescans for hot-plugged devices, classifies each event, and immediately
discards the raw evdev event after classification -- nothing raw is queued or
persisted. Requires the running user to already be in the `input` group (no
root/setuid needed to read /dev/input/event*).
"""

from __future__ import annotations

import asyncio
import time
from collections.abc import Callable

import evdev
from evdev import ecodes as e

from keybinds import NavComboMatcher
from wpm import TypingBurst, TypingTracker

RESCAN_INTERVAL_S = 20

_MOUSE_BUTTONS = frozenset({
    e.BTN_LEFT, e.BTN_RIGHT, e.BTN_MIDDLE, e.BTN_SIDE, e.BTN_EXTRA,
})

# Only deliberate pointer actions count as "mouse navigation": button clicks
# and wheel scrolls. Pointer *motion* is deliberately excluded -- moving the
# cursor happens constantly for non-navigation reasons and would swamp the
# keyboard-vs-mouse split.
_MOUSE_WHEEL = frozenset({
    getattr(e, "REL_WHEEL", 8), getattr(e, "REL_HWHEEL", 11),
    getattr(e, "REL_WHEEL_HI_RES", 12), getattr(e, "REL_HWHEEL_HI_RES", 13),
})


class EvdevSource:
    """Owns the TypingTracker (1:1 with the raw keyboard event stream) and
    drives a shared NavComboMatcher's held-modifier state. Emits only derived
    signals via callbacks -- never a raw event or key code."""

    def __init__(self, nav_matcher: NavComboMatcher,
                 on_typing_burst: Callable[[TypingBurst], None],
                 on_mouse_activity: Callable[[float], None],
                 on_keyboard_nav_combo: Callable[[float], None]):
        self._nav_matcher = nav_matcher
        self._on_typing_burst = on_typing_burst
        self._on_mouse_activity = on_mouse_activity
        self._on_keyboard_nav_combo = on_keyboard_nav_combo
        self._typing = TypingTracker()
        self._stop = False
        self._devices: dict[str, asyncio.Task] = {}

    def stop(self) -> None:
        self._stop = True
        for task in self._devices.values():
            task.cancel()

    def flush_typing(self) -> TypingBurst | None:
        """Force-close any open typing burst (daemon shutdown)."""
        return self._typing.flush(time.time())

    def check_idle(self) -> TypingBurst | None:
        """Call periodically so a burst closes even with no further keystrokes."""
        return self._typing.check_idle(time.monotonic(), time.time())

    async def run(self) -> None:
        while not self._stop:
            self._rescan()
            await asyncio.sleep(RESCAN_INTERVAL_S)

    def _rescan(self) -> None:
        try:
            paths = evdev.list_devices()
        except OSError:
            return
        for path in paths:
            if path in self._devices:
                continue
            try:
                device = evdev.InputDevice(path)
                capabilities = device.capabilities()
            except OSError:
                continue
            if e.EV_KEY not in capabilities and e.EV_REL not in capabilities:
                device.close()
                continue
            self._devices[path] = asyncio.create_task(self._read_device(path, device))

    async def _read_device(self, path: str, device) -> None:
        try:
            async for event in device.async_read_loop():
                self._handle_event(event)
        except (OSError, asyncio.CancelledError):
            pass
        finally:
            self._devices.pop(path, None)
            try:
                device.close()
            except OSError:
                pass

    def _handle_event(self, event) -> None:
        if event.type == e.EV_KEY:
            self._handle_key(event.code, event.value, time.monotonic(), time.time())
        elif event.type == e.EV_REL:
            self._handle_motion(event.code, event.value, time.monotonic())

    def _handle_key(self, code: int, value: int, now: float, wall: float) -> None:
        if code in _MOUSE_BUTTONS:
            if value == 1:
                self._on_mouse_activity(now)
            return

        is_modifier = self._nav_matcher.on_modifier_event(code, pressed=value in (1, 2))
        if value == 1 and not is_modifier and self._nav_matcher.matches(code):
            self._on_keyboard_nav_combo(now)

        burst = self._typing.on_key_event(code, value, now, wall)
        if burst is not None:
            self._on_typing_burst(burst)

    def _handle_motion(self, code: int, value: int, now: float) -> None:
        # Wheel ticks are deliberate scroll actions -> count as mouse activity.
        # Plain cursor motion (REL_X / REL_Y) is ignored on purpose.
        if code in _MOUSE_WHEEL:
            self._on_mouse_activity(now)
