import unittest
from unittest import mock

import context  # noqa: F401  — puts sender/ on sys.path; must precede the import below
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
            self.assertEqual(
                h.run_orca("working", payload_env={"ORCA_WORKTREE_ID": "wt-1"}), 0)
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
