"""The void_maps check's settings in game_checks.py (lane voidengine; no game is started)."""
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("MXL_SLOT", "2")  # importing game_ctl needs a slot; nothing here starts a game
import projtemp  # noqa: E402,F401
import game_checks as gc  # noqa: E402


class VoidMapsCheck(unittest.TestCase):
    def test_default_levels(self):
        with mock.patch.dict(os.environ, {"MXL_VOID_LEVELS": ""}):
            self.assertEqual(gc.void_levels(), [65, 74])

    def test_levels_from_env(self):
        with mock.patch.dict(os.environ, {"MXL_VOID_LEVELS": "65, x,74,"}):
            self.assertEqual(gc.void_levels(), [65, 74])
        with mock.patch.dict(os.environ, {"MXL_VOID_LEVELS": "74"}):
            self.assertEqual(gc.void_levels(), [74])

    def test_first_shot_is_the_arrival(self):
        self.assertEqual(gc.VOID_OFFSETS[0], (0, 0))

    def test_registered(self):
        self.assertIn("void_maps", [n for n, _f in gc.CHECKS])


if __name__ == "__main__":
    unittest.main()
