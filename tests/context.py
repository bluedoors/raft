"""Path setup + fixture loading for Raft's tests (no package layout in this repo)."""
import json
import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SENDER = os.path.join(ROOT, "sender")
SCRIPTS = os.path.join(ROOT, "scripts")
PROFILE = os.path.join(ROOT, "profile")
FIXTURES = os.path.join(os.path.dirname(os.path.abspath(__file__)), "fixtures")

for _p in (SENDER, SCRIPTS, PROFILE):
    if _p not in sys.path:
        sys.path.insert(0, _p)


def load_fixture(name):
    """Load tests/fixtures/<name>.json."""
    with open(os.path.join(FIXTURES, f"{name}.json")) as f:
        return json.load(f)
