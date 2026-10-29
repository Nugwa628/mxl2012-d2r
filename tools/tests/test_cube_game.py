"""tools/cube_game.py: the in-game cube check's case table, harness line parsing and judgement (no game).

Run: py -3 -I -m unittest discover -s tools/tests -p "test_cube_game.py"
"""
import sys
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))
import projtemp  # noqa: E402,F401  (temp files stay inside the project, tools/projtemp.py)
import cube_game as cg  # noqa: E402

TYPES = {"4@A": ("pmac", "tier"), "5@A": ("pmac", "tier"), "r02": ("rune",), "9o^": ("thng",), "hp1": ("hpot",)}
ITEMS = ["item id=7 code=box class=1 page=0 x=0 y=0 quality=2 index=0 identified=1 ilvl=1 sockets=0 flags=0x10",
         "item id=41 code=4@A class=9 page=3 x=0 y=0 quality=1 index=0 identified=1 ilvl=100 sockets=0 flags=0x10",
         "item id=42 code=9o^ class=2 page=3 x=2 y=0 quality=2 index=0 identified=1 ilvl=1 sockets=0 flags=0x10"]


class Parsing(unittest.TestCase):
    def test_cube_items(self):
        cube = cg.cube_items(ITEMS)
        self.assertEqual([(i["id"], i["code"], i["quality"]) for i in cube], [(41, "4@A", 1), (42, "9o^", 2)])
        self.assertEqual(cube[0]["flags"], 0x10)

    def test_item_and_stat_lines(self):
        self.assertEqual(cg.item_id(["item id=300 code=r01 class=5 page=255", "item OK"]), 300)
        self.assertIsNone(cg.item_id(["item FAIL item: unknown code"]))
        self.assertEqual(cg.istat_value(["istat 41 194:0 = 1", "istat OK"]), 1)
        self.assertIsNone(cg.istat_value(["istat FAIL istat: no such item unit"]))
        lines = ["istat 41 195:45441 = 5", "istat 41 195:45442 = 5", "istat 41 195 scan: 2 layers with a value"]
        self.assertEqual(cg.istat_layers(lines), {45441: 5, 45442: 5})
        self.assertEqual(cg.skill_ids(cg.istat_layers(lines), "2"), [710])
        self.assertEqual(cg.skill_ids({710: 1}, ""), [710])


class Judging(unittest.TestCase):
    def test_match_and_quality(self):
        case = dict(cube=["type:pmac", "9o^"], out="type:pmac", quality=1)
        ok, note = cg.judge(case, [], cg.cube_items(ITEMS), TYPES)
        self.assertTrue(ok, note)
        ok, note = cg.judge(dict(case, quality=4), [], cg.cube_items(ITEMS), TYPES)
        self.assertFalse(ok)

    def test_wrong_contents(self):
        ok, note = cg.judge(dict(cube=["9o^"], out="9o^"), [], cg.cube_items(ITEMS), TYPES)
        self.assertFalse(ok)
        self.assertIn("wanted", note)

    def test_refused(self):
        cube = cg.cube_items(ITEMS)
        self.assertTrue(cg.judge(dict(cube=[], refused=True), cube, list(cube), TYPES)[0])
        self.assertFalse(cg.judge(dict(cube=[], refused=True), cube, cube[:1], TYPES)[0])

    def test_stats(self):
        case = dict(cube=["type:pmac", "9o^"], out="type:pmac", stats={"item_numsockets": 1}, stats_min={"item_maxdamage_percent": 25})
        self.assertTrue(cg.judge(case, [], cg.cube_items(ITEMS), TYPES, {"item_numsockets": 1, "item_maxdamage_percent": 27})[0])
        self.assertFalse(cg.judge(case, [], cg.cube_items(ITEMS), TYPES, {"item_numsockets": 1, "item_maxdamage_percent": 24})[0])
        self.assertFalse(cg.judge(case, [], cg.cube_items(ITEMS), TYPES, {"item_maxdamage_percent": 30})[0])

    def test_skill_layer(self):
        case = dict(cube=["type:pmac", "9o^"], out="type:pmac", skill_layer=("item_skillonattack", "Dire Charm L"))
        self.assertTrue(cg.judge(case, [], cg.cube_items(ITEMS), TYPES, {}, (710, [710]))[0])
        self.assertFalse(cg.judge(case, [], cg.cube_items(ITEMS), TYPES, {}, (710, [708]))[0])

    def test_output_prefers_new_unit(self):
        cube = cg.cube_items(ITEMS) + [dict(id=50, code="5@A", page=3)]
        self.assertEqual(cg.output_item(dict(out="type:pmac"), cube, TYPES, inputs={41})["id"], 50)


class CaseTable(unittest.TestCase):
    def test_cases_well_formed(self):
        names = set()
        for c in cg.CASES + [cg.PREP_HONORIFIC]:
            self.assertNotIn(c["name"], names)
            names.add(c["name"])
            self.assertTrue(c["inputs"] and isinstance(c["row"], int) and c["cls"])
            self.assertLessEqual(len(c["inputs"]), len(cg.CUBE_CELLS))
            self.assertTrue(c.get("refused") or c["cube"], c["name"])
            if c.get("refused"):
                self.assertEqual(c["cube"], [])
            if c.get("again"):
                self.assertIn(c["again"], {x["name"].split(" (")[0] for x in cg.CASES})

    def test_cells_fit_the_cube(self):
        self.assertEqual(len(set(cg.CUBE_CELLS)), len(cg.CUBE_CELLS))
        self.assertTrue(all(0 <= x <= 8 and 0 <= y <= 6 for x, y in cg.CUBE_CELLS))


if __name__ == "__main__":
    unittest.main()
