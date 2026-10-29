"""The runeletters check's parser and rounds in game_checks.py (bug #334; no game is started)."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("MXL_SLOT", "2")  # importing game_ctl needs a slot; nothing here starts a game
import projtemp  # noqa: E402,F401
import game_checks as gc  # noqa: E402


class RuneLetterCheck(unittest.TestCase):
    LINE = ("runeletter on: rune letters without a D2R key drawn from the gems cell, as 1.14d (lookup 0x3e2b736 at 0x2c29da, "
            "loader patch); letters drawn from the cell 3, D2R keys kept 12")

    def test_counts(self):
        self.assertEqual(gc.rune_letter_counts("ilvl x\n" + self.LINE + "\nother"), (3, 12))

    def test_off_or_missing(self):
        self.assertIsNone(gc.rune_letter_counts("runeletter off: bytes differ at 0x2c29ae / 0x3e2b736, left as D2R"))
        self.assertIsNone(gc.rune_letter_counts(""))
        self.assertIsNone(gc.rune_letter_counts(None))

    def test_mxl2012_wants_the_line(self):
        import re
        pats = [p for n, p in [("runeletter", r"^runeletter on: rune letters without a D2R key drawn from the gems cell")]]
        self.assertTrue(re.search(pats[0], self.LINE))

    def test_rounds(self):
        rounds = gc.rune_letter_rounds()
        runes = {r for _, _, _, fs, _ in rounds for r in fs}
        self.assertEqual(runes, {"r01", "r47", "r51"})  # a D2R key, a literal that is another D2R key, a Great Rune
        for _, _, args, fs, letters in rounds:
            self.assertIn("194=%d" % len(fs), args)  # one socket per rune
            self.assertTrue(letters)

    def test_registered(self):
        names = [n for n, _ in gc.CHECKS]
        self.assertIn("runeletters", names)
        self.assertEqual(gc.unknown_checks(["runeletters"]), [])


if __name__ == "__main__":
    unittest.main()
