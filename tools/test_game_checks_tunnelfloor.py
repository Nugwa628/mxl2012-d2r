"""The tunnelfloor check's walk route and walk-map text in game_checks.py (lane tunnelfloor; no game is started)."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("MXL_SLOT", "2")  # importing game_ctl needs a slot; nothing here starts a game
import projtemp  # noqa: E402,F401
import game_checks as gc  # noqa: E402


class TunnelfloorCheck(unittest.TestCase):
    def test_other_levels_are_not_walked(self):
        known = {(0, 0): ".", (2, 0): 44, (4, 0): "."}
        self.assertEqual(gc.tf_grid_text(known), ["0 .o."])

    def test_spots_stand_on_belial_floor_cells(self):
        for _name, (cx, cy) in gc.TF_SPOTS:
            self.assertTrue(11 <= cx <= 21 and 6 <= cy <= 31, (cx, cy))

    def test_route_passes_the_neck_and_ends_at_the_bar(self):
        route = list(gc.TF_ROUTE)
        self.assertEqual(route[-1], dict(gc.TF_SPOTS)["bar"])
        self.assertIn(dict(gc.TF_SPOTS)["neck"], route)
        for a, b in zip(route, route[1:]):  # short legs: a straight walk each
            self.assertLessEqual(max(abs(a[0] - b[0]), abs(a[1] - b[1])), 4, (a, b))

    def test_registered(self):
        names = [n for n, _f in gc.CHECKS]
        for name in ("tunnelfloor", "tfreload", "tfhell"):
            self.assertIn(name, names)


if __name__ == "__main__":
    unittest.main()
