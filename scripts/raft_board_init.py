#!/usr/bin/env python3
"""Write ~/.config/raft/board.json: which worktree each LED watches.

  python3 scripts/raft_board_init.py --list
  python3 scripts/raft_board_init.py --rows <sel1> <sel2> ... (up to 5)

The pad's top row sends ⌘1–⌘5, which Orca resolves to the Nth worktree row in
its sidebar. That makes the JUMP self-correcting — it cannot mistarget and
cannot create a worktree — but the LEDs still need to know *which* worktree each
row holds, and Orca's row order is not derivable from its CLI (we tried; see the
design doc).

So you tell Raft, by reading your own sidebar top to bottom:

  python3 scripts/raft_board_init.py --rows raft radar billing-api

Selectors are case-insensitive substrings of a worktree's name, branch or repo,
and must each match exactly one worktree — not because a wrong guess is
dangerous any more, but because a wrong LED is a lie.

Set Orca's worktree sidebar sort to **Manual** first, or the rows reshuffle as
agents change state and the LEDs drift out of step with the keys.
"""
import argparse
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import raft_board as rb

BOARD_PATH = os.path.expanduser("~/.config/raft/board.json")


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--list", action="store_true", help="show worktrees and exit")
    ap.add_argument("--rows", nargs="*", default=[],
                    help="up to 5 selectors, in sidebar row order (row 1 first)")
    ap.add_argument("--out", default=BOARD_PATH)
    args = ap.parse_args()

    worktrees = rb.load_worktrees()
    if args.list or not args.rows:
        print("Orca worktrees (set the sidebar sort to Manual, then read it top to "
              "bottom):\n")
        for w in worktrees:
            print(f"{str(w.get('repo')):24} {str(w.get('displayName'))!r:44} "
                  f"{(w.get('branch') or '').replace('refs/heads/','')}")
        print("\nThen: raft_board_init.py --rows <row1> <row2> ...")
        return 0

    if len(args.rows) > rb.MAX_SLOTS:
        print(f"at most {rb.MAX_SLOTS} rows (the top row has {rb.MAX_SLOTS} keys)",
              file=sys.stderr)
        return 2

    slots = []
    for row, selector in enumerate(args.rows, start=1):
        hits = rb.matches(selector, worktrees)
        if len(hits) != 1:
            print(f"row {row}: selector {selector!r} matched {len(hits)} worktrees "
                  f"— narrow it", file=sys.stderr)
            return 2
        w = next(x for x in worktrees if x["worktreeId"] == hits[0])
        slots.append({"label": str(row), "worktree": w["worktreeId"]})

    problems = rb.check_board(slots, worktrees)
    if problems:
        for p in problems:
            print(f"REFUSED: {p}", file=sys.stderr)
        return 1

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w") as f:
        json.dump({"host": "orca", "slots": slots}, f, indent=2)
    print(f"wrote {args.out}")
    by_id = {w["worktreeId"]: w for w in worktrees}
    for row, s in enumerate(slots, start=1):
        w = by_id[s["worktree"]]
        print(f"  key {row} (⌘{row}) watches {w.get('repo')} / "
              f"{(w.get('branch') or '').replace('refs/heads/','') or w.get('displayName')}")
    print("\nNo profile rebuild needed — the pad already sends ⌘1–⌘5.")
    print("Verify any time with: python3 scripts/raft_board_verify.py")
    return 0


if __name__ == "__main__":
    sys.exit(main())
