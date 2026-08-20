#!/usr/bin/env python3
"""Capture anonymised Orca CLI fixtures for the Raft test suite.

  python3 scripts/raft_capture_fixtures.py

Writes tests/fixtures/worktree_{ps,list}.json. Requires a running Orca.
Free-text fields are dropped and identifiers are rewritten deterministically,
so the committed fixtures leak neither private prose nor real repo layout.
"""
import json
import os
import subprocess
import sys

ORCA = os.environ.get("ORCA_BIN", "/usr/local/bin/orca")
HERE = os.path.dirname(os.path.abspath(__file__))
FIXTURES = os.path.join(HERE, "..", "tests", "fixtures")

# Free text: replaced with a marker, never kept.
DROP_KEYS = ("prompt", "lastAssistantMessage", "preview", "toolInput",
             "taskTitle", "comment", "displayName", "title", "url")
# Identifiers: rewritten consistently via a first-seen counter.
MAP_KEYS = ("id", "worktreeId", "repoId", "projectId", "instanceId",
            "worktreeInstanceId", "path", "branch", "head", "paneKey",
            "parentWorktreeId", "projectHostSetupId", "repo",
            # `branchName`/`baseRef` are distinct from `branch`, and `owner` is the
            # GitHub org — all three leaked past the first pass.
            "branchName", "baseRef", "owner")


def orca_json(args):
    out = subprocess.run([ORCA, *args], capture_output=True, text=True,
                         timeout=20).stdout
    return json.loads(out)["result"]


class Anonymiser:
    def __init__(self):
        self.seen = {}

    def token(self, key, value):
        if value is None or not isinstance(value, str):
            return value
        if value not in self.seen:
            self.seen[value] = f"{key}-{len(self.seen) + 1}"
        return self.seen[value]

    def walk(self, node, key=None):
        if isinstance(node, dict):
            return {k: self.walk(v, k) for k, v in node.items()}
        if isinstance(node, list):
            return [self.walk(v, key) for v in node]
        if key in DROP_KEYS and isinstance(node, str):
            return "<dropped>"
        if key in MAP_KEYS:
            return self.token(key, node)
        return node


def main():
    os.makedirs(FIXTURES, exist_ok=True)
    anon = Anonymiser()
    for name, args in (("worktree_ps", ["worktree", "ps", "--limit", "50", "--json"]),
                       ("worktree_list", ["worktree", "list", "--json"])):
        data = anon.walk(orca_json(args))
        path = os.path.join(FIXTURES, f"{name}.json")
        with open(path, "w") as f:
            json.dump(data, f, indent=1, sort_keys=True)
        print(f"wrote {path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
