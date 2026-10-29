"""The stip_tooltips check's helpers in game_checks.py (bug #396; no game is started)."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("MXL_SLOT", "2")  # importing game_ctl needs a slot; nothing here starts a game
import projtemp  # noqa: E402,F401
import game_checks as gc  # noqa: E402


class SkillTipCheck(unittest.TestCase):
    LINE = "skilltext skill tooltip labels in 1.13c's words (0x287a50 hooked); labels cut 17"

    def test_counter(self):
        self.assertEqual(gc.stip_labels_cut("ilvl x\n" + self.LINE + "\nother"), 17)

    def test_off_or_failed(self):
        self.assertIsNone(gc.stip_labels_cut("skilltext off (mxl2012-core-off.txt)"))
        self.assertIsNone(gc.stip_labels_cut("skilltext skill tooltip labels in 1.13c's words (0x287a50 hooked) FAILED; labels cut 0"))
        self.assertIsNone(gc.stip_labels_cut(""))

    def test_mxl2012_wants_the_line(self):
        import re
        self.assertTrue(re.search(r"^skilltext skill tooltip labels in 1\.13c's words \(0x287a50 hooked\)", self.LINE))

    def test_popup_cells(self):
        hd, classic = gc.stip_popup_cells("hd"), gc.stip_popup_cells("legacy")
        self.assertEqual(hd[:2], ((857, 738), (913, 738)))  # going right from the cell left of the button
        self.assertEqual(classic[:2], ((1244, 735), (1172, 735)))  # going left from the right-most column
        self.assertTrue(all(0 < x < 1600 and 0 < y < 900 for x, y in hd + classic))

    def test_registered_above_main(self):
        self.assertIn("stip_tooltips", [n for n, _ in gc.CHECKS])
        src = open(gc.__file__, encoding="utf-8").read()
        self.assertTrue(src.rstrip().endswith('if __name__ == "__main__":\n    main()'))


if __name__ == "__main__":
    unittest.main()
