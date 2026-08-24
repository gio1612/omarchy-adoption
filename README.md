# Omarchy Adoption Tracker

A local-only Omarchy bar-widget plugin that measures how much you actually
lean on Hyprland's keyboard-driven workflow versus the mouse:

- **Typing speed** (WPM), from short typing bursts
- **Keyboard vs. mouse navigation split**, for window/workspace switching
- **SUPER+K usage count** (how often you open Omarchy's keybindings cheatsheet)

Everything is derived and aggregated locally. **No raw keystrokes, characters,
or content are ever stored** -- only timing/counts. **No network calls.**

## Install (manual, one-time)

The Omarchy plugin installer never runs plugin code, install hooks, or sudo,
so nothing below happens automatically when you `omarchy plugin add` or
enable this plugin. Run it yourself, once:

```sh
bash ~/.config/omarchy/plugins/io.github.gio1612.omarchy-adoption/scripts/setup.sh
```

This will:
1. Check you're in the `input` group (needed to read `/dev/input/event*` --
   if not, it tells you the `usermod` command to run).
2. Install the background daemon + a Python venv under `~/.local/{lib,share}/omarchy-adoption-tracker/`.
3. Install and **enable at login** a `systemd --user` unit
   (`omarchy-adoption-tracker.service`) -- this is a deliberate divergence
   from Omarchy's usual "start on demand" plugin convention, since the whole
   point is continuous background measurement.
4. Add a small tracking wrapper around `SUPER+K` in your own
   `~/.config/hypr/bindings.lua` (inside a clearly marked block; it aborts
   instead of touching anything if you've already customized that binding).

Then add the "Adoption Tracker" bar widget from Omarchy's plugin/widget
picker. Until you run `setup.sh`, the widget simply shows "not connected".

To remove: `bash scripts/uninstall.sh` (add `--purge` to also delete the
local SQLite database).

## Privacy

- Raw keyboard/mouse events are classified in memory and discarded
  immediately -- only derived aggregates (WPM values, keyboard/mouse event
  counts, timestamps) ever reach disk.
- All data lives in one local SQLite file:
  `~/.local/share/omarchy-adoption-tracker/tracker.db`.
- No network calls, anywhere, ever.
- Raw per-event rows are pruned after 90 days by default; the small daily
  aggregate rollup is kept indefinitely so long-term trends survive.

## How it works (brief)

A small Python daemon (`backend/daemon.py`, installed by `setup.sh`) reads
`/dev/input/event*` for keyboard/mouse timing, Hyprland's own IPC event
socket for window/workspace changes, and a notification from the `SUPER+K`
wrapper -- and serves the resulting stats to the bar widget over a local Unix
socket. See the plugin's design notes for the full breakdown of the typing-
speed and navigation-attribution algorithms, including their known
limitations.

## Uninstall

```sh
bash ~/.config/omarchy/plugins/io.github.gio1612.omarchy-adoption/scripts/uninstall.sh [--purge]
```
