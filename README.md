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

The tracker never touches your Hyprland keybindings: `SUPER+K` is detected
straight from the raw keyboard stream (via `hyprctl binds` + evdev), so your
`~/.config/hypr/bindings.lua` stays exactly as you left it. If you're
upgrading from a pre-1.x install that injected a tracking wrapper block,
`setup.sh` removes that legacy block and restores the stock binding
automatically.

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

## Calibration

The keyboard-vs-mouse split supports a **mouse weight** (`mouse_weight`,
default `1.0`): each mouse navigation event is counted as that many keyboard
events when the split percentage is computed.

- `1.0` — raw counts (a click and a keybind are equivalent).
- `> 1.0` — treats mouse actions as a bigger departure from keyboard-first
  workflow (e.g. `2.0`: 90 keys / 10 clicks reads as 82% keyboard).
- `< 1.0` — discounts mouse actions (e.g. you navigate mostly with a
  scroll wheel and don't want it to dominate).

Set it live without restarting the daemon:

```sh
echo '{"v":1,"id":1,"command":"set_mouse_weight","value":2.0}' | \
  socat - UNIX-CONNECT:$XDG_RUNTIME_DIR/omarchy-adoption-tracker/daemon.sock
```

Values are clamped to `[0.1, 10.0]`. Only the *percentage* is weighted —
raw counts are always reported unweighted.

## Stats windows & records

The widget's `window` setting selects the displayed range: **Today**,
**This week** (last 7 days), **This month** (last 30 days), or **All-time**.
Today's numbers reset at local midnight by construction.

Because each day resets, the panel also keeps a **Best of the best** list of
all-time personal bests:

- Fastest typing burst (WPM) and when it happened
- Most keystrokes in a single day
- Most keyboard-driven day (highest keyboard nav %, among days with at least
  20 navigation events so a 2-event day can't top the board)

Records use raw unweighted counts, so they stay stable if you later change
the calibration weight.

## How it works (brief)

A small Python daemon (`backend/daemon.py`, installed by `setup.sh`) reads
`/dev/input/event*` for typing bursts and deliberate pointer actions --
**button clicks, wheel scrolls and two-finger trackpad scrolls only; single
finger/cursor movement is ignored on purpose** -- Hyprland's own IPC event
socket for window/workspace changes, and the raw `SUPER+K` cheatsheet combo
off the keyboard stream -- and serves the resulting stats to the bar widget
over a local Unix socket. See the plugin's design notes for the full breakdown
of the typing-speed and navigation-attribution algorithms, including their
known limitations.

## Debug audit logging

The panel has a **Debug Audit** toggle (default off) that turns on live,
in-memory logging of input classification so you can verify the tracker really
is seeing your clicks, wheel/trackpad scrolls and keystrokes -- handy when the
keyboard-vs-mouse split looks suspicious (e.g. a trackpad whose scrolls didn't
register, which historically read as "99% keyboard").

- The toggle is persisted (`logging_enabled`) and can be set live from a
  socket too:
  ```sh
  echo '{"v":1,"id":1,"command":"set_logging","enabled":true}' | \
    socat - UNIX-CONNECT:$XDG_RUNTIME_DIR/omarchy-adoption-tracker/daemon.sock
  ```
- While on, the daemon records a bounded ring (up to 400 lines) of labels like
  `device:... mouse:click`, `mouse:wheel`, `mouse:trackpad-scroll`, `key`, and
  the device names discovered on each rescan. Read it via the panel's
  **Refresh** button or:
  ```sh
  echo '{"v":1,"id":1,"command":"get_log"}' | \
    socat - UNIX-CONNECT:$XDG_RUNTIME_DIR/omarchy-adoption-tracker/daemon.sock
  ```
- **Privacy:** the log lives only in memory, is cleared when you toggle off,
  and never contains raw key codes or coordinates -- just classification
  labels. Nothing from it is written to disk.

## Uninstall

```sh
bash ~/.config/omarchy/plugins/io.github.gio1612.omarchy-adoption/scripts/uninstall.sh [--purge]
```
