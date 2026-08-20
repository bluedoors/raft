#!/usr/bin/env python3
"""Repaint the whole duckyPad board from Orca's current truth, now.

Switching pad profiles clears host LED overrides, and a Codex/Gemini pane never
fires Raft's hook, so this fills the board in without waiting for a Claude event.

  python3 scripts/duckypad_repaint.py
"""
import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "sender"))
import duckypad_hook as hook


def main():
    board = hook.load_board()
    if not board:
        print(f"no board at {hook.BOARD_PATH} — run scripts/raft_board_init.py",
              file=sys.stderr)
        return 1
    worktrees = hook.orca_ps_worktrees()
    if not worktrees:
        print("orca worktree ps returned nothing — is Orca running?", file=sys.stderr)
        return 1
    states = hook.orca_board(board, worktrees)
    result = hook._set_board("orca", states)
    for ordinal, state in sorted(states.items()):
        print(f"  key {ordinal}: {state}")
    rc = getattr(result, "returncode", None)
    if rc not in (0, None):
        print(f"LED write returned {rc}: {getattr(result, 'stderr', '')}",
              file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
