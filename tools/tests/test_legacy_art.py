"""Unit tests of tools/legacy_art.py on synthetic data (no game files). Run: py -3 -I -m unittest discover -s tools/tests -p "test_legacy_art.py" """
import struct
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import projtemp  # noqa: E402,F401  (temp files stay inside the project, tools/projtemp.py)
import dc6  # noqa: E402
import legacy_art as la  # noqa: E402
from test_icons import block, solid, write_tsv  # noqa: E402

PAL = [(i, 255 - i, i // 2) for i in range(256)]


def cof(frames: int, layers: list[tuple[int, str]], dirs: int = 8) -> bytes:
    head = bytes([len(layers), frames, dirs]) + bytes(25)
    body = b"".join(bytes([c, 0, 0, 0, 0]) + wc.encode().ljust(4, b"\0") for c, wc in layers)
    return head + body + bytes(frames) + bytes(frames * dirs * len(layers))


def dcc(dirs: int = 8, frames: int = 4) -> bytes:
    return bytes([0x74, 6, dirs]) + struct.pack("<I", frames) + bytes(8)


def animdata(records: dict[str, int]) -> bytes:
    buckets = [[] for _ in range(256)]
    for name, frames in records.items():
        buckets[sum(name.encode()) & 0xFF].append(name)
    out = bytearray()
    for names in buckets:
        out += struct.pack("<I", len(names))
        for n in names:
            out += n.encode().ljust(8, b"\0") + struct.pack("<I", frames_of(records, n)) + bytes(148)
    return bytes(out)


def frames_of(records, n):
    return records[n]


def put(root: Path, rel: str, data: bytes) -> Path:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(data)
    return p


class FormatTests(unittest.TestCase):
    def test_cof(self):
        c = la.parse_cof(cof(9, [(0, "hth"), (2, "hth")]))
        self.assertEqual(c["frames"], 9)
        self.assertEqual(c["layers"], [("hd", "hth"), ("lg", "hth")])
        with self.assertRaises(ValueError):
            la.parse_cof(cof(9, [(0, "hth")])[:-1])
        with self.assertRaises(ValueError):
            la.parse_cof(cof(9, [(40, "hth")]))

    def test_dcc(self):
        self.assertEqual(la.parse_dcc(dcc(8, 12)), {"dirs": 8, "frames": 12})
        with self.assertRaises(ValueError):
            la.parse_dcc(b"\x00" * 20)

    def test_animdata_roundtrip(self):
        self.assertEqual(la.anim_frames(animdata({"A1NUHTH": 12, "ZZNUHTH": 3})), {"A1NUHTH": 12, "ZZNUHTH": 3})

    def test_classify(self):
        self.assertEqual(la.classify("global/items/inv_foo.dc6"), ("item", None))
        self.assertEqual(la.classify("global/ui/panel/invchar6.dc6"), ("panel", None))
        self.assertEqual(la.classify("global/ui/spells/skltree_ama_back.dc6"), ("skilltree", None))
        self.assertEqual(la.classify("global/ui/spells/amaskillicon.dc6"), ("skillicon", None))
        self.assertIsNotNone(la.classify("global/ui/panel/tradestash.dc6")[1])
        self.assertIsNotNone(la.classify("global/ui/frontend/title.dc6")[1])
        self.assertIsNotNone(la.classify("global/tiles/act1/town/floor.dt1")[1])
        self.assertIsNotNone(la.classify("global/animdata.d2")[1])
        self.assertEqual(la.classify("global/monsters/a1/cof/a1nuhth.cof"), ("monster", None))
        self.assertEqual(la.classify("global/excel/skills.txt")[0], "table")
        self.assertEqual(la.classify("global/weird/new.dc6")[0], "unclassified")


class RemapTests(unittest.TestCase):
    def test_hist_and_remap_keep_the_structure(self):
        pal = [(0, 0, 0)] + [(i, i, i) for i in range(1, 224)] + [(250, 250, 250)] * 0 + [(0, 0, 0)] * 32
        pal = pal[:256]
        for i in range(225, 255):
            pal[i] = (255, 0, 255)
        pal[224] = (10, 10, 10)
        pal[7] = (255, 0, 250)  # the nearest colour of the pink indices
        data = dc6.build_dc6([(3, 2, 0, 0, block([[5, None, 230], [240, 254, 1]])), solid(2, 2, 100)])
        self.assertEqual(sum(v for k, v in la.dc6_index_hist(data).items() if k in la.HAZARD), 3)
        m = la.nearest_map(pal)
        self.assertEqual(set(m), set(la.HAZARD))
        self.assertTrue(all(1 <= v <= 224 for v in m.values()))
        self.assertEqual(m[230], 7)
        out = la.remap_dc6(data, m)
        self.assertEqual(len(out), len(data))
        self.assertEqual(sum(v for k, v in la.dc6_index_hist(out).items() if k in la.HAZARD), 0)
        f0, f1 = dc6.parse_dc6(out)
        self.assertEqual(f0[:4], (3, 2, 0, 0))
        self.assertEqual(f1, solid(2, 2, 100))
        self.assertEqual(la.dc6_index_hist(out)[7], 3)
        self.assertEqual(la.dc6_index_hist(out)[5], 1)  # untouched pixels stay


class PlanTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        t = Path(self.tmp.name)
        self.med, self.base, self.out = t / "median" / "data", t / "d2r", t / "out"
        (self.base / "data").mkdir(parents=True)
        (self.out / "global").mkdir(parents=True)

    def d2r(self, files: dict[str, bytes]) -> la.D2R:
        for rel, b in files.items():
            put(self.base / "data", rel, b)
        return la.D2R(self.base)

    def test_new_and_shared_files(self):
        put(self.med, "global/items/inv_new.dc6", dc6.build_dc6([solid(2, 2, 1)]))
        put(self.med, "global/items/inv_same.dc6", dc6.build_dc6([solid(2, 2, 2)]))
        put(self.med, "global/items/inv_diff.dc6", dc6.build_dc6([solid(2, 2, 3)]))
        put(self.med, "global/ui/panel/tradestash.dc6", b"x")
        put(self.med, "global/excel/skills.txt", b"x")
        d2r = self.d2r({"global/items/inv_same.dc6": dc6.build_dc6([solid(2, 2, 2)]),
                        "global/items/inv_diff.dc6": dc6.build_dc6([solid(2, 2, 9)])})
        plan = la.plan_art(self.med, d2r, self.out)
        got = {e.rel: (e.action, e.why) for e in plan.entries}
        self.assertEqual(got["global/items/inv_new.dc6"], ("copy", "new"))
        self.assertEqual(got["global/items/inv_same.dc6"], ("skip", "same-as-d2r"))
        self.assertEqual(got["global/items/inv_diff.dc6"], ("copy", "median-wins"))
        self.assertEqual(got["global/ui/panel/tradestash.dc6"][0], "skip")
        self.assertEqual(got["global/excel/skills.txt"][0], "skip")

    def test_paired_shared_sheet_replaces_medians(self):
        """tools/shared_icons.py writes <out>/../shared_icons/skillicon.dc6: the classic shared sheet in pairs is shipped
        instead of Median's one-frame-per-icon sheet (the rewritten skilldesc cels name its frames)."""
        put(self.med, "global/ui/spells/skillicon.dc6", dc6.build_dc6([solid(2, 2, 1)]))
        put(self.med, "global/ui/spells/amskillicon.dc6", dc6.build_dc6([solid(2, 2, 2)]))
        d2r = self.d2r({"global/ui/spells/skillicon.dc6": dc6.build_dc6([solid(2, 2, 1)])})   # same as Median's: no copy
        self.assertEqual({e.rel: e.action for e in la.plan_art(self.med, d2r, self.out).entries}["global/ui/spells/skillicon.dc6"],
                         "skip")
        paired = put(self.out.parent, "shared_icons/skillicon.dc6", dc6.build_dc6([solid(2, 2, 1)] * 2))
        plan = la.plan_art(self.med, d2r, self.out)
        got = {e.rel: e for e in plan.entries}
        e = got["global/ui/spells/skillicon.dc6"]
        self.assertEqual((e.action, e.why, e.src), ("copy", "paired", paired))
        self.assertEqual(got["global/ui/spells/amskillicon.dc6"].why, "new")
        la.copy_plan(plan, self.out)
        self.assertEqual((self.out / "global/ui/spells/skillicon.dc6").read_bytes(), paired.read_bytes())

    def test_shared_monster_token_follows_animdata(self):
        put(self.med, "global/animdata.d2", animdata({"E9NUHTH": 13, "FMNUHTH": 8}))  # D2R's record wins where it has one
        for tok, f in (("e9", 13), ("fm", 8)):
            put(self.med, f"global/monsters/{tok}/cof/{tok}nuhth.cof", cof(f, [(0, "hth")]))
            put(self.med, f"global/monsters/{tok}/hd/{tok}hdlitnuhth.dcc", dcc())
        d2r = self.d2r({"global/animdata.d2": animdata({"E9NUHTH": 2, "FMNUHTH": 8}),
                        "global/monsters/e9/cof/e9nuhth.cof": cof(2, [(0, "hth")]),
                        "global/monsters/e9/hd/e9hdlitnuhth.dcc": dcc(8, 1),
                        "global/monsters/fm/cof/fmnuhth.cof": cof(8, [(0, "hth")], 4),
                        "global/monsters/fm/hd/fmhdlitnuhth.dcc": dcc(4, 1)})
        plan = la.plan_art(self.med, d2r, None)
        self.assertFalse(plan.tokens["e9"]["median_wins"])
        self.assertTrue(plan.tokens["fm"]["median_wins"])
        got = {e.rel: e.action for e in plan.entries}
        self.assertEqual(got["global/monsters/e9/cof/e9nuhth.cof"], "skip")
        self.assertEqual(got["global/monsters/fm/cof/fmnuhth.cof"], "copy")
        self.assertEqual(got["global/monsters/fm/hd/fmhdlitnuhth.dcc"], "copy")

    def test_files_of_an_own_token_are_left_out_of_the_old_one(self):
        """Slayer e9 -> KS (tools/own_tokens.py): Median's e9 files are shipped under ks/, not on top of D2R's trap."""
        import own_tokens
        put(self.med, "global/monsters/e9/cof/e9nuhth.cof", cof(13, [(0, "hth")]))
        put(self.med, "global/monsters/e9/hd/e9hdlitnuhth.dcc", dcc())
        put(self.med, "global/monsters/fm/cof/fmnuhth.cof", cof(8, [(0, "hth")]))
        own = own_tokens.Plan(moved={"e9/cof/e9nuhth.cof": "ks/cof/ksnuhth.cof", "e9/hd/e9hdlitnuhth.dcc": "ks/hd/kshdlitnuhth.dcc"})
        plan = la.plan_art(self.med, self.d2r({}), None, own)
        got = {e.rel: (e.action, e.why) for e in plan.entries}
        self.assertEqual(got["global/monsters/e9/cof/e9nuhth.cof"], ("skip", "moved to ks"))
        self.assertEqual(got["global/monsters/e9/hd/e9hdlitnuhth.dcc"], ("skip", "moved to ks"))
        self.assertEqual(got["global/monsters/fm/cof/fmnuhth.cof"][0], "copy")   # other tokens are untouched
        self.assertNotIn("e9", plan.tokens)

    def test_pink_counted_and_copy_remaps(self):
        pal = [(i, i, i) for i in range(256)]
        put(self.med, "global/items/inv_pink.dc6", dc6.build_dc6([(2, 1, 0, 0, block([[230, 4]]))]))
        plan = la.plan_art(self.med, self.d2r({}), self.out)
        (e,) = plan.shipped()
        self.assertEqual(e.pink, 1)
        n = la.copy_plan(plan, self.out / "data", la.nearest_map(pal))
        self.assertEqual(n, 1)
        written = (self.out / "data" / e.rel).read_bytes()
        self.assertEqual(sum(v for k, v in la.dc6_index_hist(written).items() if k in la.HAZARD), 0)
        self.assertEqual(la.copy_plan(plan, self.out / "data", la.nearest_map(pal)), 0)  # second run changes nothing
        # without a palette the file is copied as it is, and check says so
        n = la.copy_plan(plan, self.out / "raw", None)
        self.assertEqual((self.out / "raw" / e.rel).read_bytes(), e.src.read_bytes())
        res = la.check_art(plan, self.med, self.d2r({}), self.out, None)
        self.assertTrue(any("225-254" in w for w in res["warnings"]))
        res = la.check_art(plan, self.med, self.d2r({}), self.out, la.nearest_map(pal))
        self.assertFalse(any("225-254" in w for w in res["warnings"]))
        self.assertEqual(res["stats"]["remapped"], 1)


class CompletenessTests(unittest.TestCase):
    HEAD1 = ["Id", "Code", "MonStatsEx"]
    HEAD2 = ["Id", "mDT", "mNU", "mWL", "mKB", "BaseW", "HD", "HDv", "TR", "TRv", "Rav", "RA", "LG", "LGv"]

    def run_check(self, ms2rows: list[list[str]], view: set[str], layers: list[tuple[int, str]]):
        with tempfile.TemporaryDirectory() as d:
            med = Path(d)
            write_tsv(med / "global/excel/monstats.txt", self.HEAD1, [["one", "aa", "one"], ["two", "bb", "two"], ["three", "cc", "three"]])
            write_tsv(med / "global/excel/monstats2.txt", self.HEAD2, ms2rows)
            data = cof(4, layers)
            return la.monster_completeness(med, view, lambda rel: data)

    def test_complete_incomplete_and_empty(self):
        view = {"global/monsters/aa/cof/aadthth.cof", "global/monsters/aa/cof/aanuhth.cof",
                "global/monsters/aa/hd/aahdlitdthth.dcc", "global/monsters/aa/hd/aahdlitnuhth.dcc",
                "global/monsters/aa/hd/aahdredanuhth.dcc",
                "global/monsters/bb/cof/bbdthth.cof"}  # bb: no head files; cc: nothing at all
        rows = [["one", "1", "1", "0", "1", "hth", "1", "lit,reda", "0", "", "", "", "", ""],
                ["two", "1", "0", "0", "0", "hth", "1", "lit", "0", "", "", "", "", ""],
                ["three", "1", "0", "0", "0", "hth", "0", "", "0", "", "", "", "", ""]]
        n, problems = self.run_check(rows, view, [(0, "hth")])
        # one: mDT + mNU have COFs (mKB is not a required mode); heads: lit + reda for both modes, but redadt is missing
        self.assertEqual(n["incomplete"], 2)
        self.assertEqual(n["no art anywhere"], 1)
        self.assertTrue(any("aahdredadthth" in p for p in problems))
        self.assertTrue(any(p.startswith("bb|") for p in problems))

    def test_nil_variant_and_part_flag(self):
        view = {"global/monsters/aa/cof/aadthth.cof", "global/monsters/aa/hd/aahdlitdthth.dcc"}
        # HDv "lit,nil": nil needs no file; TR flag 0: a trunk layer in the COF is ignored
        rows = [["one", "1", "0", "0", "0", "hth", "1", "lit,nil", "0", "x", "", "", "", ""]]
        n, problems = self.run_check(rows, view, [(0, "hth"), (1, "hth")])
        self.assertEqual((n["complete"], n["incomplete"]), (1, 0), problems)


if __name__ == "__main__":
    unittest.main()
