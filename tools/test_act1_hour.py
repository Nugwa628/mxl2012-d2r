"""The first-hour check of lane act1start (tools/act1_hour.py, `act1_hour`): registered, player path only (no harness move,
travel, kill, spawn, grant or god mode in its code), and its summary helper; no game is started."""
import inspect
import os
import re
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import projtemp  # noqa: E402,F401  (temp files stay inside the project, tools/projtemp.py)
os.environ.setdefault("MXL_SLOT", "2")  # importing game_ctl needs a slot; nothing here starts a game
import act1_hour  # noqa: E402
import game_checks as gc  # noqa: E402


class Act1Hour(unittest.TestCase):
    def test_registered(self):
        self.assertIn("act1_hour", [n for n, _ in gc.CHECKS])

    def test_player_path_only(self):
        src = inspect.getsource(act1_hour)
        for pat in (r"Tank\(", r"god 1", r"goto\(", r"\"level (%d|\d)", r"\"item ", r"\"kill ", r"\"spawn ", r"\"move ", r"\"moveto ",
                    r"\"interact ", r"\"menu ", r"\"pickup ", r"\"place ", r"\"gold set", r"\"xp ", r"\"waypoint n \d+ set",
                    r"\"setskill", r"\"enter ", r"\"operate "):
            m = re.search(pat, src)
            self.assertIsNone(m, "act1_hour uses a harness shortcut: %s" % (m.group(0) if m else ""))

    def test_classes_known(self):
        import playthrough
        for cls in act1_hour.CLASSES:
            self.assertIn(cls, playthrough.CLASS_NAMES)

    def test_fight_summary(self):
        self.assertEqual(act1_hour.fight_summary([]), (0, 0, 0.0))
        self.assertEqual(act1_hour.fight_summary([(0, 2), (4, 2), (2, 0)]), (2, 4, 2.0))


if __name__ == "__main__":
    unittest.main()
