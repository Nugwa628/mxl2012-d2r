"""Lane wallscan: MXL_WALL_SPOTS parsing for wall_maps (no game is started)."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("MXL_SLOT", "2")  # importing game_ctl needs a slot; nothing here starts a game
import projtemp  # noqa: E402,F401
import game_checks as gc  # noqa: E402


class WallSpots(unittest.TestCase):
    def test_none(self):
        self.assertEqual(gc.wall_spots({}), {})

    def test_cells_and_origin(self):
        got = gc.wall_spots({"MXL_WALL_SPOTS": "84:20,30;40,12|18@10000,5000:64,64|x:1,2"})
        self.assertEqual(got[84], [(20, 30), (40, 12)])
        self.assertEqual(got[18], [(64, 64)])
        self.assertEqual(got[(18, "origin")], (10000, 5000))
        self.assertNotIn((84, "origin"), got)
        self.assertEqual(len(got), 3)


if __name__ == "__main__":
    unittest.main()
