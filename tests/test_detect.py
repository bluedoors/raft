import unittest

import context  # noqa: F401  — puts sender/ on sys.path; must precede the import below
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
