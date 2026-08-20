#!/usr/bin/env python3
"""Board query matching for Raft's Orca host.

Orca's ⌘J palette CREATES a worktree when a query matches nothing, so every
board query must provably match exactly one existing worktree. The matcher here
approximates Orca's (case-insensitive substring over worktree name, branch, and
repo); it is deliberately more conservative than Orca's fuzzy ranking, which is
why `raft_board_verify.py` exists rather than the generator being trusted.
"""
import json
import os
import subprocess

MAX_LABEL = 7
ORCA_DEFAULT = os.environ.get("ORCA_BIN", "/usr/local/bin/orca")


def haystacks(worktree):
    """Lowercased strings the palette matches this worktree on."""
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


def suggest_query(worktree, worktrees):
    """Shortest candidate matching only this worktree, or None if impossible."""
    candidates = sorted(set(haystacks(worktree)), key=len)
    for cand in candidates:
        if matches(cand, worktrees) == [worktree["worktreeId"]]:
            return cand
    # Fall back to a compound query: repo plus name usually disambiguates twins.
    branch = (worktree.get("branch") or "").replace("refs/heads/", "")
    for cand in (f"{worktree.get('repo') or ''} {branch}".strip(),):
        if cand and matches(cand, worktrees) == [worktree["worktreeId"]]:
            return cand
    return None


def check_board(slots, worktrees):
    """Human-readable problems with this board. [] means safe to push."""
    problems = []
    by_id = {w["worktreeId"]: w for w in worktrees}
    for i, slot in enumerate(slots, start=1):
        label = slot.get("label") or ""
        wid = slot.get("worktree")
        query = slot.get("query") or ""
        if len(label) > MAX_LABEL:
            problems.append(
                f"slot {i} ({label!r}): label exceeds {MAX_LABEL} characters")
        if wid not in by_id:
            problems.append(
                f"slot {i} ({label!r}): worktree {wid!r} no longer exists — its LED "
                f"will stay off")
        hits = matches(query, worktrees)
        if not hits:
            problems.append(
                f"slot {i} ({label!r}): query {query!r} matches nothing — pressing "
                f"this key would CREATE a worktree named {query!r}")
        elif len(hits) > 1:
            names = ", ".join(sorted(by_id[h].get("repo") or h for h in hits))
            problems.append(
                f"slot {i} ({label!r}): query {query!r} is ambiguous — matches "
                f"{len(hits)} worktrees ({names})")
        elif wid in by_id and hits[0] != wid:
            problems.append(
                f"slot {i} ({label!r}): query {query!r} selects the wrong worktree "
                f"({by_id[hits[0]].get('repo')} instead of {by_id[wid].get('repo')})")
    return problems


def load_worktrees(orca_bin=None):
    """Live `orca worktree ps` worktrees. Raises on failure — callers are CLIs."""
    out = subprocess.run([orca_bin or ORCA_DEFAULT, "worktree", "ps",
                          "--limit", "50", "--json"],
                         capture_output=True, text=True, timeout=20).stdout
    return json.loads(out)["result"]["worktrees"]
