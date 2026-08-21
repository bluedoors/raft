# Raft Orca Host Support Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Let Raft drive the duckyPad's status LEDs and jump keys from Orca as well as cmux, without regressing the cmux path.

**Architecture:** A host adapter seam inside `sender/duckypad_hook.py` picks cmux or Orca from the firing session's environment. The cmux adapter keeps today's single-key positional behaviour. The Orca adapter repaints all five keys from `orca worktree ps --json`, taking the firing worktree's state from the hook payload to dodge a race with Orca's own sibling hook. Orca's sidebar index is neither positional nor readable from its CLI, so keys map to worktrees through a Raft-owned `~/.config/raft/board.json`, and jumping types a uniqueness-checked query into Orca's `⌘J` palette.

**Tech Stack:** Python 3.10+ (stdlib only for the hook and tests; `hidapi` for the LED writer), duckyScript compiled by the vendored `duckypad_compile.py`, `orca` CLI as a subprocess, `unittest` for tests.

**Read first:** `docs/superpowers/specs/2026-08-18-orca-host-support-design.md`. Its "Probe log" section records measured Orca behaviour that several tasks depend on; do not re-derive it.

## Global Constraints

- **No firmware change.** The `0x04` Set-RGB-Single command and the existing six colors are the whole LED vocabulary: `working` amber `(255,120,0)`, `needs` blue `(0,90,255)`, `done` green `(0,200,0)`, `failed` red `(255,0,0)`, `idle` dim purple `(40,0,60)`, `off` `(0,0,0)`.
- **No sudoers change.** The installed rule is `<user> ALL=(root) NOPASSWD: /usr/local/libexec/duckypad-venv/bin/python3 /usr/local/libexec/duckypad_led.py *`, so any new argument shape is already allowed. Do not edit `/etc/sudoers.d/duckypad`.
- **No daemon.** Status arrives on Claude Code hooks. Detached one-shot sleepers are permitted; long-running processes are not.
- **`sender/duckypad_hook.py` must stay a single standalone file** with stdlib-only imports. It is installed by copying one file (`~/claude/duckypad_hook.py` in the current setup); it must not import project modules.
- **Ordinal → LED index is fixed:** `{1: 2, 2: 5, 3: 8, 4: 11, 5: 14}` (calibrated landscape, USB top-left). Ordinal *N* is board slot *N*.
- **duckyPad key labels are ≤7 characters.**
- **All hooks are `async: true`** and must `exit 0` on every path, including every failure. A hook must never block or fail a Claude session.
- **`orca` CLI calls get `timeout=3`** and must degrade rather than raise.
- **macOS only** for sender/hooks/profile scripts.
- **Fade window** is `FADE_DELAY_SEC`, default `120`, overridable by `DUCKYPAD_FADE_SEC`.
- **Tests run with:** `python3 -m unittest discover -s tests -v` from the repo root. No third-party test dependencies.
- **Orca agent state enum** is exactly `waiting`, `blocked`, `interrupted`, `working`, `done`, `idle`.

---

### Task 1: Test scaffold and scrubbed Orca fixtures

Every later task tests against captured Orca output. This task makes that possible and commits the fixtures, so no later task needs a live Orca.

**Files:**
- Create: `tests/context.py`
- Create: `tests/fixtures/worktree_ps.json`
- Create: `tests/fixtures/worktree_list.json`
- Create: `scripts/raft_capture_fixtures.py`
- Create: `tests/test_fixtures.py`

**Interfaces:**
- Consumes: nothing.
- Produces: `tests/context.py` exposing `SENDER`, `SCRIPTS`, `PROFILE`, `FIXTURES` (absolute path strings) and `load_fixture(name) -> dict`. Later tasks import it as `from context import load_fixture`.

- [ ] **Step 1: Write the capture/scrub script**

`scripts/raft_capture_fixtures.py` — anonymises before writing, because fixtures are committed to a public repo. Real repo names, paths and branch names are replaced with deterministic synthetic ones; free-text fields (prompts, assistant messages, terminal previews) are dropped entirely.

```python
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
             "taskTitle", "comment", "displayName", "title")
# Identifiers: rewritten consistently via a first-seen counter.
MAP_KEYS = ("id", "worktreeId", "repoId", "projectId", "instanceId",
            "worktreeInstanceId", "path", "branch", "head", "paneKey",
            "parentWorktreeId", "projectHostSetupId", "repo")


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
```

- [ ] **Step 2: Run it against live Orca and inspect the result**

Run: `python3 scripts/raft_capture_fixtures.py && python3 -c "import json;d=json.load(open('tests/fixtures/worktree_ps.json'));print(len(d['worktrees']))"`
Expected: prints two "wrote …" lines and a worktree count ≥ 1.

Then grep to prove nothing private survived:

Run: `grep -ric "$(whoami)\|your-org\|your-repos" tests/fixtures/ || echo CLEAN`
Expected: `CLEAN`. If not, add the leaking key to `DROP_KEYS` or `MAP_KEYS` and re-run.

- [ ] **Step 3: Hand-edit the ps fixture to cover the cases the live machine lacks**

The live capture will not contain every state. Edit `tests/fixtures/worktree_ps.json` so that, across its `worktrees[]`, all of these exist (add entries by copying an existing one and changing the fields):

- a worktree whose `agents` is `[]`
- a worktree with one agent `{"state": "working", "interrupted": false}`
- a worktree with two agents: `{"state": "done", ...}` and `{"state": "waiting", ...}`
- a worktree with one agent `{"state": "working", "interrupted": true}`
- a worktree with one agent `{"state": "blocked", "interrupted": false}`
- a worktree with one agent `{"state": "done", "interrupted": false, "updatedAt": 1000}` — an ancient `done`, for fade tests
- a worktree whose `parentWorktreeId` points at another fixture worktree's `worktreeId`

Every agent needs an `updatedAt` integer (epoch ms). Keep `worktreeId` values as the anonymiser wrote them.

- [ ] **Step 4: Write the shared test context and a fixture smoke test**

`tests/context.py`:

```python
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
```

`tests/test_fixtures.py`:

```python
import unittest

from context import load_fixture


class TestFixtures(unittest.TestCase):
    def test_ps_fixture_covers_every_state(self):
        wts = load_fixture("worktree_ps")["worktrees"]
        states = {a["state"] for w in wts for a in (w.get("agents") or [])}
        self.assertEqual(
            states,
            {"waiting", "blocked", "working", "done"},
            "fixture must exercise every state the mapping branches on",
        )

    def test_ps_fixture_has_empty_interrupted_and_child_cases(self):
        wts = load_fixture("worktree_ps")["worktrees"]
        self.assertTrue(any(not (w.get("agents") or []) for w in wts))
        self.assertTrue(any(a.get("interrupted")
                            for w in wts for a in (w.get("agents") or [])))
        self.assertTrue(any(w.get("parentWorktreeId") for w in wts))

    def test_every_agent_has_updated_at(self):
        wts = load_fixture("worktree_ps")["worktrees"]
        for w in wts:
            for a in (w.get("agents") or []):
                self.assertIsInstance(a.get("updatedAt"), int)
```

Note: `idle` is deliberately absent from the asserted state set — Orca reports it rarely and the mapping treats it identically to `interrupted`, which *is* covered.

- [ ] **Step 5: Run the tests**

Run: `python3 -m unittest discover -s tests -v`
Expected: 3 tests, all PASS. If `test_ps_fixture_covers_every_state` fails, the Step 3 edits are incomplete — the failure message lists the states actually present.

- [ ] **Step 6: Commit**

```bash
git add tests/ scripts/raft_capture_fixtures.py
git commit -m "test: anonymised Orca fixtures and test scaffold"
```

---

### Task 2: Orca agent state → LED state

Pure function, no I/O. Encodes the precedence table and folds the fade into the mapping so nothing has to *remember* that a green is stale.

**Files:**
- Modify: `sender/duckypad_hook.py` (add constants + one function near the top, after `VALID_STATES`)
- Create: `tests/test_orca_state.py`

**Interfaces:**
- Consumes: `tests/context.py` from Task 1.
- Produces:
  - `ORCA_TO_RAFT: dict[str, str]`
  - `ORCA_PRECEDENCE: tuple[str, ...]`
  - `orca_led_state(agents, now_ms=None, fade_sec=None) -> str` — returns one of `working|needs|done|failed|idle|off`. `agents` is the raw `worktree ps` `agents` list (may be `None`).
  - `fade_deadline_ms(agents, fade_sec=None) -> int | None` — epoch ms at which a `done` in this list becomes `off`, or `None`.

- [ ] **Step 1: Write the failing tests**

`tests/test_orca_state.py`:

```python
import unittest

from context import load_fixture
import duckypad_hook as h


class TestOrcaLedState(unittest.TestCase):
    def test_no_agents_is_off(self):
        self.assertEqual(h.orca_led_state([]), "off")
        self.assertEqual(h.orca_led_state(None), "off")

    def test_single_states_map(self):
        cases = {
            "waiting": "needs",
            "blocked": "failed",
            "working": "working",
            "done": "done",
            "idle": "idle",
            "interrupted": "idle",
        }
        for orca, raft in cases.items():
            with self.subTest(orca=orca):
                agents = [{"state": orca, "interrupted": False, "updatedAt": 5_000}]
                self.assertEqual(h.orca_led_state(agents, now_ms=5_000), raft)

    def test_waiting_outranks_everything(self):
        agents = [
            {"state": "done", "interrupted": False, "updatedAt": 5_000},
            {"state": "working", "interrupted": False, "updatedAt": 5_000},
            {"state": "waiting", "interrupted": False, "updatedAt": 5_000},
        ]
        self.assertEqual(h.orca_led_state(agents, now_ms=5_000), "needs")

    def test_blocked_outranks_working(self):
        agents = [
            {"state": "working", "interrupted": False, "updatedAt": 5_000},
            {"state": "blocked", "interrupted": False, "updatedAt": 5_000},
        ]
        self.assertEqual(h.orca_led_state(agents, now_ms=5_000), "failed")

    def test_interrupted_flag_beats_reported_state(self):
        agents = [{"state": "working", "interrupted": True, "updatedAt": 5_000}]
        self.assertEqual(h.orca_led_state(agents, now_ms=5_000), "idle")

    def test_stale_done_fades_to_off(self):
        agents = [{"state": "done", "interrupted": False, "updatedAt": 1_000}]
        now = 1_000 + 121_000
        self.assertEqual(h.orca_led_state(agents, now_ms=now, fade_sec=120), "off")

    def test_fresh_done_stays_green(self):
        agents = [{"state": "done", "interrupted": False, "updatedAt": 1_000}]
        now = 1_000 + 119_000
        self.assertEqual(h.orca_led_state(agents, now_ms=now, fade_sec=120), "done")

    def test_stale_done_does_not_mask_a_fresh_waiting(self):
        agents = [
            {"state": "done", "interrupted": False, "updatedAt": 1_000},
            {"state": "waiting", "interrupted": False, "updatedAt": 120_000},
        ]
        self.assertEqual(
            h.orca_led_state(agents, now_ms=1_000 + 200_000, fade_sec=120), "needs")

    def test_unknown_state_is_ignored_not_crashing(self):
        agents = [{"state": "teleporting", "interrupted": False, "updatedAt": 5_000}]
        self.assertEqual(h.orca_led_state(agents, now_ms=5_000), "off")

    def test_missing_updated_at_treated_as_fresh(self):
        agents = [{"state": "done", "interrupted": False}]
        self.assertEqual(h.orca_led_state(agents, now_ms=10**12, fade_sec=120), "done")

    def test_failed_never_fades(self):
        agents = [{"state": "blocked", "interrupted": False, "updatedAt": 1_000}]
        self.assertEqual(
            h.orca_led_state(agents, now_ms=1_000 + 10**7, fade_sec=120), "failed")


class TestFadeDeadline(unittest.TestCase):
    def test_none_when_no_done(self):
        self.assertIsNone(h.fade_deadline_ms([{"state": "working", "updatedAt": 1_000}]))

    def test_earliest_done_wins(self):
        agents = [
            {"state": "done", "updatedAt": 9_000},
            {"state": "done", "updatedAt": 2_000},
        ]
        self.assertEqual(h.fade_deadline_ms(agents, fade_sec=120), 2_000 + 120_000)


class TestAgainstFixture(unittest.TestCase):
    def test_every_fixture_worktree_maps_to_a_legal_state(self):
        for w in load_fixture("worktree_ps")["worktrees"]:
            with self.subTest(w=w["worktreeId"]):
                self.assertIn(h.orca_led_state(w.get("agents"), now_ms=10**12),
                              h.VALID_STATES | {"off"})


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run the tests to verify they fail**

Run: `python3 -m unittest discover -s tests -v -k OrcaLedState`
Expected: FAIL — `AttributeError: module 'duckypad_hook' has no attribute 'orca_led_state'`.

- [ ] **Step 3: Implement**

In `sender/duckypad_hook.py`, immediately after the `VALID_STATES` line, add:

```python
# ── Orca host: agent state → LED state ───────────────────────────────────────
# Orca's per-pane enum, in the order we resolve conflicts. A worktree can hold
# several agent panes; the highest-precedence one owns the key, because a pane
# that WANTS you outranks one that is merely busy or finished.
ORCA_PRECEDENCE = ("waiting", "blocked", "working", "done", "interrupted", "idle")
ORCA_TO_RAFT = {
    "waiting":     "needs",    # blue: wants you now
    "blocked":     "failed",   # red: can't proceed
    "working":     "working",  # amber
    "done":        "done",     # green (fades — see orca_led_state)
    "interrupted": "idle",     # dim purple
    "idle":        "idle",     # dim purple
}


def _agent_state(agent):
    """The precedence key for one pane. `interrupted` overrides the report."""
    if agent.get("interrupted"):
        return "interrupted"
    state = (agent.get("state") or "").lower()
    return state if state in ORCA_TO_RAFT else None


def orca_led_state(agents, now_ms=None, fade_sec=None):
    """Aggregate one worktree's agent panes into a single LED state.

    A `done` older than the fade window resolves to "off" here rather than being
    remembered somewhere: the mapping is a pure function of Orca's truth plus the
    clock, so any repaint lands in the right place without bookkeeping.
    """
    if not agents:
        return "off"
    if now_ms is None:
        now_ms = int(time.time() * 1000)
    if fade_sec is None:
        fade_sec = FADE_DELAY_SEC

    best = None
    for agent in agents:
        state = _agent_state(agent)
        if state is None:
            continue
        if state == "done":
            updated = agent.get("updatedAt")
            if isinstance(updated, int) and now_ms - updated >= fade_sec * 1000:
                continue                      # stale green: as good as no pane
        if best is None or ORCA_PRECEDENCE.index(state) < ORCA_PRECEDENCE.index(best):
            best = state
    return ORCA_TO_RAFT[best] if best else "off"


def fade_deadline_ms(agents, fade_sec=None):
    """Epoch ms at which the earliest live `done` in this list turns off."""
    if fade_sec is None:
        fade_sec = FADE_DELAY_SEC
    stamps = [a.get("updatedAt") for a in (agents or [])
              if _agent_state(a) == "done" and isinstance(a.get("updatedAt"), int)]
    return min(stamps) + fade_sec * 1000 if stamps else None
```

- [ ] **Step 4: Run the tests to verify they pass**

Run: `python3 -m unittest discover -s tests -v`
Expected: all PASS (Task 1's 3 tests plus these 15).

- [ ] **Step 5: Commit**

```bash
git add sender/duckypad_hook.py tests/test_orca_state.py
git commit -m "feat(orca): map Orca agent panes to LED states with fade folded in"
```

---

### Task 3: Board config and slot resolution

The board is Raft-owned because Orca's positions are unreadable (spec probes 2 and 3). This task turns `board.json` plus a `worktree ps` payload into `{ordinal: state}`.

**Files:**
- Modify: `sender/duckypad_hook.py`
- Create: `tests/test_board.py`

**Interfaces:**
- Consumes: `orca_led_state`, `fade_deadline_ms` from Task 2.
- Produces:
  - `BOARD_PATH = os.path.expanduser("~/.config/raft/board.json")`
  - `MAX_SLOTS = 5`
  - `load_board(path=None) -> list[dict]` — slots as `{"label": str, "worktree": str, "query": str}`, truncated to `MAX_SLOTS`; `[]` when the file is missing, unreadable, malformed, or `host != "orca"`.
  - `resolve_slot(board, worktree_id, ps_by_id) -> int | None` — 1-based ordinal, walking `parentWorktreeId`.
  - `orca_board(board, ps_worktrees, firing_id=None, firing_state=None, now_ms=None) -> dict[int, str]`

- [ ] **Step 1: Write the failing tests**

`tests/test_board.py`:

```python
import json
import os
import tempfile
import unittest

from context import load_fixture
import duckypad_hook as h


def slot(label, worktree, query=None):
    return {"label": label, "worktree": worktree, "query": query or label}


class TestLoadBoard(unittest.TestCase):
    def _write(self, payload):
        fd, path = tempfile.mkstemp(suffix=".json")
        with os.fdopen(fd, "w") as f:
            if isinstance(payload, str):
                f.write(payload)
            else:
                json.dump(payload, f)
        self.addCleanup(os.unlink, path)
        return path

    def test_missing_file_is_empty_board(self):
        self.assertEqual(h.load_board("/nonexistent/raft/board.json"), [])

    def test_malformed_json_is_empty_board(self):
        self.assertEqual(h.load_board(self._write("{not json")), [])

    def test_wrong_host_is_ignored(self):
        path = self._write({"host": "cmux", "slots": [slot("a", "id-a")]})
        self.assertEqual(h.load_board(path), [])

    def test_slots_load_in_order_and_truncate_at_five(self):
        path = self._write({"host": "orca",
                            "slots": [slot(f"s{i}", f"id-{i}") for i in range(8)]})
        board = h.load_board(path)
        self.assertEqual(len(board), 5)
        self.assertEqual([s["worktree"] for s in board],
                         [f"id-{i}" for i in range(5)])

    def test_slot_missing_worktree_key_is_dropped(self):
        path = self._write({"host": "orca",
                            "slots": [{"label": "x", "query": "x"}, slot("y", "id-y")]})
        self.assertEqual([s["worktree"] for s in h.load_board(path)], ["id-y"])


class TestResolveSlot(unittest.TestCase):
    def setUp(self):
        self.board = [slot("one", "wt-1"), slot("two", "wt-2")]
        self.ps_by_id = {
            "wt-1": {"worktreeId": "wt-1", "parentWorktreeId": None},
            "wt-2": {"worktreeId": "wt-2", "parentWorktreeId": None},
            "wt-3": {"worktreeId": "wt-3", "parentWorktreeId": "wt-2"},
            "wt-4": {"worktreeId": "wt-4", "parentWorktreeId": "wt-3"},
            "wt-9": {"worktreeId": "wt-9", "parentWorktreeId": None},
        }

    def test_direct_hit(self):
        self.assertEqual(h.resolve_slot(self.board, "wt-2", self.ps_by_id), 2)

    def test_child_rolls_up_to_parent_slot(self):
        self.assertEqual(h.resolve_slot(self.board, "wt-3", self.ps_by_id), 2)

    def test_grandchild_rolls_up(self):
        self.assertEqual(h.resolve_slot(self.board, "wt-4", self.ps_by_id), 2)

    def test_off_board_is_none(self):
        self.assertIsNone(h.resolve_slot(self.board, "wt-9", self.ps_by_id))

    def test_unknown_id_is_none(self):
        self.assertIsNone(h.resolve_slot(self.board, "nope", self.ps_by_id))

    def test_parent_cycle_terminates(self):
        ps = {"a": {"worktreeId": "a", "parentWorktreeId": "b"},
              "b": {"worktreeId": "b", "parentWorktreeId": "a"}}
        self.assertIsNone(h.resolve_slot(self.board, "a", ps))


class TestOrcaBoard(unittest.TestCase):
    def setUp(self):
        self.board = [slot("one", "wt-1"), slot("two", "wt-2"), slot("three", "wt-3")]
        self.ps = [
            {"worktreeId": "wt-1", "parentWorktreeId": None,
             "agents": [{"state": "working", "updatedAt": 5_000}]},
            {"worktreeId": "wt-2", "parentWorktreeId": None,
             "agents": [{"state": "waiting", "updatedAt": 5_000}]},
        ]

    def test_every_slot_gets_a_state(self):
        board = h.orca_board(self.board, self.ps, now_ms=5_000)
        self.assertEqual(board, {1: "working", 2: "needs", 3: "off"})

    def test_slot_absent_from_ps_is_off(self):
        board = h.orca_board(self.board, self.ps, now_ms=5_000)
        self.assertEqual(board[3], "off")

    def test_firing_state_overrides_ps_for_its_own_slot(self):
        board = h.orca_board(self.board, self.ps, firing_id="wt-1",
                             firing_state="done", now_ms=5_000)
        self.assertEqual(board[1], "done")
        self.assertEqual(board[2], "needs")

    def test_firing_child_overrides_its_parent_slot(self):
        ps = self.ps + [{"worktreeId": "wt-9", "parentWorktreeId": "wt-2", "agents": []}]
        board = h.orca_board(self.board, ps, firing_id="wt-9",
                             firing_state="working", now_ms=5_000)
        self.assertEqual(board[2], "working")

    def test_off_board_firing_worktree_does_not_disturb_the_board(self):
        ps = self.ps + [{"worktreeId": "wt-x", "parentWorktreeId": None, "agents": []}]
        board = h.orca_board(self.board, ps, firing_id="wt-x",
                             firing_state="working", now_ms=5_000)
        self.assertEqual(board, {1: "working", 2: "needs", 3: "off"})

    def test_empty_board_yields_empty_dict(self):
        self.assertEqual(h.orca_board([], self.ps), {})

    def test_works_against_the_real_fixture(self):
        wts = load_fixture("worktree_ps")["worktrees"]
        board = [slot(f"s{i}", w["worktreeId"]) for i, w in enumerate(wts[:5])]
        got = h.orca_board(board, wts, now_ms=10**12)
        self.assertEqual(sorted(got), [1, 2, 3, 4, 5])
        for state in got.values():
            self.assertIn(state, h.VALID_STATES | {"off"})


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run to verify failure**

Run: `python3 -m unittest discover -s tests -v -k Board`
Expected: FAIL — `AttributeError: … 'load_board'`.

- [ ] **Step 3: Implement**

Add to `sender/duckypad_hook.py`, after the Task 2 block:

```python
# ── Orca host: the board ─────────────────────────────────────────────────────
# Orca's ⌘N indexes visible worktree rows in a project→repo→worktree tree, and
# neither that order nor the collapse state is readable from its CLI, so Raft
# owns the key→worktree mapping instead of mirroring the sidebar.
BOARD_PATH = os.path.expanduser("~/.config/raft/board.json")
MAX_SLOTS = 5


def load_board(path=None):
    """Read the Orca board. Returns [] on anything unexpected — never raises."""
    try:
        with open(path or BOARD_PATH) as f:
            doc = json.load(f)
        if (doc.get("host") or "").lower() != "orca":
            return []                      # not ours: a stray or half-migrated file
        slots = []
        for entry in doc.get("slots") or []:
            wt = entry.get("worktree")
            if not wt:
                continue                   # a slot with no worktree can't be lit
            slots.append({"label": entry.get("label") or "",
                          "worktree": wt,
                          "query": entry.get("query") or ""})
        return slots[:MAX_SLOTS]
    except Exception:
        return []


def resolve_slot(board, worktree_id, ps_by_id):
    """1-based ordinal for worktree_id, walking parents; None if off-board."""
    index = {slot["worktree"]: i + 1 for i, slot in enumerate(board)}
    seen = set()
    current = worktree_id
    while current and current not in seen:
        if current in index:
            return index[current]
        seen.add(current)
        current = (ps_by_id.get(current) or {}).get("parentWorktreeId")
    return None


def orca_board(board, ps_worktrees, firing_id=None, firing_state=None, now_ms=None):
    """{ordinal: led_state} for every slot.

    Orca's runtime may not have applied the firing session's change yet (our hook
    and Orca's own hook are siblings on the same event), so the firing worktree's
    state comes from the hook payload and everyone else's from `worktree ps`.
    """
    if not board:
        return {}
    ps_by_id = {w.get("worktreeId"): w for w in ps_worktrees or []}
    result = {}
    for ordinal, slot in enumerate(board, start=1):
        entry = ps_by_id.get(slot["worktree"])
        result[ordinal] = orca_led_state((entry or {}).get("agents"), now_ms=now_ms)
    if firing_id and firing_state:
        own = resolve_slot(board, firing_id, ps_by_id)
        if own is not None:
            result[own] = firing_state
    return result
```

- [ ] **Step 4: Run to verify pass**

Run: `python3 -m unittest discover -s tests -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add sender/duckypad_hook.py tests/test_board.py
git commit -m "feat(orca): Raft-owned board config and slot resolution"
```

---

### Task 4: Host detection

**Files:**
- Modify: `sender/duckypad_hook.py`
- Create: `tests/test_detect.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces: `detect(env=None, cmux_probe=None) -> str | None` returning `"orca"`, `"cmux"`, or `None`. `cmux_probe` is an injectable zero-arg callable returning a truthy workspace ref; production passes `None` and the function calls `resolve_ordinal()`.

- [ ] **Step 1: Write the failing tests**

`tests/test_detect.py`:

```python
import unittest

import duckypad_hook as h


class TestDetect(unittest.TestCase):
    def test_orca_env_wins(self):
        env = {"ORCA_WORKTREE_ID": "repo::/path"}
        self.assertEqual(h.detect(env, cmux_probe=lambda: 3), "orca")

    def test_orca_short_circuits_cmux_even_when_cmux_answers(self):
        """A session under Orca must never be attributed to a cmux workspace."""
        env = {"ORCA_WORKTREE_ID": "repo::/path", "CMUX_BIN": "/x/cmux"}
        calls = []

        def probe():
            calls.append(1)
            return 2

        self.assertEqual(h.detect(env, cmux_probe=probe), "orca")
        self.assertEqual(calls, [], "cmux must not even be probed under Orca")

    def test_cmux_when_probe_resolves(self):
        self.assertEqual(h.detect({}, cmux_probe=lambda: 1), "cmux")

    def test_none_when_nothing_resolves(self):
        self.assertIsNone(h.detect({}, cmux_probe=lambda: None))

    def test_empty_orca_var_is_not_orca(self):
        self.assertEqual(h.detect({"ORCA_WORKTREE_ID": ""}, cmux_probe=lambda: 1),
                         "cmux")

    def test_raft_host_override_forces_orca(self):
        self.assertEqual(h.detect({"RAFT_HOST": "orca"}, cmux_probe=lambda: 1), "orca")

    def test_raft_host_override_forces_cmux(self):
        env = {"RAFT_HOST": "cmux", "ORCA_WORKTREE_ID": "repo::/path"}
        self.assertEqual(h.detect(env, cmux_probe=lambda: 1), "cmux")

    def test_raft_host_off_disables_everything(self):
        env = {"RAFT_HOST": "off", "ORCA_WORKTREE_ID": "repo::/path"}
        self.assertIsNone(h.detect(env, cmux_probe=lambda: 1))

    def test_unknown_raft_host_value_falls_through_to_sniffing(self):
        env = {"RAFT_HOST": "banana", "ORCA_WORKTREE_ID": "repo::/path"}
        self.assertEqual(h.detect(env, cmux_probe=lambda: 1), "orca")

    def test_cmux_probe_exception_is_not_fatal(self):
        def probe():
            raise RuntimeError("socket gone")

        self.assertIsNone(h.detect({}, cmux_probe=probe))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run to verify failure**

Run: `python3 -m unittest discover -s tests -v -k Detect`
Expected: FAIL — no attribute `detect`.

- [ ] **Step 3: Implement**

```python
def detect(env=None, cmux_probe=None):
    """Which host owns this session? Resolved from the FIRING session's env.

    Orca is checked before cmux and short-circuits it: `cmux identify` reports a
    caller, but a stale or fallback answer would silently light the wrong key, and
    an Orca session is unambiguous.
    """
    env = os.environ if env is None else env
    forced = (env.get("RAFT_HOST") or "").lower()
    if forced == "off":
        return None
    if forced in ("orca", "cmux"):
        return forced
    if env.get("ORCA_WORKTREE_ID"):
        return "orca"
    probe = cmux_probe or resolve_ordinal
    try:
        if probe():
            return "cmux"
    except Exception:
        pass
    return None
```

- [ ] **Step 4: Run to verify pass**

Run: `python3 -m unittest discover -s tests -v`
Expected: all PASS.

- [ ] **Step 5: Commit**

```bash
git add sender/duckypad_hook.py tests/test_detect.py
git commit -m "feat: host detection from the firing session's environment"
```

---

### Task 5: Wire the Orca adapter into the hook's main path

**Files:**
- Modify: `sender/duckypad_hook.py` (docstring, `_orca_json`, `_set_board`, `main`, `--repaint-in`)
- Create: `tests/test_hook_main.py`

**Interfaces:**
- Consumes: `detect`, `load_board`, `orca_board`, `fade_deadline_ms`, `orca_led_state`.
- Produces:
  - `ORCA = os.environ.get("ORCA_BIN", "/usr/local/bin/orca")`
  - `orca_ps_worktrees() -> list[dict]` — `[]` on any failure.
  - `_set_board(host, board_states) -> subprocess.CompletedProcess | None`
  - `run_orca(state, payload_env=None) -> int` — the whole Orca path; returns an exit code (always 0).
  - `main` dispatches `--repaint-in <seconds>`.

- [ ] **Step 1: Write the failing tests**

`tests/test_hook_main.py`:

```python
import unittest
from unittest import mock

import duckypad_hook as h


class TestRunOrca(unittest.TestCase):
    def setUp(self):
        self.board = [{"label": "one", "worktree": "wt-1", "query": "one"},
                      {"label": "two", "worktree": "wt-2", "query": "two"}]
        self.ps = [{"worktreeId": "wt-1", "parentWorktreeId": None,
                    "agents": [{"state": "working", "updatedAt": 5_000}]},
                   {"worktreeId": "wt-2", "parentWorktreeId": None, "agents": []}]

    def test_paints_whole_board_with_hook_state_for_the_firing_worktree(self):
        env = {"ORCA_WORKTREE_ID": "wt-2"}
        with mock.patch.object(h, "load_board", return_value=self.board), \
             mock.patch.object(h, "orca_ps_worktrees", return_value=self.ps), \
             mock.patch.object(h, "_set_board") as set_board, \
             mock.patch.object(h, "_spawn_repaint") as spawn:
            h.run_orca("done", payload_env=env)
        set_board.assert_called_once()
        host, states = set_board.call_args[0]
        self.assertEqual(host, "orca")
        self.assertEqual(states[2], "done")
        self.assertEqual(states[1], "working")
        spawn.assert_called_once()

    def test_no_board_config_means_no_write(self):
        with mock.patch.object(h, "load_board", return_value=[]), \
             mock.patch.object(h, "orca_ps_worktrees", return_value=self.ps), \
             mock.patch.object(h, "_set_board") as set_board:
            self.assertEqual(h.run_orca("working", payload_env={"ORCA_WORKTREE_ID": "wt-1"}), 0)
        set_board.assert_not_called()

    def test_orca_unreachable_still_paints_the_firing_slot(self):
        env = {"ORCA_WORKTREE_ID": "wt-1"}
        with mock.patch.object(h, "load_board", return_value=self.board), \
             mock.patch.object(h, "orca_ps_worktrees", return_value=[]), \
             mock.patch.object(h, "_set_board") as set_board, \
             mock.patch.object(h, "_spawn_repaint"):
            h.run_orca("needs", payload_env=env)
        _host, states = set_board.call_args[0]
        self.assertEqual(states[1], "needs")
        self.assertEqual(states[2], "off")

    def test_no_repaint_scheduled_without_a_live_done(self):
        env = {"ORCA_WORKTREE_ID": "wt-1"}
        with mock.patch.object(h, "load_board", return_value=self.board), \
             mock.patch.object(h, "orca_ps_worktrees", return_value=self.ps), \
             mock.patch.object(h, "_set_board"), \
             mock.patch.object(h, "_spawn_repaint") as spawn:
            h.run_orca("working", payload_env=env)
        spawn.assert_not_called()


class TestOrcaPsWorktrees(unittest.TestCase):
    def test_timeout_returns_empty_list(self):
        with mock.patch.object(h.subprocess, "run", side_effect=Exception("boom")):
            self.assertEqual(h.orca_ps_worktrees(), [])

    def test_garbage_stdout_returns_empty_list(self):
        fake = mock.Mock(stdout="not json")
        with mock.patch.object(h.subprocess, "run", return_value=fake):
            self.assertEqual(h.orca_ps_worktrees(), [])

    def test_parses_result_worktrees(self):
        fake = mock.Mock(stdout='{"ok":true,"result":{"worktrees":[{"worktreeId":"a"}]}}')
        with mock.patch.object(h.subprocess, "run", return_value=fake):
            self.assertEqual(h.orca_ps_worktrees(), [{"worktreeId": "a"}])


class TestMainDispatch(unittest.TestCase):
    def test_main_routes_orca_host_to_run_orca(self):
        with mock.patch.object(h, "detect", return_value="orca"), \
             mock.patch.object(h, "run_orca", return_value=0) as run:
            h.main(["working"])
        run.assert_called_once_with("working")

    def test_main_with_no_host_is_a_silent_success(self):
        with mock.patch.object(h, "detect", return_value=None), \
             mock.patch.object(h, "run_orca") as run, \
             mock.patch.object(h, "_set_led") as set_led:
            self.assertEqual(h.main(["working"]), 0)
        run.assert_not_called()
        set_led.assert_not_called()

    def test_invalid_state_never_reaches_a_host(self):
        with mock.patch.object(h, "detect", return_value="orca") as detect, \
             mock.patch.object(h, "run_orca") as run:
            self.assertEqual(h.main(["banana"]), 0)
        run.assert_not_called()
        detect.assert_not_called()


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run to verify failure**

Run: `python3 -m unittest discover -s tests -v -k "RunOrca or OrcaPs or MainDispatch"`
Expected: FAIL — no attribute `run_orca`.

- [ ] **Step 3: Implement**

Add near `CMUX`:

```python
ORCA = os.environ.get("ORCA_BIN", "/usr/local/bin/orca")
```

Add the Orca I/O and path:

```python
def orca_ps_worktrees():
    """`orca worktree ps --json` → worktrees list. [] if Orca is unreachable."""
    try:
        out = subprocess.run([ORCA, "worktree", "ps", "--limit", "50", "--json"],
                             capture_output=True, text=True, timeout=3).stdout
        return json.loads(out)["result"]["worktrees"]
    except Exception as e:
        _log(f"ORCA ps failed: {e!r}")
        return []


def _set_board(host, board_states):
    """One batched LED write for the whole board, via the pinned NOPASSWD sudo."""
    args = [f"{ordinal}:{state}" for ordinal, state in sorted(board_states.items())]
    try:
        return subprocess.run(
            ["sudo", "-n", LED_PY, LED_SCRIPT, "--host", host, "--board", *args],
            timeout=5, capture_output=True, text=True)
    except Exception as e:
        _log(f"SET_BOARD host={host} states={board_states} EXC={e!r}")
        return None


def _spawn_repaint(delay_sec):
    """Detached one-shot: repaint the board once, later. No token needed —
    a repaint is derived from Orca's truth, so a redundant one is a no-op."""
    try:
        subprocess.Popen(
            [sys.executable, os.path.abspath(__file__), "--repaint-in", str(delay_sec)],
            stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL, start_new_session=True)
    except Exception as e:
        _log(f"REPAINT spawn EXC={e!r}")


def run_orca(state, payload_env=None):
    """Repaint the whole board: hook state for the firing worktree, `ps` for the rest."""
    env = os.environ if payload_env is None else payload_env
    board = load_board()
    if not board:
        _log("ORCA no board config (~/.config/raft/board.json) — nothing to paint")
        return 0
    firing_id = env.get("ORCA_WORKTREE_ID") or None
    worktrees = orca_ps_worktrees()
    now_ms = int(time.time() * 1000)
    states = orca_board(board, worktrees, firing_id=firing_id,
                        firing_state=state, now_ms=now_ms)
    r = _set_board("orca", states)
    _log(f"ORCA state={state} firing={firing_id} board={states} "
         f"sudo_rc={getattr(r, 'returncode', None)}")

    # Schedule one repaint for the moment the earliest live green goes stale.
    deadlines = [d for w in worktrees
                 for d in (fade_deadline_ms(w.get("agents")),) if d]
    if state == FADE_STATE:
        deadlines.append(now_ms + FADE_DELAY_SEC * 1000)
    future = [d for d in deadlines if d > now_ms]
    if future:
        _spawn_repaint(max(1, int((min(future) - now_ms) / 1000) + 1))
    return 0


def run_repaint_later(delay_sec):
    """Sleep, then repaint from Orca's truth alone (no hook state to trust)."""
    time.sleep(delay_sec)
    board = load_board()
    if not board:
        return 0
    states = orca_board(board, orca_ps_worktrees())
    r = _set_board("orca", states)
    _log(f"REPAINT board={states} sudo_rc={getattr(r, 'returncode', None)}")
    return 0
```

Then rewrite `main`'s tail. Replace everything from `ordinal = resolve_ordinal()` to the end of `main` with:

```python
    host = detect()
    if host is None:
        _log(f"FIRED state={state} host=None — no cmux/Orca session")
        return 0

    if host == "orca":
        return run_orca(state)

    # ── cmux: unchanged single-key positional path ───────────────────────────
    ordinal = resolve_ordinal()
    if ordinal is None:
        _log(f"FIRED state={state} ordinal=None (no cmux workspace resolved)")
        return 0
    token = _write_token(ordinal)
    r = _set_led(ordinal, state, host="cmux")
    rc, err = getattr(r, "returncode", None), getattr(r, "stderr", "") or ""
    _log(f"FIRED state={state} ordinal={ordinal} sudo_rc={rc} stderr={err.strip()!r}")
    if state == FADE_STATE and token is not None:
        _spawn_fader(ordinal, token)
        _log(f"FADE scheduled ordinal={ordinal} in {FADE_DELAY_SEC}s -> {FADE_TO}")
    return 0
```

Add the `--repaint-in` branch beside the existing `--fade` branch at the top of `main`:

```python
    if argv and argv[0] == "--repaint-in":
        if len(argv) >= 2:
            try:
                run_repaint_later(float(argv[1]))
            except Exception as e:
                _log(f"REPAINT EXC={e!r}")
        return 0
```

Move the `if state not in VALID_STATES: return 0` guard **above** the `detect()` call so an invalid state never probes a host. Update `_set_led` to accept an optional host and forward it:

```python
def _set_led(ordinal, state, host=None):
    """Root LED write via the pinned NOPASSWD-sudo helper. Returns rc or None."""
    cmd = ["sudo", "-n", LED_PY, LED_SCRIPT]
    if host:
        cmd += ["--host", host]
    cmd += [str(ordinal), state]
    try:
        return subprocess.run(cmd, timeout=5, capture_output=True, text=True)
    except Exception as e:
        _log(f"SET_LED ordinal={ordinal} state={state} EXC={e!r}")
        return None
```

Finally update the module docstring: it currently claims cmux exclusively. Replace its first paragraph with:

```
Invoked by Claude Code lifecycle hooks (SessionStart/UserPromptSubmit/
Notification/Stop/StopFailure/SessionEnd). Detects whether the firing session
belongs to Orca or cmux and paints accordingly: Orca repaints all five board
keys from `orca worktree ps`, cmux sets the one key for its own workspace
ordinal. No-ops silently (exit 0) when neither host, nor the pad, is present.
```

- [ ] **Step 4: Run to verify pass**

Run: `python3 -m unittest discover -s tests -v`
Expected: all PASS.

- [ ] **Step 5: Verify the cmux path did not regress, by hand**

Run: `RAFT_HOST=off python3 sender/duckypad_hook.py working; echo "rc=$?"`
Expected: `rc=0`, and `/tmp/duckypad_hook.log` gains no LED write.

Run: `python3 sender/duckypad_hook.py --resolve`
Expected: prints `None` under Orca (no cmux socket). No traceback.

- [ ] **Step 6: Commit**

```bash
git add sender/duckypad_hook.py tests/test_hook_main.py
git commit -m "feat(orca): repaint the whole board from worktree ps on every hook"
```

---

### Task 6: LED writer — batch board writes and the ownership gate

The pad has one active profile and the two hosts' profiles differ, so only the host whose profile is loaded may write. The pad already reports its current profile in the `0x00` response.

**Files:**
- Modify: `sender/duckypad_led.py`
- Create: `tests/test_led_args.py`

**Interfaces:**
- Consumes: nothing from earlier tasks.
- Produces:
  - `PROFILE_MAP_PATH = "/usr/local/libexec/duckypad_profiles.json"`
  - `PROFILE_HOST_DEFAULT = {1: "cmux", 2: "orca"}`
  - `LOCK_PATH = "/tmp/duckypad_led.lock"`
  - `load_profile_host_map(path=None) -> dict[int, str]`
  - `parse_board(items) -> list[tuple[int, str]]`
  - `host_owns_board(host, current_profile, profile_map) -> bool`
  - `_query_current_profile(h) -> int | None`
  - `main` accepts `--host <name>` before any other form, plus `--board <ord:state> …`.

- [ ] **Step 1: Write the failing tests**

`tests/test_led_args.py`:

```python
import json
import os
import tempfile
import unittest

import duckypad_led as led


class TestParseBoard(unittest.TestCase):
    def test_parses_ordinal_state_pairs(self):
        self.assertEqual(led.parse_board(["1:working", "3:off"]),
                         [(1, "working"), (3, "off")])

    def test_drops_unknown_state(self):
        self.assertEqual(led.parse_board(["1:banana", "2:done"]), [(2, "done")])

    def test_drops_out_of_range_ordinal(self):
        self.assertEqual(led.parse_board(["0:done", "6:done", "2:done"]), [(2, "done")])

    def test_drops_malformed_items(self):
        self.assertEqual(led.parse_board(["nope", "", "2:done", "3:"]), [(2, "done")])


class TestProfileMap(unittest.TestCase):
    def test_default_when_file_absent(self):
        self.assertEqual(led.load_profile_host_map("/nonexistent/x.json"),
                         led.PROFILE_HOST_DEFAULT)

    def test_reads_file_and_coerces_keys_to_int(self):
        fd, path = tempfile.mkstemp(suffix=".json")
        with os.fdopen(fd, "w") as f:
            json.dump({"3": "orca", "4": "cmux"}, f)
        self.addCleanup(os.unlink, path)
        self.assertEqual(led.load_profile_host_map(path), {3: "orca", 4: "cmux"})

    def test_malformed_file_falls_back_to_default(self):
        fd, path = tempfile.mkstemp(suffix=".json")
        with os.fdopen(fd, "w") as f:
            f.write("{broken")
        self.addCleanup(os.unlink, path)
        self.assertEqual(led.load_profile_host_map(path), led.PROFILE_HOST_DEFAULT)


class TestOwnership(unittest.TestCase):
    def setUp(self):
        self.map = {1: "cmux", 2: "orca"}

    def test_matching_host_owns_the_board(self):
        self.assertTrue(led.host_owns_board("orca", 2, self.map))

    def test_other_hosts_profile_is_refused(self):
        self.assertFalse(led.host_owns_board("orca", 1, self.map))

    def test_unknown_profile_number_is_allowed(self):
        """A hand-made profile must not lock a single-host user out."""
        self.assertTrue(led.host_owns_board("orca", 7, self.map))

    def test_unreadable_profile_is_allowed(self):
        self.assertTrue(led.host_owns_board("orca", None, self.map))

    def test_no_host_declared_is_allowed(self):
        self.assertTrue(led.host_owns_board(None, 1, self.map))


class TestMainGating(unittest.TestCase):
    """main() must be hardware-free when the pad is absent, and always exit 0."""

    def test_board_write_without_pad_is_silent_success(self):
        original = led._open_device
        led._open_device = lambda: None
        self.addCleanup(setattr, led, "_open_device", original)
        self.assertEqual(led.main(["--host", "orca", "--board", "1:working"]), 0)

    def test_no_args_is_silent_success(self):
        self.assertEqual(led.main([]), 0)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run to verify failure**

Run: `python3 -m unittest discover -s tests -v -k "ParseBoard or ProfileMap or Ownership"`
Expected: FAIL — no attribute `parse_board`.

Note: `duckypad_led` imports `hid` lazily inside `_open_device`, so these tests run without `hidapi` installed.

- [ ] **Step 3: Implement**

Add after `WS_LED_INDEX`:

```python
# Board ownership: the pad has ONE active profile and the cmux/Orca profiles send
# different keystrokes, so only the host whose profile is loaded may write LEDs —
# otherwise a board lies. The map is generated by duckypad_push_profile.py.
PROFILE_MAP_PATH = "/usr/local/libexec/duckypad_profiles.json"
PROFILE_HOST_DEFAULT = {1: "cmux", 2: "orca"}
LOCK_PATH = "/tmp/duckypad_led.lock"


def load_profile_host_map(path=None):
    """{profile_number: host}. Falls back to the built-in default."""
    try:
        with open(path or PROFILE_MAP_PATH) as f:
            return {int(k): str(v) for k, v in json.load(f).items()}
    except Exception:
        return dict(PROFILE_HOST_DEFAULT)


def host_owns_board(host, current_profile, profile_map):
    """May `host` write? Unknown or unreadable profiles are allowed on purpose:
    a user with a hand-made profile must not be locked out, and a single-host
    user never has a conflicting writer anyway."""
    if not host or current_profile is None:
        return True
    owner = profile_map.get(current_profile)
    return owner is None or owner == host


def parse_board(items):
    """["1:working", …] -> [(ordinal, state)], silently dropping nonsense."""
    out = []
    for item in items:
        ordinal, _, state = (item or "").partition(":")
        try:
            ordinal = int(ordinal)
        except ValueError:
            continue
        state = state.lower()
        if ordinal in WS_LED_INDEX and state in STATE_COLOR:
            out.append((ordinal, state))
    return out


def _query_current_profile(h):
    """HID 0x00 query-info → current profile number (response byte 11)."""
    buf = [0] * 64
    buf[0] = 0x05
    buf[2] = 0x00
    try:
        h.write(buf)
        resp = h.read(64, timeout_ms=200)
        return resp[11] if resp and len(resp) > 11 else None
    except Exception:
        return None
```

Add `import json` and `import fcntl` to the imports.

In `main`, consume `--host` first and thread it through:

```python
def main(argv):
    if len(argv) < 1:
        return 0

    host = None
    if argv[0] == "--host":
        if len(argv) < 3:
            return 0
        host, argv = argv[1], argv[2:]
```

Add the `--board` form alongside the existing ones (before the final `else`):

```python
    elif argv[0] == "--board":
        actions = [(WS_LED_INDEX[o], *STATE_COLOR[s]) for o, s in parse_board(argv[1:])]
```

Replace the device-write block at the end of `main` with a locked, gated version:

```python
    # Serialise writers: two sessions finishing at once would otherwise interleave
    # two boards through one device.
    lock = None
    try:
        lock = open(LOCK_PATH, "w")
        fcntl.flock(lock, fcntl.LOCK_EX)
    except Exception:
        lock = None

    h = _open_device()
    if h is None:
        if lock:
            lock.close()
        return 0                          # pad absent → silent no-op
    try:
        if host is not None:
            current = _query_current_profile(h)
            if not host_owns_board(host, current, load_profile_host_map()):
                return 0                  # another host owns the board: write nothing
        for idx, r, g, b in actions:
            _set_led(h, idx, r, g, b)
    finally:
        try:
            h.close()
        except Exception:
            pass
        if lock:
            try:
                fcntl.flock(lock, fcntl.LOCK_UN)
            finally:
                lock.close()
    return 0
```

Update the usage docstring to list `--host <name>` and `--board <ord:state> …`, noting that `--index` and `--all-off` deliberately bypass the gate as manual operations.

- [ ] **Step 4: Run to verify pass**

Run: `python3 -m unittest discover -s tests -v`
Expected: all PASS.

- [ ] **Step 5: Exercise it against the real pad**

Run: `sudo /usr/local/libexec/duckypad-venv/bin/python3 sender/duckypad_led.py --host orca --board 1:working 2:needs 3:done 4:failed 5:idle`
Expected: the five top-row keys show amber, blue, green, red, dim purple — *if* the loaded profile is Orca's or an unknown number. If the pad has cmux's profile (number 1) loaded, expect **nothing to light**; that is the gate working. Confirm with `python3 scripts/duckypad_probe.py` to see `current_profile`.

Then clear: `sudo /usr/local/libexec/duckypad-venv/bin/python3 sender/duckypad_led.py --all-off`

- [ ] **Step 6: Install the updated writer and commit**

```bash
sudo cp sender/duckypad_led.py /usr/local/libexec/duckypad_led.py
sudo chown root:wheel /usr/local/libexec/duckypad_led.py
git add sender/duckypad_led.py tests/test_led_args.py
git commit -m "feat: batched board writes, flock, and profile-based ownership gate"
```

---

### Task 7: Board query matching, init, and verify

The palette creates a worktree when a query matches nothing (spec probe 10), so uniqueness is enforced when the board is written and re-checkable at any time.

**Files:**
- Create: `scripts/raft_board.py`
- Create: `scripts/raft_board_init.py`
- Create: `scripts/raft_board_verify.py`
- Create: `tests/test_board_queries.py`

**Interfaces:**
- Consumes: `tests/context.py`.
- Produces, in `scripts/raft_board.py`:
  - `haystacks(worktree) -> list[str]` — the lowercased strings Orca's palette matches a worktree on.
  - `matches(query, worktrees) -> list[str]` — worktreeIds whose haystacks contain the query.
  - `suggest_query(worktree, worktrees) -> str | None` — shortest candidate that matches only this worktree.
  - `check_board(slots, worktrees) -> list[str]` — human-readable problems; `[]` means good.
  - `load_worktrees(orca_bin=None) -> list[dict]` — live `worktree ps` worktrees.

- [ ] **Step 1: Write the failing tests**

`tests/test_board_queries.py`:

```python
import unittest

import raft_board as rb


def wt(wid, name, branch, repo):
    return {"worktreeId": wid, "displayName": name,
            "branch": branch, "repo": repo}


WORKTREES = [
    wt("id-raft", "orca-host-support", "refs/heads/orca-host-support", "raft"),
    wt("id-main1", "main", "refs/heads/main", "radar"),
    wt("id-main2", "main", "refs/heads/main", "flight-station"),
    wt("id-vpc", "fix: make VPC reuse repeatable", "refs/heads/fix/vpc-reuse", "gateway"),
]


class TestMatches(unittest.TestCase):
    def test_unique_substring_matches_one(self):
        self.assertEqual(rb.matches("orca-host", WORKTREES), ["id-raft"])

    def test_match_is_case_insensitive(self):
        self.assertEqual(rb.matches("ORCA-HOST", WORKTREES), ["id-raft"])

    def test_ambiguous_query_matches_several(self):
        self.assertEqual(len(rb.matches("main", WORKTREES)), 2)

    def test_branch_is_searchable(self):
        self.assertEqual(rb.matches("vpc-reuse", WORKTREES), ["id-vpc"])

    def test_repo_name_is_searchable(self):
        self.assertEqual(rb.matches("flight-station", WORKTREES), ["id-main2"])

    def test_no_match_is_empty(self):
        self.assertEqual(rb.matches("zzqq", WORKTREES), [])

    def test_empty_query_matches_nothing(self):
        self.assertEqual(rb.matches("", WORKTREES), [])


class TestSuggestQuery(unittest.TestCase):
    def test_suggests_a_unique_query(self):
        query = rb.suggest_query(WORKTREES[0], WORKTREES)
        self.assertEqual(rb.matches(query, WORKTREES), ["id-raft"])

    def test_returns_none_when_nothing_distinguishes(self):
        twins = [wt("a", "main", "refs/heads/main", "same"),
                 wt("b", "main", "refs/heads/main", "same")]
        self.assertIsNone(rb.suggest_query(twins[0], twins))

    def test_distinguishes_same_named_worktrees_by_repo(self):
        query = rb.suggest_query(WORKTREES[1], WORKTREES)
        self.assertEqual(rb.matches(query, WORKTREES), ["id-main1"])


class TestCheckBoard(unittest.TestCase):
    def test_good_board_has_no_problems(self):
        slots = [{"label": "raft", "worktree": "id-raft", "query": "orca-host"}]
        self.assertEqual(rb.check_board(slots, WORKTREES), [])

    def test_ambiguous_query_is_a_problem(self):
        slots = [{"label": "r", "worktree": "id-main1", "query": "main"}]
        problems = rb.check_board(slots, WORKTREES)
        self.assertEqual(len(problems), 1)
        self.assertIn("ambiguous", problems[0].lower())

    def test_no_match_query_is_a_problem_naming_the_create_hazard(self):
        slots = [{"label": "r", "worktree": "id-raft", "query": "zzqq"}]
        problems = rb.check_board(slots, WORKTREES)
        self.assertEqual(len(problems), 1)
        self.assertIn("create", problems[0].lower())

    def test_query_matching_the_wrong_worktree_is_a_problem(self):
        slots = [{"label": "r", "worktree": "id-raft", "query": "vpc-reuse"}]
        problems = rb.check_board(slots, WORKTREES)
        self.assertEqual(len(problems), 1)
        self.assertIn("wrong worktree", problems[0].lower())

    def test_missing_worktree_is_a_problem(self):
        slots = [{"label": "r", "worktree": "id-gone", "query": "orca-host"}]
        problems = rb.check_board(slots, WORKTREES)
        self.assertTrue(any("no longer exists" in p.lower() for p in problems))

    def test_overlong_label_is_a_problem(self):
        slots = [{"label": "waytoolong", "worktree": "id-raft", "query": "orca-host"}]
        problems = rb.check_board(slots, WORKTREES)
        self.assertTrue(any("7 characters" in p for p in problems))


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run to verify failure**

Run: `python3 -m unittest discover -s tests -v -k "Matches or SuggestQuery or CheckBoard"`
Expected: FAIL — `ModuleNotFoundError: No module named 'raft_board'`.

- [ ] **Step 3: Implement `scripts/raft_board.py`**

```python
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
```

- [ ] **Step 4: Run to verify pass**

Run: `python3 -m unittest discover -s tests -v`
Expected: all PASS.

- [ ] **Step 5: Implement the two CLIs**

`scripts/raft_board_init.py`:

```python
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
            print(f"{w.get('repo'):24} {w.get('displayName')!r:44} "
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
```

`scripts/raft_board_verify.py`:

```python
#!/usr/bin/env python3
"""Check ~/.config/raft/board.json against live Orca. Exit 1 if unsafe.

Run after renaming a branch or reshaping the board. A stale query is not
cosmetic: Orca's palette would CREATE a worktree when the pad types it.
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
        print(f"\n{len(problems)} problem(s). Re-run raft_board_init.py, then "
              f"rebuild and push the profile.", file=sys.stderr)
        return 1
    print(f"board OK — {len(slots)} slot(s), every query uniquely resolved")
    return 0


if __name__ == "__main__":
    sys.exit(main())
```

- [ ] **Step 6: Exercise both CLIs against live Orca**

Run: `python3 scripts/raft_board_init.py --list`
Expected: one line per worktree.

Run: `python3 scripts/raft_board_init.py --slots raft <two more substrings of your own>`
Expected: writes `~/.config/raft/board.json` and prints the key mapping.

Run: `python3 scripts/raft_board_verify.py; echo "rc=$?"`
Expected: `board OK …` and `rc=0`.

Run: `python3 -c "
import json,os
p=os.path.expanduser('~/.config/raft/board.json')
d=json.load(open(p)); d['slots'][0]['query']='zzqq'
json.dump(d,open('/tmp/bad_board.json','w'))
" && python3 scripts/raft_board_verify.py /tmp/bad_board.json; echo "rc=$?"`
Expected: `PROBLEM: … would CREATE a worktree named 'zzqq'` and `rc=1`.

- [ ] **Step 7: Commit**

```bash
git add scripts/raft_board.py scripts/raft_board_init.py scripts/raft_board_verify.py tests/test_board_queries.py
git commit -m "feat(orca): board init/verify with uniqueness enforcement"
```

---

### Task 8: Host-parameterised profile generator

**Files:**
- Modify: `profile/duckypad_build_profile.py`
- Create: `tests/test_profile_gen.py`

**Interfaces:**
- Consumes: `load_board` semantics from Task 3 (same `board.json`), `scripts/raft_board.py` only for `MAX_LABEL`.
- Produces:
  - `COMMON_KEYS: dict[int, tuple[str, str, tuple[int,int,int]]]` — the ten Claude keys.
  - `HOST_KEYS: dict[str, dict[int, tuple]]` — per-host middle-row overrides.
  - `TOP_ROW = [3, 6, 9, 12, 15]`
  - `top_row_keys(host, slots) -> dict[int, tuple]`
  - `build(host, slots, out_dir) -> None`
  - `main()` accepting `--host {cmux,orca}`, `--board <path>`, `--out <dir>`, `--no-enter`.

- [ ] **Step 1: Write the failing tests**

`tests/test_profile_gen.py`:

```python
import unittest

import duckypad_build_profile as gen


SLOTS = [{"label": "raft", "worktree": "id-1", "query": "orca-host"},
         {"label": "gw", "worktree": "id-2", "query": "vpc-reuse"}]


class TestTopRow(unittest.TestCase):
    def test_cmux_top_row_is_positional(self):
        keys = gen.top_row_keys("cmux", [])
        self.assertEqual(keys[3][1], "GUI 1")
        self.assertEqual(keys[15][1], "GUI 5")
        self.assertEqual(len(keys), 5)

    def test_orca_top_row_types_the_query_and_sends_enter(self):
        keys = gen.top_row_keys("orca", SLOTS)
        script = keys[3][1]
        self.assertIn("GUI j", script)
        self.assertIn("STRING orca-host", script)
        self.assertIn("ENTER", script)
        self.assertIn("DELAY", script)

    def test_orca_delays_bracket_the_string(self):
        """Enter must not fire before the palette's ~300ms debounce settles."""
        lines = [l.strip() for l in gen.top_row_keys("orca", SLOTS)[3][1].splitlines()]
        self.assertEqual(lines[0], "GUI j")
        self.assertTrue(lines[1].startswith("DELAY "))
        self.assertTrue(lines[2].startswith("STRING "))
        self.assertTrue(lines[3].startswith("DELAY "))
        self.assertEqual(lines[4], "ENTER")
        self.assertGreaterEqual(int(lines[3].split()[1]), 300)

    def test_no_enter_variant_omits_enter(self):
        keys = gen.top_row_keys("orca", SLOTS, send_enter=False)
        self.assertNotIn("ENTER", keys[3][1])

    def test_unfilled_orca_slots_are_inert(self):
        keys = gen.top_row_keys("orca", SLOTS)
        self.assertEqual(keys[9][1], "")
        self.assertEqual(keys[12][1], "")

    def test_orca_labels_come_from_the_board(self):
        keys = gen.top_row_keys("orca", SLOTS)
        self.assertEqual(keys[3][0], "raft")
        self.assertEqual(keys[6][0], "gw")

    def test_labels_never_exceed_seven_characters(self):
        slots = [{"label": "waytoolonglabel", "worktree": "i", "query": "q"}]
        self.assertLessEqual(len(gen.top_row_keys("orca", slots)[3][0]), 7)


class TestHostKeys(unittest.TestCase):
    def test_cmux_middle_row_unchanged(self):
        self.assertEqual(gen.HOST_KEYS["cmux"][2][1], "GUI SHIFT u")
        self.assertEqual(gen.HOST_KEYS["cmux"][8][1], "CTRL GUI ]")

    def test_orca_middle_row_uses_palette_and_navigate_down(self):
        self.assertEqual(gen.HOST_KEYS["orca"][2][1], "GUI j")
        self.assertEqual(gen.HOST_KEYS["orca"][8][1], "GUI SHIFT DOWNARROW")

    def test_both_hosts_share_the_claude_keys(self):
        self.assertEqual(gen.COMMON_KEYS[1][1], "STRING yes\nENTER")
        self.assertEqual(gen.COMMON_KEYS[13][1], "SHIFT TAB")
        self.assertEqual(set(gen.COMMON_KEYS), {1, 4, 7, 10, 13, 5, 11, 14})


class TestBuild(unittest.TestCase):
    def test_build_writes_fifteen_keys_and_a_config(self):
        import os
        import tempfile
        out = tempfile.mkdtemp()
        gen.build("orca", SLOTS, out)
        for n in range(1, 16):
            self.assertTrue(os.path.exists(os.path.join(out, f"key{n}.txt")),
                            f"key{n}.txt missing")
        config = open(os.path.join(out, "config.txt")).read()
        self.assertIn("z3 raft", config)
        self.assertIn("SWCOLOR_3", config)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run to verify failure**

Run: `python3 -m unittest discover -s tests -v -k "TopRow or HostKeys or Build"`
Expected: FAIL — no attribute `top_row_keys`.

- [ ] **Step 3: Implement**

Replace the `KEYS` dict and `main()` in `profile/duckypad_build_profile.py` with:

```python
# Keys that talk to CLAUDE, not the host — identical on every host.
COMMON_KEYS = {
    # bottom row (Claude Code actions)
    1:  ("Yes",     "STRING yes\nENTER",      (0, 90, 0)),
    4:  ("No",      "STRING no\nENTER",       (90, 0, 0)),
    7:  ("/clear",  "STRING /clear\nENTER",   (90, 45, 0)),
    10: ("compact", "STRING /compact\nENTER", (90, 45, 0)),
    13: ("Auto/Pl", "SHIFT TAB",              (60, 0, 90)),
    # middle row, host-independent
    5:  ("New WS",  "GUI n",                  (0, 50, 60)),   # ⌘N on both hosts
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
PALETTE_OPEN_DELAY_MS = 150          # ⌘J → palette focused
PALETTE_FILTER_DELAY_MS = 400        # > the palette's ~300ms debounce (see spec probe 10)
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

    os.makedirs(out_dir, exist_ok=True)
    config = []
    for n in sorted(keys):
        config.append(f"z{n} {keys[n][0]}")
    config.append("BG_COLOR %d %d %d" % BG_COLOR)
    config.append("DIM_UNUSED_KEYS 0")
    config.append("IS_LANDSCAPE 1")

    for n in sorted(keys):
        label, script, color = keys[n]
        with open(os.path.join(out_dir, f"key{n}.txt"), "w", newline="") as f:
            f.write(script)
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
```

Add `import argparse` and `import json` to the imports, and delete the now-unused `OUT` constant and old `KEYS` dict.

- [ ] **Step 4: Run to verify pass**

Run: `python3 -m unittest discover -s tests -v`
Expected: all PASS.

- [ ] **Step 5: Regenerate both profiles and confirm cmux is byte-identical**

```bash
cp -R profile/profile_cmux /tmp/profile_cmux_before
python3 profile/duckypad_build_profile.py --host cmux
diff -r /tmp/profile_cmux_before profile/profile_cmux && echo "CMUX PROFILE UNCHANGED"
python3 profile/duckypad_build_profile.py --host orca
cat profile/profile_orca/key3.txt
```

Expected: `CMUX PROFILE UNCHANGED`, and `key3.txt` contains the five-line palette macro for your first board slot.

If the cmux diff is non-empty, the refactor changed behaviour — fix before continuing. The one legitimate difference is key ordering inside `config.txt`; if that is all `diff` reports, confirm the label/colour lines are the same set and move on.

- [ ] **Step 6: Commit**

```bash
git add profile/duckypad_build_profile.py profile/profile_orca tests/test_profile_gen.py
git commit -m "feat: generate per-host profiles, Orca top row from board.json"
```

---

### Task 9: Push script — `--profile` and the profile→host map

**Files:**
- Modify: `profile/duckypad_push_profile.py`

**Interfaces:**
- Consumes: `profile_<host>/` directories from Task 8.
- Produces: `/usr/local/libexec/duckypad_profiles.json` mapping assigned profile numbers to hosts, consumed by `load_profile_host_map` from Task 6.

- [ ] **Step 1: Add the profile→host recorder**

Add `import argparse` and `import json` to the imports, delete the module-level `LOCAL` and `PROFILE_NAME` constants (lines 21–22), and add:

```python
PROFILE_MAP_PATH = "/usr/local/libexec/duckypad_profiles.json"


def record_profile_host(number, name):
    """Tell the LED writer which host owns which pad profile.

    duckypad_led.py refuses to paint when another host's profile is loaded; this
    is where that mapping comes from, so it is generated rather than hand-edited.
    """
    if name not in ("cmux", "orca"):
        return                      # only Raft's own profiles participate
    try:
        try:
            with open(PROFILE_MAP_PATH) as f:
                mapping = json.load(f)
        except Exception:
            mapping = {}
        mapping = {k: v for k, v in mapping.items() if v != name}   # drop stale entry
        mapping[str(number)] = name
        os.makedirs(os.path.dirname(PROFILE_MAP_PATH), exist_ok=True)
        with open(PROFILE_MAP_PATH, "w") as f:
            json.dump(mapping, f, indent=2)
        os.chmod(PROFILE_MAP_PATH, 0o644)
        print(f"recorded profile {number} -> host {name} in {PROFILE_MAP_PATH}")
    except PermissionError:
        print(f"WARNING: could not write {PROFILE_MAP_PATH} (need sudo). The LED "
              f"writer will fall back to its built-in default map {{1: cmux, 2: orca}}.")
```

- [ ] **Step 2: Replace `main()` with the host-parameterised version**

Replace the whole of `main()` (lines 94–129) with this. It also fixes a latent bug: the existing "already listed" branch computes an unused `nums` and never derives a profile number, so re-pushing an existing profile had no number to record.

```python
def main():
    ap = argparse.ArgumentParser(description="Push a generated profile to the duckyPad.")
    ap.add_argument("--profile", default="cmux", choices=("cmux", "orca"),
                    help="which generated profile_<name>/ directory to push")
    args = ap.parse_args()
    profile_name = args.profile
    local = os.path.join(_HERE, f"profile_{profile_name}")
    if not os.path.isdir(local):
        print(f"no generated profile at {local} — run "
              f"duckypad_build_profile.py --host {profile_name} first", file=sys.stderr)
        return 2

    h = open_dev()
    try:
        # 1. read profile_info.txt; reuse this profile's number or assign the next
        info = read_file(h, "/profile_info.txt")
        info_txt = info.decode("utf-8", "replace") if info else ""
        lines = [l for l in info_txt.splitlines() if l.strip()]
        existing = [l for l in lines if l.split(maxsplit=1)[-1].strip() == profile_name]
        if existing:
            assigned = int(existing[0].split()[0])
            print(f"profile '{profile_name}' already listed as #{assigned}; "
                  f"overwriting its files")
        else:
            assigned = max((int(l.split()[0]) for l in lines), default=0) + 1
            lines.append(f"{assigned} {profile_name}")
            print(f"adding profile #{assigned} {profile_name}")
        new_info = ("\n".join(lines) + "\n").encode()

        # 2. create dir + push files
        mkdir(h, f"/profile_{profile_name}")
        for fn in sorted(os.listdir(local)):
            with open(os.path.join(local, fn), "rb") as f:
                write_file(h, f"/profile_{profile_name}/{fn}", f.read())

        # 3. write updated profile_info.txt
        write_file(h, "/profile_info.txt", new_info)
        print("profile_info.txt updated:\n" + new_info.decode())

        # 4. soft-reset to leave file-access mode and reload profiles
        print("resetting device to reload...")
        h.write(buf(C_SW_RESET))
        time.sleep(0.3)
    finally:
        try:
            h.close()
        except Exception:
            pass

    record_profile_host(assigned, profile_name)
    print(f"DONE. Device should reboot; select the '{profile_name}' profile "
          f"with the +/- buttons.")
    return 0
```

Change the entry point to propagate the exit code:

```python
if __name__ == "__main__":
    sys.exit(main())
```

Update the module docstring: it names `cmux` throughout and says `sudo python3 duckypad_push_profile.py`; make it `sudo python3 duckypad_push_profile.py --profile <cmux|orca>` and describe `/profile_<name>`.

- [ ] **Step 3: Check the CLI surface without a pad**

Run: `python3 profile/duckypad_push_profile.py --help`
Expected: usage shows `--profile {cmux,orca}`, no traceback.

Run: `python3 profile/duckypad_push_profile.py --profile orca 2>&1 | head -3`
Expected: if `profile/profile_orca/` is missing, the "run duckypad_build_profile.py first" message; if it exists, an HID permission error from `open_dev()` (this is not run under sudo). Either proves argument handling works before the device is touched.

- [ ] **Step 4: Push the Orca profile to the pad**

Run: `sudo python3 profile/duckypad_push_profile.py --profile orca`
Expected: creates `/profile_orca` on the pad, appends `<n> orca` to `profile_info.txt`, prints `recorded profile <n> -> host orca`, and soft-resets the pad.

Run: `cat /usr/local/libexec/duckypad_profiles.json`
Expected: JSON containing `"<n>": "orca"`.

- [ ] **Step 5: Commit**

```bash
git add profile/duckypad_push_profile.py
git commit -m "feat: push --profile and record the profile->host ownership map"
```

---

### Task 10: On-demand repaint script

Needed because switching pad profiles clears host LED overrides (the firmware drops them on profile switch), so the newly-owning host's keys are dark until its next hook.

**Files:**
- Create: `scripts/duckypad_repaint.py`

**Interfaces:**
- Consumes: `run_repaint_later` machinery is *not* reused; this script imports `duckypad_hook` and calls `orca_board` + `_set_board`.
- Produces: a standalone command, `python3 scripts/duckypad_repaint.py`.

- [ ] **Step 1: Write it**

```python
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
```

- [ ] **Step 2: Run it**

Run: `python3 scripts/duckypad_repaint.py`
Expected: prints five `key N: <state>` lines, and the pad's top row matches what Orca shows for those worktrees. With the pad unplugged: same output, exit 0 (the writer no-ops).

- [ ] **Step 3: Commit**

```bash
git add scripts/duckypad_repaint.py
git commit -m "feat: on-demand board repaint from Orca truth"
```

---

### Task 11: End-to-end hardware verification and docs

**Files:**
- Modify: `README.md`
- Modify: `profile/README.md`
- Modify: `docs/calibration.md`
- Modify: `hooks/settings.snippet.json` (comment only)

**Interfaces:**
- Consumes: everything above.
- Produces: no code.

- [ ] **Step 1: Run the end-to-end hardware checklist and record the results**

Do these in order, on the pad, with the Orca profile loaded. Note the outcome of each — Step 2's docs depend on what you observe.

1. **Status, single session.** In an Orca worktree that is board slot 1, submit a prompt. Expected: key 1 amber, then green when the turn ends, then off ~2 min later. Check `/tmp/duckypad_hook.log` for `ORCA state=… board={…}`.
2. **Status, parallel sessions.** Run agents in two board worktrees at once. Expected: both keys track independently; a permission prompt turns its key blue while the other stays amber.
3. **Interrupt.** Interrupt a turn, then fire any hook in any session. Expected: the interrupted key becomes dim purple rather than staying amber.
4. **Non-Claude agent.** Start a Codex pane in a board worktree, then trigger any Claude hook elsewhere. Expected: the Codex worktree's key lights from `worktree ps`.
5. **Jump macro timing — the one open question.** Press each top-row key. Expected: Orca switches to that worktree, no worktree is created, no palette left open. **If a key ever lands on the wrong worktree or leaves the palette open, raise `PALETTE_FILTER_DELAY_MS` by 200 and regenerate.** If it creates a worktree, `orca worktree rm` it, regenerate with `--no-enter`, and record that the two-press variant is required on this machine.
6. **Ownership gate.** Switch the pad to the cmux profile with the +/- buttons, then trigger a hook from an Orca session. Expected: nothing lights, and the log shows the write happened but the writer refused. Switch back and run `scripts/duckypad_repaint.py`; expected: the board fills in.
7. **Pad unplugged.** Unplug, trigger hooks. Expected: sessions behave normally, no errors, `exit 0`.
8. **Stale board.** Rename a board worktree's branch, run `python3 scripts/raft_board_verify.py`. Expected: exit 1 naming the create hazard.

- [ ] **Step 2: Update the docs to match what you observed**

`README.md`:
- Retitle the intro from "a raft of Claude Code agents running in cmux" to cover cmux **or** Orca.
- Update the "How it works" ASCII diagram: add the Orca lane (`hook → $ORCA_WORKTREE_ID + orca worktree ps → --board write`).
- Replace "What you need" bullet `cmux with Claude Code sessions` with `cmux **or** Orca with Claude Code sessions`.
- Add an Orca setup subsection under "Reproduce it": `raft_board_init.py --slots …`, `duckypad_build_profile.py --host orca`, `duckypad_push_profile.py --profile orca`, `raft_board_verify.py`.
- Add these to "Known limitations", each one sentence plus the reason:
  - Orca addressing is by name, not position, because `⌘N` indexes visible worktree rows in a project→repo→worktree tree whose order and collapse state its CLI does not expose.
  - A stale board query can make Orca *create* a worktree; re-run `raft_board_verify.py` after renaming branches.
  - Leave Orca's `terminalShortcutPolicy` on its default `orca-first`, or `⌘J` stops reaching Orca from a focused pane.
  - `⌘J` from a focused pane pops a "Terminal shortcut handled" toast; cosmetic, dismissible.
  - The pad's loaded profile decides which host owns the board; the other host's hooks no-op.
  - Scope the existing `reorderOnNotification` limitation to cmux explicitly — Orca does not need it.
  - Orca installs its *own* Claude Code hook as a sibling entry on the same events, so after an Orca upgrade, confirm Raft's entry survived (see the check below).

Add a short "After an Orca upgrade" section to `docs/calibration.md` with the check itself, since Orca owns a block in the same file Raft does:

```bash
python3 -c "
import json, os
hooks = json.load(open(os.path.expanduser('~/.claude/settings.json')))['hooks']
for event, entries in hooks.items():
    raft = sum('duckypad_hook.py' in h.get('command','')
               for e in entries for h in e.get('hooks', []))
    orca = sum('orca/agent-hooks' in h.get('command','')
               for e in entries for h in e.get('hooks', []))
    print(f'{event:20} raft={raft} orca={orca}')
"
```

Expected: `raft=1` on every event Raft wires. A `raft=0` means an Orca upgrade replaced the block — re-merge `hooks/settings.snippet.json`.

`profile/README.md`: document `--host`, `--profile`, both output directories, and the Orca top-row macro shape including why the delays exist.

`docs/calibration.md`: add a short section recording the `PALETTE_OPEN_DELAY_MS` / `PALETTE_FILTER_DELAY_MS` values that worked on this hardware, since Step 1.5 may have changed them.

`hooks/settings.snippet.json`: update `_comment` to say the hook auto-detects cmux or Orca, and that on Orca every event repaints the whole board.

- [ ] **Step 3: Verify the docs describe reality**

Run: `grep -n "cmux" README.md | head -30`
Expected: every remaining mention is either historical, explicitly cmux-scoped, or in the credits — no bare claim that Raft requires cmux.

Run: `python3 -m unittest discover -s tests -v`
Expected: all PASS (nothing in this task should have touched code).

- [ ] **Step 4: Commit**

```bash
git add README.md profile/README.md docs/calibration.md hooks/settings.snippet.json
git commit -m "docs: host-agnostic README, Orca setup, and the caveats the probes found"
```

---

## Deferred, deliberately

- **Orca plugin for exact one-press jumping.** Orca's keybinding validator accepts `plugin:<name>/<command>` ids, so a plugin registering "focus worktree X" would beat palette macros: one press, no debounce race, no create hazard. No plugin-authoring guide ships with the CLI, so this needs API spelunking first.
- **`raft_board_verify.py` on `SessionStart`.** Cheap enough (~250 ms, async) to self-police the board, but it would need a quiet failure channel — an unattended hook cannot usefully tell you it found a problem. Revisit once there is somewhere to report to.
- **Reading Orca's sidebar order.** Only screenshots expose it (its AX tree is Electron-opaque). Not worth OCR for a mapping the user can declare in five lines of JSON.
