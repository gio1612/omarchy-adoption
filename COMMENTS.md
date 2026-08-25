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
