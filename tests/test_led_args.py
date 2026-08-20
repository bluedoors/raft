import json
import os
import tempfile
import unittest

import context  # noqa: F401  — puts sender/ on sys.path; must precede the import below
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
