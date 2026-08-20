import unittest

import context  # noqa: F401  — puts profile/ on sys.path; must precede the import below
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
        gen.build("orca", SLOTS, out)
        for n in range(1, 16):
            self.assertTrue(os.path.exists(os.path.join(out, f"key{n}.txt")),
                            f"key{n}.txt missing")
        config = open(os.path.join(out, "config.txt")).read()
        self.assertIn("z3 raft", config)
        self.assertIn("SWCOLOR_3", config)


if __name__ == "__main__":
    unittest.main()
