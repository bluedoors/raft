#!/usr/bin/env python3
"""Generate a duckyPad profile ('cmux' or 'orca') as SD-card files.

Maps PHYSICAL key number -> action, using the calibrated landscape grid
(USB top-left). File keyN corresponds to LED index N-1:

  landscape LED-index grid        ->   key-file grid (LED idx + 1)
    top:    2  5  8 11 14                top:  key3  key6  key9  key12 key15  (1..5)
    mid:    1  4  7 10 13                mid:  key2  key5  key8  key11 key14
    bot:    0  3  6  9 12                bot:  key1  key4  key7  key10 key13

Needs a Python 3.10+ (the Configurator source uses 3.10+ syntax):
  python3 duckypad_build_profile.py --host orca
Writes ./profile_<host>/ next to this script (config.txt, keyN.txt, keyN.dsb).

The output does NOT depend on ~/.config/raft/board.json. Both hosts address the
top row positionally (⌘1–⌘5), so the profile is a constant: generate and push it
once, then rearrange your board freely without touching the pad again.
"""
import os
import io
import sys
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
    11: ("Rewind",  "ESCAPE\nESCAPE",         (60, 5, 28)),
    14: ("Intrpt",  "ESCAPE",                 (90, 20, 0)),
}

# Middle-row keys that differ per host. ⌘N is the same keystroke on both but
# means different things, so the label is per-host: cmux makes a workspace,
# Orca opens its create-WORKTREE flow.
HOST_KEYS = {
    "cmux": {
        2: ("Unread",  "GUI SHIFT u",         (0, 50, 60)),
        5: ("New WS",  "GUI n",               (0, 50, 60)),
        8: ("Next WS", "CTRL GUI ]",          (0, 50, 60)),
    },
    "orca": {
        # Orca has no jump-to-unread, so this becomes the bare switch palette.
        # Mostly redundant now that the top row is ⌘1–⌘5, but harmless and it
        # still reaches worktrees past row 9, which no key can address.
        2: ("Jump",    "GUI j",               (0, 50, 60)),
        5: ("New WT",  "GUI n",               (0, 50, 60)),
        8: ("Next WT", "GUI SHIFT DOWNARROW", (0, 50, 60)),
    },
}

TOP_ROW = [3, 6, 9, 12, 15]          # physical keys, left→right in landscape
TOP_ROW_COLOR = (25, 25, 25)         # hooks override this live

MAX_LABEL = 7


def top_row_keys(host, slots=None):
    """The five status/jump keys. Positional on BOTH hosts: ⌘1–⌘5.

    Orca's ⌘1–⌘9 selects the Nth worktree row in the sidebar, and with the
    sidebar's sort set to Manual that row order is whatever you dragged — it no
    longer churns as agents change state. So the key is a single instant
    keystroke that cannot mistarget: "go to row 3" is true by construction.

    The earlier Orca design typed a name into the ⌘J palette instead, because we
    believed row order was unknowable. It worked, but it cost ~900ms of delays,
    could type into a live prompt if the palette opened slowly, and — worst —
    CREATED a worktree when its saved query went stale. All three are gone.

    Labels are just "1".."5": which worktree a row holds is decided in Orca's
    sidebar, so baking a name into the pad would only go stale. `slots` is
    accepted and ignored for call-site compatibility.
    """
    return {keynum: (str(i + 1), f"GUI {i + 1}", TOP_ROW_COLOR)
            for i, keynum in enumerate(TOP_ROW)}


def build(host, out_dir):
    """Write config.txt + key*.{txt,dsb} for one host into out_dir."""
    keys = dict(COMMON_KEYS)
    keys.update(HOST_KEYS[host])
    keys.update(top_row_keys(host))
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
    ap.add_argument("--out", default=None)
    args = ap.parse_args()
    # Deliberately independent of ~/.config/raft/board.json: the top row is five
    # fixed keystrokes, so rearranging your board never needs a re-push.
    out = args.out or os.path.join(_HERE, f"profile_{args.host}")
    build(args.host, out)


if __name__ == "__main__":
    main()
