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
import json
import argparse
import contextlib

_HERE = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, _HERE)


def _compiler():
    """Import duckypad_compile lazily.

    It hard-exits at import time when the duckyPad Configurator source is absent
    (RAFT_CONFIG_SRC), which is correct for generating a profile but would make
    the key tables untestable on a machine without that third-party toolchain.
    Only build() actually compiles.
    """
    import duckypad_compile
    return duckypad_compile

BG_COLOR = (0, 0, 0)

# Keys that talk to CLAUDE, not the host — identical on every host.
# physical key number -> (label<=7ch, duckyScript source, (r,g,b) color)
COMMON_KEYS = {
    # bottom row (Claude Code actions)
    1:  ("Yes",     "STRING yes\nENTER",      (0, 90, 0)),
    4:  ("No",      "STRING no\nENTER",       (90, 0, 0)),
    7:  ("/clear",  "STRING /clear\nENTER",   (90, 45, 0)),
    10: ("compact", "STRING /compact\nENTER", (90, 45, 0)),
    13: ("Auto/Pl", "SHIFT TAB",              (60, 0, 90)),  # plan / auto-accept
    # middle row, host-independent
    5:  ("New WS",  "GUI n",                  (0, 50, 60)),  # ⌘N on both hosts
    11: ("Rewind",  "ESCAPE\nESCAPE",         (60, 5, 28)),
    14: ("Intrpt",  "ESCAPE",                 (90, 20, 0)),
}

# Middle-row keys that differ per host.
HOST_KEYS = {
    "cmux": {
        2: ("Unread",  "GUI SHIFT u",         (0, 50, 60)),
        8: ("Next WS", "CTRL GUI ]",          (0, 50, 60)),
    },
    "orca": {
        # Orca has no jump-to-unread, so this becomes the bare switch palette.
        2: ("Jump",    "GUI j",               (0, 50, 60)),
        8: ("Next WT", "GUI SHIFT DOWNARROW", (0, 50, 60)),
    },
}

TOP_ROW = [3, 6, 9, 12, 15]          # physical keys, left→right in landscape
TOP_ROW_COLOR = (25, 25, 25)         # hooks override this live
# ⌘J → palette focused. MEASURED ON HARDWARE 2026-08-20: 150ms is far too short
# for a COLD open (the first jump after the app has been idle). When the palette
# is not yet focused, STRING types into whatever pane has focus — it leaked "raf"
# into a live agent's prompt — and the trailing ENTER would then SUBMIT that text
# as a prompt. Warm opens were fine at 150ms, which is exactly what makes a small
# value dangerous: it works until it doesn't. 500ms costs nothing perceptible.
PALETTE_OPEN_DELAY_MS = 500
PALETTE_FILTER_DELAY_MS = 400        # > the palette's ~300ms debounce; verified on
                                     # hardware with a 34-character query

MAX_LABEL = 7


def top_row_keys(host, slots, send_enter=True):
    """The five status/jump keys for `host`.

    cmux addresses workspaces positionally. Orca cannot: ⌘N indexes visible
    worktree rows in a tree whose order and collapse state its CLI does not
    expose, so each key types a uniqueness-checked query into the ⌘J palette.
    """
    keys = {}
    for i, keynum in enumerate(TOP_ROW):
        if host == "cmux":
            keys[keynum] = (f"WS{i + 1}", f"GUI {i + 1}", TOP_ROW_COLOR)
            continue
        if i >= len(slots):
            keys[keynum] = ("--", "", TOP_ROW_COLOR)     # unbound slot: inert key
            continue
        slot = slots[i]
        lines = ["GUI j",
                 f"DELAY {PALETTE_OPEN_DELAY_MS}",
                 f"STRING {slot['query']}",
                 f"DELAY {PALETTE_FILTER_DELAY_MS}"]
        if send_enter:
            lines.append("ENTER")
        label = (slot.get("label") or f"WT{i + 1}")[:MAX_LABEL]
        keys[keynum] = (label, "\n".join(lines), TOP_ROW_COLOR)
    return keys


def build(host, slots, out_dir, send_enter=True):
    """Write config.txt + key*.{txt,dsb} for one host into out_dir."""
    keys = dict(COMMON_KEYS)
    keys.update(HOST_KEYS[host])
    keys.update(top_row_keys(host, slots, send_enter=send_enter))
    duckypad_compile = _compiler()

    os.makedirs(out_dir, exist_ok=True)
    config = []
    # labels first (z<N>), then colors, matching the Configurator's ordering
    for n in sorted(keys):
        config.append(f"z{n} {keys[n][0]}")
    config.append("BG_COLOR %d %d %d" % BG_COLOR)
    config.append("DIM_UNUSED_KEYS 0")
    config.append("IS_LANDSCAPE 1")   # Configurator editing hint; firmware ignores it

    for n in sorted(keys):
        label, script, color = keys[n]
        # source
        with open(os.path.join(out_dir, f"key{n}.txt"), "w", newline="") as f:
            f.write(script)
        # compiled (suppress the compiler's chatty stdout)
        with contextlib.redirect_stdout(io.StringIO()):
            dsb = duckypad_compile.compile_ds(script) if script.strip() else b""
        with open(os.path.join(out_dir, f"key{n}.dsb"), "wb") as f:
            f.write(dsb)
        config.append("SWCOLOR_%d %d %d %d" % (n, color[0], color[1], color[2]))
        first = script.splitlines()[0] if script.strip() else "(inert)"
        print(f"key{n:<2} {label:<8} {first:<26} dsb={len(dsb)}B color={color}")

    with open(os.path.join(out_dir, "config.txt"), "w", newline="") as f:
        f.write("\n".join(config) + "\n")
    print(f"\nWrote profile to {out_dir}")


def main():
    ap = argparse.ArgumentParser(description="Generate a duckyPad profile for one host.")
    ap.add_argument("--host", choices=sorted(HOST_KEYS), default="cmux")
    ap.add_argument("--board", default=os.path.expanduser("~/.config/raft/board.json"))
    ap.add_argument("--out", default=None)
    ap.add_argument("--no-enter", action="store_true",
                    help="type the palette query but do not send ENTER")
    args = ap.parse_args()

    slots = []
    if args.host == "orca":
        try:
            with open(args.board) as f:
                slots = (json.load(f).get("slots") or [])[:len(TOP_ROW)]
        except Exception as e:
            print(f"no usable board at {args.board} ({e}) — top row will be inert.\n"
                  f"Run: python3 scripts/raft_board_init.py --slots …")
    out = args.out or os.path.join(_HERE, f"profile_{args.host}")
    build(args.host, slots, out, send_enter=not args.no_enter)


if __name__ == "__main__":
    main()
