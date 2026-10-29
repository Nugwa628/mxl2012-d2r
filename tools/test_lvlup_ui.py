"""game_checks.py check `lvlup_ui` (lane uiplus, bugs #488 / #489): the button spots and the panel-opened test of its clicks."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("MXL_SLOT", "2")  # importing game_ctl needs a slot; nothing here starts a game
import projtemp  # noqa: E402,F401
import game_checks as gc  # noqa: E402
from PIL import Image  # noqa: E402


def scene(left=(30, 40, 20), right=(30, 40, 20)):
    """A 1600 x 900 client: the half where the stat panel opens (left) and where the skill tree opens (right)."""
    im = Image.new("RGB", (1600, 900), (30, 40, 20))
    im.paste(Image.new("RGB", (600, 600), left), (200, 100))
    im.paste(Image.new("RGB", (600, 600), right), (800, 100))
    return im


class PanelChange(unittest.TestCase):
    def test_no_change_reads_zero(self):
        self.assertEqual(gc.lvlup_panel_change(scene(), scene(), "stat"), 0.0)

    def test_stat_panel_seen_on_the_left_only(self):
        opened = scene(left=(120, 110, 100))
        self.assertGreater(gc.lvlup_panel_change(scene(), opened, "stat"), 20)
        self.assertEqual(gc.lvlup_panel_change(scene(), opened, "skill"), 0.0)

    def test_skill_tree_seen_on_the_right_only(self):
        opened = scene(right=(120, 110, 100))
        self.assertGreater(gc.lvlup_panel_change(scene(), opened, "skill"), 20)
        self.assertEqual(gc.lvlup_panel_change(scene(), opened, "stat"), 0.0)

    def test_hud_below_the_box_is_not_counted(self):
        lit = scene()
        lit.paste(Image.new("RGB", (40, 40), (200, 20, 20)), (512, 846))  # the classic stat + turning red (row 846-886)
        self.assertEqual(gc.lvlup_panel_change(scene(), lit, "stat"), 0.0)


class Spots(unittest.TestCase):
    def test_spots_inside_the_client(self):
        for mode in ("legacy", "hd"):
            for x, y in gc.LVLUP_XY[mode]:
                self.assertTrue(0 < x < 1600 and 0 < y < 900, (mode, x, y))

    def test_legacy_spots_inside_the_pillarbox(self):  # legacy graphics draw 4:3 (1200 x 900) between black side bars
        for x, _y in gc.LVLUP_XY["legacy"]:
            self.assertTrue(200 <= x < 1400, x)


if __name__ == "__main__":
    unittest.main()
