# AGENTS.md

Guidance for AI agents working in this repo. Read this before making changes —
the deployment layout is the #1 source of confusion.

## What this is

An Omarchy (Hyprland/Quickshell) **bar-widget plugin** that tracks typing
speed (WPM), a keyboard-vs-mouse navigation split, SUPER+K cheatsheet usage,
and app-launch method (keybind vs. panel). A local Python daemon reads
`/dev/input/event*` + the Hyprland IPC socket, writes SQLite aggregates, and
serves them to the QML widget over a Unix socket.

- Front end: `BarWidget.qml`, `StatsPanel.qml`, `StatsFormat.js`, `BackendClient.qml`
- Back end: `backend/*.py` (daemon, evdev reader, storage, protocol, attributors)

**Privacy stance (hard constraint):** only derived aggregates are ever
persisted or surfaced. Raw key codes / coordinates / content are classified in
memory and discarded. Never add anything that leaks raw keystrokes, what was
typed, or exact cursor positions.

## Critical: this project has THREE copies

Edits in this repo do **NOT** reach the running plugin by themselves. There are
three separate locations:

| # | Location | What runs there |
|---|----------|-----------------|
| 1 | **this repo** (develop + test here) | source of truth |
| 2 | `~/.config/omarchy/plugins/io.github.gio1612.omarchy-adoption/` | where the shell loads the QML widget |
| 3 | `~/.local/lib/omarchy-adoption-tracker/` | where the systemd service runs `daemon.py` |

The daemon service: `omarchy-adoption-tracker.service` (user unit).

## Deploy changes: always via the script

```sh
bash scripts/deploy.sh            # sync #1->#2 +#3, restart daemon, reload shell
bash scripts/deploy.sh --no-shell # skip the shell reload
bash scripts/deploy.sh --dry-run  # preview, change nothing
```

`deploy.sh` copies root `*.qml`/`*.js`/`manifest.json` → #2, and `backend/*.py`
→ #2/backend and #3, then restarts the daemon and rescans the shell.

**Never** hand-`cp` files into #2 or #3, and never edit them directly or run
`git pull`/`omarchy plugin update` there as part of a normal dev loop — use
`deploy.sh`. (The plugin #2 is itself a git clone of this repo; long-term
*release* flow is commit+push → `git pull` in #2 → `deploy.sh`, but for
iterating, `deploy.sh` alone is correct.)

## Testing

```sh
# from repo root; uses tests/requirements.txt (pytest). A conftest.py at the
# repo root adds backend/ to sys.path.
.venv/bin/python -m pytest tests/ -q     # or just: python3 -m pytest tests/
```

## Live verification after a change

- Daemon recommends a new command answer over the real socket:
  `echo '{"v":1,"id":1,"command":"<cmd>"}' | socat - UNIX-CONNECT:"$XDG_RUNTIME_DIR/omarchy-adoption-tracker/daemon.sock"`
- QML picked up cleanly (no plugin errors): `journalctl --user -b --no-pager --since "-30 seconds" | grep -i omarchy-shell`
- Backend restarted cleanly: `journalctl --user -u omarchy-adoption-tracker.service -n 20 --no-pager`

## Validation

```sh
omarchy plugin validate <path-to-this-repo>
```

## Key behaviors to preserve

- **Mouse counts only deliberate actions:** button clicks (`BTN_*`), wheel
  scrolls (`REL_WHEEL`/`REL_HWHEEL`/hi-res), and **two-finger trackpad
  scrolls** (`TrackpadScrollDetector` in `backend/evdev_reader.py`). Single-
  finger / `REL_X`/`REL_Y` cursor motion is deliberately excluded — don't
  "fix" this into counting movement.
- **Debug audit logging:** a panel toggle ("Debug Audit", persisted
  `logging_enabled`) turns on an in-memory, non-persisted ring of
  classification labels (`mouse:click`, `mouse:wheel`, `mouse:trackpad-scroll`,
  `key`, device names) read via the `get_log` socket command. It's how the user
  verifies the tracker actually sees their input. Never make this persisted or
  more granular.
- `StatsFormat.js` is the single home for formatting/derivation logic.
- Widget click handling must stay on `WidgetButton` (see `BarWidget.qml`).
- Never commit secrets, and don't commit/push unless the user asks.
