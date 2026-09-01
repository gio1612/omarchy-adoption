# AGENTS.md

Guidance for AI agents working in this repo. Read this before making changes —
the deployment layout is the #1 source of confusion.

## What this is

An Omarchy (Hyprland/Quickshell) **bar-widget plugin** that tracks typing
speed (WPM), a keyboard-vs-mouse navigation split, SUPER+K cheatsheet usage,
and app-launch method (keybind vs. panel). A local Python daemon reads
`/dev/input/event*` + the Hyprland IPC socket, writes SQLite aggregates, and
serves them to the QML widget over a Unix socket.

**Privacy stance (hard constraint):** only derived aggregates are ever
persisted or surfaced. Raw key codes / coordinates / content are classified in
memory and discarded. Never add anything that leaks raw keystrokes, what was
typed, or exact cursor positions.

**Config stance (hard constraint):** this project owns exactly three paths
(see "Three copies" below) and nothing else. Never edit `~/.config/hypr/`, or
any other application's configuration, from a script or the daemon. Reading
Hyprland state (`hyprctl binds -j`, the event socket) is fine; writing is not.

## Layout

Front end (QML, loaded by the Omarchy shell):

| File | Role |
|---|---|
| `BarWidget.qml` | manifest entry point; owns the bar label, settings, and the panel Loader |
| `BackendClient.qml` | JSON-lines Unix-socket client with backoff + request bookkeeping |
| `StatsPanel.qml` | popup composition and **all** derivation; no hand-drawn chrome |
| `SplitBar.qml` | two-segment A-vs-B percentage bar (nav split, app launches) |
| `Sparkline.qml` | WPM trend canvas |
| `TrendBars.qml` | per-day keyboard-share bars |
| `RecordsList.qml` | "Best of the best" cards |
| `AuditLogSection.qml` | Debug Audit toggle + virtualized log tail |
| `StatsFormat.js` | pure formatting/derivation helpers, shared by all of the above |

Back end (`backend/*.py`):

| File | Role |
|---|---|
| `daemon.py` | lifecycle + socket protocol dispatch table (`_COMMANDS`) |
| `storage.py` | SQLite aggregates, retention sweep, `StorageClosed` |
| `evdev_reader.py` | device discovery, event classification, input-access health |
| `hypr_ipc.py` | Hyprland socket2 event client with reconnect |
| `keybinds.py` | live allowlists parsed from `hyprctl binds -j` |
| `nav_attrib.py`, `app_launch_attrib.py`, `wpm.py` | attribution heuristics |
| `protocol.py` | newline-delimited JSON request/response/event helpers |

## Critical: this project has THREE copies

Edits in this repo do **NOT** reach the running plugin by themselves:

| # | Location | What runs there |
|---|----------|-----------------|
| 1 | **this repo** (develop + test here) | source of truth |
| 2 | `~/.config/omarchy/plugins/io.github.gio1612.omarchy-adoption/` | where the shell loads the QML widget |
| 3 | `~/.local/lib/omarchy-adoption-tracker/` | where the systemd service runs `daemon.py` |

```sh
bash scripts/deploy.sh            # sync #1 -> #2 + #3, restart daemon, reload shell
bash scripts/deploy.sh --no-shell # skip the shell reload
bash scripts/deploy.sh --dry-run  # preview, change nothing
```

**Never** hand-`cp` files into #2 or #3, and never edit them directly. Release
flow is commit + push + tag; users install with `omarchy plugin add`.

## Checks — run these before saying anything works

```sh
python3 -m pytest tests/ -q      # unit tests
python3 tools/smoke_daemon.py    # boots the real daemon on a real socket,
                                 # SIGTERMs it, asserts a clean shutdown
./tools/lint-qml.sh              # qmllint against the installed Omarchy shell
ruff check backend tests tools
./tools/check-version.sh         # manifest.json version == DAEMON_VERSION
```

**`tools/lint-qml.sh` is not optional.** The QML front end has no unit tests,
and a bad property assignment does not fail until the shell reloads. It once
shipped `borderSpec:` (a `BorderSurface` property) on a plain `Rectangle`,
which made `StatsPanel.qml` unloadable and took the entire bar widget offline
with only a line in the journal to show for it. The linter catches exactly
that, but only because it resolves `qs.Ui` / `qs.Commons` against a real
Omarchy shell tree. CI shallow-clones `basecamp/omarchy` to get one.

Prefer the shell's own `qs.Ui` components (`BorderSurface`, `Button`,
`ToggleSwitch`, `PanelSectionHeader`, `PanelSeparator`, `PanelActionButton`,
`WidgetButton`) over hand-rolled `Rectangle`s. Every one of those hand-rolled
blocks was a place this bug could recur.

## Live verification after a change

```sh
# daemon answers over the real socket
echo '{"v":1,"id":1,"command":"stats","window":"today"}' | \
  socat - UNIX-CONNECT:"$XDG_RUNTIME_DIR/omarchy-adoption-tracker/daemon.sock"

# QML loaded cleanly (no plugin errors)
journalctl --user -b --no-pager --since "-30 seconds" | grep -i omarchy-shell

# daemon restarted cleanly
journalctl --user -u omarchy-adoption-tracker.service -n 20 --no-pager
```

`omarchy plugin validate <path>` validates the manifest, but only on a tree
with no symlinks — run it on `git archive HEAD`, not on a working tree that
has a `.venv`.

## Key behaviors to preserve

- **Mouse counts only deliberate actions:** button clicks (`BTN_*`), wheel
  scrolls (`REL_WHEEL`/`REL_HWHEEL`/hi-res), and **two-finger trackpad
  scrolls** (`TrackpadScrollDetector`). Single-finger / `REL_X`/`REL_Y` cursor
  motion is deliberately excluded — don't "fix" this into counting movement.
- **Trackpad enrollment is explicit.** Only devices whose capabilities
  advertise `ABS_MT_POSITION_X` get a scroll detector. Do not reintroduce lazy
  registration from any `EV_ABS` event — that enrolled tablets and lid
  switches as trackpads.
- **Nothing blocks the event loop.** Every SQLite call goes through
  `Daemon._db()` (worker thread + lock); device discovery goes through
  `asyncio.to_thread`. Adding a synchronous DB call back onto the loop
  reintroduces the stalls this refactor removed.
- **Shutdown order is load-bearing.** Cancel client tasks *before*
  `server.wait_closed()`, and close storage *last*. Getting this wrong caused
  both a `sqlite3.ProgrammingError` crash-loop and a hang until systemd's
  `TimeoutStopSec` SIGKILLed the service. `tools/smoke_daemon.py` guards it.
- **Storage never raises sqlite errors past the socket.** Post-close access
  raises `StorageClosed`, which the daemon turns into a `shutting_down`
  protocol error.
- **`get_log` is bounded.** The panel polls it; returning the whole 400-line
  ring on every poll is what made the shell hitch.
- **Derived arrays are memoized in `StatsPanel.qml`.** Calling a `Fmt.*`
  helper inline in a binding allocates a fresh array, and a fresh array as a
  `Repeater` model rebuilds every delegate.
- `StatsFormat.js` is the single home for formatting/derivation logic.
- Widget click handling must stay on `WidgetButton` (see `BarWidget.qml`).
- Never commit secrets, and don't commit/push unless the user asks.

## Versioning & release

`manifest.json` `version` and `backend/daemon.py` `DAEMON_VERSION` must match;
`tools/check-version.sh` enforces it and CI runs it. A release is a `v*` tag on
the default branch — `.github/workflows/release.yml` re-runs the full CI suite,
checks tag/manifest agreement, and publishes GitHub release notes. There is no
build artifact: `omarchy plugin add` clones the repository.
