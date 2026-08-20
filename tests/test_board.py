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
