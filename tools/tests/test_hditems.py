"""Unit tests of the HD item picture quality tools (upscale, item_reuse, the unused-index fill) on synthetic data (no game
files). Run: py -3 -I -m unittest discover -s tools/tests -p "test_hditems.py" """
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import projtemp  # noqa: E402,F401  (temp files stay inside the project, tools/projtemp.py)
import art_provenance  # noqa: E402
import colour_shift  # noqa: E402
import dc6  # noqa: E402
import item_art  # noqa: E402
import item_hd  # noqa: E402
import item_icon_check  # noqa: E402
import item_reuse  # noqa: E402
import upscale  # noqa: E402
from test_icons import PAL, block, solid  # noqa: E402

# a palette with real hues for the recolour tests: 1-63 red ramp, 64-127 blue ramp, 128-191 grey ramp, 225-254 black
RAMP = [(0, 0, 0)] + [(4 * i, 0, 0) for i in range(1, 64)] + [(0, 0, 4 * (i - 63)) for i in range(64, 128)] \
       + [(2 * (i - 127),) * 3 for i in range(128, 192)] + [(200, 200, 0)] * 33 + [(0, 0, 0)] * 30 + [(255, 255, 255)]


def rgba(h: int, w: int, colour=(200, 50, 50)) -> np.ndarray:
    a = np.zeros((h, w, 4), np.uint8)
    a[...] = (*colour, 255)
    return a


class UpscaleTests(unittest.TestCase):
    def test_scale2x_rounds_a_diagonal(self):
        # a 2 x 2 checker of one colour on transparent: EPX fills the inner corners where two neighbours agree
        a = np.zeros((2, 2, 4), np.uint8)
        a[0, 0] = a[1, 1] = (255, 0, 0, 255)
        b = upscale.scale2x(a)
        self.assertEqual(b.shape, (4, 4, 4))
        self.assertTrue((b[0:2, 0:2, 3] == 255).all())     # the pixel itself stays
        self.assertEqual(b[1, 2, 3], 255)                   # inner corner of the top-right pixel: B (above) is transparent,
        self.assertEqual(b[0, 3, 3], 0)                     # ... D (left) and H (below) are red -> its lower-left sub-pixel

    def test_scale3x_and_solid_colour(self):
        a = rgba(3, 4)
        for big, n in ((upscale.scale3x(a), 3), (upscale.scale2x(a), 2)):
            self.assertEqual(big.shape, (3 * n, 4 * n, 4))
            self.assertTrue((big[1:-1, 1:-1] == a[0, 0]).all())   # the inside keeps its colour
            self.assertEqual(big[0, 0, 3], 0)                      # ScaleNx rounds the corners against the transparent outside

    def test_every_method_keeps_size_colour_and_transparency(self):
        a = np.zeros((10, 8, 4), np.uint8)
        a[2:8, 2:6] = (40, 160, 90, 255)
        for m in upscale.METHODS:
            with self.subTest(method=m):
                b = upscale.upscale(a, 3.5, m)
                self.assertEqual(b.shape, (35, 28, 4))
                self.assertEqual(b[0, 0, 3], 0)                          # outside stays transparent
                self.assertEqual(b[17, 14, 3], 255)                      # the middle of a flat area keeps its colour
                self.assertLessEqual(np.abs(b[17, 14, :3].astype(int) - (40, 160, 90)).max(), 2)
                self.assertEqual(upscale.upscale(a, 1.75, m).shape, (18, 14, 4))
        with self.assertRaises(ValueError):
            upscale.upscale(a, 2, "nope")

    def test_sharpen_never_exceeds_alpha_or_range(self):
        a = np.zeros((6, 6, 4), np.uint8)
        a[:, 3:] = (255, 255, 255, 255)
        a[:, :3] = (0, 0, 0, 128)
        b = upscale.sharpen(a, 2.0)
        self.assertTrue((b[..., 3] == a[..., 3]).all())
        self.assertEqual(upscale.sharpen(a, 0) is a, True)

    def test_edge_weight(self):
        a = rgba(5, 5, (100, 100, 100))
        a[2, 2] = (101, 100, 100, 255)
        w = upscale.edge_weight(a)
        self.assertEqual(w[2, 2], 0)        # a one-step shade is texture
        self.assertEqual(w[0, 0], 1)        # next to the transparent outside: an edge

    def test_place_centres_and_crops(self):
        img = rgba(2, 2)
        out = upscale.place(img, 6, 4)
        self.assertEqual(out.shape, (4, 6, 4))
        self.assertTrue((out[1:3, 2:4, 3] == 255).all() and out[..., 3].sum() == 4 * 255)
        self.assertEqual(upscale.place(rgba(8, 8), 4, 4).shape, (4, 4, 4))


class FillTests(unittest.TestCase):
    def test_unused_index_takes_neighbour_colour(self):
        lines = [[10, 10, 10], [10, 230, 10], [10, 10, 10]]
        w, h, _x, _y, blk = 3, 3, 0, 0, block(lines)
        plain = dc6.decode_frame(w, h, blk, PAL)
        self.assertEqual(plain[1][1], PAL[230] + (255,))
        filled = dc6.decode_frame(w, h, blk, PAL, fill=True)
        self.assertEqual(filled[1][1], PAL[10] + (255,))
        self.assertEqual(filled[0][0], PAL[10] + (255,))

    def test_cluster_is_filled_from_outside_in_and_transparency_is_kept(self):
        lines = [[None, 20, 20, 20], [None, 230, 231, 20], [None, 20, 20, 20]]
        rows = dc6.decode_frame(4, 3, block(lines), PAL, fill=True)
        self.assertEqual(rows[1][0], (0, 0, 0, 0))
        self.assertEqual(rows[1][1], PAL[20] + (255,))
        self.assertEqual(rows[1][2], PAL[20] + (255,))


class ReuseTests(unittest.TestCase):
    def setUp(self):
        self._pal = art_provenance._pal
        art_provenance._pal = np.array(RAMP, np.float64)

    def tearDown(self):
        art_provenance._pal = self._pal

    @staticmethod
    def gem(offset: int = 0, h: int = 12, w: int = 10) -> np.ndarray:
        """A textured oval of palette indices 20-50 (+ offset), 0 outside."""
        y, x = np.mgrid[0:h, 0:w]
        inside = ((y - h / 2 + 0.5) / (h / 2)) ** 2 + ((x - w / 2 + 0.5) / (w / 2)) ** 2 <= 1
        tex = 20 + (3 * x + 5 * y + (x * y) % 7) % 30
        return np.where(inside, tex + offset, 0).astype(np.uint8)

    def test_classify(self):
        g = self.gem()
        self.assertEqual(item_reuse.classify(g, g)[0], "exact")
        kind, _q, scale, co = item_reuse.classify(self.gem(64), g)     # red ramp -> blue ramp, same structure
        self.assertEqual((kind, round(scale, 2)), ("recolour", 1.0))
        s = item_reuse.shift_of(co)
        self.assertAlmostEqual(abs(s["hue"]), 1 / 3, delta=0.02)        # red -> blue is a third of a turn
        bar = np.zeros((12, 10), np.uint8)
        bar[:, 4:6] = 30
        self.assertIsNone(item_reuse.classify(bar, g))

    def test_find_render_and_direct(self):
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            (root / "lib").mkdir()
            (root / "src").mkdir()

            def dc6_of(a: np.ndarray) -> bytes:
                lines = [[int(v) or None for v in row] for row in a[::-1]]
                return dc6.build_dc6([(a.shape[1], a.shape[0], 0, 0, block(lines))])
            (root / "lib" / "invgem.dc6").write_bytes(dc6_of(self.gem()))
            (root / "lib" / "invbar.dc6").write_bytes(dc6_of(np.full((20, 4), 30, np.uint8)))
            (root / "src" / "same.dc6").write_bytes(dc6_of(self.gem()))
            (root / "src" / "blue.dc6").write_bytes(dc6_of(self.gem(64)))
            (root / "src" / "new.dc6").write_bytes(dc6_of(np.full((5, 25), 40, np.uint8)))
            np.testing.assert_array_equal(item_reuse.indices(root / "src" / "same.dc6"), self.gem())
            found = item_reuse.find({k: root / "src" / f"{k}.dc6" for k in ("same", "blue", "new")},
                                    {"invgem": ("misc", "gem/red"), "invbar": ("misc", "bar")}, root / "lib")
            self.assertEqual(set(found), {"same", "blue"})
            self.assertEqual((found["same"].kind, found["same"].asset, found["same"].shift), ("exact", "gem/red", None))
            self.assertEqual(found["blue"].kind, "recolour")
            self.assertIn("recolour of misc/gem/red", found["blue"].label())
            # D2R's HD sprite: a red 100 x 100 square in the middle of 98 x 98? no: 100 x 100, like D2R's chipped gems
            hd = root / "hd"
            pic = np.zeros((100, 100, 4), np.uint8)
            pic[30:70, 35:65] = (200, 0, 0, 255)
            dc6.write_item_sprite(hd / "misc" / "gem" / "red.sprite", 100, 100, pic.tobytes())
            dc6.write_item_sprite(hd / "misc" / "gem" / "red.lowend.sprite", 50, 50, pic[::2, ::2].copy().tobytes())
            same = item_reuse.render(found["same"], 98, 98, False, hd)
            self.assertEqual(same.shape, (98, 98, 4))
            self.assertEqual(int((same[..., 3] > 0).sum()), 40 * 30)          # cropped and centred, not scaled
            blue = item_reuse.render(found["blue"], 98, 98, False, hd)
            r, g, b = blue[49, 49, :3]
            self.assertTrue(b > 100 and r < 60, (r, g, b))                       # the HD picture took the recolour
            self.assertEqual(item_reuse.render(found["same"], 49, 49, True, hd).shape, (49, 49, 4))
            self.assertFalse(item_reuse.direct(found["same"], "misc", (98, 98), hd))   # D2R's sprite is 100 x 100
            self.assertTrue(item_reuse.direct(found["same"], "misc", (100, 100), hd))
            self.assertFalse(item_reuse.direct(found["same"], "armor", (100, 100), hd))
            self.assertFalse(item_reuse.direct(found["blue"], "misc", (100, 100), hd))
            # item_art writes the reused picture where the upscale would go
            name = item_art.make_asset("mxl", "blue", "misc", 1, 1, PAL, root / "out", {"mxl": root / "src"},
                                       reuse=found["blue"], hd_items=hd)
            self.assertEqual(name, "mxl/blue")
            sp = root / "out" / "global" / "ui" / "items" / "misc" / "mxl" / "blue.sprite"
            self.assertEqual(dc6.sprite_info(sp)["strip_width"], 98)
            self.assertEqual(dc6.sprite_info(sp.with_name("blue.lowend.sprite"))["strip_width"], 49)

    def test_rescale_uses_the_scale(self):
        m = item_reuse.Match("invbig", "misc", "big", "rescale", 0.5, 0.9)
        with tempfile.TemporaryDirectory() as t:
            hd = Path(t)
            pic = np.zeros((196, 196, 4), np.uint8)
            pic[20:180, 20:180] = (10, 200, 10, 255)
            dc6.write_item_sprite(hd / "misc" / "big.sprite", 196, 196, pic.tobytes())
            out = item_reuse.render(m, 98, 98, False, hd)
            self.assertEqual(int((out[..., 3] > 0).sum()), 80 * 80)


class ColourShiftTests(unittest.TestCase):
    def test_saturation_factor(self):
        a = np.array([[[200, 100, 100, 255]]], np.uint8)
        grey = colour_shift.shift_pixels(a, 0, 0, 0, 0.0)
        self.assertEqual(tuple(grey[0, 0]), (200, 200, 200, 255))
        self.assertEqual(tuple(colour_shift.shift_pixels(a, 0, 0, 0)[0, 0]), (200, 100, 100, 255))


class PipelineTests(unittest.TestCase):
    def test_plan_points_at_d2r_for_an_exact_copy(self):
        mod = {"weapons": [], "armor": [], "misc": [{"name": "Vex", "code": "r26", "invfile": "invrvex", "type": "rune",
                                                    "invwidth": "1", "invheight": "1"}], "uniqueitems": [], "setitems": []}
        d2r = {"weapons": [], "armor": [], "uniqueitems": [], "setitems": [],
               "misc": [{"code": "r26", "invfile": "invrvex", "type": "rune"}]}
        maps = {"items": {"r26": {"asset": "rune/vex_rune"}}, "uniques": {}, "sets": {}}
        with tempfile.TemporaryDirectory() as t:
            hd = Path(t)
            dc6.write_item_sprite(hd / "misc" / "rune" / "vex_rune.sprite", 98, 98, bytes(98 * 98 * 4))
            match = item_reuse.Match("invrvex", "misc", "rune/vex_rune", "exact", 1.0, 1.0)
            p = item_hd.Plan(mod, d2r, maps, {"misc/rune/vex_rune"}, {"invrvex"}, {"invrvex"}, [],
                             reuse={"mxl/invrvex": match}, hd_items=hd, dc6_size=lambda g, i: (26, 27))
            items, _u, _s = p.run()
            self.assertEqual(items[0]["r26"]["asset"], "rune/vex_rune")
            self.assertEqual(p.direct, {"invrvex": "misc/rune/vex_rune"})
            self.assertEqual(p.needs, {})
            # without the reuse the mod's picture is converted
            p = item_hd.Plan(mod, d2r, maps, {"misc/rune/vex_rune"}, {"invrvex"}, {"invrvex"}, [])
            self.assertEqual(p.run()[0][0]["r26"]["asset"], "mxl/invrvex")

    def test_generate_removes_stale_sprites(self):
        with tempfile.TemporaryDirectory() as t:
            out = Path(t)
            old = out / "global" / "ui" / "items" / "misc" / "mxl"
            dc6.write_item_sprite(old / "gone.sprite", 1, 1, bytes(4))
            dc6.write_item_sprite(old / "gone.lowend.sprite", 1, 1, bytes(4))
            p = item_hd.Plan({"weapons": [], "armor": [], "misc": []}, {}, {"items": {}, "uniques": {}, "sets": {}}, set(),
                             set(), set(), [])
            n = item_hd.generate(p, PAL, out)
            self.assertEqual(n["stale removed"], 2)
            self.assertFalse(any(old.iterdir()))

    def test_check_accepts_direct_reuse_and_looser_reused_sprite(self):
        tables = {"weapons": [], "armor": [], "uniqueitems": [], "setitems": [],
                  "misc": [{"code": "r26", "invfile": "invrvex", "name": "Vex"}]}
        items = {"r26": {"asset": "rune/vex_rune"}}
        r = item_icon_check.check_items(tables, items, {}, {}, {"misc/rune/vex_rune"}, {"invrvex"}, set())
        self.assertEqual(r["mod_art_not_used"], ["r26"])
        r = item_icon_check.check_items(tables, items, {}, {}, {"misc/rune/vex_rune"}, {"invrvex"}, set(),
                                        direct={"invrvex": "misc/rune/vex_rune"})
        self.assertEqual(r["mod_art_not_used"], [])
        with tempfile.TemporaryDirectory() as t:
            root = Path(t)
            (root / "pic.dc6").write_bytes(dc6.build_dc6([solid(28, 28, 77)]))
            pic = np.zeros((98, 98, 4), np.uint8)
            pic[:, :] = (*PAL[77], 255)
            pic[:8] = 0                                  # D2R's redraw covers a little less
            dc6.write_item_sprite(root / "pic.sprite", 98, 98, pic.tobytes())
            self.assertTrue(item_icon_check.check_sprite(root / "pic.sprite", root / "pic.dc6", PAL, 98))
            self.assertEqual(item_icon_check.check_sprite(root / "pic.sprite", root / "pic.dc6", PAL, 98, reused=True), [])


if __name__ == "__main__":
    unittest.main()
