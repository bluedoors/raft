#!/usr/bin/env python3
"""Check ~/.config/raft/board.json against live Orca. Exit 1 if a row is dead.

Run after deleting a worktree or rearranging the sidebar. Nothing here can
prevent a bad jump — ⌘1–⌘5 always land on real rows — so this is purely about
the LEDs telling the truth: a row pointing at a deleted worktree goes dark and
quietly stops reporting.
"""
import json
import os
import sys

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import raft_board as rb

BOARD_PATH = os.path.expanduser("~/.config/raft/board.json")


def main():
    path = sys.argv[1] if len(sys.argv) > 1 else BOARD_PATH
    try:
        with open(path) as f:
            doc = json.load(f)
    except Exception as e:
        print(f"cannot read {path}: {e}", file=sys.stderr)
        return 1
    slots = doc.get("slots") or []
    problems = rb.check_board(slots, rb.load_worktrees())
    if problems:
        for p in problems:
            print(f"PROBLEM: {p}", file=sys.stderr)
        print(f"\n{len(problems)} problem(s). Re-run raft_board_init.py --rows … "
              f"(no profile rebuild needed).", file=sys.stderr)
        return 1
    print(f"board OK — {len(slots)} row(s), every LED points at a live worktree")
    return 0


if __name__ == "__main__":
    sys.exit(main())
