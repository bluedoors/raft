#!/usr/bin/env python3
"""Board helpers for Raft's Orca host.

The board maps LED row -> worktreeId. Jumping is positional (⌘1–⌘5, resolved by
Orca), so nothing here affects where a key sends you; these helpers only decide
which worktree each LED reports on. `matches` exists so you can name a worktree
by substring instead of pasting a composite id, and `check_board` catches the one
failure that still matters: a row pointing at a worktree that no longer exists,
which would silently show a dark or wrong-coloured key.
"""
import json
import os
import subprocess

MAX_LABEL = 7
MAX_SLOTS = 5
ORCA_DEFAULT = os.environ.get("ORCA_BIN", "/usr/local/bin/orca")


def haystacks(worktree):
    """Lowercased strings a selector may match this worktree on."""
    branch = (worktree.get("branch") or "").replace("refs/heads/", "")
    fields = (worktree.get("displayName"), branch, worktree.get("repo"))
    return [f.lower() for f in fields if f]


def matches(query, worktrees):
    """worktreeIds whose haystacks contain `query` (case-insensitive)."""
    q = (query or "").strip().lower()
    if not q:
        return []
    return [w["worktreeId"] for w in worktrees
            if any(q in hay for hay in haystacks(w))]


def check_board(slots, worktrees):
    """Human-readable problems with this board. [] means every LED is truthful.

    Deliberately short now. The old version also had to prove each query matched
    exactly one worktree, because a stale query made Orca CREATE one; positional
    jumping removed that whole class of problem.
    """
    problems = []
    by_id = {w["worktreeId"]: w for w in worktrees}
    for i, slot in enumerate(slots, start=1):
        label = slot.get("label") or ""
        wid = slot.get("worktree")
        if len(label) > MAX_LABEL:
            problems.append(
                f"row {i} ({label!r}): label exceeds {MAX_LABEL} characters")
        if wid not in by_id:
            problems.append(
                f"row {i} ({label!r}): worktree {wid!r} no longer exists — this key's "
                f"LED will stay off while ⌘{i} still jumps somewhere")
    return problems


def load_worktrees(orca_bin=None):
    """Live `orca worktree ps` worktrees. Raises on failure — callers are CLIs."""
    out = subprocess.run([orca_bin or ORCA_DEFAULT, "worktree", "ps",
                          "--limit", "50", "--json"],
                         capture_output=True, text=True, timeout=20).stdout
    return json.loads(out)["result"]["worktrees"]
