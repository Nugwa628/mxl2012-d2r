"""Unit tests of the item picture review tools (item_art_review: visibility ranking, the proposal switch; item_art_sheets:
loose silhouette match, colour match, colour by position, upscale variants, sheet drawing) on synthetic data (no game
files). Run: py -3 -I -m unittest discover -s tools/tests -p "test_itemart.py" """
import json
import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import projtemp  # noqa: E402,F401  (temp files stay inside the project, tools/projtemp.py)
import item_art_review as R  # noqa: E402
import item_art_sheets as S  # noqa: E402
import upscale  # noqa: E402


def disc(h: int, w: int, colour=(200, 50, 50)) -> np.ndarray:
    """An opaque ellipse filling an h x w box."""
    y, x = np.mgrid[:h, :w]
    a = np.zeros((h, w, 4), np.uint8)
    m = ((y - (h - 1) / 2) / (h / 2)) ** 2 + ((x - (w - 1) / 2) / (w / 2)) ** 2 <= 1
    a[m] = (*colour, 255)
    return a


def box(h: int, w: int, colour=(200, 50, 50)) -> np.ndarray:
    a = np.zeros((h, w, 4), np.uint8)
    a[...] = (*colour, 255)
    return a


class TreasureClassTests(unittest.TestCase):
    def tc(self, name, picks, nodrop, *items):
        r = {"Treasure Class": name, "Picks": str(picks), "NoDrop": str(nodrop)}
        for i, (item, p) in enumerate(items, 1):
            r[f"Item{i}"], r[f"Prob{i}"] = item, str(p)
        return r

    def test_positive_picks_share_with_nodrop(self):
        t = R.TreasureClasses([self.tc("A", 2, 2, ("x", 1), ("y", 1))])
        e = t.expect("A")
        self.assertAlmostEqual(e["x"], 2 * 1 / 4)
        self.assertAlmostEqual(e["y"], 0.5)

    def test_negative_picks_drop_each_entry_prob_times(self):
        t = R.TreasureClasses([self.tc("A", -3, 0, ("x", 2), ("y", 1))])
        self.assertEqual(dict(t.expect("A")), {"x": 2, "y": 1})

    def test_nested_classes_multiply_and_codes_drop_the_parameters(self):
        t = R.TreasureClasses([self.tc("Top", 1, 0, ("Inner", 1), ("z", 1)), self.tc("Inner", 1, 1, ("r48,mul=2", 1))])
        e = t.expect("Top")
        self.assertAlmostEqual(e["r48"], 0.5 * 0.5)
        self.assertAlmostEqual(e["z"], 0.5)

    def test_monster_drops_sum_the_three_difficulties_of_enabled_rows(self):
        t = R.TreasureClasses([self.tc("A", 1, 0, ("x", 1))])
        mons = [{"enabled": "1", "TreasureClass1": "A", "TreasureClass1(N)": "A", "TreasureClass1(H)": ""},
                {"enabled": "0", "TreasureClass1": "A"}]
        self.assertEqual(R.monster_drops(mons, t)["x"], 2)


class RankTests(unittest.TestCase):
    def test_vendor_and_cube_columns(self):
        misc = [{"code": "a", "AkaraMin": "1"}, {"code": "b", "AkaraMin": "0", "GheedMagicMin": "2"},
                {"code": "c", "AkaraMin": "0"}]
        self.assertEqual(R.vendor_sold(misc), {"a", "b"})
        cube = [{"enabled": "1", "output": "a", "output b": '"b,qty=2"'}, {"enabled": "0", "output": "a"}]
        self.assertEqual(dict(R.cube_outputs(cube)), {"a": 1, "b": 1})

    def test_rank_orders_by_visibility(self):
        def pic(key, code, typ, lvl):
            p = R.Picture(key, "misc")
            p.users.append({"table": "misc", "code": code, "name": code, "type": typ, "level": lvl})
            return p
        pics = {p.key: p for p in (pic("mxl/a", "a", "thng", "90"), pic("mxl/b", "b", "rune", "60"),
                                   pic("mxl/c", "c", "thng", "0"))}
        out = R.rank(pics, {"b": 0.3}, {"c"}, {"a": 1})
        self.assertEqual([p.key for p in out], ["mxl/b", "mxl/c", "mxl/a"])
        self.assertTrue(out[0].kept and not out[0].low)
        self.assertIn("sold", out[1].why())

    def test_review_order_puts_proposals_first_and_keeps_set_members_below_the_top(self):
        ranked = [R.Picture(k, "misc") for k in ("mxl/a", "mxl/b", "mxl/c", "mxl/d")]
        order = R.review_order(ranked, 2, {"pictures": {"mxl/b": {}, "mxl/d": {}}})
        self.assertEqual([(n, p.key, has) for n, p, has in order], [(2, "mxl/b", True), (4, "mxl/d", True), (1, "mxl/a", False)])


class ProposalTests(unittest.TestCase):
    def test_nothing_is_used_while_the_file_switch_is_off(self):
        data = {"enabled": False, "pictures": {"mxl/a": {"method": "hybrid-crisp", "enabled": True}}}
        self.assertEqual(R.enabled_proposals(data), {})
        data["enabled"] = True
        self.assertEqual(list(R.enabled_proposals(data)), ["mxl/a"])
        data["pictures"]["mxl/a"]["enabled"] = False
        self.assertEqual(R.enabled_proposals(data), {})

    def test_the_committed_proposals_are_all_off_and_well_formed(self):
        data = json.loads(R.PROPOSALS.read_text("utf-8"))
        self.assertFalse(data["enabled"])
        self.assertEqual(R.enabled_proposals(data), {})
        for k, v in data["pictures"].items():
            self.assertRegex(k, r"^(mxl|classic)/[\w\-]+$")
            self.assertFalse(v["enabled"], k)
            self.assertTrue(v.get("why"), k)
            self.assertEqual(sum(1 for f in ("method", "reuse") if v.get(f)), 1, k)
            if v.get("method"):
                self.assertIn(v["method"], set(upscale.METHODS) | set(S.VARIANTS), k)
            else:
                self.assertTrue({"folder", "asset"} <= set(v["reuse"]), k)


    def test_report_entry_says_off_or_on(self):
        data = {"enabled": False, "pictures": {"mxl/a": {"method": "hybrid-crisp", "enabled": True},
                                               "mxl/b": {"reuse": {"folder": "misc", "asset": "gem/saphire",
                                                                   "colour": "by position"}, "enabled": False}}}
        self.assertEqual(R.report_entry(data), {"mxl/a": "upscale hybrid-crisp (off: owner review)",
                                                "mxl/b": "D2R misc/gem/saphire, colours by position (off: owner review)"})
        data["enabled"] = True
        self.assertTrue(R.report_entry(data)["mxl/a"].endswith("(ON)"))


class SilhouetteTests(unittest.TestCase):
    def test_same_outline_scores_one_and_size_does_not_matter(self):
        self.assertAlmostEqual(S.silhouette_score(disc(20, 20), disc(60, 60)), 1.0, places=1)

    def test_other_aspect_and_shape_score_lower(self):
        round_ = S.silhouette_score(disc(20, 20), disc(20, 20))
        self.assertLess(S.silhouette_score(disc(20, 20), disc(20, 40)), 0.5 * round_)
        self.assertLess(S.silhouette_score(disc(20, 20), box(20, 20)), round_)

    def test_loose_candidates_keep_the_best_above_the_floor(self):
        lib = {"round": disc(40, 40), "square": box(40, 40), "bar": box(10, 60)}
        out = S.loose_candidates(disc(20, 20), lib, n=2, floor=0.5)
        self.assertEqual(out[0][0], "round")
        self.assertNotIn("bar", [k for k, _ in out])

    def test_empty_picture_scores_zero(self):
        self.assertEqual(S.silhouette_score(np.zeros((5, 5, 4), np.uint8), disc(5, 5)), 0.0)


class ColourTests(unittest.TestCase):
    def test_colour_match_turns_blue_into_red(self):
        s = S.colour_match(disc(10, 10, (200, 40, 40)), disc(10, 10, (40, 40, 200)))
        self.assertAlmostEqual(abs(s["hue"]), 1 / 3, places=2)
        self.assertAlmostEqual(s["val"], 0.0, places=2)

    def test_colour_by_position_takes_the_source_hue_per_side_and_keeps_alpha(self):
        src = np.zeros((10, 10, 4), np.uint8)
        src[:, :5] = (220, 30, 30, 255)
        src[:, 5:] = (30, 30, 220, 255)
        hd = disc(60, 60, (180, 180, 180))
        out = S.colour_by_position(hd, src)
        self.assertTrue((out[..., 3] == hd[..., 3]).all())
        left, right = out[30, 8, :3].astype(int), out[30, 51, :3].astype(int)
        self.assertGreater(left[0], left[2])
        self.assertGreater(right[2], right[0])

    def test_render_reuse_matches_the_area_and_fits_the_cells(self):
        img = S.render_reuse(disc(200, 200, (100, 100, 100)), disc(20, 20), 98, 98, None)
        self.assertEqual(img.shape, (98, 98, 4))
        w = np.nonzero((img[..., 3] > 0).any(0))[0]
        self.assertAlmostEqual(w[-1] - w[0] + 1, 20 * 3.5, delta=3)


class SheetTests(unittest.TestCase):
    def test_variant_upscale_restores_the_module_settings(self):
        before = (upscale.EDGE_LO, upscale.EDGE_HI, upscale.SHARPEN)
        a = S.upscaled(disc(8, 8), "hybrid-crisp")
        self.assertEqual(a.shape[:2], (28, 28))
        self.assertEqual((upscale.EDGE_LO, upscale.EDGE_HI, upscale.SHARPEN), before)

    def test_wrap_breaks_long_captions(self):
        from PIL import Image, ImageDraw
        d = ImageDraw.Draw(Image.new("RGBA", (1, 1)))
        lines = S.wrap("word " * 40, S._font(13), 120, d)
        self.assertGreater(len(lines), 3)
        self.assertTrue(all(d.textlength(x, font=S._font(13)) <= 120 for x in lines))

    def test_sheet_has_three_columns_and_a_row_per_item(self):
        img = box(98, 98)
        row = {"cells": (1, 1), "images": [img, img, img], "caption": "mxl/x: Thing (abc)", "labels": ["a", "b", "c"]}
        one, two = S.draw_sheet([row], "t"), S.draw_sheet([row, row], "t")
        self.assertEqual(one.width, S.PAD + 3 * (S.MIN_COL + S.PAD))
        self.assertGreater(two.height, one.height + 98)


if __name__ == "__main__":
    unittest.main()
