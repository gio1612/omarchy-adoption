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
