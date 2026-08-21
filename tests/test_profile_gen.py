import unittest

import context  # noqa: F401  — puts profile/ on sys.path; must precede the import below
import duckypad_build_profile as gen


SLOTS = [{"label": "raft", "worktree": "id-1", "query": "orca-host"},
         {"label": "gw", "worktree": "id-2", "query": "vpc-reuse"}]


class TestTopRow(unittest.TestCase):
    """Both hosts address the top row positionally. No typing, no board input."""

    def test_cmux_top_row_is_positional(self):
        keys = gen.top_row_keys("cmux", [])
        self.assertEqual(keys[3][1], "GUI 1")
        self.assertEqual(keys[15][1], "GUI 5")
        self.assertEqual(len(keys), 5)

    def test_orca_top_row_is_positional_too(self):
        keys = gen.top_row_keys("orca", SLOTS)
        self.assertEqual(keys[3][1], "GUI 1")
        self.assertEqual(keys[15][1], "GUI 5")

    def test_orca_and_cmux_top_rows_are_identical(self):
        """The hosts converged. If this ever diverges, say why in a comment."""
        self.assertEqual(gen.top_row_keys("orca", SLOTS), gen.top_row_keys("cmux", []))

    def test_top_row_never_types_or_opens_the_palette(self):
        """Regression guard for the retired \u2318J macro.

        That macro could type into a live agent's prompt on a cold palette open,
        and its trailing ENTER could submit the leaked text. It could also CREATE
        a worktree when its saved query went stale. Nothing here may reintroduce
        keystrokes that depend on timing or on matching a name.
        """
        for script in (k[1] for k in gen.top_row_keys("orca", SLOTS).values()):
            self.assertNotIn("GUI j", script)
            self.assertNotIn("STRING", script)
            self.assertNotIn("DELAY", script)
            self.assertNotIn("ENTER", script)

    def test_labels_are_just_row_numbers(self):
        """A name baked into the pad goes stale the moment you rearrange Orca."""
        keys = gen.top_row_keys("orca", SLOTS)
        self.assertEqual([keys[k][0] for k in gen.TOP_ROW], ["1", "2", "3", "4", "5"])

    def test_output_ignores_the_board(self):
        """No board, half a board, or a full board must all generate the same keys."""
        self.assertEqual(gen.top_row_keys("orca", []), gen.top_row_keys("orca", SLOTS))
        self.assertEqual(gen.top_row_keys("orca", None), gen.top_row_keys("orca", SLOTS))

    def test_labels_never_exceed_seven_characters(self):
        for label, _, _ in gen.top_row_keys("orca", SLOTS).values():
            self.assertLessEqual(len(label), gen.MAX_LABEL)


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
        self.assertEqual(set(gen.COMMON_KEYS), {1, 4, 7, 10, 13, 11, 14})

    def test_cmd_n_is_labelled_per_host(self):
        """Same keystroke, different meaning: cmux workspace vs Orca worktree."""
        self.assertEqual(gen.HOST_KEYS["cmux"][5], ("New WS", "GUI n", (0, 50, 60)))
        self.assertEqual(gen.HOST_KEYS["orca"][5], ("New WT", "GUI n", (0, 50, 60)))

    def test_every_host_defines_all_fifteen_keys(self):
        """A key missing from a host would silently ship as an inert blank."""
        for host in gen.HOST_KEYS:
            keys = set(gen.COMMON_KEYS) | set(gen.HOST_KEYS[host]) | set(gen.TOP_ROW)
            self.assertEqual(keys, set(range(1, 16)), f"{host} is missing keys")


def _compiler_available():
    """Is the duckyPad Configurator source reachable? build() needs it to emit .dsb."""
    try:
        gen._compiler()
        return True
    except SystemExit:
        return False


@unittest.skipUnless(_compiler_available(),
                     "duckyPad Configurator source absent (set RAFT_CONFIG_SRC)")
class TestBuild(unittest.TestCase):
    def test_build_writes_fifteen_keys_and_a_config(self):
        import os
        import tempfile
        out = tempfile.mkdtemp()
        gen.build("orca", out)
        for n in range(1, 16):
            self.assertTrue(os.path.exists(os.path.join(out, f"key{n}.txt")),
                            f"key{n}.txt missing")
        config = open(os.path.join(out, "config.txt")).read()
        self.assertIn("z3 1", config)   # top-left key is labelled "1"
        self.assertIn("SWCOLOR_3", config)


if __name__ == "__main__":
    unittest.main()
