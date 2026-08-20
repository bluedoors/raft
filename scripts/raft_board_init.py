#!/usr/bin/env python3
"""Write ~/.config/raft/board.json from live Orca worktrees.

  python3 scripts/raft_board_init.py --list
  python3 scripts/raft_board_init.py --slots <worktree-substring> [... up to 5]

Each --slots argument selects a worktree the same way you'd type it into Orca's
⌘J palette. The board is refused unless every selector resolves to exactly one
worktree, because a query that matches nothing makes the palette CREATE one.
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
    ap.add_argument("--slots", nargs="*", default=[],
                    help="up to 5 selectors, in key order")
    ap.add_argument("--out", default=BOARD_PATH)
    args = ap.parse_args()

    worktrees = rb.load_worktrees()
    if args.list or not args.slots:
        for w in worktrees:
            print(f"{str(w.get('repo')):24} {str(w.get('displayName'))!r:44} "
                  f"{(w.get('branch') or '').replace('refs/heads/','')}")
        return 0

    if len(args.slots) > 5:
        print("at most 5 slots (the top row has 5 keys)", file=sys.stderr)
        return 2

    slots = []
    for selector in args.slots:
        hits = rb.matches(selector, worktrees)
        if len(hits) != 1:
            print(f"selector {selector!r} matched {len(hits)} worktrees — "
                  f"narrow it", file=sys.stderr)
            return 2
        w = next(x for x in worktrees if x["worktreeId"] == hits[0])
        query = rb.suggest_query(w, worktrees)
        if query is None:
            print(f"{w.get('repo')}: no query can uniquely select this worktree "
                  f"— rename its branch", file=sys.stderr)
            return 2
        label = (w.get("repo") or w.get("displayName") or "wt")[:rb.MAX_LABEL]
        slots.append({"label": label, "worktree": w["worktreeId"], "query": query})

    problems = rb.check_board(slots, worktrees)
    if problems:
        for p in problems:
            print(f"REFUSED: {p}", file=sys.stderr)
        return 1

    os.makedirs(os.path.dirname(args.out), exist_ok=True)
    with open(args.out, "w") as f:
        json.dump({"host": "orca", "slots": slots}, f, indent=2)
    print(f"wrote {args.out}")
    for i, s in enumerate(slots, 1):
        print(f"  key {i}: {s['label']:8} query={s['query']!r}")
    print("\nNow regenerate and push the profile:")
    print("  python3 profile/duckypad_build_profile.py --host orca")
    print("  sudo python3 profile/duckypad_push_profile.py --profile orca")
    return 0


if __name__ == "__main__":
    sys.exit(main())
