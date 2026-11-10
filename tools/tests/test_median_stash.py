"""Median's runes and gems in the RotW stash's Runes / Gems pages (tools/median_stash.py)."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import projtemp  # noqa: E402,F401  (temp files stay inside the project, tools/projtemp.py)
import median_stash as ms  # noqa: E402

FAMILIES = ["w", "g", "r", "y", "v", "b"]  # D2R's gem colours by column; skulls are the 7th column
D2R_GEMS = [(f"g{q}{f}", (164 + 120 * i, 232 + 98 * j, 98, 98)) for i, f in enumerate(FAMILIES)
            for j, q in enumerate("cfslp")] + [(f"sk{q}", (884, 232 + 98 * j, 98, 98)) for j, q in enumerate("cfulz")]
D2R_RUNES = [(f"r{n:02d}", (114 + 104 * ((n - 1) % 9), 268 + 98 * ((n - 1) // 9), 98, 98)) for n in range(1, 34)]


def slot(code, r):
    x, y, w, h = r
    return {"type": "AdvancedStashSlotWidget", "name": code,
            "fields": {"rect": {"x": x, "y": y, "width": w, "height": h}, "itemCode": code}}


def layout():
    return {"type": "Widget", "name": "root", "children": [
        {"type": "Widget", "name": "advancedstash_gems", "fields": {"visible": False},
         "children": [slot(c, r) for c, r in D2R_GEMS] + [{"type": "ImageWidget", "name": "bg"}]},
        {"type": "Widget", "name": "advancedstash_materials", "children": [
            slot("pk1", (102, 232, 98, 196)), slot("dhn", (102, 460, 98, 98)), slot("rvs", (204, 596, 98, 98))]},
        {"type": "Widget", "name": "advancedstash_runes", "children": [slot(c, r) for c, r in D2R_RUNES]}]}


def overlaps(rects):
    return [(a, b) for i, (a, (ax, ay, aw, ah)) in enumerate(rects) for b, (bx, by, bw, bh) in rects[:i]
            if ax < bx + bw and bx < ax + aw and ay < by + bh and by < ay + ah]


class Codes(unittest.TestCase):
    def test_median_codes(self):
        self.assertEqual(len(ms.MEDIAN_RUNES), 23)
        self.assertEqual((ms.MEDIAN_RUNES[0], ms.MEDIAN_RUNES[-1]), ("r34", "r56"))
        self.assertEqual(len(ms.MEDIAN_GEMS), 25)
        self.assertEqual([f[0] for f in ms.MEDIAN_GEM_FAMILIES], ["yo1", "g$a", "9$a", "7$a", "5$a"])
        self.assertEqual(len(set(ms.CODES)), 48)


class Slots(unittest.TestCase):
    def test_runes_in_reading_order(self):
        s = ms.slots("runes", D2R_RUNES)
        self.assertEqual([c for c, _r in s], [f"r{n:02d}" for n in range(1, 57)])
        self.assertEqual(s[0][1], (114, 218, 98, 98))
        self.assertEqual(s[44][1], (946, 610, 98, 98))   # r45: the grid's last cell
        self.assertEqual(s[45][1], (114, 708, 98, 98))   # r46: the first side cell
        self.assertEqual(s[-1][1], (842, 904, 98, 98))   # r56
        self.assertEqual(overlaps(s), [])

    def test_gems_one_column_per_family(self):
        s = dict(ms.slots("gems", D2R_GEMS))
        self.assertEqual(len(s), 35 + 25)
        self.assertEqual(s["gcw"], (114, 218, 98, 98))
        self.assertEqual(s["gpw"], (114, 610, 98, 98))
        self.assertEqual(s["skz"], (738, 610, 98, 98))
        self.assertEqual(s["yo1"], (842, 218, 98, 98))
        self.assertEqual(s["g$e"], (946, 610, 98, 98))
        self.assertEqual(s["9$a"], (114, 708, 98, 98))
        self.assertEqual(s["7$e"], (218, 1100, 98, 98))
        self.assertEqual(s["5$e"], (946, 1100, 98, 98))
        self.assertEqual(overlaps(list(s.items())), [])

    def test_slots_stay_on_the_page_and_off_the_cube_plinth(self):
        for page, d2r in (("gems", D2R_GEMS), ("runes", D2R_RUNES)):
            for c, (x, y, w, h) in ms.slots(page, d2r):
                self.assertTrue(86 <= x and x + w <= 1077 and 216 <= y and y + h <= 1204, (page, c))
                if y + h > 717:  # beside the plinth (x 362-798)
                    self.assertTrue(x + w <= 362 or x >= 798, (page, c))

    def test_too_many_refused(self):
        with self.assertRaises(ValueError):
            ms.slots("runes", D2R_RUNES + [(f"x{n}", (0, 0, 98, 98)) for n in range(10)])
        with self.assertRaises(ValueError):
            ms.slots("materials", [])


class Layout(unittest.TestCase):
    def test_apply_keeps_the_rest(self):
        lay = ms.apply(layout())
        gems = ms._find(lay, "advancedstash_gems")
        self.assertEqual(gems["fields"], {"visible": False})
        self.assertEqual(gems["children"][-1], {"type": "ImageWidget", "name": "bg"})
        self.assertEqual(sum(c["type"] == "AdvancedStashSlotWidget" for c in gems["children"]), 60)
        runes = ms._find(lay, "advancedstash_runes")["children"]
        self.assertEqual(runes[-1]["fields"], {"rect": {"width": 98, "height": 98, "x": 842, "y": 904}, "itemCode": "r56"})
        self.assertEqual(len(ms._find(lay, "advancedstash_materials")["children"]), 3)


@unittest.skipIf(ms.Image is None, "Pillow")
class Art(unittest.TestCase):
    def test_page_art(self):
        mat = ms.Image.new("RGBA", (ms.PAGE_W, ms.PAGE_H), (60, 60, 60, 255))
        d = ms.ImageDraw.Draw(mat)
        for x, y, h in ((105, 461, 91), (105, 235, 190), (209, 599, 91)):  # pk1, dhn, rvs: off their rects as D2R's
            d.rectangle((x - 3, y - 3, x + 93, y + h + 2), fill=(150, 120, 80, 255))
            d.rectangle((x, y, x + 90, y + h - 1), fill=(10, 10, 10, 255))
        im = ms.page_image("runes", layout(), mat)
        self.assertEqual(im.size, (ms.PAGE_W, ms.PAGE_H))
        self.assertEqual(im.getpixel((114 + 49, 218 + 49)), (10, 10, 10, 255))   # a recess under r01
        self.assertEqual(im.getpixel((114 + 3, 218 + 3)), (10, 10, 10, 255))     # its inside 3 pixels in from the rect
        self.assertEqual(im.getpixel((114 + 1, 218 + 1)), (150, 120, 80, 255))   # its frame on the rect's edge
        stone = ms.page_image("runes", layout(), mat, stone_only=True)
        self.assertNotEqual(stone.getpixel((114 + 49, 218 + 49)), (10, 10, 10, 255))  # no recess
        self.assertEqual(im.getpixel((500, 900)), (60, 60, 60, 255))           # the plinth stays
        self.assertEqual(ms.lowend(im).size, (ms.PAGE_W // 2, ms.PAGE_H // 2))
        with self.assertRaises(ValueError):
            ms.page_image("runes", layout(), mat.resize((10, 10)))


if __name__ == "__main__":
    unittest.main()
