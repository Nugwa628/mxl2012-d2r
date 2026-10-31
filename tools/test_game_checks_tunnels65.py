"""The tunnels65 check's spot maths in game_checks.py (lane tunnels65; no game is started)."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("MXL_SLOT", "2")  # importing game_ctl needs a slot; nothing here starts a game
import projtemp  # noqa: E402,F401
import game_checks as gc  # noqa: E402


class Tunnels65Check(unittest.TestCase):
    def test_origin_is_the_lowest_room_corner(self):
        lines = ["h: presets rooms", "room x=20040 y=5080 w=40", "room x=20000 y=5120", "presets 2 rooms"]
        self.assertEqual(gc.t65_origin(lines), (20000, 5080))
        self.assertIsNone(gc.t65_origin(["presets 0 rooms"]))

    def test_spots_are_cell_middles(self):
        self.assertEqual(gc.t65_spots((100, 200), ((0, 0), (16, 7))), [(102, 202), (182, 237)])

    def test_spots_stand_on_belial_floor_cells(self):
        # the platform of belial.ds1 (lane tunnels65's dump): columns 11-21, rows 6-31
        for cx, cy in gc.T65_CELLS:
            self.assertTrue(11 <= cx <= 21 and 6 <= cy <= 31, (cx, cy))

    def test_registered(self):
        self.assertIn("tunnels65", [n for n, _f in gc.CHECKS])


if __name__ == "__main__":
    unittest.main()
