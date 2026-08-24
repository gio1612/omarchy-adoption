"""Typing-speed classification and burst segmentation.

Classifies raw evdev keydowns into typing bursts and computes WPM. Only ever
returns/persists derived aggregates (duration, keystroke count, WPM) -- never
which keys were pressed. Raw key codes are consulted transiently, in memory,
purely to classify the event, then discarded.
"""

from __future__ import annotations

from dataclasses import dataclass

from evdev import ecodes as e

IDLE_GAP_MS = 2000
MIN_KEYSTROKES = 5
MIN_DURATION_MS = 300
CHARS_PER_WORD = 5

# Modifiers that indicate "this keydown is probably a keybind, not prose" for
# WPM-gating purposes. Shift is deliberately excluded here: Shift+letter is
# ordinary typing (capitals, punctuation), not a navigation combo. Ctrl/Alt/
# Super are the modifiers Hyprland binds actually use for dispatchers.
NAV_GATING_MODIFIERS = frozenset({
    e.KEY_LEFTCTRL, e.KEY_RIGHTCTRL,
    e.KEY_LEFTALT, e.KEY_RIGHTALT,
    e.KEY_LEFTMETA, e.KEY_RIGHTMETA,
})

_LETTERS = frozenset(getattr(e, f"KEY_{c}") for c in "ABCDEFGHIJKLMNOPQRSTUVWXYZ")
_DIGITS_ROW = frozenset(getattr(e, f"KEY_{d}") for d in "0123456789")
_KEYPAD_DIGITS = frozenset(getattr(e, f"KEY_KP{d}") for d in "0123456789")

TYPING_KEYS = frozenset(_LETTERS | _DIGITS_ROW | _KEYPAD_DIGITS | {
    e.KEY_SPACE, e.KEY_MINUS, e.KEY_EQUAL, e.KEY_LEFTBRACE, e.KEY_RIGHTBRACE,
    e.KEY_SEMICOLON, e.KEY_APOSTROPHE, e.KEY_GRAVE, e.KEY_BACKSLASH,
    e.KEY_COMMA, e.KEY_DOT, e.KEY_SLASH, e.KEY_ENTER, e.KEY_KPENTER,
    e.KEY_BACKSPACE, e.KEY_KPDOT,
})


@dataclass
class TypingBurst:
    ended_at: float  # unix epoch seconds (wall clock)
    duration_ms: int
    keystroke_count: int
    wpm: float


def compute_wpm(keystroke_count: int, duration_ms: int) -> float:
    duration_min = max(duration_ms, 500) / 60000
    return (keystroke_count / CHARS_PER_WORD) / duration_min


class TypingTracker:
    """Feed it evdev keydowns one at a time; it emits closed typing bursts."""

    def __init__(self, idle_gap_ms: int = IDLE_GAP_MS,
                 min_keystrokes: int = MIN_KEYSTROKES,
                 min_duration_ms: int = MIN_DURATION_MS):
        self._idle_gap_ms = idle_gap_ms
        self._min_keystrokes = min_keystrokes
        self._min_duration_ms = min_duration_ms
        self._held_gating_modifiers: set[int] = set()
        self._burst_start: float | None = None
        self._burst_last: float | None = None
        self._burst_count = 0

    def on_key_event(self, code: int, value: int, monotonic_ts: float,
                      wall_ts: float) -> TypingBurst | None:
        """Feed one raw evdev key event. Returns a closed burst, if any."""
        if code in NAV_GATING_MODIFIERS:
            if value == 0:
                self._held_gating_modifiers.discard(code)
            elif value == 1:
                self._held_gating_modifiers.add(code)
            return None

        if value != 1:
            return None
        if code not in TYPING_KEYS or self._held_gating_modifiers:
            return None

        closed = None
        if self._burst_last is not None and \
                (monotonic_ts - self._burst_last) * 1000 > self._idle_gap_ms:
            closed = self._close(wall_ts)

        if self._burst_start is None:
            self._burst_start = monotonic_ts
        self._burst_last = monotonic_ts
        self._burst_count += 1
        return closed

    def check_idle(self, monotonic_ts: float, wall_ts: float) -> TypingBurst | None:
        """Call periodically so a burst closes even with no further keystrokes."""
        if self._burst_last is None:
            return None
        if (monotonic_ts - self._burst_last) * 1000 > self._idle_gap_ms:
            return self._close(wall_ts)
        return None

    def flush(self, wall_ts: float) -> TypingBurst | None:
        """Force-close whatever burst is open (daemon shutdown)."""
        return self._close(wall_ts)

    def _close(self, wall_ts: float) -> TypingBurst | None:
        start, last, count = self._burst_start, self._burst_last, self._burst_count
        self._burst_start = None
        self._burst_last = None
        self._burst_count = 0
        if start is None or last is None:
            return None
        duration_ms = max(0, int((last - start) * 1000))
        if count < self._min_keystrokes or duration_ms < self._min_duration_ms:
            return None
        return TypingBurst(
            ended_at=wall_ts,
            duration_ms=duration_ms,
            keystroke_count=count,
            wpm=round(compute_wpm(count, duration_ms), 1),
        )
