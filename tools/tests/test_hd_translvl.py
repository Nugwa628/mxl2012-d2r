"""Unit tests of tools/hd_translvl.py (per-TransLvl colours of D2R HD units) on synthetic data (no game or Median files).
Run: py -3 -I -m unittest discover -s tools/tests -p "test_hd_translvl.py" """
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import projtemp  # noqa: E402,F401  (temp files stay inside the project, tools/projtemp.py)
import hd_translvl as t  # noqa: E402

ZERO = {"x": 0.0, "y": 0.0, "z": 0.0, "w": 0.0}


def transform(name, adj=(0.0, 0.0, 0.0, 1.0), tint=(0.0, 0.0, 0.0, 0.0)):
    return {"type": "ColorTransform", "name": name, "colorAdjustment": dict(zip("xyzw", adj)),
            "hueAdjustment0": dict(ZERO), "hueAdjustment1": dict(ZERO), "satAdjustment0": dict(ZERO),
            "satAdjustment1": dict(ZERO), "colorTint": dict(zip("xyzw", tint))}


def table(coloured: dict[int, tuple] | None = None) -> dict:
    """An 8-entry D2R-style variant table; `coloured` {entry index: colorAdjustment} for authored levels."""
    names = ["cold", "poison", "level0", "level1", "level2", "level3", "level4", "misc"]
    entries = []
    for i, n in enumerate(names):
        adj = (coloured or {}).get(i, (0.0, 0.0, 0.0, 1.0))
        entries.append({"type": "VariantColorTransform", "name": n,
                        "transforms": [transform(f"{c}{i:03d}", adj) for c in ("Red", "Green", "Blue")]})
    return {"dependencies": {"particles": []}, "type": "VariantTransformTable", "name": "x_VariantTransformTable",
            "entries": entries, "customColorShiftEntries": []}


def tsv(path: Path, head: list[str], rows: list[list[str]]):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join("\t".join(r) for r in [head, *rows]) + "\n", encoding="latin-1")


class Entries(unittest.TestCase):
    def test_identity(self):
        self.assertTrue(t.entry_identity(table()["entries"][3]))
        self.assertFalse(t.entry_identity(table({3: (0.5, 0.0, 0.0, 1.0)})["entries"][3]))
        e = table()["entries"][3]
        e["transforms"][1]["colorTint"]["w"] = 0.4
        self.assertFalse(t.entry_identity(e))
        e = table()["entries"][3]
        e["transforms"][2]["satAdjustment0"]["x"] = 1.0
        self.assertFalse(t.entry_identity(e))

    def test_fill_adds_to_level0_and_wraps_hue(self):
        v = table({2: (0.9, 0.5, -0.8, 1.0)})
        e = t.fill_entry(v["entries"][5], v["entries"][2], [0.2, 0.7, -0.5, 1.0], [0.0, 0.0, 0.0, 0.0])
        a = e["transforms"][0]["colorAdjustment"]
        self.assertAlmostEqual(a["x"], 0.1)          # 0.9 + 0.2 turns
        self.assertEqual((a["y"], a["z"], a["w"]), (1.0, -1.0, 1.0))   # clipped to [-1, 1]
        self.assertEqual(e["name"], "level3")        # the entry keeps its name and its 3 masks
        self.assertEqual(len(e["transforms"]), 3)

    def test_fill_tint_wins_only_when_it_has_an_amount(self):
        v = table()
        v["entries"][2]["transforms"][0]["colorTint"] = {"x": 0.3882353, "y": 1.0, "z": 0.0, "w": 0.5}
        keep = t.fill_entry(v["entries"][4], v["entries"][2], [0.1, 0.0, 0.0, 1.0], [0.0, 0.0, 0.0, 0.0])
        self.assertEqual(keep["transforms"][0]["colorTint"], {"x": 0.39, "y": 1.0, "z": 0.0, "w": 0.5})  # rounded copy
        own = t.fill_entry(v["entries"][4], v["entries"][2], [0.1, 0.0, 0.0, 1.0], [1.0, 0.0, 0.0, 0.4])
        self.assertEqual(own["transforms"][0]["colorTint"], {"x": 1.0, "y": 0.0, "z": 0.0, "w": 0.4})

    def test_fit_shortens_names_then_rounds_then_gives_up(self):
        v = table()
        v["entries"][5] = t.fill_entry(v["entries"][5], v["entries"][2], [0.33, -0.27, -0.13, 1.0], [0.0] * 4)
        full = len(t.dump(v))
        self.assertEqual(len(t.fit(json.loads(json.dumps(v)), [5], full)), full)
        short = t.fit(json.loads(json.dumps(v)), [5], full - 1)
        self.assertLess(len(short), full)
        self.assertIn(b'"name":"L3R"', short)
        rounded = t.fit(json.loads(json.dumps(v)), [5], len(short) - 1)
        self.assertIsNotNone(rounded)
        self.assertIn(b'"x":0.3', rounded)
        self.assertIsNone(t.fit(json.loads(json.dumps(v)), [5], 100))


class Colour(unittest.TestCase):
    PAL = [(0, 0, 0)] * 256

    def setUp(self):
        self.pal = list(self.PAL)
        self.pal[10] = (200, 30, 30)    # red
        self.pal[20] = (30, 30, 200)    # blue
        self.pal[30] = (190, 40, 35)    # nearly the same red

    def test_level_shift_turns_red_to_blue(self):
        hist = [0] * 256
        hist[10] = 100
        shift = list(range(256))
        shift[10] = 20
        adj, tint, label = t.level_shift(hist, self.pal, shift)
        self.assertNotEqual(label, "none")
        self.assertGreater(adj[0], 0.5)            # hue turns about 2/3 (red -> blue)
        self.assertEqual(adj[3], 1.0)

    def test_level_shift_is_relative_to_level0(self):
        hist = [0] * 256
        hist[10] = 100
        same = list(range(256))
        same[10] = 20
        self.assertEqual(t.level_shift(hist, self.pal, same, same)[2], "none")   # level 0 already blue: no change

    def test_small_shift_is_none(self):
        hist = [0] * 256
        hist[10] = 100
        shift = list(range(256))
        shift[10] = 30
        self.assertEqual(t.level_shift(hist, self.pal, shift)[2], "none")


class PlanAndBuild(unittest.TestCase):
    """A D2R tree with one unit `rat1` (token `rt`, palshift red -> blue) and the build's monstats on it."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        r = Path(self.tmp.name)
        self.d2r, self.mod = r / "d2r", r / "mod"
        hd_ = self.d2r / "data" / "hd" / "character"
        (hd_ / "enemy" / "rat1").mkdir(parents=True)
        (hd_ / "monsters.json").write_text(json.dumps({"rat1": "rat1", "rat2": "rat1", "rat4": "rat1"}), "utf-8")
        v = table({3: (0.5, 0.0, 0.0, 1.0)})   # D2R authored level 1 only
        self.src = hd_ / "enemy" / "rat1" / "rat1_variant.json"
        self.src.write_text(json.dumps(v, indent=1), "utf-8")   # pretty: room to grow
        ex = self.d2r / "data" / "global" / "excel"
        tsv(ex / "monstats.txt", ["Id", "Code", "TransLvl"], [["rat1", "RT", "0"], ["rat2", "RT", "1"], ["rat4", "RT", "3"]])
        shift = bytearray(range(256)) * 8
        shift[(3 + 2) * 256 + 10] = 20   # TransLvl 3 draws through table 5
        cof = self.d2r / "data" / "global" / "monsters" / "rt" / "cof"
        cof.mkdir(parents=True)
        (cof / "palshift.dat").write_bytes(bytes(shift))
        mx = self.mod / "data" / "global" / "excel"
        tsv(mx / "monstats.txt", ["Id", "Code", "TransLvl", "MonStatsEx"],
            [["rat1", "RT", "0", "rat1"], ["rat2", "RT", "1", "rat1"], ["bigrat", "RT", "2", "rat1"],
             ["hugerat", "RT", "4", "rat1"], ["ghostrat", "RT", "7", "rat1"], ["mine", "XX", "3", "mine"]])
        self.mj = {"rat1": "rat1", "rat2": "rat1", "bigrat": "rat1", "hugerat": "rat1", "ghostrat": "rat1",
                   "mine": "mxl_rat1_abc"}

    def tearDown(self):
        self.tmp.cleanup()

    def test_states(self):
        p = t.plan(self.mod / "data" / "global" / "excel", self.mj, self.d2r)
        st = {tl: e["state"] for tl, e in p["rat1"].items()}
        self.assertEqual(st, {1: "D2R colour", 2: "fill", 4: "fill", 7: "no entry"})
        self.assertNotIn("mxl_rat1_abc", p)        # stand-ins draw Median's own tokens: not this step's
        self.assertEqual(p["rat1"][2]["ids"], ["bigrat"])
        self.assertFalse(p["rat1"][2]["d2r_uses"])

    def test_d2r_levels_can_be_kept(self):
        # rat4 makes level 3 a D2R level; hugerat (4) stays a Median-only level
        self.mj["rat4"] = "rat1"
        tsv(self.mod / "data" / "global" / "excel" / "monstats.txt", ["Id", "Code", "TransLvl", "MonStatsEx"],
            [["rat4", "RT", "3", "rat1"], ["hugerat", "RT", "4", "rat1"]])
        p = t.plan(self.mod / "data" / "global" / "excel", self.mj, self.d2r)
        self.assertEqual(p["rat1"][3]["state"], "fill")
        p = t.plan(self.mod / "data" / "global" / "excel", self.mj, self.d2r, keep_d2r_levels=True)
        self.assertEqual(p["rat1"][3]["state"], "D2R identity")
        self.assertEqual(p["rat1"][4]["state"], "fill")

    def test_no_palshift(self):
        (self.d2r / "data" / "global" / "monsters" / "rt" / "cof" / "palshift.dat").unlink()
        p = t.plan(self.mod / "data" / "global" / "excel", self.mj, self.d2r)
        self.assertEqual(p["rat1"][2]["state"], "no palshift")

    def test_build_writes_a_table_no_larger_than_d2r(self):
        p = t.plan(self.mod / "data" / "global" / "excel", self.mj, self.d2r)
        p["rat1"][2].update(adj=[0.66, 0.0, 0.0, 1.0], tint=[0.0] * 4, label="hue +0.66")
        p["rat1"][4].update(state="below threshold")
        done = t.build_tables(p, self.d2r, self.mod / "data")
        out = self.mod / "data" / "hd" / "character" / "enemy" / "rat1" / "rat1_variant.json"
        self.assertTrue(out.exists())
        self.assertLessEqual(out.stat().st_size, self.src.stat().st_size)
        self.assertEqual(done["rat1"][2], [2])
        v = json.loads(out.read_text("utf-8"))
        self.assertAlmostEqual(v["entries"][4]["transforms"][0]["colorAdjustment"]["x"], 0.66)
        self.assertTrue(t.entry_identity(v["entries"][6]))            # level 4 below threshold: untouched
        self.assertEqual(v["entries"][3], table({3: (0.5, 0.0, 0.0, 1.0)})["entries"][3])  # D2R's level 1 kept
        self.assertEqual(p["rat1"][2]["state"], "filled")
        self.assertIn("| filled | 1 | 1 |", t.report(p, done))

    def test_build_deletes_tables_of_an_earlier_run(self):
        enemy = self.mod / "data" / "hd" / "character" / "enemy"
        old = enemy / "oldunit" / "oldunit_variant.json"
        ours = enemy / "mxl" / "mxl_variant.json"     # hd_monsters.py's folder: not this step's
        for f in (old, ours):
            f.parent.mkdir(parents=True, exist_ok=True)
            f.write_text("{}", "utf-8")
        t.build_tables({}, self.d2r, self.mod / "data")
        self.assertFalse(old.exists())
        self.assertTrue(ours.exists())

    def test_build_skips_a_table_that_would_grow(self):
        p = t.plan(self.mod / "data" / "global" / "excel", self.mj, self.d2r)
        for tl in (2, 4):
            p["rat1"][tl].update(adj=[0.33, -0.25, -0.15, 1.0], tint=[0.9, 0.1, 0.1, 0.45], label="x")
        real = t.fit
        t.fit = lambda table, filled, limit: None   # nothing fits
        try:
            done = t.build_tables(p, self.d2r, self.mod / "data")
        finally:
            t.fit = real
        self.assertEqual(done, {})
        self.assertFalse((self.mod / "data" / "hd" / "character" / "enemy" / "rat1" / "rat1_variant.json").exists())
        self.assertEqual({p["rat1"][2]["state"], p["rat1"][4]["state"]}, {"too large"})


if __name__ == "__main__":
    unittest.main()
