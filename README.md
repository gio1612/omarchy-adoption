# Omarchy Adoption Tracker

[![CI](https://github.com/gio1612/omarchy-adoption/actions/workflows/ci.yml/badge.svg)](https://github.com/gio1612/omarchy-adoption/actions/workflows/ci.yml)

A local-only Omarchy bar-widget plugin that measures how much you actually
lean on Hyprland's keyboard-driven workflow versus the mouse:

- **Typing speed** (WPM), from short typing bursts
- **Keyboard vs. mouse navigation split**, for window/workspace switching
- **App launches**: keybind vs. the Omarchy/apps menu
- **SUPER+K usage count** (how often you open the keybindings cheatsheet)

Everything is derived and aggregated locally. **No raw keystrokes, characters,
or content are ever stored** — only timing/counts. **No network calls.**

---

## Install

```sh
omarchy plugin add https://github.com/gio1612/omarchy-adoption
bash ~/.config/omarchy/plugins/io.github.gio1612.omarchy-adoption/scripts/setup.sh
```

Then add the **Adoption Tracker** widget from Omarchy's plugin/widget picker.

### Why the second command

Omarchy's plugin installer never runs plugin code, install hooks, or `sudo`, so
nothing about the background daemon is set up by `omarchy plugin add`. Until you
run `setup.sh`, the widget shows "not connected".

`setup.sh` touches exactly three paths, all owned by this plugin:

| Path | What lands there |
|------|------------------|
| `~/.local/lib/omarchy-adoption-tracker/` | the daemon's Python modules |
| `~/.local/share/omarchy-adoption-tracker/` | its venv and the SQLite database |
| `~/.config/systemd/user/omarchy-adoption-tracker.service` | the user service |

It does **not** edit your Hyprland config, or any other configuration file.
`SUPER+K` is detected straight from the raw keyboard stream and matched against
the allowlist the daemon reads out of `hyprctl binds -j`, so
`~/.config/hypr/bindings.lua` stays exactly as you left it.

The service is **enabled at login** — a deliberate divergence from Omarchy's
usual "start on demand" plugin convention, since the whole point is continuous
background measurement.

### Prerequisite: the `input` group

Reading `/dev/input/event*` requires group membership. Without it the daemon
starts, runs, and measures **nothing** — every keyboard and pointer device is
permission-denied.

Check before you install:

```sh
bash scripts/setup.sh --check
```

If it tells you you're not in the `input` group:

```sh
sudo usermod -aG input $USER
# then log out and back in
```

You can confirm the daemon can actually see your hardware at any time:

```sh
~/.local/share/omarchy-adoption-tracker/venv/bin/python \
  ~/.local/lib/omarchy-adoption-tracker/daemon.py --self-test
```

It reports how many input devices are readable and how many of them are real
keyboards. If no keyboard is readable, the bar widget says **⚠ no input
access** and the panel shows the exact fix instead of an empty "no data yet".

### Updating

```sh
omarchy plugin update io.github.gio1612.omarchy-adoption
bash ~/.config/omarchy/plugins/io.github.gio1612.omarchy-adoption/scripts/setup.sh
```

Re-running `setup.sh` is safe and idempotent; it refreshes the daemon code and
restarts the service. Your database is untouched.

### Upgrading from a pre-0.2 install

Versions before 0.2 shipped a `setup.sh` that edited
`~/.config/hypr/bindings.lua` to inject (and later remove) a `SUPER+K` tracking
wrapper. Nothing in this plugin edits Hyprland config any more. If an old
install left a block behind, remove it yourself once:

```sh
grep -n "omarchy-adoption-tracker" ~/.config/hypr/bindings.lua
# if anything shows up, delete the BEGIN..END block by hand, then:
hyprctl reload
```

### Uninstall

```sh
bash ~/.config/omarchy/plugins/io.github.gio1612.omarchy-adoption/scripts/uninstall.sh [--purge]
omarchy plugin remove io.github.gio1612.omarchy-adoption
```

`--purge` also deletes the local SQLite database; without it your history is
kept in case you reinstall.

---

## Privacy

- Raw keyboard/mouse events are classified in memory and discarded
  immediately — only derived aggregates (WPM values, keyboard/mouse event
  counts, timestamps) ever reach disk.
- All data lives in one local SQLite file:
  `~/.local/share/omarchy-adoption-tracker/tracker.db`.
- No network calls, anywhere, ever.
- Raw per-event rows are pruned after 90 days; the small daily aggregate
  rollup is kept indefinitely so long-term trends survive. The sweep runs at
  most once per local day.

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
- Most keybind-driven app-launch day (min 5 launches)

Records use raw unweighted counts, so they stay stable if you later change the
calibration weight.

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

Values are clamped to `[0.1, 10.0]`. Only the *percentage* is weighted — raw
counts are always reported unweighted.

## How it works (brief)

A small Python daemon (`backend/daemon.py`) reads:

- `/dev/input/event*` for typing bursts and deliberate pointer actions —
  **button clicks, wheel scrolls and two-finger trackpad scrolls only;
  single-finger/cursor movement is ignored on purpose**;
- Hyprland's own IPC event socket for window/workspace changes and
  `openwindow` events;
- the raw `SUPER+K` cheatsheet combo off the keyboard stream.

It writes SQLite aggregates and serves them to the bar widget over a local Unix
socket (`$XDG_RUNTIME_DIR/omarchy-adoption-tracker/daemon.sock`), one JSON
object per line. See `DESIGN.md` for the full breakdown of the typing-speed and
attribution algorithms, including their known limitations.

## Debug audit logging

The panel has a **Debug Audit** toggle (default off) that turns on live,
in-memory logging of input classification, so you can verify the tracker really
is seeing your clicks, wheel/trackpad scrolls and keystrokes.

- The toggle is persisted (`logging_enabled`) and can be set from a socket too:
  ```sh
  echo '{"v":1,"id":1,"command":"set_logging","enabled":true}' | \
    socat - UNIX-CONNECT:$XDG_RUNTIME_DIR/omarchy-adoption-tracker/daemon.sock
  ```
- While on, the daemon keeps a bounded ring (400 lines) of labels like
  `device:... mouse:click`, `mouse:wheel`, `mouse:trackpad-scroll`, `key`, and
  the device names discovered on each rescan. Read it via the panel, or:
  ```sh
  echo '{"v":1,"id":1,"command":"get_log","limit":50}' | \
    socat - UNIX-CONNECT:$XDG_RUNTIME_DIR/omarchy-adoption-tracker/daemon.sock
  ```
- **Privacy:** the log lives only in memory, is cleared when you toggle off,
  and never contains raw key codes or coordinates — just classification
  labels. Nothing from it is written to disk.

## Troubleshooting

| Symptom | Check |
|---|---|
| Widget says "not connected" | `systemctl --user status omarchy-adoption-tracker.service` |
| Widget says "⚠ no input access" | `daemon.py --self-test` — you likely need the `input` group |
| Widget missing from the bar entirely | `journalctl --user -b \| grep -i omarchy-shell` for a QML load error |
| Numbers look wrong | turn on **Debug Audit** in the panel and watch what the daemon classifies |
| Daemon logs | `journalctl --user -u omarchy-adoption-tracker.service -f` |

## Development

See [`AGENTS.md`](AGENTS.md) for the repo layout, the deploy loop, and the
checks CI runs.

```sh
python3 -m pytest tests/ -q     # unit tests
python3 tools/smoke_daemon.py   # end-to-end: real socket, real shutdown
./tools/lint-qml.sh             # QML against the installed Omarchy shell
ruff check backend tests tools
```

## License

MIT
