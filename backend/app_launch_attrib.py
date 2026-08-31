"""Keybind-vs-panel attribution for app launches, correlated against
Hyprland's own openwindow>> event.

Not an Omarchy-documented convention -- our own timing-correlation
heuristic, same category as nav_attrib.py's NavAttributor. Only ever
timestamps are tracked in memory; window class/title from the triggering
openwindow>> line is never read, let alone stored.

Known limitation (documented, not fixed): an openwindow>> that fires for
an unrelated reason while a channel is still armed (e.g. a notification's
own window, or a second app the user manually started from a terminal
during the panel's long arm window) can be misattributed. This is
inherent to timing correlation without dispatcher-identity ground truth,
same accepted trade-off nav_attrib.py already documents for a personal
adoption metric.
"""

from __future__ import annotations

# An app-launch keybind press is usually followed within a couple of
# seconds by its window appearing; bounded generously for slow-starting
# apps (Docker Desktop, Obsidian cold start) without risking correlation
# with a much later, unrelated launch.
KEYBIND_ARM_WINDOW_S = 3.0

# The panel bind only opens the menu -- the actual launch (click or Enter
# after typing a filter) can be many seconds later. Bounded generously so
# "still browsing the menu" stays armed, but finite so a stale arm can't
# attribute an unrelated launch minutes later.
PANEL_ARM_WINDOW_S = 12.0


class AppLaunchAttributor:
    """Attributes an openwindow>> event to 'keybind', 'panel', or None."""

    def __init__(self,
                 keybind_window_s: float = KEYBIND_ARM_WINDOW_S,
                 panel_window_s: float = PANEL_ARM_WINDOW_S):
        self._keybind_window = keybind_window_s
        self._panel_window = panel_window_s
        self._keybind_armed_ts: float | None = None
        self._panel_armed_ts: float | None = None

    def note_keybind_press(self, monotonic_ts: float) -> None:
        """Call only when the keydown's (modmask, key) matches
        keybinds.py's live app_launch allowlist."""
        self._keybind_armed_ts = monotonic_ts

    def note_panel_press(self, monotonic_ts: float) -> None:
        """Call only when the keydown's (modmask, key) matches keybinds.py's
        live panel_launch allowlist (SUPER+SPACE / SUPER+ALT+SPACE)."""
        self._panel_armed_ts = monotonic_ts

    def on_openwindow(self, monotonic_ts: float) -> str | None:
        keybind_ok = self._within_window(
            self._keybind_armed_ts, monotonic_ts, self._keybind_window)
        panel_ok = self._within_window(
            self._panel_armed_ts, monotonic_ts, self._panel_window)

        if keybind_ok and panel_ok:
            # Most-recent-arm-wins, same tie-break NavAttributor uses for
            # simultaneous keyboard/mouse signals.
            winner = ("keybind" if self._keybind_armed_ts > self._panel_armed_ts
                      else "panel")
        elif keybind_ok:
            winner = "keybind"
        elif panel_ok:
            winner = "panel"
        else:
            return None

        # Single-shot consumption: clear the arm that was just used so a
        # second, closely-following openwindow>> (e.g. a second window
        # from the same app's own startup) isn't double-counted.
        if winner == "keybind":
            self._keybind_armed_ts = None
        else:
            self._panel_armed_ts = None
        return winner

    @staticmethod
    def _within_window(armed_ts: float | None, now_ts: float, window_s: float) -> bool:
        if armed_ts is None:
            return False
        delta = now_ts - armed_ts
        return 0 <= delta <= window_s
