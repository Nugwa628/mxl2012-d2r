"""Tests of tools/objstr.py, tools/string_gaps.py and the id table of tools/ds1_remap.py (lane objstr): synthetic tables, no game files.

  py -3 -I -m unittest discover -s tools/tests -p "test_objstr.py" -v
"""
import json
import sys
import tempfile
import unittest
from collections import Counter
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import projtemp  # noqa: E402,F401  (temp files stay inside the project, tools/projtemp.py)
sys.path.insert(0, str(Path(__file__).resolve().parent))
import ds1_remap  # noqa: E402
import objstr  # noqa: E402
import string_gaps  # noqa: E402
from test_maps import make_ds1  # noqa: E402


def objects_table(*classes, names=None):
    names = names or [c.upper() for c in classes]
    return ["Class", "Name", "AutoMap"], [[c, n, str(i)] for i, (c, n) in enumerate(zip(classes, names))]


class ObjectChecks(unittest.TestCase):
    PRESETS = {1: {0: "Fountain", 1: "TikiTorch1"}, 2: {0: "Casket"}}

    def test_every_id_resolves(self):
        used = Counter({("a.ds1", 1, 0): 3, ("a.ds1", 1, 1): 1, ("b.ds1", 2, 0): 1})
        b = objects_table("fountain", "TikiTorch1", "casket")
        m = (["Name", "x"], [["FOUNTAIN", ""], ["TIKITORCH1", ""], ["CASKET", ""]])
        problems, notes, st = objstr.check_objects(used, self.PRESETS, b, m, [])
        self.assertEqual(problems, [])
        self.assertEqual((st["objects"], st["distinct"]), (5, 3))

    def test_class_is_case_insensitive(self):
        used = Counter({("a.ds1", 1, 0): 1})
        b = objects_table("FOUNTAIN")
        problems, _n, _s = objstr.check_objects(used, self.PRESETS, b, (["Name"], [["FOUNTAIN"]]), [])
        self.assertEqual(problems, [])

    def test_problems(self):
        used = Counter({("a.ds1", 1, 7): 1, ("a.ds1", 2, 0): 1, ("a.ds1", 1, -1): 1})
        b = objects_table("fountain")          # no Casket row
        problems, _n, st = objstr.check_objects(used, self.PRESETS, b, (["Name"], [["FOUNTAIN"]]), [(5, 9)])
        text = "\n".join(problems)
        self.assertIn("id 7 (act 1) has no row in D2R's ObjPreset", text)
        self.assertIn("id -1 (act 1) has no row", text)
        self.assertIn("ObjectClass 'Casket'", text)
        self.assertIn("change id", text)
        self.assertEqual((st["missing_slot"], st["no_class"]), (2, 1))

    def test_renamed_row_and_duplicate_class(self):
        b = objects_table("a", "A", names=["One", "Two"])
        problems, _n, _s = objstr.check_objects(Counter(), {}, b, (["Name"], [["One"], ["Other"]]), [])
        text = "\n".join(problems)
        self.assertIn("Class used by several rows", text)
        self.assertIn("Name differs from the mod's in rows [1]", text)

    def test_namespaced_name_is_the_same_name(self):
        b = (["Class", "Name"], [["a", "mxl2012:Zoo"], ["b", "mxlname_3"]])
        problems, _n, _s = objstr.check_objects(Counter(), {}, b, (["Name"], [["Zoo"], ["Long Key"]]), [])
        self.assertEqual(problems, [])

    def test_d2r_only_row_is_a_note(self):
        used = Counter({("a.ds1", 1, 0): 1})
        b = objects_table("a", "fountain")
        problems, notes, st = objstr.check_objects(used, self.PRESETS, b, (["Name"], [["A"]]), [])
        self.assertEqual((problems, st["d2r_only_row"]), ([], 1))
        self.assertTrue(notes)

    def test_preset_classes(self):
        h = ["Index", "Act", "ObjectClass"]
        self.assertEqual(objstr.preset_classes(h, [["0", "1", "A"], ["3", "2", "B"], ["x", "2", "C"]]), {1: {0: "A"}, 2: {3: "B"}})

    def test_ds1_objects_counts_type2_only(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "sub").mkdir()
            (Path(d) / "sub" / "m.ds1").write_bytes(make_ds1(2, 2, act=1, objects=[(2, 5, 0, 0, 0), (2, 5, 1, 1, 0), (1, 9, 0, 0, 0)]))
            self.assertEqual(objstr.ds1_objects(Path(d)), Counter({("sub/m.ds1", 2, 5): 2}))


class AutomapChecks(unittest.TestCase):
    TYPES = ["None", "Act 1 - Town", "Act 5 - Ice Caves", "Expansion", "Act 5 - Town"]
    OBJ = objects_table("a", "b")

    def folder(self, root, name, types=None, automap=None, extra=()):
        d = Path(root) / name
        d.mkdir(parents=True)
        if types is not None:
            (d / "lvltypes.txt").write_text("Name\tId\r\n" + "".join(f"{t}\t{i}\r\n" for i, t in enumerate(types)), "utf-8")
        if automap is not None:
            (d / "automap.txt").write_text("LevelName\tTileName\r\n" + "".join(f"{a}\tfl\r\n" for a in automap), "utf-8")
        for f in extra:
            (d / f).write_text("x\r\n", "utf-8")
        return d

    def run_check(self, src_extra=(), mod_types=None, built_extra=()):
        with tempfile.TemporaryDirectory() as root:
            src = self.folder(root, "src", extra=src_extra)
            built = self.folder(root, "built", types=mod_types or self.TYPES, extra=built_extra)
            d2r = self.folder(root, "d2r", types=self.TYPES, automap=["1 Town", "5 Ice", "Expansion"])
            return objstr.check_automap(src, built, d2r, self.OBJ, self.OBJ)

    def test_same_level_types_no_table_is_clean(self):
        problems, notes = self.run_check()
        self.assertEqual(problems, [])
        self.assertTrue(any("ships no automap" in n for n in notes))
        self.assertTrue(any("Act 5 - Town" in n for n in notes))      # no AutoMap row: a note, not a problem

    def test_shipped_table_is_a_problem(self):
        problems, _n = self.run_check(src_extra=("automap.bin",))
        self.assertTrue(any("ships ['automap.bin']" in p for p in problems))
        problems, _n = self.run_check(built_extra=("objpreset.txt",))
        self.assertTrue(any("objpreset.txt" in p and "replace" in p for p in problems))

    def test_level_type_names_must_match(self):
        problems, _n = self.run_check(mod_types=["None", "Act 1 - Town", "Act 5 - Ice", "Expansion", "Act 5 - Town"])
        self.assertTrue(any("lvltypes.txt names differ" in p for p in problems))
        problems, _n = self.run_check(mod_types=self.TYPES + ["Act 6 - New"])
        self.assertTrue(any("lvltypes.txt names differ" in p for p in problems))

    def test_automap_cel_of_objects(self):
        h = ["Class", "AutoMap"]
        mod, built = (h, [["a", "5"], ["b", "6"]]), (h, [["a", "5"], ["b", "7"]])
        with tempfile.TemporaryDirectory() as root:
            src, bdir = self.folder(root, "src"), self.folder(root, "built")
            d2r = self.folder(root, "d2r")
            problems, _n = objstr.check_automap(src, bdir, d2r, mod, built)
            self.assertTrue(any("AutoMap differs" in p for p in problems))
            problems, _n = objstr.check_automap(src, bdir, d2r, mod, (h, [["a", "5"], ["b", "1600"]]))
            self.assertTrue(any("above D2R's atlas" in p for p in problems))

    def test_type_names(self):
        self.assertEqual(objstr.norm_type_name("Act 1 - Town"), "1 Town")
        self.assertEqual(objstr.norm_type_name("Expansion"), "Expansion")


class Ds1Ids(unittest.TestCase):
    def maps(self):
        m = ds1_remap.Maps({0: 0, 1: 1, 5: 9}.get, {1: 2})
        m.monster_rows = 6
        return m

    def test_json_round_trip(self):
        data = self.maps().to_json()
        self.assertEqual(data, {"monster": {"0": 0, "1": 1, "5": 9}, "presets": {"1": 2}})
        back = ds1_remap.Maps.from_json(json.loads(json.dumps(data)))
        self.assertEqual([back.monster_new(0, i) for i in (0, 1, 2, 5, 7, -3)], [0, 1, None, 9, None, None])

    def test_remap_tree_reads_the_ids_file(self):
        with tempfile.TemporaryDirectory() as d:
            ids = Path(d) / "ds1_ids.json"
            ids.write_text(json.dumps(self.maps().to_json()), "utf-8")
            tiles = Path(d) / "tiles"
            tiles.mkdir()
            (tiles / "m.ds1").write_bytes(make_ds1(2, 2, act=0, objects=[(1, 5, 0, 0, 0), (2, 3, 1, 1, 0), (1, 1, 0, 0, 0)]))
            old = ds1_remap.IDS_FILE
            ds1_remap.IDS_FILE = ids
            try:
                stats = ds1_remap.remap_tree(tiles)
            finally:
                ds1_remap.IDS_FILE = old
            self.assertEqual((stats["files_changed"], stats["type1_renumbered"]), (1, 1))
            objs = ds1_remap.Ds1((tiles / "m.ds1").read_bytes()).objects
            self.assertEqual([(o[0], o[1]) for o in objs], [(1, 9), (2, 3), (1, 1)])

    def test_cli_uses_the_ids_file(self):
        with tempfile.TemporaryDirectory() as d:
            ids = Path(d) / "ids.json"
            ids.write_text(json.dumps({"monster": {"5": 6}, "presets": {"1": 2}}), "utf-8")
            (Path(d) / "m.ds1").write_bytes(make_ds1(2, 2, objects=[(1, 5, 0, 0, 0)]))
            old = sys.argv
            sys.argv = ["ds1_remap.py", "--ids-file", str(ids), str(d)]
            try:
                ds1_remap.main()
            finally:
                sys.argv = old
            self.assertEqual(ds1_remap.Ds1((Path(d) / "m.ds1").read_bytes()).objects[0][1], 6)


class StringGaps(unittest.TestCase):
    """The old `empty` behaviour; the other actions and the committed rows are in test_string_gaps.py."""

    def test_the_data_file_is_valid_and_complete(self):
        gaps = string_gaps.load()
        self.assertGreater(len(gaps), 50)
        self.assertEqual(len({(g["table"], g["column"], g["key"]) for g in gaps}), len(gaps))
        self.assertTrue(all(g["reason"] for g in gaps))
        texts = string_gaps.texts(gaps)
        self.assertEqual(texts["Pandora"], "Pandora")
        self.assertEqual(texts["ModitemLevReq"], "Required Level")   # a description line is written, not emptied
        self.assertNotIn("blah", {g["key"] for g in gaps})           # the shrine cells are a port fix (txt_migrate shrine_strings)

    def test_bad_action_is_refused(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "g.tsv"
            p.write_text("table\tcolumn\tkey\taction\ttext\tcells\treason\nmisc\tnamestr\tx\tshow\tt\t\tn\n", "utf-8")
            with self.assertRaises(ValueError):
                string_gaps.load(p)

    def test_apply_empty(self):
        base = {"text": "", "cells": "", "reason": "n"}
        gaps = [dict(base, table="itemstatcost", column="descstrpos", key="Gone", action="empty"),
                dict(base, table="itemstatcost", column="descstrneg", key="Gone", action="empty"),
                dict(base, table="misc", column="spelldescstr", key="Lost", action="empty"),
                dict(base, table="misc", column="namestr", key="Name", action="text", text="A Name")]
        with tempfile.TemporaryDirectory() as d:
            ex = Path(d)
            (ex / "itemstatcost.txt").write_bytes((
                "Stat\tdescfunc\tdescval\tdescstrpos\tdescstrneg\tdescstr2\tdgrpfunc\r\n"
                "a\t4\t2\tGone\tgone\t\t3\r\n"
                "b\t4\t2\tGone\tKept\t\t3\r\n"
                "c\t1\t1\tKept\tKept\t\t3\r\n").encode())
            (ex / "misc.txt").write_bytes(b"name\tnamestr\tspelldescstr\r\nx\tName\tLost\r\ny\tName\tOther\r\n")
            done = string_gaps.apply_empty(ex, gaps)
            rows = (ex / "itemstatcost.txt").read_bytes().decode().split("\r\n")
            self.assertEqual(rows[1], "a\t\t\t\t\t\t3")                   # strings and their function / value gone
            self.assertEqual(rows[2], "b\t4\t2\t\tKept\t\t3")             # one string left: the function stays
            self.assertEqual(rows[3], "c\t1\t1\tKept\tKept\t\t3")
            misc = (ex / "misc.txt").read_bytes().decode().split("\r\n")
            self.assertEqual(misc[1:3], ["x\tName\t", "y\tName\tOther"])    # `text` rows without `cells` are not touched here
            self.assertEqual(done["misc.spelldescstr"], 1)
            self.assertEqual(done["itemstatcost.descfunc"], 1)

    def test_docs_table(self):
        text = string_gaps.docs_table()
        self.assertIn("shrines.StringName / StringPhrase", text)
        self.assertIn("`Pandora`", text)
        self.assertIn("itemstatcost.descstrneg / descstrpos", text)


if __name__ == "__main__":
    unittest.main()
