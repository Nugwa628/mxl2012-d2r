"""Unit tests of tools/own_tokens.py on synthetic data (no game files).
Run: py -3 -I -m unittest discover -s tools/tests -p "test_own_tokens.py" """
import struct
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import projtemp  # noqa: E402,F401  (temp files stay inside the project, tools/projtemp.py)
import own_tokens as ot  # noqa: E402
from txt_migrate import read_tsv  # noqa: E402

HD, TR, RH = 0, 1, 5      # composite ids in a COF (own_tokens.COMPS)


def cof(frames: int, layers: list[tuple[int, str]], dirs: int = 2, prio: bytes | None = None) -> bytes:
    n = len(layers)
    head = bytes([n, frames, dirs]) + bytes(25)
    body = b"".join(bytes([c, 0, 0, 0, 0]) + wc.encode().ljust(4, b"\0") for c, wc in layers)
    order = prio if prio is not None else bytes(c for c, _ in layers) * (frames * dirs)
    return head + body + bytes(frames) + order


def dcc(frames: int = 4) -> bytes:
    return bytes([0x74, 6, 2]) + struct.pack("<I", frames) + bytes(8)


def tsv(*rows):
    return "\r\n".join("\t".join(r) for r in rows) + "\r\n"


def put(root: Path, rel: str, data: bytes) -> Path:
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(data)
    return p


SPLIT = {"mode": "split", "old": "e9", "new": "KS", "rows": ["slayer"], "why": "t"}
BORROW = {"mode": "borrow", "old": "cr", "new": "HN", "donor": "archer", "weapons": ["bow"], "rows": ["haunt"], "why": "t"}
COMPLETE = {"mode": "complete", "token": "hg", "rows": ["horned"], "drop_missing_layers": True, "why": "t"}

MS = ["Id", "*hcIdx", "Code", "MonStatsEx"]
MS2 = ["Id", "BaseW", "TR", "TRv", "RH", "RHv", "mDT", "mNU", "mGH"]


class TableTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.excel = Path(self.temp.name) / "excel"
        for bank in ("base", ""):
            d = self.excel / bank
            d.mkdir(parents=True, exist_ok=True)
            (d / "monstats.txt").write_text(tsv(MS, ["slayer", "1", "e9", "slayer"], ["trap", "2", "e9", "trap"],
                                                ["horned", "3", "HG", "horned"], ["Expansion", "", "", ""]), encoding="utf-8")
            (d / "monstats2.txt").write_text(tsv(MS2, ["slayer", "hth", "1", "lit", "0", "", "1", "1", "0"],
                                                 ["trap", "hth", "1", "lit", "0", "", "1", "1", "0"],
                                                 ["horned", "hth", "1", "lit", "1", "lit", "1", "1", "1"],
                                                 ["Expansion", "", "", "", "", "", "", "", ""]), encoding="utf-8")

    def test_row_token(self):
        self.assertEqual(ot.row_token("slayer", "e9", [SPLIT]), "KS")
        self.assertEqual(ot.row_token("Slayer", "E9", [SPLIT]), "KS")
        self.assertEqual(ot.row_token("trap", "e9", [SPLIT]), "e9")        # not a listed row
        self.assertEqual(ot.row_token("slayer", "zz", [SPLIT]), "zz")      # listed row, but another code: untouched

    def test_apply_tables_both_banks(self):
        lines = ot.apply_tables(self.excel, [SPLIT])
        self.assertEqual(len(lines), 2)
        for bank in ("base", ""):
            _, rows = read_tsv(self.excel / bank / "monstats.txt")
            codes = {r[0]: r[2] for r in rows}
            self.assertEqual((codes["slayer"], codes["trap"]), ("KS", "e9"))
        self.assertEqual(ot.apply_tables(self.excel, [SPLIT])[0].count("slayer"), 0)   # second run: nothing left to rewrite

    def test_missing_row_is_an_error(self):
        with self.assertRaises(SystemExit):
            ot.apply_tables(self.excel, [{**SPLIT, "rows": ["nobody"]}])


class CofTests(unittest.TestCase):
    def test_parse(self):
        c = ot.parse_cof(cof(3, [(TR, "hth"), (RH, "1hs")]))
        self.assertEqual((c["frames"], c["dirs"], c["layers"]), (3, 2, [("tr", "hth"), ("rh", "1hs")]))
        with self.assertRaises(ValueError):
            ot.parse_cof(cof(3, [(TR, "hth")])[:-1])

    def test_drop_layers_removes_record_and_priority_bytes(self):
        two = cof(3, [(TR, "hth"), (RH, "hth")])
        one = ot.drop_layers(two, {"rh"})
        self.assertEqual(one, cof(3, [(TR, "hth")]))
        self.assertEqual(ot.drop_layers(two, {"hd"}), two)                  # not in the COF: unchanged
        self.assertEqual(ot.drop_layers(cof(3, [(RH, "hth")]), {"rh"}), cof(3, [(RH, "hth")]))   # never empties a COF


class PlanTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        t = Path(self.temp.name)
        self.med, self.d2r, self.out, self.excel = t / "med", t / "d2r", t / "out", t / "excel"
        for bank in ("base", ""):
            (self.excel / bank).mkdir(parents=True, exist_ok=True)

    def tables(self, *ms2_rows, ms_rows):
        for bank in ("base", ""):
            (self.excel / bank / "monstats.txt").write_text(tsv(MS, *ms_rows), encoding="utf-8")
            (self.excel / bank / "monstats2.txt").write_text(tsv(MS2, *ms2_rows), encoding="utf-8")

    def plan(self, *entries):
        return ot.make_plan(list(entries), self.med, self.d2r, self.excel)

    def test_split_renames_median_files_and_fills_from_d2r(self):
        put(self.med, "e9/cof/e9nuhth.cof", cof(13, [(TR, "hth")]))
        put(self.med, "e9/tr/e9trlitnuhth.dcc", dcc(13))
        put(self.d2r, "e9/cof/e9nuhth.cof", cof(2, [(TR, "hth")]))          # D2R's trap: Median's wins
        put(self.d2r, "e9/cof/e9a1hth.cof", cof(15, [(TR, "hth")]))         # a mode Median ships nothing for
        plan = self.plan(SPLIT)
        self.assertEqual(sorted(plan.ops), ["ks/cof/ksa1hth.cof", "ks/cof/ksnuhth.cof", "ks/tr/kstrlitnuhth.dcc"])
        self.assertEqual(plan.ops["ks/cof/ksnuhth.cof"].origin, "median")
        self.assertEqual(plan.ops["ks/cof/ksa1hth.cof"].origin, "d2r")
        self.assertEqual(plan.ops["ks/cof/ksnuhth.cof"].read(), cof(13, [(TR, "hth")]))
        self.assertEqual(plan.moved, {"e9/cof/e9nuhth.cof": "ks/cof/ksnuhth.cof", "e9/tr/e9trlitnuhth.dcc": "ks/tr/kstrlitnuhth.dcc"})
        anims = {a.name: (a.source, a.frames) for a in plan.anims}
        self.assertEqual(anims, {"KSNUHTH": ("E9NUHTH", 13), "KSA1HTH": ("E9A1HTH", 15)})
        self.assertEqual(ot.cof_stems(plan), {"ksnuhth", "ksa1hth"})
        self.assertEqual(set(ot.virtual_index(plan)), set(plan.ops))

    def test_complete_derives_missing_mode_and_drops_missing_layer(self):
        self.tables(["horned", "hth", "1", "lit", "1", "lit", "1", "1", "1"], ["Expansion"] + [""] * 8,
                    ms_rows=[["horned", "3", "hg", "horned"], ["Expansion", "", "", ""]])
        put(self.med, "hg/cof/hgnuhth.cof", cof(8, [(TR, "hth"), (RH, "hth")]))
        put(self.med, "hg/cof/hgghhth.cof", cof(5, [(TR, "hth")]))
        put(self.med, "hg/tr/hgtrlitnuhth.dcc", dcc(8))
        put(self.med, "hg/tr/hgtrlitghhth.dcc", dcc(5))
        plan = self.plan(COMPLETE)
        # mDT asks for a COF Median ships none of: the death COF comes from the other death mode, else nothing to derive from
        self.assertNotIn("hg/cof/hgdthth.cof", plan.ops)
        # the right-hand layer has no DCC in any look: dropped from the NU COF
        self.assertEqual(plan.ops["hg/cof/hgnuhth.cof"].read(), cof(8, [(TR, "hth")]))
        self.assertTrue(any("layer rh dropped" in n for n in plan.notes))

    def test_complete_copies_a_neighbouring_mode(self):
        self.tables(["horned", "hth", "1", "lit", "0", "", "1", "1", "1"], ["Expansion"] + [""] * 8,
                    ms_rows=[["horned", "3", "hg", "horned"], ["Expansion", "", "", ""]])
        put(self.med, "hg/cof/hgnuhth.cof", cof(8, [(TR, "hth")]))
        put(self.med, "hg/cof/hgddhth.cof", cof(9, [(TR, "hth")]))
        put(self.med, "hg/tr/hgtrlitnuhth.dcc", dcc(8))
        put(self.med, "hg/tr/hgtrlitddhth.dcc", dcc(9))
        plan = self.plan(COMPLETE)
        self.assertEqual(plan.ops["hg/cof/hgdthth.cof"].origin, "derived: DD COF")          # DT <- DD
        self.assertEqual(plan.ops["hg/tr/hgtrlitdthth.dcc"].origin, "derived: DD DCC")      # the DCC follows under the DT name
        self.assertEqual(plan.ops["hg/cof/hgghhth.cof"].origin, "derived: NU COF")          # GH <- NU
        self.assertIn(("HGDTHTH", "HGDDHTH", 9), {(a.name, a.source, a.frames) for a in plan.anims})
        self.assertEqual({a.table for a in plan.anims}, {"merged"})

    def test_borrow_copies_the_donor_weapon_class_and_fills_the_rows_modes(self):
        # the row (after the tables step) asks for NU and GH with the donor's bow; D2R's CR has NU only, for bow and 1hs;
        # the variant cell is quoted as in D2R's own monstats2
        self.tables(["haunt", "bow", "1", '"lit,med"', "0", "", "0", "1", "1"], ["Expansion"] + [""] * 8,
                    ms_rows=[["haunt", "5", "HN", "haunt"], ["Expansion", "", "", ""]])
        put(self.d2r, "cr/cof/crnubow.cof", cof(8, [(TR, "lit")]))
        put(self.d2r, "cr/cof/crnu1hs.cof", cof(8, [(TR, "1hs")]))
        for v in ("lit", "med"):
            put(self.d2r, f"cr/tr/crtr{v}nulit.dcc", dcc(8))
        put(self.d2r, "cr/tr/crtrlitnu1hs.dcc", dcc(8))
        plan = self.plan(BORROW)
        self.assertEqual(plan.ops["hn/cof/hnnubow.cof"].origin, "d2r")
        self.assertNotIn("hn/cof/hnnu1hs.cof", plan.ops)                         # another weapon class: not copied
        self.assertNotIn("hn/tr/hntrlitnu1hs.dcc", plan.ops)
        self.assertEqual(plan.ops["hn/tr/hntrmednulit.dcc"].origin, "d2r")
        self.assertEqual(plan.ops["hn/cof/hnghbow.cof"].origin, "derived: NU COF")        # GH <- NU
        self.assertEqual({r for r in plan.ops if r.startswith("hn/tr/") and "gh" in r},
                         {"hn/tr/hntrlitghlit.dcc", "hn/tr/hntrmedghlit.dcc"})          # both looks of the quoted cell
        self.assertIn(("HNNUBOW", "CRNUBOW", 8), {(a.name, a.source, a.frames) for a in plan.anims})
        self.assertEqual(ot.row_token("haunt", "AM", [BORROW]), "HN")

    def test_borrow_tables_take_the_donor_row_and_keep_the_rows_modes(self):
        d2r_excel = Path(self.temp.name) / "d2rx"
        for bank in ("base", ""):
            (d2r_excel / bank).mkdir(parents=True, exist_ok=True)
            (d2r_excel / bank / "monstats2.txt").write_text(tsv(MS2, ["archer", "bow", "1", '"lit,med"', "1", "lit", "1", "1", "0"]),
                                                             encoding="utf-8")
        self.tables(["haunt", "pil", "1", "hvy", "0", "", "0", "1", "1"], ms_rows=[["haunt", "5", "AM", "haunt"]])
        lines = ot._borrow_tables(BORROW, self.excel, d2r_excel)
        self.assertEqual(len(lines), 2)
        for bank in ("base", ""):
            _, rows = read_tsv(self.excel / bank / "monstats.txt")
            self.assertEqual(next(r for r in rows if r[0] == "haunt")[2], "HN")
            _, rows2 = read_tsv(self.excel / bank / "monstats2.txt")
            # donor's visual columns and modes (DT, NU), plus the row's own GH
            self.assertEqual(next(r for r in rows2 if r[0] == "haunt")[:9], ["haunt", "bow", "1", '"lit,med"', "1", "lit", "1", "1", "1"])

    def test_write_and_report(self):
        put(self.med, "e9/cof/e9nuhth.cof", cof(13, [(TR, "hth")]))
        rows = ot.write(self.out, self.plan(SPLIT))
        self.assertEqual(rows, ["| ks/cof/ksnuhth.cof | median |"])
        self.assertEqual((self.out / "global/monsters/ks/cof/ksnuhth.cof").read_bytes(), cof(13, [(TR, "hth")]))


def anim_record(name: str, frames: int, tail: int = 0) -> bytes:
    return name.encode().ljust(8, b"\0") + struct.pack("<I", frames) + bytes([tail]) * 148


class AnimdataTests(unittest.TestCase):
    def test_median_record_with_the_cof_frames_wins_over_d2rs(self):
        plan = ot.Plan(anims=[ot.Anim("KSNUHTH", "E9NUHTH", "", 13), ot.Anim("KSA1HTH", "E9A1HTH", "", 15),
                              ot.Anim("KSDTHTH", "E9DDHTH", "merged", 1), ot.Anim("KSS1HTH", "E9S1HTH", "", 99)])
        mxl = {b"E9NUHTH": anim_record("E9NUHTH", 13, 7)}
        d2r = {b"E9NUHTH": anim_record("E9NUHTH", 2, 1), b"E9A1HTH": anim_record("E9A1HTH", 15, 2), b"E9S1HTH": anim_record("E9S1HTH", 15, 3)}
        merged = dict(d2r)
        merged[b"E9DDHTH"] = anim_record("E9DDHTH", 1, 4)
        added = ot.add_animdata(merged, mxl, d2r, plan)
        self.assertEqual(added, ["KSNUHTH", "KSA1HTH", "KSDTHTH"])
        self.assertEqual(struct.unpack_from("<I", merged[b"KSNUHTH"], 8)[0], 13)
        self.assertEqual(merged[b"KSNUHTH"][:8], b"KSNUHTH\0")
        self.assertEqual(merged[b"KSNUHTH"][12], 7)                      # Median's timing
        self.assertEqual(merged[b"KSA1HTH"][12], 2)                      # D2R's, same frames
        self.assertEqual(merged[b"KSDTHTH"][12], 4)                      # from the merged table
        self.assertNotIn(b"KSS1HTH", merged)                             # no record with 99 frames anywhere
        self.assertTrue(any("KSS1HTH" in n for n in plan.notes))
        self.assertEqual(struct.unpack_from("<I", merged[b"E9NUHTH"], 8)[0], 2)   # the old token's record is untouched


class DataTests(unittest.TestCase):
    def test_committed_entries_are_well_formed(self):
        entries = ot.load()
        self.assertTrue(entries)
        for e in entries:
            self.assertIn(e["mode"], ("split", "complete", "borrow"))
            self.assertTrue(e["why"])
            self.assertTrue(e["rows"])
        self.assertEqual({e["old"] for e in ot.splits(entries)}, {"e9"})
        self.assertEqual(ot.row_token("slayer", "e9", entries), "KS")
        self.assertTrue(all(len(e["new"]) == 2 for e in ot.splits(entries) + ot.borrows(entries)))   # a monstats Code has two characters
        self.assertEqual(ot.row_token("haunt_vasily", "AM", entries), "HN")

    def test_a_token_in_use_is_refused(self):
        with tempfile.TemporaryDirectory() as t:
            put(Path(t) / "d2r", "ks/cof/ksnuhth.cof", cof(2, [(TR, "hth")]))
            with self.assertRaises(SystemExit):
                ot.make_plan([SPLIT], Path(t) / "med", Path(t) / "d2r", Path(t) / "excel")


if __name__ == "__main__":
    unittest.main()
