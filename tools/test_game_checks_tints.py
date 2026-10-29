"""The helpers of check tint_hd (lane tints) on synthetic reports; no game is started and no run folder is made."""
import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import projtemp  # noqa: E402,F401  (temp files stay inside the project, tools/projtemp.py)
os.environ.setdefault("MXL_SLOT", "2")  # importing game_ctl needs a slot; nothing here starts a game
import game_checks  # noqa: E402

LEVELS = {"quillbear1": {"level0": "quillbear1", "levels": {"3": {"ids": ["quillbear4", "elite_quillsA"], "shift": "x"},
                                                              "4": {"ids": ["quillbear5"], "shift": "y"}}},
          "nolevel0": {"level0": None, "levels": {"2": {"ids": ["a"], "shift": "z"}}}}
RECOLOURS = [{"kind": "missile", "from": "firebolt", "src_row": "firebolt", "to": "fireb_123456", "rows": ["magefirebolt1", "x"]},
             {"kind": "missile", "from": "old", "to": "old_c", "src_rows": ["medianrow"], "rows": ["y"]},  # no D2R row
             {"kind": "overlay", "from": "common/a", "to": "b", "rows": ["b"]}]


class TintHelpers(unittest.TestCase):
    def test_pairs_skip_units_without_a_level0_id(self):
        self.assertEqual(game_checks.tint_pairs(LEVELS), [("quillbear1", "quillbear4", "quillbear1", "3"),
                                                          ("quillbear1", "quillbear5", "quillbear1", "4")])

    def test_missile_pairs(self):
        self.assertEqual(game_checks.tint_missile_pairs(RECOLOURS), [("magefirebolt1", "firebolt", "fireb_123456"),
                                                                     ("y", "medianrow", "old_c")])

    def test_missile_pairs_take_a_source_row_the_table_has(self):
        known = {"magefirebolt1", "firebolt", "y"}
        self.assertEqual(game_checks.tint_missile_pairs(RECOLOURS, known), [("magefirebolt1", "firebolt", "fireb_123456")])

    def test_class_is_the_row_of_the_built_table(self):
        rows = [{"Id": "skeleton1"}, {"Id": "quillbear4"}]
        with patch.object(game_checks, "table", return_value=rows):
            self.assertEqual(game_checks.tint_class("quillbear4"), 1)
            self.assertIsNone(game_checks.tint_class("nothing"))

    def test_registered(self):
        self.assertIn("tint_hd", [name for name, _ in game_checks.CHECKS])


if __name__ == "__main__":
    unittest.main()
