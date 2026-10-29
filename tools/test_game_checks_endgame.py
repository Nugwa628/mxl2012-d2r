"""Lane endgame in game_checks.py: the asked-only Mephisto melee stage, the moat line read and the known #394 assert (no game
is started)."""
import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("MXL_SLOT", "2")  # importing game_ctl needs a slot; nothing here starts a game
import projtemp  # noqa: E402,F401
import game_checks as gc  # noqa: E402


class Stages(unittest.TestCase):
    def test_mephmelee_only_when_asked(self):
        self.assertNotIn("mephmelee", gc.acts_stages(""))
        self.assertEqual(gc.acts_stages("mephmelee,diablo"), ["mephmelee", "diablo"])

    def test_throne_before_baal(self):
        order = gc.acts_stages("baal,throne")
        self.assertEqual(order, ["throne", "baal"])

    def test_394_is_known(self):
        self.assertTrue(any(k in "BC_ASSERT: ptCreate->hSource" for k in gc.KNOWN_ASSERTS))


class LineBlocked(unittest.TestCase):
    def test_moat_cells_counted(self):
        # a 9 x 1 strip from x 100: free, then 3 blocked (the moat), then free; the line runs along it
        wm = {"grid": [".." + "###" + "...."], "x0": 100, "y0": 50, "step": 1, "level": 102, "others": {}}
        with patch.object(gc, "relp_walkmap", return_value=wm):
            self.assertEqual(gc.line_blocked(100, 50, 108, 50, []), (3, 0, 7))

    def test_no_walkmap(self):
        with patch.object(gc, "relp_walkmap", return_value=None):
            self.assertIsNone(gc.line_blocked(0, 0, 5, 5, []))


class Portals(unittest.TestCase):
    def test_tyrael_portal_class(self):
        self.assertEqual(gc.TYRAEL_PORTAL, 566)  # objects.txt NotKiddingLastPortal "Harrogath", OperateFn 73

    def test_no_portal_object(self):
        with patch.object(gc, "Hl", return_value=(True, ["objects 0"])):
            self.assertEqual(gc.acts_click_portal(566, 103, 109, []), "no object 566 in area 103")


if __name__ == "__main__":
    unittest.main()
