"""Bug #3: D2R asks for the get-hit COF of a monster with the knockback mode on; without that file the game ends."""
import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))
import projtemp  # noqa: E402,F401  (temp files stay inside the project, tools/projtemp.py)
spec = importlib.util.spec_from_file_location("gfx_placeholders", TOOLS / "gfx_placeholders.py")
gp = importlib.util.module_from_spec(spec)
spec.loader.exec_module(gp)


def tsv(*rows):
    return "\r\n".join("\t".join(r) for r in rows) + "\r\n"


MS = ["Id", "*hcIdx", "Code", "MonStatsEx"]
MS2 = ["Id", "BaseW", "mGH", "mKB", "mSQ", "mA1"]


class ClearGhModesTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.out = Path(self.temp.name) / "data"
        for bank in ("base", ""):
            d = self.out / "global" / "excel" / bank
            d.mkdir(parents=True, exist_ok=True)
            (d / "monstats.txt").write_text(tsv(MS, ["necromorb", "1", "IM", "necromorb"], ["orb", "2", "IM", "orb"],
                                                ["zombie1", "3", "ZO", "zombie1"], ["Expansion", "", "", ""]), encoding="utf-8")
            (d / "monstats2.txt").write_text(tsv(MS2, ["necromorb", "hth", "", "1", "1", "1"], ["orb", "hth", "", "", "", "1"],
                                                 ["zombie1", "hth", "1", "1", "1", "1"], ["Expansion", "", "", "", "", ""]),
                                             encoding="utf-8")
        gp.OUT = self.out

    def row(self, bank, mid):
        h, rows = gp.read_tsv(self.out / "global" / "excel" / bank / "monstats2.txt")
        return dict(zip(h, next(r for r in rows if r[0] == mid)))

    def test_knockback_without_a_gh_cof_is_cleared_in_both_banks(self):
        lines = gp.clear_gh_modes({"imnuhth", "ima1hth", "ims1hth", "zoghhth"})
        for bank in ("base", ""):
            r = self.row(bank, "necromorb")
            self.assertEqual((r["mKB"], r["mSQ"], r["mA1"]), ("", "1", "1"))  # the sequence mode needs no GH COF
        self.assertTrue(any("necromorb" in ln for ln in lines))

    def test_rows_with_a_gh_cof_or_without_knockback_stay(self):
        gp.clear_gh_modes({"imnuhth", "zoghhth"})
        for bank in ("base", ""):
            z = self.row(bank, "zombie1")
            self.assertEqual((z["mGH"], z["mKB"], z["mSQ"]), ("1", "1", "1"))
            self.assertEqual(self.row(bank, "orb")["mA1"], "1")

    def test_a_gh_cof_of_the_token_keeps_knockback(self):
        gp.clear_gh_modes({"imnuhth", "imghhth"})
        for bank in ("base", ""):
            n = self.row(bank, "necromorb")
            self.assertEqual((n["mKB"], n["mSQ"]), ("1", "1"))


if __name__ == "__main__":
    unittest.main()
