"""Mouse-vs-keyboard attribution for Hyprland window/workspace navigation.

Not an Omarchy-documented convention -- our own timing-correlation heuristic.
Only ever timestamps are tracked in memory; nothing about *what* was pressed
or clicked is persisted.

Known limitation (documented, not fixed): a bound combo that happens to be
followed within the correlation window by an unrelated focus change (e.g. a
notification popup stealing focus) can be misattributed as "keyboard nav".
This is inherent to timing correlation without dispatcher-identity ground
truth, and is an acceptable trade-off for a personal adoption metric.
"""

from __future__ import annotations

CORRELATION_WINDOW_S = 0.4
COALESCE_WINDOW_S = 0.08


class NavAttributor:
    """Attributes a Hyprland nav episode to 'keyboard', 'mouse', or None."""

    def __init__(self, correlation_window_s: float = CORRELATION_WINDOW_S):
        self._window = correlation_window_s
        self._last_mouse_ts: float | None = None
        self._last_kbd_nav_ts: float | None = None

    def note_mouse_activity(self, monotonic_ts: float) -> None:
        """Call on a mouse button press or wheel-scroll tick -- both are
        decided by the caller (evdev_reader). Pointer motion is never
        forwarded, so it can't contaminate the split."""
        self._last_mouse_ts = monotonic_ts

    def note_keyboard_nav_combo(self, monotonic_ts: float) -> None:
        """Call only when the keydown's (modmask, key) matches the live
        nav-dispatcher allowlist from keybinds.py -- never for a bare typing
        keystroke, so normal prose never touches this channel."""
        self._last_kbd_nav_ts = monotonic_ts

    def attribute(self, episode_ts: float) -> str | None:
        kbd_ok = self._within_window(self._last_kbd_nav_ts, episode_ts)
        mouse_ok = self._within_window(self._last_mouse_ts, episode_ts)
        if kbd_ok and mouse_ok:
            return "keyboard" if self._last_kbd_nav_ts > self._last_mouse_ts else "mouse"
        if kbd_ok:
            return "keyboard"
        if mouse_ok:
            return "mouse"
        return None

    def _within_window(self, ts: float | None, episode_ts: float) -> bool:
        if ts is None:
            return False
        delta = episode_ts - ts
        return 0 <= delta <= self._window


class EpisodeCoalescer:
    """Coalesces bursts of related Hyprland events (e.g. activewindow and
    workspace firing together for one user action) into a single nav episode,
    keyed on the earliest event's timestamp."""

    def __init__(self, coalesce_window_s: float = COALESCE_WINDOW_S):
        self._window = coalesce_window_s
        self._pending_ts: float | None = None

    def add_event(self, monotonic_ts: float) -> float | None:
        """Returns the episode timestamp to attribute now if this event opens
        a new episode, or None if it was merged into the still-open one."""
        if self._pending_ts is not None and (monotonic_ts - self._pending_ts) <= self._window:
            return None
        self._pending_ts = monotonic_ts
        return monotonic_ts
