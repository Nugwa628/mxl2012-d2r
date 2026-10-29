"""Unit tests of the pure parts of tools/playthrough.py (no game is started)."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import projtemp  # noqa: E402,F401  (temp files stay inside the project, tools/projtemp.py)
import playthrough as pt  # noqa: E402


class Parsers(unittest.TestCase):
    def test_parse_items(self):
        lines = ["h: items",
                 "item id=12 code=hp1 class=587 page=0 x=3 y=1 quality=2 index=0 identified=1 ilvl=1 sockets=0 flags=0x10",
                 "  item id=40 code=box class=549 page=0 x=0 y=0 quality=2 index=0 identified=1 ilvl=1 sockets=0 flags=0x2000010",
                 "items: 2"]
        got = pt.parse_items(lines)
        self.assertEqual([i["id"] for i in got], [12, 40])
        self.assertEqual(got[0]["code"], "hp1")
        self.assertEqual((got[0]["page"], got[0]["x"], got[0]["y"]), (0, 3, 1))
        self.assertEqual(got[1]["flags"], "0x2000010")
        self.assertEqual(pt.parse_items(["item id=21 code=600 page=255 x=3 y=0"])[0]["code"], "600")  # a numeric code stays text

    def test_parse_objects_both_forms(self):
        lines = ["object id=7 class=119 mode=0 dist=12 at 25290,5110",
                 "obj id=9 class=59 mode=1 dist=3 at 100,200 dest=2",
                 "objects 2"]
        got = pt.parse_objects(lines)
        self.assertEqual(len(got), 2)
        self.assertEqual((got[0]["class"], got[0]["x"], got[0]["y"]), (119, 25290, 5110))
        self.assertEqual(got[1]["dest"], 2)
        self.assertEqual(got[0]["dist"], 12)

    def test_parse_ground(self):
        lines = ["ground id=77 code=hp1 mode=3 x=5655 y=5526 dist=3.2 flags=0x10", "ground id=78 code=600 mode=3 x=1 y=2 dist=41.0 flags=0x10",
                 "ground items 2"]
        got = pt.parse_ground(lines)
        self.assertEqual([(d["id"], d["code"], d["dist"]) for d in got], [(77, "hp1", 3.2), (78, "600", 41.0)])

    def test_item_changes(self):
        a = [{"id": 1, "code": "hp1", "page": 0, "x": 0, "y": 0}, {"id": 2, "code": "01-", "page": 0, "x": 1, "y": 0}]
        b = [{"id": 1, "code": "hp1", "page": 0, "x": 0, "y": 0}, {"id": 2, "code": "01-", "page": 3, "x": 0, "y": 0},
             {"id": 5, "code": "cap", "page": 0, "x": 4, "y": 0}]
        new, gone, moved = pt.item_changes(a, b)
        self.assertEqual([i["id"] for i in new], [5])
        self.assertEqual(gone, [])
        self.assertEqual([(x["id"], y["page"]) for x, y in moved], [(2, 3)])
        new, gone, moved = pt.item_changes(b, a)
        self.assertEqual([i["code"] for i in gone], ["cap"])

    def test_kit_signature_ignores_ids(self):
        a = [{"id": 1, "code": "hp1", "page": 0, "x": 0, "y": 0}, {"id": 2, "code": "box", "page": 0, "x": 2, "y": 0}]
        b = [{"id": 90, "code": "box", "page": 0, "x": 2, "y": 0}, {"id": 91, "code": "hp1", "page": 0, "x": 0, "y": 0}]
        self.assertEqual(pt.kit_signature(a), pt.kit_signature(b))
        b[0]["page"] = 3
        self.assertNotEqual(pt.kit_signature(a), pt.kit_signature(b))

    def test_char_name_letters_only_and_unique(self):
        n1, n2 = pt.char_name("sorceress", 1761600000), pt.char_name("sorceress", 1761600001)
        self.assertNotEqual(n1, n2)
        for n in (n1, n2, pt.char_name("necromancer", 0)):
            self.assertTrue(n.isalpha(), n)
            self.assertLessEqual(len(n), 15)
            self.assertTrue(n.startswith("Pt"))
        self.assertTrue(n1.startswith("PtSor"))

    def test_loader_log_problems(self):
        text = ("[info] D2R startup complete\n[ERROR] Could not add cof file: X\n[info] validate: 0 errors\n"
                "[warn] Unhandled exception at 0x1234\n")
        bad = pt.parse_loader_log_tail(text)
        self.assertEqual(len(bad), 2)
        self.assertIn("Could not add", bad[0])


class Finders(unittest.TestCase):
    def test_label_hit(self):
        # slot 2, 'Quilted Armor (1)' hovered at (0.483, 0.525): four regions along the name
        found = [(0.435, 0.507, 8), (0.5025, 0.507, 10), (0.465, 0.511, 4), (0.545, 0.511, 2)]
        self.assertTrue(pt.label_hit(found, 0.483, 0.525))
        self.assertFalse(pt.label_hit([], 0.483, 0.525))
        self.assertFalse(pt.label_hit([(0.48, 0.50, 5)], 0.483, 0.525))  # a small compact change: idle animation
        self.assertFalse(pt.label_hit([(0.48, 0.30, 40)], 0.483, 0.525))  # far above the cursor: not its label

    def test_menu_frame(self):
        bg, gold = [30, 28, 27], [140, 117, 68]
        img = [[list(bg) for _ in range(300)] for _ in range(200)]

        def box(x0, x1, y0, y1):
            for x in range(x0, x1 + 1):
                img[y0][x] = list(gold)
                img[y1][x] = list(gold)
            for y in range(y0, y1 + 1):
                img[y][x0] = list(gold)
                img[y][x1] = list(gold)
        box(100, 220, 120, 190)  # the menu
        self.assertEqual(pt.menu_frame(img, y0=40, y1=200), (160.0, 120))
        for x in range(20, 140):
            img[60][x] = list(gold)  # a piece of the greeting box's top line: no edge going down from its ends
        self.assertEqual(pt.menu_frame(img, y0=40, y1=200), (160.0, 120))
        self.assertIsNone(pt.menu_frame([[list(bg)] * 300] * 200))

    def test_spot_offsets(self):
        offs = pt.spot_offsets(3)
        self.assertEqual(offs[0], (0, 0))
        self.assertIn((3, 0), offs)
        self.assertNotIn((3, 3), offs)
        d = [x * x + y * y for x, y in offs]
        self.assertEqual(d, sorted(d))


class Panel(unittest.TestCase):
    def test_grey_patches(self):
        self.assertTrue(pt.grey_patches([(63, 63, 63), (57, 57, 56)]))  # inventory open (slot 2 capture)
        self.assertFalse(pt.grey_patches([(50, 41, 29), (34, 30, 26)]))  # town scene
        self.assertFalse(pt.grey_patches([(30, 30, 30), (57, 57, 56)]))  # dark: a loading screen


class Tables(unittest.TestCase):
    TABLES = {
        "itemtypes": [{"Code": "helm", "Body": "1", "BodyLoc1": "head", "Equiv1": "armo"},
                      {"Code": "armo", "Body": "", "BodyLoc1": ""},
                      {"Code": "circ", "Body": "", "BodyLoc1": "", "Equiv1": "helm"},
                      {"Code": "hpot", "Body": "", "BodyLoc1": "", "Equiv1": "pots"},
                      {"Code": "swor", "Body": "1", "BodyLoc1": "rarm", "BodyLoc2": "larm", "Equiv1": "mele"}],
        "armor": [{"code": "cap", "type": "helm"}, {"code": "ci0", "type": "circ"}],
        "weapons": [{"code": "ssd", "type": "swor"}],
        "misc": [{"code": "hp1", "type": "hpot"}],
    }

    def test_body_loc_follows_the_type_chain(self):
        self.assertEqual(pt.body_loc_of("cap", self.TABLES), "head")
        self.assertEqual(pt.body_loc_of("ci0", self.TABLES), "head")
        self.assertEqual(pt.body_loc_of("ssd", self.TABLES), "rarm")
        self.assertEqual(pt.body_loc_of("hp1", self.TABLES), "")
        self.assertEqual(pt.body_loc_of("zzz", self.TABLES), "")


class Backpack(unittest.TestCase):
    TABLES = {"misc": [{"code": "box", "invwidth": "2", "invheight": "2"}, {"code": "zen", "invwidth": "1", "invheight": "2"},
                       {"code": "tsc", "invwidth": "1", "invheight": "1"}],
              "armor": [{"code": "600", "invwidth": "2", "invheight": "3", "type": "tors"}],
              "itemtypes": [{"Code": "tors", "Body": "1", "BodyLoc1": "tors"}, {"Code": "hpot"}]}

    def test_free_cell(self):
        items = [{"code": "box", "page": 0, "x": 0, "y": 0}, {"code": "zen", "page": 0, "x": 2, "y": 0},
                 {"code": "tsc", "page": 0, "x": 3, "y": 0}, {"code": "600", "page": 255, "x": 3, "y": 0}]
        self.assertEqual(pt.free_cell(items, self.TABLES, 1, 1), (4, 0))
        self.assertEqual(pt.free_cell(items, self.TABLES, 2, 3), (4, 0))
        self.assertEqual(pt.free_cell(items, self.TABLES, 4, 2), (4, 0))
        full = [{"code": "tsc", "page": 0, "x": x, "y": y} for x in range(10) for y in range(6)]
        self.assertIsNone(pt.free_cell(full, self.TABLES))

    def test_worn_on(self):
        self.assertTrue(pt.worn_on({"page": 255, "x": 3}, "tors"))  # the kit's 600, slot 2
        self.assertTrue(pt.worn_on({"page": 255, "x": 5}, "rarm"))  # a weapon in the other hand
        self.assertFalse(pt.worn_on({"page": 255, "x": 0}, "rarm"))  # on the cursor / in the belt
        self.assertFalse(pt.worn_on({"page": 0, "x": 4}, "rarm"))
        self.assertFalse(pt.worn_on({}, "head"))

    def test_worn_skips_belt_potions(self):
        items = [{"code": "hp1", "page": 255, "x": 3, "y": 0}, {"code": "600", "page": 255, "x": 3, "y": 0}]
        tables = dict(self.TABLES, misc=[{"code": "hp1", "type": "hpot"}])
        self.assertEqual([i["code"] for i in pt.worn(items, tables)], ["600"])
        self.assertEqual([i["code"] for i in pt.belt_potions(items)], ["hp1"])


class Verdict(unittest.TestCase):
    def test_selected_steps(self):
        self.assertIsNone(pt.selected_steps(None))
        self.assertIsNone(pt.selected_steps(""))
        self.assertEqual(pt.selected_steps("vendor, kit"), {"create", "vendor", "kit"})
        with self.assertRaises(ValueError):
            pt.selected_steps("vendr")
        only = pt.selected_steps("vendor")
        self.assertEqual(pt.class_verdict({"create": ("PASS", ""), "vendor": ("PASS", "")}, only), "PASS")

    def test_class_verdict(self):
        steps = {s: ("PASS", "") for s in pt.STEPS}
        self.assertEqual(pt.class_verdict(steps), "PASS")
        steps["vendor"] = ("BLOCKED", "no NPC menu in background mode")
        self.assertEqual(pt.class_verdict(steps), "PARTIAL")
        steps["reload"] = ("FAIL", "items lost")
        self.assertEqual(pt.class_verdict(steps), "FAIL")
        self.assertEqual(pt.class_verdict({"create": ("PASS", "")}), "PARTIAL")
        self.assertIn("vendor BLOCKED (no NPC menu", pt.class_note(steps))


if __name__ == "__main__":
    unittest.main()
