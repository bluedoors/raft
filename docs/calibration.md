# LED calibration — index vs. physical key

The firmware addresses each key LED by a flat **LED index** `0–14` (via the
firmware's `pixel_map`). The host sends "set LED index N to color", but *which
physical key* index N lights up depends on how you are physically holding the
pad. This doc explains the default calibration and how to redo it for a
different orientation.

## Default orientation: landscape, USB at top-left

Everything in Raft (the `WS_LED_INDEX` map in `sender/duckypad_led.py`, the
`KEYS` layout in `profile/duckypad_build_profile.py`) is calibrated for the pad
held in **landscape** with the **USB cable exiting at the top-left** (i.e. the
physical portrait pad rotated 90° counter-clockwise).

In that orientation the LED indices fall on the 3×5 grid like this:

```
        col1 col2 col3 col4 col5
 top:     2    5    8   11   14      <- workspace status row (WS1..WS5)
 mid:     1    4    7   10   13
 bot:     0    3    6    9   12
```

So the top-row workspace status LEDs are indices **2, 5, 8, 11, 14**, which is
exactly `WS_LED_INDEX = {1: 2, 2: 5, 3: 8, 4: 11, 5: 14}`. Only 5 keys are in
the top row, so workspaces 6+ get no status LED in this layout.

## Key-file numbering vs. LED index

The profile stores per-key files as `keyN.txt` / `keyN.dsb`, numbered `1–15`
(the duckyPad's 1-based key numbering). These are offset by one from the
0-based LED index:

> **key-file N  ⟷  LED index N − 1**

For example, key-file `key3` is LED index `2` (top-left workspace key, `WS1`).
`profile/duckypad_build_profile.py` uses this relationship directly (see the
grid in its docstring).

## Re-calibrating for a different orientation

If you mount the pad differently (portrait, USB at bottom, etc.), the physical
position of each LED index changes and you must remap.

1. **Light every LED with a distinct color and print a legend:**

   ```bash
   sudo /usr/local/libexec/duckypad_led.py --calibrate
   # or, before install:
   sudo python3 sender/duckypad_led.py --calibrate
   ```

   This lights all 15 keys and prints `index N = COLOR`. It also works as a
   raw single-LED test:

   ```bash
   sudo python3 sender/duckypad_led.py --index <0-14> <R> <G> <B>
   ```

   (`scripts/duckypad_ledtest.py` is a similar hold-test that keeps colors on
   for several seconds.)

2. **Hold the pad in your chosen orientation** and write down the color grid
   left→right, top→bottom, noting which edge the USB cable is on. Convert each
   color back to its index using the printed legend. That gives you the LED
   index at each physical position.

3. **Update `WS_LED_INDEX`** in `sender/duckypad_led.py` so ordinal 1 maps to
   the top-left status key's index in *your* grid, ordinal 2 to the next, etc.

4. **Update the profile layout** in `profile/duckypad_build_profile.py` if you
   want the key labels/actions to follow the same physical arrangement, then
   rebuild and re-push (see [`../profile/README.md`](../profile/README.md)).
