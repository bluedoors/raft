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


if __name__ == "__main__":
    unittest.main()
