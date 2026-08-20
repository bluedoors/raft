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
