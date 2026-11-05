"""Pure helpers of the leech check (lane leech, bug #540, tools/leech_checks.py); no game is started.
Run: py -3 -I -m unittest discover -s tools/tests -p "test_leech_checks.py" """
import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import projtemp  # noqa: E402,F401  (temp files stay inside the project, tools/projtemp.py)
os.environ.setdefault("MXL_SLOT", "2")  # importing game_ctl needs a slot; nothing here starts a game
import leech_checks as lc  # noqa: E402


class ExpectedGain(unittest.TestCase):
    def test_normal_quarter(self):
        # 100 % leech on Normal (divisor 4): a quarter of the physical damage
        self.assertEqual(lc.expected_gain(400 << 8, 100, 4), 100 << 8)

    def test_nightmare_and_hell(self):
        self.assertEqual(lc.expected_gain(1000 << 8, 100, 100), 10 << 8)  # 6400 / 100 = 64: 1 %
        self.assertEqual(lc.expected_gain(1000 << 8, 100, 200), 5 << 8)   # 6400 / 200 = 32: 0.5 %

    def test_truncation(self):
        # 10 % on Hell: 640 / 200 = 3 (not 3.2), so 3 / 64 % of the damage
        self.assertEqual(lc.expected_gain(25600, 10, 200), 25600 * 3 // 100 >> 6)
        self.assertEqual(lc.expected_gain(100, 1, 200), 0)  # 64 / 200 = 0: nothing at all

    def test_vanilla_divisors(self):
        self.assertEqual(lc.expected_gain(300 << 8, 10, 1), 30 << 8)
        self.assertEqual(lc.expected_gain(300 << 8, 10, 3), 300 * 256 * 213 // 100 >> 6)

    def test_nothing(self):
        self.assertEqual(lc.expected_gain(0, 100, 4), 0)
        self.assertEqual(lc.expected_gain(1000, 0, 4), 0)
        self.assertEqual(lc.expected_gain(1000, 100, 4, drain=0), 0)

    def test_drain(self):
        self.assertEqual(lc.expected_gain(400 << 8, 100, 1, drain=50), 200 << 8)


class Judge(unittest.TestCase):
    def test_match_and_slack(self):
        hits = [(400 << 8, 100 << 8), (800 << 8, (200 << 8) + 1)]
        self.assertEqual(lc.judge(hits, 100, 4), (300 << 8 | 1, 300 << 8, True))

    def test_mismatch(self):
        got, want, ok = lc.judge([(400 << 8, 0)], 100, 4)
        self.assertEqual((got, want, ok), (0, 100 << 8, False))

    def test_divisors_are_median(self):
        self.assertEqual(lc.DIVISORS, {"normal": (4, 4), "nightmare": (100, 100), "hell": (200, 200)})


if __name__ == "__main__":
    unittest.main()
