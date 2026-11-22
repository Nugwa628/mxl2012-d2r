"""tools/monster_turn_sheet.py: which shot of a mon_turn run stands for a facing, and where the monster is in it."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

import projtemp  # noqa: E402,F401
import monster_turn_sheet as mts  # noqa: E402


def rec(shot, key, mode, t, spawn_key=0, graphics="hd", after=None, x=108, y=100):
    before = {"mode": mode, "dir": key * 8, "key": key, "x": x, "y": y, "px": 100, "py": 100}
    return {"shot": shot, "graphics": graphics, "spawn_key": spawn_key, "what": "e0", "t": t,
            "before": before, "after": dict(before, **(after or {}))}


class Pick(unittest.TestCase):
    def test_a_shot_between_two_keys_is_not_taken(self):
        index = [rec("a.png", 3, 1, 0.2, after={"key": 4}), rec("b.png", 3, 1, 0.9)]
        self.assertFalse(mts.steady(index[0]))
        self.assertEqual(mts.pick(index, "hd", 3, (1, 2))["shot"], "b.png")

    def test_a_shot_between_two_unit_modes_is_not_taken(self):
        self.assertFalse(mts.steady(rec("a.png", 3, 1, 0.2, after={"mode": 2})))

    def test_a_shot_without_a_facing_is_not_taken(self):
        self.assertFalse(mts.steady({"shot": "a.png", "graphics": "hd", "before": {}, "after": {}}))
        self.assertIsNone(mts.pick([{"shot": "a.png", "graphics": "hd", "before": {}, "after": {}}], "hd", 0, (1,)))

    def test_the_first_unit_mode_asked_for_wins(self):
        index = [rec("walk.png", 2, 2, 0.1), rec("stand.png", 2, 1, 0.8)]
        self.assertEqual(mts.pick(index, "hd", 2, (1, 2))["shot"], "stand.png")
        self.assertEqual(mts.pick(index, "hd", 2, (2, 1))["shot"], "walk.png")

    def test_the_monster_spawned_for_the_key_wins_then_the_earliest_shot(self):
        index = [rec("other.png", 5, 1, 0.1, spawn_key=4), rec("late.png", 5, 1, 0.7, spawn_key=5), rec("own.png", 5, 1, 0.3, spawn_key=5)]
        self.assertEqual(mts.pick(index, "hd", 5, (1,))["shot"], "own.png")

    def test_graphics_modes_are_kept_apart(self):
        index = [rec("hd.png", 1, 1, 0.1), rec("legacy.png", 1, 1, 0.1, graphics="legacy")]
        self.assertEqual(mts.pick(index, "legacy", 1, (1,))["shot"], "legacy.png")
        self.assertIsNone(mts.pick(index, "legacy", 2, (1,)))

    def test_the_middle_shot_of_the_first_run_that_holds_the_key(self):
        one = {"graphics": "hd", "index": [rec("a.png", 1, 3, 0.1)]}
        two = {"graphics": "hd", "index": [rec("b.png", 2, 3, 0.9), rec("c.png", 2, 3, 0.1), rec("d.png", 2, 3, 0.5), rec("e.png", 1, 3, 0.2)]}
        self.assertEqual(mts.middle([one, two], 1, 3)[1]["shot"], "a.png")
        self.assertEqual(mts.middle([one, two], 2, 3)[1]["shot"], "d.png")
        self.assertIsNone(mts.middle([one, two], 4, 3))  # never from another direction
        self.assertIsNone(mts.middle([one, two], 2, 4))

    def test_a_shot_near_the_character_goes_before_a_far_one_of_an_earlier_run(self):
        far = {"graphics": "hd", "index": [rec("far.png", 6, 2, 0.1, x=85)]}
        near = {"graphics": "hd", "index": [rec("near.png", 6, 2, 0.1, x=97)]}
        self.assertEqual(mts.middle([far, near], 6, 2)[1]["shot"], "near.png")
        self.assertEqual(mts.middle([far], 6, 2)[1]["shot"], "far.png")

    def test_coverage_lists_the_keys_per_unit_mode(self):
        index = [rec("a.png", 1, 1, 0.1), rec("b.png", 3, 1, 0.1), rec("c.png", 3, 5, 0.1), rec("d.png", 7, 5, 0.1, after={"key": 0})]
        self.assertEqual(mts.coverage(index, "hd"), {1: [1, 3], 5: [3]})


class Project(unittest.TestCase):
    def test_a_step_along_x_is_screen_down_right_and_along_y_down_left(self):
        view = (800.0, 428.0, 1.5)
        self.assertEqual(mts.project(rec("a.png", 0, 1, 0, x=100, y=100), view), (800.0, 428.0))
        self.assertEqual(mts.project(rec("a.png", 0, 1, 0, x=108, y=100), view), (800.0 + 8 * 24, 428.0 + 8 * 12))
        self.assertEqual(mts.project(rec("a.png", 0, 1, 0, x=100, y=108), view), (800.0 - 8 * 24, 428.0 + 8 * 12))


class Sheets(unittest.TestCase):
    def test_a_facings_sheet_has_a_row_per_run_and_a_cut_per_key(self):
        from PIL import Image
        with tempfile.TemporaryDirectory() as tmp:
            run = Path(tmp) / "run"
            run.mkdir()
            index = []
            for k in range(7):  # key 7 was not shot
                Image.new("RGB", (1600, 900), (10 * k, 60, 30)).save(run / ("s%d.png" % k))
                index.append(rec("s%d.png" % k, k, 1, 0.1 * k, spawn_key=k))
            (run / "monturn_index.json").write_text(json.dumps(index), encoding="utf-8")
            out = Path(tmp) / "sheet.png"
            self.assertEqual(mts.main(["facings", str(out), "card=%s:hd" % run, "cut=100"]), 0)
            with Image.open(out) as im:
                self.assertEqual(im.size, (190 + 8 * 100, 54 + 100))
                self.assertEqual(im.getpixel((190 + 3 * 100 + 50, 54 + 30)), (30, 60, 30))
                self.assertEqual(im.getpixel((190 + 7 * 100 + 50, 54 + 30)), mts.BG)
            self.assertEqual(mts.main(["walk", str(out), "card=%s" % run, "key=3", "cut=100"]), 0)
            self.assertEqual(mts.main(["grid", str(out), "card=%s" % run, "modes=1,5", "cut=100"]), 0)
            with Image.open(out) as im:
                self.assertEqual(im.size, (190 + 8 * 100, 54 + 2 * 100))
            self.assertEqual(mts.main(["blocks", str(out), "card=%s" % run, "card=%s" % run, "modes=1,3", "cut=100"]), 0)
            with Image.open(out) as im:
                self.assertEqual(im.size, (190 + 8 * 100, 2 * (54 + 100 + 12)))
            self.assertEqual(mts.main(["strip", str(out), "classic=%s@0,0,200,200" % (run / "s1.png"), "card=%s" % (run / "s2.png"), "cut=100"]), 0)
            with Image.open(out) as im:
                self.assertEqual(im.size, (190 + 2 * 100, 54 + 100))


if __name__ == "__main__":
    unittest.main()
