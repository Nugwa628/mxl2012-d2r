"""Bug #34: Median's death COFs exist for weapon class hth only; the rows of the token use another class."""
import sys
import tempfile
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))
import projtemp  # noqa: E402,F401  (temp files stay inside the project, tools/projtemp.py)
import death_cofs as dc  # noqa: E402


def tsv(*rows):
    return "\r\n".join("\t".join(r) for r in rows) + "\r\n"


MS = ["Id", "*hcIdx", "Code", "MonStatsEx"]
MS2 = ["Id", "BaseW", "mDT", "mDD"]


class DeathCofTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.tmp = Path(self.temp.name)
        self.excel = self.tmp / "excel"
        for bank in ("base", ""):
            d = self.excel / bank
            d.mkdir(parents=True, exist_ok=True)
            (d / "monstats.txt").write_text(tsv(MS, ["amazon", "1", "9X", "amazon"], ["zombie", "2", "ZO", "zombie"],
                                                ["goat", "3", "GM", "goat"], ["swordman", "4", "SW", "swordman"],
                                                ["Expansion", "", "", ""]), encoding="utf-8")
            (d / "monstats2.txt").write_text(tsv(MS2, ["amazon", "bow", "1", "1"], ["zombie", "hth", "1", "1"],
                                                 ["goat", "2hs", "1", "1"], ["swordman", "1hs", "1", ""],
                                                 ["Expansion", "", "", ""]), encoding="utf-8")
        self.mxl = {}
        for name in ("9xdthth", "9xddhth", "swdthth", "zodthth"):
            p = self.tmp / "mxl" / name[:2] / "cof" / f"{name}.cof"
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(self.cof())
            self.mxl[name] = p

    @staticmethod
    def cof(wclass=b"hth\0"):
        """A one-layer ('tr') COF: 1 frame, 1 direction."""
        return bytes([1, 1, 1]) + bytes(25) + bytes([1, 0, 0, 0, 0]) + wclass + bytes([0, 0])

    def cof_two_layers(self):
        """cof() with the added left hand layer: 2 layers, the priority row [tr, lh]."""
        return (bytes([2, 1, 1]) + bytes(25) + bytes([1, 0, 0, 0, 0]) + b"hth\0" + bytes([6, 1, 1, 0, 0]) + b"bow\0"
                + bytes([0]) + bytes([0, 6]))

    def test_bow_row_gets_both_death_files_from_hth(self):
        got = dc.plan(self.excel, set(), self.mxl)
        self.assertIn(("9x", "DT", "bow"), got)
        self.assertIn(("9x", "DD", "bow"), got)

    def test_only_median_hth_files_are_sources_and_only_enabled_modes_count(self):
        got = dc.plan(self.excel, set(), self.mxl)
        self.assertNotIn(("gm", "DT", "2hs"), got)   # D2R's token: no Median hth file, D2R's own files rule
        self.assertEqual([g for g in got if g[0] == "sw"], [("sw", "DT", "1hs")])   # mDD off for swordman
        self.assertFalse([g for g in got if g[0] == "zo"])   # hth rows need nothing

    def test_existing_files_are_kept(self):
        got = dc.plan(self.excel, {"9xdtbow"}, self.mxl)
        self.assertEqual([g for g in got if g[0] == "9x"], [("9x", "DD", "bow")])
        have = {**self.mxl, "9xdtbow": self.mxl["9xdthth"], "9xddbow": self.mxl["9xddhth"]}   # Median ships both
        self.assertFalse([g for g in dc.plan(self.excel, set(), have) if g[0] == "9x"])

    def test_apply_adds_a_left_hand_layer_in_the_row_class(self):
        orig = dc.median_cofs
        dc.median_cofs = lambda: self.mxl
        self.addCleanup(setattr, dc, "median_cofs", orig)
        out = self.tmp / "out"
        lines = dc.apply_cofs(out, [("9x", "DT", "bow")])
        got = (out / "global/monsters/9x/cof/9xdtbow.cof").read_bytes()
        self.assertEqual(got, self.cof_two_layers())
        self.assertIn("| 9x | DT | bow | 9xdthth.cof |", lines)

    def test_layer_tables_stay_consistent_for_several_frames_and_directions(self):
        # 3 frames, 2 directions, 2 layers (tr, lg): priorities become 3 bytes each, lh (6) last
        head = bytes([2, 3, 2]) + bytes(25)
        layers = bytes([1, 1, 1, 0, 0]) + b"hth\0" + bytes([2, 1, 1, 0, 0]) + b"hth\0"
        prio = bytes([1, 2, 2, 1, 1, 2, 2, 1, 1, 2, 2, 1])
        got = dc.add_weapon_layer(head + layers + bytes(3) + prio, "bow")
        self.assertEqual(got[0], 3)
        self.assertEqual(len(got), 28 + 27 + 3 + 3 * 2 * 3)
        self.assertEqual(got[28 + 18:28 + 27], bytes([6, 1, 1, 0, 0]) + b"bow\0")
        self.assertEqual(got[28 + 27 + 3:], bytes([1, 2, 6, 2, 1, 6, 1, 2, 6, 2, 1, 6, 1, 2, 6, 2, 1, 6]))

    def test_animdata_record_is_the_hth_record_under_the_new_name(self):
        rec = b"9XDTHTH\0" + bytes(range(152))
        recs = {b"9XDTHTH": rec}
        self.assertEqual(dc.animdata_records(recs, [("9x", "DT", "bow"), ("9x", "DD", "bow")]), ["9XDTBOW"])
        self.assertEqual(recs[b"9XDTBOW"], b"9XDTBOW\0" + rec[8:])
        self.assertEqual(len(recs[b"9XDTBOW"]), 160)


if __name__ == "__main__":
    unittest.main()
