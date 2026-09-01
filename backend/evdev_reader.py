"""Evdev device discovery and raw keyboard/mouse event classification.

Rescans for hot-plugged devices, classifies each event, and immediately
discards the raw evdev event after classification -- nothing raw is queued or
persisted. Requires the running user to already be in the `input` group (no
root/setuid needed to read /dev/input/event*).

Optional audit logging: when `logging_enabled` is True, device discovery and
classifications are emitted to an `on_log` callback (wired by the daemon to a
transient in-memory log; nothing is persisted and no raw key codes /
coordinates are ever exposed -- only classification labels).
"""

from __future__ import annotations

import asyncio
import contextlib
import glob
import os
import time
from collections.abc import Callable

import evdev
from evdev import ecodes as e
from keybinds import NavComboMatcher
from wpm import TypingBurst, TypingTracker

RESCAN_INTERVAL_S = 20

# Keys that identify a device as a real typing keyboard rather than a
# power button, lid switch, or "System Control" node. A laptop with no
# readable keyboard cannot measure anything, which is worth reporting
# loudly instead of silently showing "no data yet" forever.
_KEYBOARD_PROBE_KEYS = (
    getattr(e, "KEY_A", 30), getattr(e, "KEY_S", 31), getattr(e, "KEY_SPACE", 57),
)

_MOUSE_BUTTONS = frozenset({
    e.BTN_LEFT, e.BTN_RIGHT, e.BTN_MIDDLE, e.BTN_SIDE, e.BTN_EXTRA,
})

# Only deliberate pointer actions count as "mouse navigation": button clicks,
# wheel scrolls and two-finger trackpad scrolls. Pointer *motion* is
# deliberately excluded -- moving the cursor happens constantly for
# non-navigation reasons and would swamp the keyboard-vs-mouse split.
_MOUSE_WHEEL = frozenset({
    getattr(e, "REL_WHEEL", 8), getattr(e, "REL_HWHEEL", 11),
    getattr(e, "REL_WHEEL_HI_RES", 12), getattr(e, "REL_HWHEEL_HI_RES", 13),
})

# Multitouch (protocol B) trackpad axes. A two-finger scroll on a touchpad
# shows up as >=2 concurrently active ABS_MT tracking slots whose positions
# move together -- a deliberate scroll/gesture action, analogous to a physical
# mouse's REL_WHEEL. Single-finger cursor motion is deliberately excluded,
# consistent with the REL_X/REL_Y exclusion above.
_ABS_MT_SLOT = getattr(e, "ABS_MT_SLOT", 47)
_ABS_MT_TRACKING_ID = getattr(e, "ABS_MT_TRACKING_ID", 57)
_ABS_MT_POSITION_X = getattr(e, "ABS_MT_POSITION_X", 53)
_ABS_MT_POSITION_Y = getattr(e, "ABS_MT_POSITION_Y", 54)
_ABS_MT_TRACKING_ID_EMPTY = -1

# A two-finger scroll must accumulate at least this many absolute units of
# movement before it counts, and each further chunk this size counts again --
# so both a quick flick and a long drag register, without per-scanline noise.
SCROLL_THRESHOLD = 40

# Minimum number of concurrent fingers before movement is treated as a
# deliberate two-finger scroll rather than single-finger cursor motion.
SCROLL_MIN_FINGERS = 2


class TrackpadScrollDetector:
    """Detects deliberate two-finger scroll gestures from multitouch (protocol
    B) trackpad events. Returns True from `feed` once a scroll chunk crosses
    the movement threshold while >=2 fingers are down. Only emits derived
    signals; raw coordinates are discarded after classification."""

    def __init__(self) -> None:
        self._slots: dict[int, int] = {}                  # slot -> tracking_id
        self._positions: dict[int, tuple[int, int]] = {}  # tracking_id -> (x, y)
        self._seen: dict[int, tuple[bool, bool]] = {}     # tracking_id -> (x_seen, y_seen)
        self._acc = 0
        self._active_slot = 0

    def feed(self, code: int, value: int) -> bool:
        """Process one ABS_MT event. Returns True when a scroll chunk fired."""
        if code == _ABS_MT_SLOT:
            self._active_slot = value
            return False

        if code == _ABS_MT_TRACKING_ID:
            slot = self._active_slot
            if value == _ABS_MT_TRACKING_ID_EMPTY:
                tid = self._slots.pop(slot, None)
                if tid is not None:
                    self._positions.pop(tid, None)
                    self._seen.pop(tid, None)
                if self._finger_count() < SCROLL_MIN_FINGERS:
                    self._acc = 0
                return False
            self._slots[slot] = value
            return False

        if code in (_ABS_MT_POSITION_X, _ABS_MT_POSITION_Y):
            tid = self._slots.get(self._active_slot)
            if tid is None:
                return False
            x, y = self._positions.get(tid, (0, 0))
            seen_x, seen_y = self._seen.get(tid, (False, False))
            if code == _ABS_MT_POSITION_X:
                moved = (value - x) if seen_x else 0  # first reading primes, no delta
                self._positions[tid] = (value, y)
                self._seen[tid] = (True, seen_y)
            else:
                moved = (value - y) if seen_y else 0
                self._positions[tid] = (x, value)
                self._seen[tid] = (seen_x, True)
            if self._finger_count() < SCROLL_MIN_FINGERS:
                return False
            self._acc += moved
            return self._flush_if_scroll()

        return False

    def _finger_count(self) -> int:
        return len(self._slots)

    def _flush_if_scroll(self) -> bool:
        if abs(self._acc) >= SCROLL_THRESHOLD:
            self._acc = 0
            return True
        return False


class EvdevSource:
    """Owns the TypingTracker (1:1 with the raw keyboard event stream) and
    drives a shared NavComboMatcher's held-modifier state. Emits only derived
    signals via callbacks -- never a raw event or key code."""

    def __init__(self, nav_matcher: NavComboMatcher,
                 on_typing_burst: Callable[[TypingBurst], None],
                 on_mouse_activity: Callable[[float], None],
                 on_keyboard_nav_combo: Callable[[float], None],
                 on_app_launch_keybind_combo: Callable[[float], None],
                 on_panel_launch_combo: Callable[[float], None],
                 on_cheatsheet_combo: Callable[[float], None],
                 logging_enabled: bool = False,
                 on_log: Callable[[str], None] | None = None):
        self._nav_matcher = nav_matcher
        self._on_typing_burst = on_typing_burst
        self._on_mouse_activity = on_mouse_activity
        self._on_keyboard_nav_combo = on_keyboard_nav_combo
        self._on_app_launch_keybind_combo = on_app_launch_keybind_combo
        self._on_panel_launch_combo = on_panel_launch_combo
        self._on_cheatsheet_combo = on_cheatsheet_combo
        self.logging_enabled = logging_enabled
        self._on_log = on_log
        self._typing = TypingTracker()
        self._stop = False
        self._devices: dict[str, asyncio.Task] = {}
        self._trackpads: dict[str, TrackpadScrollDetector] = {}
        # Input-access health, refreshed on every rescan. Without membership
        # of the `input` group (or a udev/ACL grant) most /dev/input/event*
        # nodes are EACCES, and the tracker silently measures nothing -- so
        # the counts are surfaced all the way to the panel.
        self._blocked_devices = 0
        self._total_devices = 0
        self._keyboards: set[str] = set()

    def _log(self, msg: str) -> None:
        if self.logging_enabled and self._on_log is not None:
            self._on_log(msg)

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

    def health(self) -> dict:
        """Input-access summary for the panel and the logs.

        `keyboards` is the one that matters: a session can happily open a
        power-button node and still be unable to see a single keystroke."""
        return {
            "readable": len(self._devices),
            "blocked": self._blocked_devices,
            "total": self._total_devices,
            "keyboards": len(self._keyboards),
        }

    def register_trackpad(self, path: str) -> TrackpadScrollDetector:
        """Marks `path` as a multitouch trackpad so its ABS_MT stream feeds a
        scroll detector. Called by _rescan for devices whose capabilities
        actually advertise ABS_MT_POSITION_X, and by tests that drive
        _handle_event directly.

        Registration is explicit on purpose: _handle_event used to create a
        detector for *any* device that emitted an EV_ABS event, which quietly
        enrolled graphics tablets, joysticks and lid switches as trackpads."""
        detector = self._trackpads.get(path)
        if detector is None:
            detector = TrackpadScrollDetector()
            self._trackpads[path] = detector
        return detector

    async def run(self) -> None:
        while not self._stop:
            # Device discovery opens every /dev/input/event* node and reads
            # its capabilities -- tens of blocking syscalls. Off the event
            # loop so a slow or wedged node cannot stall input handling.
            try:
                discovered = await asyncio.to_thread(self._discover)
            except OSError:
                discovered = []
            for path, device, is_trackpad, is_keyboard, name in discovered:
                if self._stop or path in self._devices:
                    device.close()
                    continue
                if is_trackpad:
                    self.register_trackpad(path)
                if is_keyboard:
                    self._keyboards.add(path)
                kinds = ("".join((" trackpad" if is_trackpad else "",
                                  " keyboard" if is_keyboard else "")))
                self._log(f"device:{path} name={name!r}{kinds}")
                self._devices[path] = asyncio.create_task(
                    self._read_device(path, device))
            await asyncio.sleep(RESCAN_INTERVAL_S)

    def _discover(self) -> list[tuple[str, object, bool, bool, str]]:
        """Blocking half of the rescan: opens newly appeared devices and
        reports (path, device, is_trackpad, is_keyboard, name) for each one we
        want to read. Runs on a worker thread; the caller owns task creation.

        Also refreshes the access-health counters. `evdev.list_devices()` only
        returns nodes the process can already open, so counting what is
        *missing* means globbing the directory ourselves -- otherwise a
        session locked out of every keyboard looks identical to a session with
        no keyboards attached."""
        all_paths = sorted(glob.glob("/dev/input/event*"))
        self._total_devices = len(all_paths)
        readable = set(evdev.list_devices())
        self._blocked_devices = sum(
            1 for path in all_paths
            if path not in readable and not os.access(path, os.R_OK))

        found: list[tuple[str, object, bool, bool, str]] = []
        for path in sorted(readable):
            if path in self._devices:
                continue
            try:
                device = evdev.InputDevice(path)
                capabilities = device.capabilities()
                name = device.name
            except OSError:
                continue
            if e.EV_KEY not in capabilities and e.EV_REL not in capabilities:
                device.close()
                continue
            keys = capabilities.get(e.EV_KEY, ())
            is_keyboard = all(code in keys for code in _KEYBOARD_PROBE_KEYS)
            has_mt = (e.EV_ABS in capabilities and
                      _ABS_MT_POSITION_X in capabilities.get(e.EV_ABS, {}))
            found.append((path, device, has_mt, is_keyboard, name))
        return found

    async def _read_device(self, path: str, device) -> None:
        try:
            async for event in device.async_read_loop():
                self._handle_event(event, path)
        except (OSError, asyncio.CancelledError):
            pass
        finally:
            self._devices.pop(path, None)
            self._trackpads.pop(path, None)
            self._keyboards.discard(path)
            with contextlib.suppress(OSError):
                device.close()

    def _handle_event(self, event, path: str | None = None) -> None:
        if event.type == e.EV_KEY:
            if path is not None:
                if event.code in _MOUSE_BUTTONS and event.value == 1:
                    self._log(f"device:{path} mouse:click")
                else:
                    self._log(f"device:{path} key")
            self._handle_key(event.code, event.value, time.monotonic(), time.time())
        elif event.type == e.EV_REL:
            if path is not None and event.code in _MOUSE_WHEEL:
                self._log(f"device:{path} mouse:wheel")
            self._handle_motion(event.code, event.value, time.monotonic())
        elif event.type == e.EV_ABS:
            # Only devices _rescan (or an explicit register_trackpad) marked
            # as multitouch trackpads feed the scroll detector. An EV_ABS
            # event from anything else is not pointer navigation.
            trackpad = self._trackpads.get(path) if path else None
            if trackpad is not None and trackpad.feed(event.code, event.value):
                self._log(f"device:{path} mouse:trackpad-scroll")
                self._on_mouse_activity(time.monotonic())

    def _handle_key(self, code: int, value: int, now: float, wall: float) -> None:
        if code in _MOUSE_BUTTONS:
            if value == 1:
                self._on_mouse_activity(now)
            return

        is_modifier = self._nav_matcher.on_modifier_event(code, pressed=value in (1, 2))
        if value == 1 and not is_modifier:
            if self._nav_matcher.matches(code):
                self._on_keyboard_nav_combo(now)
            if self._nav_matcher.matches_app_launch(code):
                self._on_app_launch_keybind_combo(now)
            if self._nav_matcher.matches_panel_launch(code):
                self._on_panel_launch_combo(now)
            if self._nav_matcher.matches_cheatsheet(code):
                # wall-clock timestamp: this one goes straight to storage,
                # unlike the nav channels which correlate in monotonic time.
                self._on_cheatsheet_combo(wall)

        burst = self._typing.on_key_event(code, value, now, wall)
        if burst is not None:
            self._on_typing_burst(burst)

    def _handle_motion(self, code: int, value: int, now: float) -> None:
        # Wheel ticks are deliberate scroll actions -> count as mouse activity.
        # Plain cursor motion (REL_X / REL_Y) is ignored on purpose.
        if code in _MOUSE_WHEEL:
            self._on_mouse_activity(now)
