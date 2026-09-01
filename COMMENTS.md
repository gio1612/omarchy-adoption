# My Comments
The mouse usage need to be limited to clicks and scrolling, because if we measure with movement maybe is a lot.

Also I don't know if we need a calibration parameter, such as, weighting parameter of mouse vs keyboard.

---
## Addressed in iteration 2 (branch: iteration/2-mouse-clicks-and-calibration)

1. **Clicks + scroll only** -- cursor movement is no longer counted as mouse
   navigation. Only button presses and wheel ticks feed `NavAttributor`
   (`backend/evdev_reader.py`).
2. **Calibration weight added** -- configurable `mouse_weight` (default 1.0,
   clamped to [0.1, 10.0]) applied to the keyboard/mouse *percentage* only;
   raw counts stay untouched. Settable live via the daemon's
   `set_mouse_weight` command; see README "Calibration".

## Addressed in iteration 3 (branch: iteration/3-day-week-month-and-records)

3. **Day / week / month statistics** -- the widget's window setting now
   supports Today, This week (7 days), This month (30 days) and All-time.
4. **Daily reset + best-of-the-best KPIs** -- today's stats reset at local
   midnight as before, and the panel now shows an all-time records list:
   fastest typing burst, most keystrokes in a day, and the most
   keyboard-driven day (min 20 nav events so tiny days can't win by luck).

## Addressed in a follow-up (trackpad + audit logging)

Why the split read "~99% keyboard": the daemon counted clicks and physical
wheel scrolls (EV_KEY/BTN_*, EV_REL/REL_WHEEL) but ignored `EV_ABS`
multitouch, so a trackpad whose two-finger scroll only emits ABS_MT axes
never counted as mouse activity.

5. **Two-finger trackpad scroll detection** --
   `TrackpadScrollDetector` in `backend/evdev_reader.py` tracks concurrent
   ABS_MT slots and counts an accumulated two-finger movement crossing
   `SCROLL_THRESHOLD` as a mouse nav event (like a wheel tick). Single-finger
   cursor motion stays excluded, consistent with the REL_X/REL_Y decision.
6. **Debug audit logging** -- a panel toggle ("Debug Audit", persisted as
   `logging_enabled`) turns on a bounded in-memory ring of classification
   labels (`mouse:click`, `mouse:wheel`, `mouse:trackpad-scroll`, `key`,
   discovered device names) readable via the panel / `get_log`. Off by
   default; never persisted; cleared when toggled off. This is how you verify
   the tracker is actually seeing your pointer input.

## Addressed in the 0.2.0 refactor

Reported: "too many bugs, at this moment it is not working, from time to time
the project freeze."

**Why it wasn't working at all.** Two independent hard failures:

7. **The bar widget didn't load.** `StatsPanel.qml` assigned `borderSpec:` —
   a `qs.Ui` `BorderSurface` property — to a plain QtQuick `Rectangle`, in two
   places. The shell reported `Type StatsPanel unavailable` and dropped the
   whole widget. Fixed, and the hand-rolled chrome that invited it was
   replaced with the shell's own components. `tools/lint-qml.sh` now catches
   this class of error before it ships.
8. **The daemon could not see the keyboard.** This user is not in the `input`
   group, so 23 of 24 `/dev/input/event*` nodes are permission-denied; the
   only readable one was a "System Control" node. The daemon ran happily and
   measured nothing. Worse, `--self-test` passed, because it only checked that
   *some* device opened. Self-test now requires a readable keyboard, the
   daemon logs the verdict at startup, and the widget/panel surface it as
   "⚠ no input access" with the exact fix.

**Why it froze.**

9. **The Debug Audit view rebuilt up to 400 QML `Text` items every second** in
   an unvirtualized Column, on the UI thread. The daemon now returns a bounded
   tail (120 lines), the client skips the assignment when nothing changed, the
   poll dropped to 2s and is gated on visibility, and the view is a `ListView`.
10. **Derived arrays were recomputed inside bindings.** `Fmt.recordCards(...)`,
    `Fmt.keyboardTrendBars(...)` etc. were called directly in `model:` and
    `visible:`, allocating a fresh array each evaluation — and a fresh array as
    a `Repeater` model rebuilds every delegate. All memoized now.
11. **The socket client leaked in-flight requests.** `pending` was never
    cleared on disconnect and was copied on every send, so a long session did
    quadratic work on a timer. It is now mutated in place, cleared on
    disconnect, and reaped on timeout. Reconnect backoff went from a 300ms–5s
    spin to 400ms–30s.
12. **SQLite ran on the asyncio event loop**, so every flush stalled evdev
    reads. All storage calls now run on a worker thread behind a lock.
    Retention pruning — documented but never actually called — now runs once
    per local day, and only VACUUMs when it frees enough rows to be worth the
    stall.

**Other real bugs found and fixed.**

13. `sqlite3.ProgrammingError: Cannot operate on a closed database` crash-loop:
    shutdown closed storage while client handlers were still serving requests.
    Ordered shutdown + `StorageClosed` + a per-request error boundary.
14. Shutdown then hung on `server.wait_closed()` (which waits for live
    handlers) until systemd SIGKILLed it — found by the new smoke test.
15. Pushed `stats_update` always carried `today`, silently overwriting a panel
    set to "This week". Each client's window is tracked now.
16. `hypr_ipc` leaked a socket + transport on every reconnect.
17. `hyprctl binds -j` was unbounded, and is awaited from the Hyprland event
    read loop — a wedged hyprctl would stall all nav events. Now 5s-bounded.
18. Any device emitting `EV_ABS` was lazily enrolled as a trackpad, including
    tablets and lid switches. Enrollment is capability-checked now.
19. The panel had no scroll container, so with every section visible the
    records and Debug Audit sections fell off the bottom unreachably.

**Config hygiene.** `setup.sh` / `uninstall.sh` no longer edit
`~/.config/hypr/bindings.lua` (or call `hyprctl reload`). See README
"Upgrading from a pre-0.2 install" for the one-time manual cleanup.

**CI/CD.** `.github/workflows/ci.yml` (pytest on 3.11–3.13, ruff, shellcheck,
qmllint against a real Omarchy shell, `omarchy plugin validate` on a clean
export, and an end-to-end daemon smoke test) plus
`.github/workflows/release.yml` (tag `v*` → re-run CI, verify tag ==
manifest == `DAEMON_VERSION`, publish release notes).
