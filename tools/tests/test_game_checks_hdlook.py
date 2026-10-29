"""Helpers of game_checks' `hdl_look` check (lane hdlook) on the built tables; no game is started.
Run: py -3 -I -m unittest discover -s tools/tests -p "test_game_checks_hdlook.py" """
import json
import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import projtemp  # noqa: E402,F401  (temp files stay inside the project, tools/projtemp.py)
os.environ.setdefault("MXL_SLOT", "2")  # importing game_ctl needs a slot; nothing here starts a game
import game_checks as gc  # noqa: E402

BUILT = os.path.isfile(os.path.join(gc.EXCEL, "missiles.txt"))
RECOLOUR = Path(gc.EXCEL).parents[2] / "hd_recolour.json"


class Stages(unittest.TestCase):
    def test_default_all(self):
        self.assertEqual(gc.hdl_stages({}), ["fx", "mons", "ui", "items", "walls", "picks"])

    def test_order_and_unknown(self):
        self.assertEqual(gc.hdl_stages({"MXL_HDL": "walls,bogus,fx"}), ["walls", "fx"])


class Stash(unittest.TestCase):
    def test_stash_item_is_a_backpack_item_not_the_cube(self):
        items = [{"id": 1, "code": "box", "page": 0, "x": 0, "y": 0}, {"id": 2, "code": "5$a", "page": 0, "x": 2, "y": 0},
                 {"id": 3, "code": "rin", "page": 255, "x": 6, "y": 0}]
        self.assertEqual(gc.hdl_stash_item(items)["id"], 2)
        self.assertIsNone(gc.hdl_stash_item(items + [{"id": 4, "code": "r26", "page": 4, "x": 0, "y": 0}]))  # one is there
        self.assertIsNone(gc.hdl_stash_item(items[:1]))

    def test_stash_cell_is_left_of_the_inventory(self):
        x, y = gc.rp_inv_xy(*gc.HDL_STASH_CELL, gc.HDL_STASH)
        self.assertTrue(0.05 < x < 0.45 and 0.15 < y < 0.8)


@unittest.skipUnless(BUILT and RECOLOUR.is_file(), "needs a build in work/mod (tools/build.py)")
class Tables(unittest.TestCase):
    def test_fx_rows_are_tinted_missiles(self):
        tinted = {r for x in json.loads(RECOLOUR.read_text(encoding="utf-8"))["recolours"] for r in x["rows"]}
        for cls, skills in gc.HDL_FX.items():
            for sid, name, rows in skills:
                self.assertIsNotNone(gc.row_of("skills", "*Id", sid), name)
                for r in rows:
                    self.assertIn(r, tinted, "%s %s" % (cls, r))
                    self.assertIsNotNone(gc.missile_id(r), r)

    def test_drawn_counts_wanted_rows_only(self):
        mid = gc.missile_id("darkpowernova")
        self.assertEqual(gc.hdl_drawn(("darkpowernova", "balefireball"), {mid: 3}), {"darkpowernova": 3, "balefireball": 0})

    def test_monster_rows_exist(self):
        for _tag, ids in gc.HDL_MONS:
            for m in ids:
                self.assertIsNotNone(gc.tint_class(m), m)

    def test_oskill_item_is_blackheart(self):
        code, uniq, _loc = gc.HDL_OSKILL_ITEM[669]
        row = gc.table("uniqueitems")[uniq]
        self.assertIn("Blackheart", row["index"])
        self.assertEqual(row["code"], code)

    def test_oskill_item_fits_its_class(self):
        """The class that casts an item oskill may wear the item (Median's wands are Necromancer-only)."""
        types = {r["Code"]: r for r in gc.table("itemtypes")}
        weapons = {r["code"]: r for r in gc.table("weapons")}
        for cls, skills in gc.HDL_FX.items():
            for sid, name, _rows in skills:
                if sid in gc.HDL_OSKILL_ITEM:
                    t = types[weapons[gc.HDL_OSKILL_ITEM[sid][0]]["type"]]
                    self.assertIn(t["Class"], ("", cls[:3]), name)
                    self.assertIn(cls, gc.HDL_CHARS)

    def test_pick_skills_are_class_skills_that_fire_the_picked_rows(self):
        """HDL_PICKS: each skill is of its class, and every row is a missile whose art is a hand pick (hd-effects-picks.tsv)."""
        root = Path(__file__).resolve().parents[2]
        picked = {ln.split("	")[1] for ln in (root / "data/hd-effects-picks.tsv").read_text("utf-8").splitlines()
                  if ln.startswith("missile	")}
        for cls, skills in gc.HDL_PICKS.items():
            self.assertIn(cls, gc.HDL_CHARS)
            for sid, name, rows in skills:
                row = gc.row_of("skills", "*Id", sid)
                self.assertEqual(row["charclass"], cls[:3], name)
                for r in rows:
                    m = gc.row_of("missiles", "Missile", r)
                    self.assertIsNotNone(m, r)
                    self.assertTrue(any(m["CelFile"].lower().replace("\\", "/").endswith(a.split("/")[-1]) for a in picked),
                                    (r, m["CelFile"]))

    def test_nightmare_comes_from_the_skeleton(self):
        mon, _n = gc.HDL_NIGHTMARE
        row = gc.table("monstats")[gc.tint_class(mon)]
        self.assertIn("Nightmare", [row["Skill%d" % i] for i in range(1, 9)])


if __name__ == "__main__":
    unittest.main()
