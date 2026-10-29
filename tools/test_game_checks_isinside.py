"""The lane isinside check in game_checks.py (bug #242): registration and the portal filter (no game is started)."""
import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("MXL_SLOT", "2")  # importing game_ctl needs a slot; nothing here starts a game
import projtemp  # noqa: E402,F401
import game_checks as gc  # noqa: E402


class InsLevels(unittest.TestCase):
    def test_registered(self):
        names = [n for n, _ in gc.CHECKS]
        self.assertIn("ins_levels", names)
        self.assertEqual(gc.unknown_checks(["ins_levels"]), [])

    def test_levels(self):
        self.assertEqual(gc.INS_LEVELS, (84, 125, 126, 127))
        self.assertEqual(gc.INS_SPIDER_FOREST, 76)

    def test_portal_objects_near_only(self):
        lines = ["object id=5 class=59 mode=1 dist=3 at 100,200", "object id=6 class=59 mode=1 dist=40 at 140,240",
                 "object id=7 class=119 mode=1 dist=2 at 101,201", "object id=8 class=60 mode=1 dist=12 at 110,210"]
        with patch.object(gc, "Hl", return_value=(True, lines)):
            self.assertEqual([o["id"] for o in gc.ins_portal_objects([])], [5, 8])


if __name__ == "__main__":
    unittest.main()
