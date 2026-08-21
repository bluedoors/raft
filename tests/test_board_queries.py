import unittest

import context  # noqa: F401  — puts scripts/ on sys.path; must precede the import below
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


class TestCheckBoard(unittest.TestCase):
    """check_board only guards LED truthfulness now — jumping is Orca's job."""

    def test_good_board_has_no_problems(self):
        slots = [{"label": "1", "worktree": "id-raft"}]
        self.assertEqual(rb.check_board(slots, WORKTREES), [])

    def test_missing_worktree_is_a_problem(self):
        slots = [{"label": "1", "worktree": "id-gone"}]
        problems = rb.check_board(slots, WORKTREES)
        self.assertTrue(any("no longer exists" in p.lower() for p in problems))

    def test_missing_worktree_says_the_key_still_jumps(self):
        """The failure is a lying LED, not a broken key — say so, or the user
        goes looking for a jump bug that doesn't exist."""
        problems = rb.check_board([{"label": "3", "worktree": "id-gone"}], WORKTREES)
        self.assertIn("jumps", problems[0].lower())

    def test_overlong_label_is_a_problem(self):
        slots = [{"label": "waytoolong", "worktree": "id-raft"}]
        problems = rb.check_board(slots, WORKTREES)
        self.assertTrue(any("7 characters" in p for p in problems))

    def test_a_board_without_queries_is_valid(self):
        """Queries are gone. A board carrying none must not be faulted for it."""
        slots = [{"label": str(i), "worktree": w} for i, w in
                 enumerate(["id-raft", "id-main1", "id-vpc"], start=1)]
        self.assertEqual(rb.check_board(slots, WORKTREES), [])

    def test_ambiguity_is_no_longer_a_problem(self):
        """Two rows may watch worktrees that share a name; only ids matter."""
        slots = [{"label": "1", "worktree": "id-main1"},
                 {"label": "2", "worktree": "id-main2"}]
        self.assertEqual(rb.check_board(slots, WORKTREES), [])


if __name__ == "__main__":
    unittest.main()
