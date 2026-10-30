"""Unit tests of the item picture review tools (item_art_review: visibility ranking, the proposal switch; item_art_sheets:
loose silhouette match, colour match, colour by position, upscale variants, sheet drawing, the rune stone
recomposition of lane itemart3, the redrawn signs and the chisel of round 3 (item_glyphs), the retint; lane runehd's rune
upscale (rune_hd); lane itemart5's picture rebuild (item_rebuild); item_hd / item_art: the build
makes the pictures of the proposals switched on) on synthetic data, plus one check of og4 against lane itemart's review
sheet (skipped without the game files and the sheet). Run: py -3 -I -m unittest discover -s tools/tests -p "test_itemart.py" """
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import projtemp  # noqa: E402,F401  (temp files stay inside the project, tools/projtemp.py)
import item_art_review as R  # noqa: E402
import item_art_sheets as S  # noqa: E402
import item_glyphs as G  # noqa: E402
import item_rebuild  # noqa: E402
import rune_hd  # noqa: E402
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

    def test_the_committed_proposals_are_well_formed_and_the_approved_ones_are_on(self):
        data = json.loads(R.PROPOSALS.read_text("utf-8"))
        self.assertTrue(data["enabled"])
        # owner, 2026-10-30: og1..og5 (lane itemart2), lane itemart3's 59 entries and its 7 signets (round 4: the runes
        # and signets with the redrawn signs); the 23 runes off again for 0.1.5 ("we need to work on those more"), now
        # lane runehd's upscales of Median's own pictures, off until the owner has seen them
        rune = lambda k: k.startswith(("mxl/r-a-", "mxl/r-d-"))
        approved = lambda k, v: k.startswith("mxl/og") or (v.get("lane") in ("itemart3", "itemart3-signets") and not rune(k))
        self.assertEqual(len(R.enabled_proposals(data)), 5 + 36 + 7)
        for k, v in data["pictures"].items():
            self.assertRegex(k, r"^(mxl|classic)/[\w\-]+$")
            self.assertEqual(v["enabled"], approved(k, v), k)
            self.assertTrue(v.get("why"), k)
            self.assertEqual(sum(1 for f in ("method", "reuse") if v.get(f)), 1, k)
            if v.get("method"):
                self.assertIn(v["method"], set(upscale.METHODS) | set(S.VARIANTS), k)
            else:
                self.assertTrue({"folder", "asset"} <= set(v["reuse"]), k)


    def test_lane_itemart3_proposals_in_pick_order_the_signets_on_with_redrawn_signs(self):
        pics = R.load_proposals()["pictures"]
        lane = {k: v for k, v in pics.items() if v.get("lane") == "itemart3"}
        self.assertEqual(len(lane), 36)  # 59 less the 23 runes (lane runehd since 2026-10-30)
        self.assertEqual(len({v["pick"] for v in lane.values()}), 36)
        self.assertTrue(all(v["enabled"] for v in lane.values()))
        self.assertFalse([k for k in lane if k.startswith(("mxl/r-a-", "mxl/r-d-"))])
        signets = {k: v for k, v in pics.items() if v.get("lane") == "itemart3-signets"}
        self.assertEqual(sorted(signets), sorted(f"mxl/{k}" for k in (
            "sigil1b", "sigil2b", "sigil3b", "sigil4b", "sigil5b", "sigil6b", "sigilxl")))
        for k, v in signets.items():
            self.assertTrue(v["enabled"], k)
            self.assertEqual((v["reuse"].get("seal"), v["reuse"].get("sign")), ("chisel", k))
        self.assertEqual(sorted(G.SIGNETS), sorted(signets))
        # owner's colour notes (round 3): Sunstone of Thunder yellow, Oil of Jewelcraft pink; both stay on
        self.assertEqual(pics["classic/invgmw"]["reuse"]["tint"]["hue"], 52)
        self.assertEqual(pics["mxl/zelixir7"]["reuse"]["tint"]["hue"], 330)
        self.assertTrue(pics["classic/invgmw"]["enabled"] and pics["mxl/zelixir7"]["enabled"])

    def test_lane_runehd_the_23_runes_are_median_pictures_upscaled_again_and_off(self):
        # owner, 2026-10-30: "just upscale the runes again" (the round-4 chisel held back from 0.1.5)
        pics = R.load_proposals()["pictures"]
        lane = {k: v for k, v in pics.items() if v.get("lane") == "runehd"}
        runes = sorted(k for k in pics if k.startswith(("mxl/r-a-", "mxl/r-d-")))
        self.assertEqual(sorted(lane), runes)
        self.assertEqual(len(runes), 23)
        self.assertEqual(sorted(v["pick"] for v in lane.values()), list(range(1, 24)))
        for k, v in lane.items():
            self.assertFalse(v["enabled"], k)
            self.assertIn(v["method"], rune_hd.METHODS, k)
            self.assertNotIn("reuse", v, k)
        self.assertEqual(sorted(G.RUNES), runes)  # the redrawn signs stay for the comparison sheets
        self.assertEqual(S.round4_rune("mxl/r-a-01")["reuse"]["glyph"], "chisel")

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

    def test_sheet_takes_a_fourth_smaller_column(self):
        img = box(98, 98)
        row = {"cells": (1, 1), "images": [img, img, img, box(49, 49)], "caption": "c", "labels": ["a", "b", "c", "d"]}
        self.assertEqual(S.draw_sheet([row], "t").width, S.PAD + 4 * (S.MIN_COL + S.PAD))
        self.assertEqual(S.in_game(img, 1, 1).shape[:2], (49, 49))


# -- the build uses the proposals switched on (item_hd.generate -> item_art.make_asset -> item_art_sheets.candidate) --------
class SealTests(unittest.TestCase):
    """seal (lane itemart3 round 2): a D2R gold disc with Median's centre colour and sign."""

    def test_seal_enamels_the_centre_and_stamps_the_sign(self):
        disc = np.zeros((90, 90, 4), np.uint8)
        yy, xx = np.mgrid[0:90, 0:90]
        r = np.hypot(yy - 44.5, xx - 44.5)
        disc[r < 45] = (200, 170, 60, 255)  # a plain gold disc
        src = np.zeros((28, 28, 4), np.uint8)
        sr = np.hypot(*np.mgrid[0:28, 0:28] - 13.5)
        src[sr < 14] = (180, 140, 40, 255)          # gold ring
        src[sr < 7] = (40, 80, 230, 255)            # blue centre
        src[10:18, 13:15] = (5, 5, 5, 255)          # a dark bar: the sign
        out = S.seal(disc, src)
        self.assertTrue((out[..., 3] == disc[..., 3]).all())
        self.assertTrue((out[5, 45] == disc[5, 45]).all())  # the rim stays D2R's gold
        blue = out[45, 25, :3].astype(int)                   # in the enamel, off the sign
        self.assertGreater(blue[2], blue[0] + 60)
        self.assertLess(out[45, 44:46, :3].mean(), 40)       # the sign, stamped dark


class ChiselTests(unittest.TestCase):
    """item_glyphs (lane itemart3 round 3): Median's signs as strokes, cut in crisp with a lit and a shadowed wall."""

    def test_every_sign_is_well_formed_and_inside_its_classic_picture(self):
        kinds = {"line", "loop", "ring", "dot", "fill"}
        for k, g in G.GLYPHS.items():
            self.assertTrue(g, k)
            self.assertTrue(all(p[0] in kinds for p in g), k)
            size = 24 if k in G.RUNES else 26
            y, x = np.mgrid[0:size * 4, 0:size * 4] / 4.0
            sd = G.signed_distance(g, x, y)
            self.assertTrue(np.isfinite(sd).all(), k)
            self.assertGreater((sd < 0).mean(), 0.02, k)   # something is cut
            self.assertLess((sd < 0).mean(), 0.35, k)      # strokes, not a blob
            self.assertFalse((sd[:, :4] < 0).any() or (sd[:, -4:] < 0).any(), k)  # off the picture's edge

    def test_signed_distance_of_a_line_a_dot_and_a_fill(self):
        x, y = np.array([5.5, 5.5, 9.0]), np.array([5.5, 7.0, 5.5])
        line = G.signed_distance([("line", [(2, 5), (8, 5)], 2.0)], x, y)
        self.assertAlmostEqual(line[0], -1.0)                 # on the centre line, half the width in
        self.assertGreater(line[1], 0)                        # 1.5 px off it: outside
        dot = G.signed_distance([("dot", (5, 5, 1.0))], x, y)
        self.assertAlmostEqual(dot[0], -1.0)
        fill = G.signed_distance([("fill", [(3, 3), (8, 3), (8, 8), (3, 8)])], x, y)
        self.assertAlmostEqual(fill[0], -2.0)               # 2 px from the nearest edge (corners at +0.5)
        self.assertGreater(fill[2], 0)

    def test_chisel_cuts_a_dark_floor_lit_far_wall_and_shadowed_near_wall(self):
        rgb = np.full((40, 40, 3), 150.0)
        out, cut = G.chisel(rgb, [("line", [(10, 2), (10, 18)], 4.0)], lambda x, y: (x / 2, y / 2))
        row = out[20, :, 0]
        self.assertLess(row[20:22].mean(), 40)                # the floor (centre line x = 21 px)
        self.assertGreater(row[23:26].max(), 160)             # the right wall faces the light: lit
        self.assertLess(row[16:19].min(), 120)                # the left wall: shadow
        self.assertTrue((out[:, :8] == 150).all())            # untouched off the cut
        self.assertTrue(cut[20, 21] and not cut[20, 5])
        self.assertGreater(np.abs(np.diff(row)).max(), 60)    # a hard edge, no blur ramp

    def test_engrave_rune_cuts_the_sign_inside_the_stone(self):
        stone = np.zeros((98, 98, 4), np.uint8)
        stone[10:90, 10:90] = (150, 150, 150, 255)
        out = S.engrave_rune(stone, stone[::4, ::4].copy(), [("line", [(10, 2), (10, 18)], 2.0)])
        self.assertTrue((out[..., 3] == stone[..., 3]).all())
        self.assertLess(out[50, 48:52, :3].mean(), 60)
        self.assertTrue((out[50, 15:30] == stone[50, 15:30]).all())

    def test_seal_with_strokes_engraves_them_on_the_enamel(self):
        disc = np.zeros((90, 90, 4), np.uint8)
        r = np.hypot(*(np.mgrid[0:90, 0:90] - 44.5))
        disc[r < 45] = (200, 170, 60, 255)
        src = np.zeros((26, 26, 4), np.uint8)
        sr = np.hypot(*(np.mgrid[0:26, 0:26] - 12.5))
        src[sr < 13] = (180, 140, 40, 255)
        src[sr < 7] = (40, 80, 230, 255)
        out = S.seal(disc, src, [("line", [(12.5, 9), (12.5, 16)], 1.6)])
        self.assertLess(out[45, 44:46, :3].mean(), 70)       # the stroke, engraved dark
        blue = out[45, 30, :3].astype(int)                    # the enamel off the stroke
        self.assertGreater(blue[2], blue[0] + 60)
        self.assertTrue((out[5, 45] == disc[5, 45]).all())

    def test_tint_moves_the_chosen_hues_and_keeps_the_rest(self):
        a = np.zeros((2, 2, 4), np.uint8)
        a[..., 3] = 255
        a[0, 0, :3] = (120, 40, 160)   # purple: in range
        a[0, 1, :3] = (200, 150, 60)   # cork brown: out of range
        a[1, 0, :3] = (128, 128, 128)  # grey: below min_sat
        out = S.tint(a, {"hue": 330, "sat": 0.5, "from": [250, 345], "min_sat": 0.2})
        h, _s, _v = S._hsv(out[..., :3])
        self.assertAlmostEqual(h[0, 0] * 360, 330, delta=3)
        self.assertTrue((out[0, 1] == a[0, 1]).all() and (out[1, 0] == a[1, 0]).all())
        grey = S.tint(a, {"hue": 52, "sat": 0.8})            # no range: every pixel, grey too
        h, s, _v = S._hsv(grey[1:, :1, :3])
        self.assertAlmostEqual(h[0, 0] * 360, 52, delta=3)
        self.assertGreater(s[0, 0], 0.7)

    def test_round2_of_a_round3_entry_is_the_carved_classic_glyph_untinted(self):
        p = {"reuse": {"folder": "misc", "asset": "rune/ist_rune", "glyph": "chisel", "sign": "mxl/r-a-01",
                       "tint": {"hue": 1, "sat": 1}}, "enabled": False}
        self.assertEqual(S._round2(p)["reuse"], {"folder": "misc", "asset": "rune/ist_rune", "glyph": "median"})
        self.assertEqual(p["reuse"]["glyph"], "chisel")


class RuneStoneTests(unittest.TestCase):
    """blank_stone / glyph_mask / carve (lane itemart3): D2R's stone, Median's glyph."""

    @staticmethod
    def stone(n: int = 80, glyph: bool = True) -> np.ndarray:
        rng = np.random.default_rng(1)
        a = np.zeros((n, n, 4), np.uint8)
        a[..., :3] = np.clip(150 + rng.normal(0, 8, (n, n, 1)), 0, 255).astype(np.uint8)
        a[4:-4, 4:-4, 3] = 255
        if glyph:
            a[20:60, 36:44, :3] = 20  # a dark vertical stroke
        return a

    def test_blank_stone_takes_the_glyph_out_and_keeps_the_rest(self):
        a = self.stone()
        b = S.blank_stone(a)
        self.assertGreater(b[20:60, 36:44, :3].mean(), 120)
        self.assertTrue((b[..., 3] == a[..., 3]).all())
        self.assertTrue((b[5:15, 5:15] == a[5:15, 5:15]).all())
        plain = self.stone(glyph=False)
        self.assertTrue((S.blank_stone(plain) == plain).all())

    def test_glyph_mask_finds_the_stroke_not_the_rim(self):
        src = np.zeros((23, 23, 4), np.uint8)
        src[..., 3] = 255
        src[..., :3] = 100
        src[0:2, :, :3] = 60     # Median's darker stone rim
        src[6:17, 10:12, :3] = 35  # the glyph
        g = S.glyph_mask(src)
        self.assertEqual(g[6:17, 10:12].min(), 1.0)
        self.assertEqual(g[:3].max(), 0.0)
        self.assertEqual(g.sum(), 22)

    def test_carve_darkens_the_glyph_on_the_stone(self):
        blank = self.stone(glyph=False)
        g = np.zeros((10, 10))
        g[2:8, 4:6] = 1
        out = S.carve(blank, g)
        self.assertLess(out[30:50, 38:42, :3].mean(), 60)
        self.assertGreater(out[10:15, 10:15, :3].mean(), 120)
        self.assertTrue((out[..., 3] == blank[..., 3]).all())


PAL = [(i, (i * 3) % 256, 255 - i) for i in range(256)]


def dc6_frame(left: int, right: int, n: int = 24) -> bytes:
    """A one-frame DC6 of an n x n square: palette index `left` on the left half, `right` on the right half."""
    from dc6 import build_dc6
    row = bytes([n]) + bytes([left] * (n // 2) + [right] * (n - n // 2)) + b"\x80"
    return build_dc6([(n, n, 0, 0, row * n)])


def classic_rune(seed: int = 1) -> np.ndarray:
    """A synthetic Median rune (28 x 28): a grey trapezoid stone with a dark rim, speckle, a darker lower-right edge,
    and a sign of two 1 px vertical strokes (x 11 and 13, a 1 px gap at x 12) joined by a bar at y 9."""
    rng = np.random.default_rng(seed)
    a = np.zeros((28, 28, 4), np.uint8)
    for y in range(3, 25):
        half = 7 + (y - 3) * 4 // 21
        x0, x1 = 14 - half, 14 + half
        a[y, x0:x1] = (110, 108, 104, 255)
    op = a[..., 3] > 0
    a[..., :3] = np.clip(a[..., :3].astype(int) + rng.integers(-8, 9, (28, 28, 1)), 0, 255)
    a[op & ~rune_hd.erode(op, 1), :3] = 30                      # the dark rim
    a[22:24, 14:20][op[22:24, 14:20], :3] = 74                  # the stone's own darker lower edge (no sign)
    a[9:19, 11, :3] = a[9:19, 13, :3] = 50                      # two strokes ...
    a[9, 11:14, :3] = 50                                        # ... joined at the top
    a[16, 6, :3] = 80                                           # one dark speckle (no sign)
    a[~op] = 0
    return a


class RuneHdTests(unittest.TestCase):
    """rune_hd (lane runehd): Median's rune picture rebuilt crisp at the HD size."""
    src = classic_rune()

    def test_sign_mask_takes_the_strokes_not_the_speckle_or_the_rims_shading(self):
        dark, m = rune_hd.sign_layers(self.src, self.src[..., 3] > 0)
        self.assertTrue(m[9:19, 11].all() and m[9:19, 13].all() and m[9, 12])
        self.assertFalse(m[10:19, 12].any())  # the gap
        self.assertFalse(m[16, 6] or m[22:24].any())
        self.assertTrue((dark[~rune_hd.dilate(m, 1)] == 0).all())

    def test_every_method_keeps_size_shape_strokes_and_the_one_pixel_gap(self):
        for method in rune_hd.METHODS:
            out = upscale.upscale(self.src, 3.5, method)
            self.assertEqual(out.shape, (98, 98, 4), method)
            v = out[..., :3].astype(float).mean(-1)
            stroke = v[40:60, round(11.5 * 3.5)]  # the middle of the stroke at x 11
            gap = v[40:60, round(12.5 * 3.5)]
            stone = v[40:60, round(8.5 * 3.5)]
            self.assertLess(stroke.mean(), 0.75 * stone.mean(), method)
            self.assertGreater(gap.mean(), 0.85 * stone.mean(), method)  # the gap stays open
            area = (out[..., 3] > 127).sum() / (self.src[..., 3] > 0).sum() / 3.5 ** 2
            self.assertAlmostEqual(area, 1.0, delta=0.08)

    def test_edges_are_anti_aliased_and_colours_stay_in_the_originals_range(self):
        op = self.src[..., 3] > 0
        lo, hi = self.src[op][:, :3].min(0).astype(int), self.src[op][:, :3].max(0).astype(int)
        for method in rune_hd.METHODS:
            out = rune_hd.rune_upscale(self.src, 98, 98, method)
            al = out[..., 3]
            self.assertTrue(((al > 0) & (al < 255)).sum() > 50)  # a smooth edge, not a staircase of full pixels
            rgb = out[al == 255][:, :3].astype(int)
            if method == "rune-flat":  # no new colours
                self.assertTrue((rgb >= lo - 2).all() and (rgb <= hi + 2).all())
            else:  # the shading pass: the lit bevel and lip lift the brightest stone a little, the cut darkens the sign
                top = hi * (1 + rune_hd.BEVEL + rune_hd.LIP) + 4 * rune_hd.FINE
                self.assertTrue((rgb >= lo * 0.75).all() and (rgb <= top).all(), method)

    def test_deterministic_lowend_size_and_empty_picture(self):
        a = rune_hd.rune_upscale(self.src, 98, 98, "rune-hd")
        self.assertTrue((a == rune_hd.rune_upscale(self.src, 98, 98, "rune-hd")).all())
        self.assertEqual(upscale.upscale(self.src, 1.75, "rune-crisp").shape, (49, 49, 4))
        self.assertFalse(rune_hd.rune_upscale(np.zeros((28, 28, 4), np.uint8), 98, 98).any())
        with self.assertRaises(ValueError):
            rune_hd.rune_upscale(self.src, 98, 98, "rune-x")

    def test_a_method_proposal_is_drawn_by_candidate_as_the_build_does(self):
        img, label = S.candidate({"method": "rune-hd"}, self.src, 98, 98, Path("."))
        self.assertEqual(label, "rune-hd")
        self.assertTrue((img == upscale.place(S.upscaled(self.src, "rune-hd"), 98, 98)).all())


def classic_fruit(seed: int = 2) -> np.ndarray:
    """A synthetic Median picture (28 x 28): a red ball (radius 8, centre 14, 17) with a dark outline, a white
    highlight, low-contrast speckle on its face, and a 1 px green stem (x 14, y 3..8) over it."""
    rng = np.random.default_rng(seed)
    a = np.zeros((28, 28, 4), np.uint8)
    y, x = np.mgrid[:28, :28]
    ball = (y - 17) ** 2 + (x - 14) ** 2 <= 64
    a[ball] = (170, 30, 30, 255)
    a[ball, :3] = np.clip(a[ball, :3].astype(int) + rng.integers(-6, 7, (ball.sum(), 1)), 0, 255)
    a[ball & ~rune_hd.erode(ball, 1), :3] = (60, 10, 10)
    a[13:15, 10:12, :3] = 245
    a[3:9, 14] = (40, 150, 40, 255)
    return a


class ItemRebuildTests(unittest.TestCase):
    """item_rebuild (lane itemart5): Median's own picture rebuilt crisp at the HD size."""
    src = classic_fruit()

    def test_size_shape_thin_stem_and_highlight_kept_in_both_methods(self):
        for method in item_rebuild.METHODS:
            out = upscale.upscale(self.src, 3.5, method)
            self.assertEqual(out.shape, (98, 98, 4), method)
            area = (out[..., 3] > 127).sum() / (self.src[..., 3] > 0).sum() / 3.5 ** 2
            self.assertAlmostEqual(area, 1.0, delta=0.1, msg=method)
            stem = out[14:26, 48:52]  # the 1 px stem at x 14 (HD 49..52), y 4..7
            self.assertTrue((stem[..., 3] > 200).any(), method)
            g = stem[stem[..., 3] > 200][:, :3].astype(int)
            self.assertTrue((g[:, 1] > g[:, 0] + 40).all(), method)  # still green: no red bled into it
            self.assertGreater(out[47:51, 36:41, :3].mean(), 200, method)  # the highlight
            face = out[64:80, 44:60, :3].astype(float)
            self.assertGreater(face[..., 0].mean(), 2 * face[..., 1].mean(), method)  # the red face stays red

    def test_edges_are_anti_aliased_and_colours_stay_in_the_originals_range(self):
        op = self.src[..., 3] > 0
        lo, hi = self.src[op][:, :3].min(0).astype(int), self.src[op][:, :3].max(0).astype(int)
        for method in item_rebuild.METHODS:
            out = item_rebuild.rebuild(self.src, 98, 98, method)
            al = out[..., 3]
            self.assertTrue(((al > 0) & (al < 255)).sum() > 60, method)
            rgb = out[al > 0][:, :3].astype(int)
            self.assertTrue((rgb >= lo - 20).all() and (rgb <= hi + 12).all(), method)
            y, src_y = item_rebuild.luma(rgb.astype(float)), item_rebuild.luma(self.src[op][:, :3].astype(float))
            self.assertTrue((y >= src_y.min() - 2).all() and (y <= src_y.max() + 2).all(), method)  # the tones kept

    def test_soft_evens_out_the_speckle_and_keeps_the_outline(self):
        hd, soft = (item_rebuild.rebuild(self.src, 98, 98, m)[60:84, 40:64, 0].astype(float) for m in item_rebuild.METHODS)
        self.assertLess(soft.std(), hd.std())
        y = item_rebuild.luma(self.src[..., :3].astype(float))
        d = item_rebuild.despeckle(y, self.src[..., 3] > 0)
        self.assertEqual(d[13, 10], y[13, 10])  # the highlight is no speckle
        self.assertEqual(d[9, 14], y[9, 14])    # nor the outline

    def test_deterministic_lowend_size_empty_picture_and_candidate(self):
        a = item_rebuild.rebuild(self.src, 98, 98)
        self.assertTrue((a == item_rebuild.rebuild(self.src, 98, 98)).all())
        self.assertEqual(upscale.upscale(self.src, 1.75, "item-soft").shape, (49, 49, 4))
        self.assertFalse(item_rebuild.rebuild(np.zeros((28, 28, 4), np.uint8), 98, 98).any())
        with self.assertRaises(ValueError):
            item_rebuild.rebuild(self.src, 98, 98, "item-x")
        img, label = S.candidate({"method": "item-hd"}, self.src, 98, 196, Path("."))
        self.assertEqual((img.shape, label), ((196, 98, 4), "item-hd"))

    def test_lane_itemart5_the_21_unmatched_pictures_rebuilt_and_off(self):
        pics = R.load_proposals()["pictures"]
        lane = {k: v for k, v in pics.items() if v.get("lane") == "itemart5"}
        self.assertEqual(sorted(lane), sorted(["mxl/" + k for k in (
            "jbscross", "pearl1", "pearl2", "pearl3", "pearl4", "catal1", "catal2", "catal3", "realapple", "apple",
            "cherries", "moon1", "evileye", "skullstar", "ring08", "s1", "summbook")]
            + ["classic/" + k for k in ("invfary3", "invfary4", "invbonr3", "invcndl")]))
        self.assertEqual(sorted(v["pick"] for v in lane.values()), list(range(1, 22)))
        for k, v in lane.items():
            self.assertFalse(v["enabled"], k)
            self.assertIn(v["method"], item_rebuild.METHODS, k)
            for alt in v.get("alt", []):
                self.assertEqual(sum(1 for f in ("method", "reuse") if alt.get(f)), 1, k)
                self.assertIn(alt.get("method", "item-hd"), item_rebuild.METHODS, k)


class BuildProposalTests(unittest.TestCase):
    """item_hd.generate makes a picture from its proposal entry when the entry is switched on, else the usual upscale."""

    def setUp(self):
        import item_hd
        from dc6 import write_item_sprite
        self.t = tempfile.TemporaryDirectory()
        t = Path(self.t.name)
        self.src, self.hd_items, self.out = t / "mxl", t / "d2r" / "items", t / "out"
        self.src.mkdir()
        for inv in ("a", "b"):
            (self.src / f"{inv}.dc6").write_bytes(dc6_frame(40, 150))
        for name, n in (("x", 98), ("x.lowend", 49)):
            img = disc(n * 3 // 4, n * 3 // 4, (60, 60, 200))
            write_item_sprite(self.hd_items / "misc" / "gem" / f"{name}.sprite", n, n,
                              upscale.place(img, n, n).tobytes())
        entry = {"reuse": {"folder": "misc", "asset": "gem/x", "colour": "by position"}, "why": "t"}
        self.data = {"enabled": True, "pictures": {"mxl/a": dict(entry, enabled=True), "mxl/b": dict(entry, enabled=False)}}
        self.plan = item_hd.Plan({}, {}, {"items": {}, "uniques": {}, "sets": {}}, set(), {"a", "b"}, set(), [],
                                 hd_items=self.hd_items)
        self.plan.needs = {("misc", "mxl", "a"): (1, 1), ("misc", "mxl", "b"): (1, 1)}

    def tearDown(self):
        self.t.cleanup()

    def generate(self):
        import item_art
        import item_hd
        self.plan.proposals, self.plan.proposal_keys = R.enabled_proposals(self.data), set(self.data["pictures"])
        with mock.patch.dict(item_art.GROUPS, {"mxl": self.src}):
            return item_hd.generate(self.plan, PAL, self.out)

    def sprite(self, inv: str, low: bool = False) -> np.ndarray:
        from dc6 import read_sprite
        p = self.out / "global" / "ui" / "items" / "misc" / "mxl" / f"{inv}{'.lowend' if low else ''}.sprite"
        return upscale.rows_to_array(read_sprite(p)[0])

    def source(self) -> np.ndarray:
        from dc6 import decode_frame, parse_dc6
        w, h, _ox, _oy, block = parse_dc6(dc6_frame(40, 150))[0]
        return upscale.rows_to_array(decode_frame(w, h, block, PAL, fill=True))

    def test_an_enabled_entry_is_used_with_the_sheets_own_render(self):
        n = self.generate()
        self.assertEqual(self.plan.report["proposal_on"], ["mxl/a"])
        self.assertEqual((n["mxl from proposal"], n["mxl upscaled"]), (1, 1))
        prop = self.data["pictures"]["mxl/a"]
        want, _label = S.candidate(prop, self.source(), 98, 98, self.hd_items)
        self.assertTrue((self.sprite("a") == want).all())
        want_low, _label = S.candidate(prop, self.source(), 49, 49, self.hd_items, 49)
        self.assertTrue((self.sprite("a", low=True) == want_low).all())
        # D2R's blue disc, Median's colours by position: the two halves take the source's two palette colours' hues
        left, right = self.sprite("a")[49, 30, :3].astype(int), self.sprite("a")[49, 68, :3].astype(int)
        self.assertGreater(left[2], left[0])
        self.assertGreater(right[0], right[2])

    def test_a_disabled_entry_or_file_is_not_used(self):
        self.generate()
        keep = upscale.place(upscale.upscale(self.source(), 98 / 28), 98, 98)
        self.assertTrue((self.sprite("b") == keep).all())
        self.data["enabled"] = False  # the file's switch off: entry a is not used either (fresh output folder)
        self.out = self.out.with_name("out2")
        self.plan.report.clear()
        n = self.generate()
        self.assertEqual((self.plan.report["proposal_on"], n["mxl upscaled"]), ([], 2))
        self.assertTrue((self.sprite("a") == keep).all())

    def test_a_varinvgfx_item_gets_its_picture_as_numbered_copies(self):
        # bugs.md #513: D2R asks a VarInvGfx type (rings, Median's Mega Rings `kill`) for <asset><n>
        import item_hd
        plan = item_hd.Plan({"misc": [{"code": "r@r", "invfile": "a", "type": "kill", "invwidth": "1", "invheight": "1"},
                                      {"code": "cx1", "invfile": "b", "type": "char", "invwidth": "1", "invheight": "1"}]},
                            {}, {"items": {}, "uniques": {}, "sets": {}}, set(), {"a", "b"}, set(),
                            [{"Code": "kill", "VarInvGfx": "3"}, {"Code": "char", "VarInvGfx": ""}], hd_items=self.hd_items)
        plan.run()
        self.assertEqual(plan.variants, {("misc", "mxl", "a"): 3})
        self.plan.variants = plan.variants
        n = self.generate()
        self.assertEqual(n["mxl variant copies"], 3)
        self.assertEqual(self.plan.report["variant_copies"], [[f"mxl/a{v}", "mxl/a"] for v in (1, 2, 3)])
        for v in (1, 2, 3):
            for low in (False, True):
                self.assertTrue((self.sprite(f"a{v}", low) == self.sprite("a", low)).all())
        self.generate()  # a second build keeps the copies (not stale)
        self.assertTrue((self.out / "global" / "ui" / "items" / "misc" / "mxl" / "a3.sprite").exists())

    def test_the_icon_check_holds_a_proposal_sprite_to_its_candidate(self):
        import item_icon_check as C
        self.generate()
        prop = self.data["pictures"]["mxl/a"]
        sp = self.out / "global" / "ui" / "items" / "misc" / "mxl"
        for name, cell in (("a.sprite", 98), ("a.lowend.sprite", 49)):
            self.assertEqual(C.check_proposal_sprite(sp / name, self.src / "a.dc6", PAL, cell, prop, self.hd_items), [])
        # the upscale of b is not entry a's picture
        self.assertEqual(C.check_proposal_sprite(sp / "b.sprite", self.src / "b.dc6", PAL, 98, prop, self.hd_items),
                         ["b.sprite: not the approved proposal picture"])


class Og4AgainstTheReviewSheetTests(unittest.TestCase):
    """The build's og4 (Flawless Rainbow Stone) is the candidate the owner approved on lane itemart's sheet 1."""

    def test_og4_matches_the_review_candidate(self):
        import fxpaths
        import item_art
        from dc6 import palette, read_sprite
        from PIL import Image
        sheet = fxpaths.RUNS / "itemart" / "review" / "sheet_01.png"
        hd_items = fxpaths.D2R_DATA / "hd" / "global" / "ui" / "items"
        pal = item_art.BASE / "palette" / "pal.dat"
        src = item_art.MOD_ITEMS / "og4.dc6"
        if not all(p.exists() for p in (sheet, hd_items / "misc" / "gem" / "flawless_saphire.sprite", pal, src)):
            self.skipTest("needs the game files and mxl2012-runs/itemart/review/sheet_01.png")
        prop = R.load_proposals()["pictures"]["mxl/og4"]
        with tempfile.TemporaryDirectory() as t:
            dst = Path(t) / "og4.sprite"
            item_art.convert(src, dst, 1, 1, palette(pal), item_art.CELL_HD, None, hd_items, prop)
            a = upscale.rows_to_array(read_sprite(dst)[0])
        g = np.asarray(S.on_grid(a, 1, 1)).astype(int)
        sh = np.asarray(Image.open(sheet).convert("RGBA")).astype(int)
        h, w = g.shape[:2]
        best = 255
        for y, x in zip(*np.nonzero((sh[:-h + 1, :-w + 1] == g[0, 0]).all(-1))):
            if (sh[y, x:x + w] == g[0]).all():
                best = min(best, int(np.abs(sh[y:y + h, x:x + w] - g).max()))
        self.assertLessEqual(best, 2)


if __name__ == "__main__":
    unittest.main()
