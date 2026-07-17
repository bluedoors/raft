#!/usr/bin/env python3
"""duckypad_led.py — set a single duckyPad key LED over HID (command 0x04).

Requires the CUSTOM firmware that implements HID_COMMAND_SET_LED_SINGLE
(stock OG-duckyPad firmware returns status 6 / UNKNOWN_CMD — see the plan).
Opening the HID config interface needs ROOT on macOS, so this is invoked via
NOPASSWD sudo from Claude Code hooks (plan §6-A). It opens/closes the device
per call (no persistent handle → dodges the macOS keypress-lock bug) and
NO-OPS SILENTLY (exit 0) whenever the pad is absent or busy.

Usage:
  duckypad_led.py <workspace_ordinal> <state>   # state: working|needs|done|off
  duckypad_led.py --index <0-14> <R> <G> <B>    # light a raw physical LED (calibration)
  duckypad_led.py --all-off                     # clear all 15 LEDs

Run as root, e.g.:
  sudo /usr/local/libexec/duckypad_led.py 2 working
"""
import sys

VID, PID, CFG_USAGE, CFG_PAGE = 0x0483, 0xD11C, 0x3A, 0x0001
NEOPIXEL_COUNT = 15

# state -> RGB
STATE_COLOR = {
    "working": (255, 120, 0),    # amber: session active / thinking
    "needs":   (0, 90, 255),     # blue: waiting on you (permission / input)
    "done":    (0, 200, 0),      # green: finished, your turn
    "off":     (0, 0, 0),        # cleared
}

# Workspace ordinal (matches ⌘N) -> physical LED index 0-14.
# CALIBRATED 2026-07-17 for landscape, USB cable at top-left (portrait rotated
# 90deg CCW). Grid of LED indices in that orientation:
#     top:     2  5  8 11 14   <- workspace status row (WS1..WS5)
#     middle:  1  4  7 10 13
#     bottom:  0  3  6  9 12
# Only 5 keys in the top row, so workspaces 6+ get no status LED in this layout.
WS_LED_INDEX = {1: 2, 2: 5, 3: 8, 4: 11, 5: 14}


def _open_device():
    """Return an opened hid.device on the config interface, or None if absent."""
    try:
        import hid
    except Exception:
        return None
    try:
        path = None
        for d in hid.enumerate(VID, PID):
            if d.get("usage") == CFG_USAGE and d.get("usage_page") == CFG_PAGE:
                path = d["path"]
                break
        if path is None:
            return None
        h = hid.device()
        h.open_path(path)
        h.set_nonblocking(0)
        return h
    except Exception:
        return None


def _set_led(h, index, r, g, b):
    """Send one 0x04 Set-RGB-Single packet. Returns status byte or None."""
    buf = [0] * 64
    buf[0] = 0x05          # HID usage id (PC -> duckyPad)
    buf[2] = 0x04          # HID_COMMAND_SET_LED_SINGLE
    buf[3] = index & 0xFF
    buf[4], buf[5], buf[6] = r & 0xFF, g & 0xFF, b & 0xFF
    try:
        h.write(buf)
        resp = h.read(64, timeout_ms=200)
        return resp[2] if resp else None
    except Exception:
        return None


def main(argv):
    if len(argv) < 1:
        # No args: nothing to do. Silent success (hook-safe).
        return 0

    # Calibration: light all 15 with distinct colors + print a legend, so the
    # index -> physical-key mapping can be read straight off the pad. (Step 3.)
    if argv[0] == "--calibrate":
        palette = [
            (255, 0, 0), (0, 255, 0), (0, 60, 255), (255, 120, 0), (255, 0, 200),
            (0, 255, 255), (255, 255, 255), (140, 70, 0), (150, 0, 255), (255, 60, 90),
            (60, 255, 0), (0, 130, 120), (80, 0, 0), (0, 80, 0), (0, 0, 90),
        ]
        names = ["RED", "GREEN", "BLUE", "ORANGE", "MAGENTA", "CYAN", "WHITE",
                 "BROWN", "PURPLE", "PINK", "LIME", "TEAL", "DIM-RED", "DIM-GREEN", "DIM-BLUE"]
        h = _open_device()
        if h is None:
            print("duckyPad absent — cannot calibrate")
            return 0
        try:
            for i in range(NEOPIXEL_COUNT):
                _set_led(h, i, *palette[i])
        finally:
            h.close()
        print("Lit all 15 keys. Legend (LED index -> color):")
        for i, n in enumerate(names):
            print(f"  index {i:2d} = {n}")
        print("\nHold the pad in your LANDSCAPE orientation and tell me the color grid,")
        print("reading left->right, top->bottom (note which edge the USB cable is on).")
        return 0

    # Parse into (list of (index, r, g, b)) actions.
    actions = []
    if argv[0] == "--all-off":
        actions = [(i, 0, 0, 0) for i in range(NEOPIXEL_COUNT)]
    elif argv[0] == "--index":
        if len(argv) != 5:
            return 0
        try:
            idx = int(argv[1]); r, g, b = int(argv[2]), int(argv[3]), int(argv[4])
        except ValueError:
            return 0
        if not 0 <= idx < NEOPIXEL_COUNT:
            return 0
        actions = [(idx, r, g, b)]
    else:
        if len(argv) < 2:
            return 0
        try:
            ordinal = int(argv[0])
        except ValueError:
            return 0
        state = argv[1].lower()
        if ordinal not in WS_LED_INDEX or state not in STATE_COLOR:
            return 0
        r, g, b = STATE_COLOR[state]
        actions = [(WS_LED_INDEX[ordinal], r, g, b)]

    h = _open_device()
    if h is None:
        return 0                      # pad absent → silent no-op
    try:
        for idx, r, g, b in actions:
            _set_led(h, idx, r, g, b)
    finally:
        try:
            h.close()
        except Exception:
            pass
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
