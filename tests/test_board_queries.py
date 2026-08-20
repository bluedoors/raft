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
