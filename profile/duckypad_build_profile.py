#!/usr/bin/env python3
"""Generate the 'cmux' duckyPad profile (plan §9) as SD-card files.

Maps PHYSICAL key number -> action, using the calibrated landscape grid
(USB top-left). File keyN corresponds to LED index N-1:

  landscape LED-index grid        ->   key-file grid (LED idx + 1)
    top:    2  5  8 11 14                top:  key3  key6  key9  key12 key15  (WS1..WS5)
    mid:    1  4  7 10 13                mid:  key2  key5  key8  key11 key14
    bot:    0  3  6  9 12                bot:  key1  key4  key7  key10 key13

Needs a Python 3.10+ (the Configurator source uses 3.10+ syntax):
  python3 duckypad_build_profile.py
Writes ./profile_cmux/ next to this script (config.txt, keyN.txt, keyN.dsb).
"""
import os
import io
import sys
import contextlib

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)
import duckypad_compile

OUT = os.path.join(_HERE, "profile_cmux")

# physical key number -> (label<=7ch, duckyScript source, (r,g,b) color)
KEYS = {
    # bottom row (Claude Code actions)
    1:  ("Yes",     "STRING yes\nENTER",           (0, 90, 0)),
    4:  ("No",      "STRING no\nENTER",            (90, 0, 0)),
    7:  ("/clear",  "STRING /clear\nENTER",        (90, 45, 0)),
    10: ("compact", "STRING /compact\nENTER",      (90, 45, 0)),
    13: ("Auto/Pl", "SHIFT TAB",                   (60, 0, 90)),  # cycle plan / auto-accept mode
    # middle row (navigation / mode)
    2:  ("Unread",  "GUI SHIFT u",                 (0, 50, 60)),
    5:  ("New WS",  "GUI n",                       (0, 50, 60)),
    8:  ("Next WS", "CTRL GUI ]",                  (0, 50, 60)),
    11: ("Rewind",  "ESCAPE\nESCAPE",              (60, 5, 28)),
    14: ("Intrpt",  "ESCAPE",                      (90, 20, 0)),
    # top row (workspace jump + status LED; hooks override the color live)
    3:  ("WS1",     "GUI 1",                       (25, 25, 25)),
    6:  ("WS2",     "GUI 2",                       (25, 25, 25)),
    9:  ("WS3",     "GUI 3",                       (25, 25, 25)),
    12: ("WS4",     "GUI 4",                       (25, 25, 25)),
    15: ("WS5",     "GUI 5",                       (25, 25, 25)),
}
BG_COLOR = (0, 0, 0)


def main():
    os.makedirs(OUT, exist_ok=True)
    config = []
    # labels first (z<N>), then colors, matching the Configurator's ordering
    for n in sorted(KEYS):
        label, script, color = KEYS[n]
        config.append(f"z{n} {label}")
    config.append("BG_COLOR %d %d %d" % BG_COLOR)
    config.append("DIM_UNUSED_KEYS 0")
    config.append("IS_LANDSCAPE 1")   # Configurator editing hint; firmware ignores it

    for n in sorted(KEYS):
        label, script, color = KEYS[n]
        # source
        with open(os.path.join(OUT, f"key{n}.txt"), "w", newline="") as f:
            f.write(script)
        # compiled (suppress the compiler's chatty stdout)
        with contextlib.redirect_stdout(io.StringIO()):
            dsb = duckypad_compile.compile_ds(script)
        with open(os.path.join(OUT, f"key{n}.dsb"), "wb") as f:
            f.write(dsb)
        config.append("SWCOLOR_%d %d %d %d" % (n, color[0], color[1], color[2]))
        print(f"key{n:<2} {label:<8} {script.split(chr(10))[0]:<18} dsb={len(dsb)}B color={color}")

    with open(os.path.join(OUT, "config.txt"), "w", newline="") as f:
        f.write("\n".join(config) + "\n")
    print(f"\nWrote profile to {OUT}")
    print("config.txt:\n" + "\n".join("  " + l for l in config))


if __name__ == "__main__":
    main()
