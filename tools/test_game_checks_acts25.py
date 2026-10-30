"""Lane acts25 in game_checks.py: the click-entry routes of an act, the `reassign` counter line, the boss and travel tables (no game
is started)."""
import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("MXL_SLOT", "2")  # importing game_ctl needs a slot; nothing here starts a game
import projtemp  # noqa: E402,F401
import game_checks as gc  # noqa: E402

LEVELS = [{"Id": "40", "Act": "1", "Vis0": "47", "Warp0": "19", "Vis1": "47", "Warp1": "20", "Vis2": "41", "Warp2": "-1"},
          {"Id": "47", "Act": "1", "Vis0": "40", "Warp0": "22", "Vis1": "48", "Warp1": "23"},
          {"Id": "48", "Act": "1", "Vis0": "47", "Warp0": "22"},
          {"Id": "75", "Act": "2", "Vis0": "76", "Warp0": "-1"},
          {"Id": "107", "Act": "3", "Vis0": "106", "Warp0": "70", "Vis1": "108", "Warp1": "-1"}]


class Routes(unittest.TestCase):
    def test_pairs_once_tiles_only(self):
        with patch.object(gc, "table", return_value=LEVELS):
            self.assertEqual(gc.a25_routes(2), [(40, 47), (47, 48)])  # 40-41 is an outdoor edge (Warp -1): no tile
            self.assertEqual(gc.a25_routes(3), [])
            self.assertEqual(gc.a25_routes(4), [(106, 107)])


class Reassign(unittest.TestCase):
    def test_counter_line(self):
        text = "mxl2012 ...\nreassign on: guard; commands 53, units left without a room 11, the player without a room 0\n"
        with patch.object(gc, "mxl_text", return_value=text):
            self.assertEqual(gc.a25_reassign(), (53, 11, 0))

    def test_no_line(self):
        with patch.object(gc, "mxl_text", return_value="mxl2012 ...\n"):
            self.assertIsNone(gc.a25_reassign())


class Tables(unittest.TestCase):
    def test_last_boss_opens_next_act(self):
        for act, bosses in gc.A25_BOSSES.items():
            self.assertTrue(bosses[-1][3], act)
            self.assertEqual(sum(1 for b in bosses if b[3]), 1, act)

    def test_travel_and_revivers(self):
        self.assertTrue(all(a in gc.A25_REVIVERS for a in (2, 3, 4, 5)))
        self.assertNotEqual(gc.A25_TALK, 0)

    def test_hireling_not_a_target(self):
        st = {"mons": [{"id": 46, "class": 338, "dist": 3, "life": 5120000}, {"id": 7, "class": 5, "dist": 4, "life": 10}]}
        self.assertEqual([m["id"] for m in gc.hostiles_near(st, 10, unkillable=set())], [7])

    def test_registered(self):
        self.assertIn("acts25", [n for n, _f in gc.CHECKS])


if __name__ == "__main__":
    unittest.main()
