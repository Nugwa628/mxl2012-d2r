"""Grid geometry of the mod's stash pages (MEDIAN, ORBS, the Materials tab's Median page: tools/median_tabs.py; the redrawn Runes
and Gems pages: tools/median_stash.py, rotw_stash_legacy.py): every slot on one pitch, and the page art's recess exactly under
every slot, HD and classic. D2R's own recesses sit -2 to +5 pixels off their
layout rects; the art copied them by the rect, so the cell frames drifted against the items and each other (user report,
mxl2012-runs/stashgrid/user-report.png)."""
import json
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import projtemp  # noqa: E402,F401  (temp files stay inside the project, tools/projtemp.py)
import numpy as np  # noqa: E402
from PIL import Image, ImageDraw  # noqa: E402

import median_stash as ms  # noqa: E402
import median_tabs as mt  # noqa: E402
import rotw_stash_legacy as rsl  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
BUILT = ROOT / "work" / "mod" / "data"
HD_PITCH = {"medtab_median_bg": (98, 98), "medtab_orbs_bg": (98, 98), "medtab_mat_bg": (104, 98)}
SD_PITCH = {"medtab_median_bg": (27, 28), "medtab_orbs_bg": (27, 28), "medtab_mat_bg": (29, 28)}
# D2R's own Runes / Gems slots (as tools/tests/test_median_stash.py): median_stash.slots puts them and Median's on its grid
D2R_GEMS = [(f"g{q}{f}", (164 + 120 * i, 232 + 98 * j, 98, 98)) for i, f in enumerate("wgryvb") for j, q in enumerate("cfslp")] +     [(f"sk{q}", (884, 232 + 98 * j, 98, 98)) for j, q in enumerate("cfulz")]
D2R_RUNES = [(f"r{n:02d}", (114 + 104 * ((n - 1) % 9), 268 + 98 * ((n - 1) // 9), 98, 98)) for n in range(1, 34)]
MOD_PAGES = {"runes": ms.slots("runes", D2R_RUNES), "gems": ms.slots("gems", D2R_GEMS)}
# offsets of D2R's own recesses from their rects on the Materials page (measured: x -2..+5, y -1..+3), used by the fake page
OFFSETS = [(-2, -1), (5, 3), (0, 0), (4, -1), (-1, 2), (3, 3), (1, 0)]


def fake_materials():
    """A Materials page of grey stone with recesses (91-wide dark inside, a light 3-pixel frame) off their rects as D2R's."""
    im = Image.new("RGBA", (rsl.HD_W, rsl.HD_H), (70, 66, 62, 255))
    d = ImageDraw.Draw(im)
    rects = []
    for i in range(14):
        w, h = mt.SLOT, mt.SLOT if i < 7 else 2 * mt.SLOT
        x, y = 102 + 140 * (i % 7), 240 + 260 * (i // 7)
        ox, oy = OFFSETS[i % len(OFFSETS)]
        ix, iy, ih = x + 3 + ox, y + 3 + oy, h - 7 if h == mt.SLOT else h - 6
        d.rectangle((ix - 3, iy - 3, ix + 91 + 2, iy + ih + 2), fill=(150, 120, 80, 255))
        d.rectangle((ix, iy, ix + 90, iy + ih - 1), fill=(12, 11, 10, 255))
        rects.append((f"c{i:02d}", (x, y, w, h)))
    return im, rects


def lum(im):
    return np.asarray(im.convert("L"), dtype=np.int16)


def interiors_ok(test, page_im, slots, origin):
    """Every slot's recess inside starts RECESS_LEAD in from the slot's rect and is 91 wide (190 tall for 1 x 2)."""
    l = lum(page_im)
    ox, oy = origin
    pad = np.full((l.shape[0] + 40, l.shape[1] + 40), 255, dtype=np.int16)
    pad[20:-20, 20:-20] = l  # room for recess_inside's margin at the field's edge
    for c, (x, y, w, h) in slots:
        got = mt.recess_inside(pad, (x - ox + 20, y - oy + 20, w, h))
        want = (x - ox + 20 + mt.RECESS_LEAD, y - oy + 20 + mt.RECESS_LEAD, mt.RECESS_IN,
                mt.RECESS_IN if h == mt.SLOT else h - 2 * mt.RECESS_LEAD)
        test.assertEqual(got, want, c)


class Geometry(unittest.TestCase):
    def test_hd_pitch(self):
        for name, slots, box in mt.PAGES:
            px, py = HD_PITCH[name]
            x0, y0 = min(r[0] for _c, r in slots), min(r[1] for _c, r in slots)
            for c, (x, y, w, h) in slots:
                self.assertEqual(((x - x0) % px, (y - y0) % py), (0, 0), c)
                self.assertIn((w, h), [(mt.SLOT, mt.SLOT), (mt.SLOT, 2 * mt.SLOT)], c)
                self.assertTrue(box[0] <= x and x + w <= box[2] and box[1] <= y and y + h <= box[3], c)
        self.assertEqual(min(r[:2] for _c, r in mt.median_slots()), mt.GRID)  # the shared stash's 10 x 10

    def test_classic_pitch(self):
        for name, slots, box in mt.PAGES:
            self.assertEqual(mt.classic_pitch(slots)[2:], SD_PITCH[name], name)
            px, py = SD_PITCH[name]
            cs = mt.classic_slots(slots)
            fx, fy, fw, fh = mt.classic_field(box)
            x0, y0 = cs[0][1][:2]
            for (c, (x, y, w, h)), (_c, hd) in zip(cs, slots):
                self.assertEqual(((x - x0) % px, (y - y0) % py), (0, 0), c)
                self.assertIn((w, h), [(28, 28), (28, 57)], c)  # classic cells: 29 per cell less the grid line
                self.assertTrue(fx <= x and x + w <= fx + fw and fy <= y and y + h <= fy + fh, c)
                hx, hy = (hd[0] + hd[2] / 2) / rsl.SX, (hd[1] + hd[3] / 2) / rsl.SY
                self.assertLessEqual(abs(x + w / 2 - hx), 3, c)  # stays where the HD slot lands at the panel scale
                self.assertLessEqual(abs(y + h / 2 - hy), 3, c)


class Art(unittest.TestCase):
    def test_recess_inside_finds_offsets(self):
        im, rects = fake_materials()
        l = lum(im)
        for (c, (x, y, w, h)), k in zip(rects, range(len(rects))):
            ox, oy = OFFSETS[k % len(OFFSETS)]
            self.assertEqual(mt.recess_inside(l, (x, y, w, h))[:3], (x + 3 + ox, y + 3 + oy, 91), c)

    def test_tiles_normalised(self):
        im, rects = fake_materials()
        tiles = mt.recess_tiles(im, rects)
        for (w, h), pics in tiles.items():
            for t in pics:
                self.assertEqual(t.size, (w, h))
                interiors_ok(self, t, [("t", (0, 0, w, h))], (0, 0))

    def test_hd_pages(self):
        im, rects = fake_materials()
        for name, slots, box in mt.PAGES:
            page = mt.page_art(im, rects, slots, box, name)
            self.assertEqual(page.size, (box[2] - box[0], box[3] - box[1]))
            interiors_ok(self, page, slots, box[:2])

    def test_classic_pages(self):
        im, rects = fake_materials()
        tiles = mt.recess_tiles(im, rects)
        for name, slots, box in mt.PAGES:
            small = mt.classic_page_art(mt.stone_art(im, box, name), tiles, slots, box)
            fx, fy, fw, fh = mt.classic_field(box)
            self.assertEqual(small.size, (fw, fh))
            l = lum(small)
            for c, (x, y, w, h) in mt.classic_slots(slots):
                x, y = x - fx, y - fy
                self.assertLess(l[y + 3:y + h - 3, x + 3:x + w - 3].max(), 40, c)    # the recess fills the box
                self.assertGreater(l[y:y + h, x].mean(), 40, c)                      # its frame on the box's own edge
            occupied = np.zeros_like(l, dtype=bool)
            for _c, (x, y, w, h) in mt.classic_slots(slots):
                occupied[y - fy:y - fy + h, x - fx:x - fx + w] = True
            self.assertGreater(l[~occupied].mean(), 40, name)                       # stone elsewhere

    def test_d2r_art(self):
        try:
            import fxpaths
            import median_stash as ms
            d2r = rsl.D2R(fxpaths.D2R, use_cache=True)
            mat = d2r.sprite(f"panel/stash/additionalstash/{ms.BASE_ART}")[0]
            rects = ms._rects(ms._find(d2r.layout(rsl.HD_LAYOUT), "advancedstash_materials")["children"])
        except Exception as e:  # noqa: BLE001  (no D2R extraction or cache on this machine)
            self.skipTest(f"no D2R Materials page: {e}")
        tiles = mt.recess_tiles(mat, rects)  # raises on a recess that is not 91 wide
        self.assertEqual(sum(len(v) for v in tiles.values()), 23)
        for name, slots, box in mt.PAGES:
            interiors_ok(self, mt.page_art(mat, rects, slots, box, name), slots, box[:2])


class ModPages(unittest.TestCase):
    """The Runes and Gems pages the mod redraws (tools/median_stash.py)."""

    def test_hd_grid(self):
        for page, slots in MOD_PAGES.items():
            self.assertEqual(len(slots), {"runes": 56, "gems": 60}[page])
            self.assertTrue(rsl.on_mod_grid(page, slots), page)
            self.assertEqual(rsl.grid_pitch(slots), (104, 98, 29, 28), page)
            for c, (x, y, w, h) in slots:
                self.assertEqual((w, h), (mt.SLOT, mt.SLOT), c)

    def test_classic_grid(self):
        for page, slots in MOD_PAGES.items():
            boxes = rsl.page_boxes(page, slots)
            x0, y0 = boxes[0][:2]
            for (c, hd), (x, y, w, h) in zip(slots, boxes):
                self.assertEqual(((x - x0) % 29, (y - y0) % 28, w, h), (0, 0, 28, 28), c)  # 1-pixel line between columns
                self.assertTrue(0 <= x and x + w <= 320 and rsl.TAB_BAND <= y and y + h <= 432, c)
                self.assertLessEqual(abs(x + 14 - (hd[0] + 49) / rsl.SX), 3, c)
                self.assertLessEqual(abs(y + 14 - (hd[1] + 49) / rsl.SY), 3, c)
            self.assertEqual(len(set(boxes)), len(boxes))

    def test_d2r_pages_keep_their_boxes(self):
        """A D2R page (not on the mod's grid: the Materials page, D2R's own Runes rects) keeps classic_box per slot."""
        mat = [("pk1", (102, 232, 98, 196)), ("dhn", (102, 460, 98, 98)), ("toa", (540, 596, 98, 98))]
        self.assertEqual(rsl.page_boxes("materials", mat), [rsl.classic_box(r) for _c, r in mat])
        self.assertFalse(rsl.on_mod_grid("runes", D2R_RUNES))
        self.assertEqual(rsl.page_boxes("runes", D2R_RUNES), [rsl.classic_box(r) for _c, r in D2R_RUNES])

    def test_hd_art(self):
        im, rects = fake_materials()
        for page, slots in MOD_PAGES.items():
            interiors_ok(self, ms.page_art(page, im, rects, slots), slots, (0, 0))

    def test_hd_art_d2r(self):
        try:
            import fxpaths
            d2r = rsl.D2R(fxpaths.D2R, use_cache=True)
            mat = d2r.sprite(f"panel/stash/additionalstash/{ms.BASE_ART}")[0]
            lay = d2r.layout(rsl.HD_LAYOUT)
        except Exception as e:  # noqa: BLE001  (no D2R extraction or cache on this machine)
            self.skipTest(f"no D2R Materials page: {e}")
        for page in ms.PAGES:
            slots = ms._rects(ms.widget(page, ms._find(lay, f"advancedstash_{page}"))["children"])
            interiors_ok(self, ms.page_image(page, lay, mat), slots, (0, 0))


class Built(unittest.TestCase):
    def layout(self, name):
        p = BUILT / "global" / "ui" / "layouts" / name
        if not p.exists():
            self.skipTest("no built mod (tools/build.py)")
        lay = rsl.lenient_json(p.read_text("utf-8-sig"))
        if mt.find(lay, mt.LAYOUT_MARK) is None:
            self.skipTest("built layout without the Median tabs")
        return lay

    def rects(self, lay, page, codes):
        kids = {c["name"]: c["fields"]["rect"] for c in mt.find(lay, page)["children"]}
        return [(c, tuple(kids[mt.layout_code(c)][k] for k in ("x", "y", "width", "height"))) for c in codes]

    def test_built_slots(self):
        for f, conv in (("bankexpansionlayouthd.json", lambda s: s), ("bankexpansionlayout.json", mt.classic_slots)):
            lay = self.layout(f)
            for name, slots, box in mt.PAGES:
                page = "advancedstash_materials" if name == "medtab_mat_bg" else "advancedstash_runes"
                self.assertEqual(self.rects(lay, page, [c for c, _r in slots]), conv(slots), (f, name))
                bg = next(c for c in lay["children"] if c.get("name", "").startswith(name))["fields"]["rect"]
                want = box[:2] if conv is not mt.classic_slots else mt.classic_field(box)[:2]
                self.assertEqual((bg["x"], bg["y"]), tuple(want), (f, name))

    def test_built_mod_pages(self):
        hd, sd = self.layout("bankexpansionlayouthd.json"), self.layout("bankexpansionlayout.json")
        new = {mt.layout_code(c) for c in mt.CODES}  # MEDIAN / ORBS slots share advancedstash_runes (median_tabs)
        for page in ms.PAGES:
            slots = [s for s in ms._rects(mt.find(hd, f"advancedstash_{page}")["children"]) if s[0] not in new]
            self.assertTrue(rsl.on_mod_grid(page, slots), page)
            got = [tuple(c["fields"]["rect"][k] for k in ("x", "y", "width", "height"))
                   for c in mt.find(sd, f"advancedstash_{page}")["children"]
                   if c.get("type") == "AdvancedStashSlotWidget" and c["fields"]["itemCode"] not in new]
            self.assertEqual(got, rsl.page_boxes(page, slots), page)


if __name__ == "__main__":
    unittest.main()
