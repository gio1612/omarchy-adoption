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
