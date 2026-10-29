"""hireling.HiringMaxLevelDifference by Version as D2R's own rows have it (docs/median-rules-audit.md ME4): classic 5,
expansion 1. A key match alone gave every Median row the first D2R row's value (classic Rogue Scout: 5)."""
import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))
import projtemp  # noqa: E402,F401  (temp files stay inside the project, tools/projtemp.py)
spec = importlib.util.spec_from_file_location("txt_migrate", TOOLS / "txt_migrate.py")
tm = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tm)

COLS = ["Hireling", "Version", "Difficulty", "HiringMaxLevelDifference"]


def tsv(*rows):
    return "\r\n".join("\t".join(r) for r in rows) + "\r\n"


class HirelingLevelDifferenceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.out, self.d2r = root / "out", root / "d2r"
        for bank in ("base", ""):
            d = self.out / "data" / "global" / "excel" / bank
            d.mkdir(parents=True, exist_ok=True)
            (d / "hireling.txt").write_text(tsv(COLS, ["Rogue Scout", "0", "1", "5"], ["Rogue Scout", "100", "1", "5"],
                                                ["Barbarian", "100", "3", ""]), encoding="utf-8")
            e = self.d2r / bank
            e.mkdir(parents=True, exist_ok=True)
            (e / "hireling.txt").write_text(tsv(COLS, ["Rogue Scout", "0", "1", "5"], ["Rogue Scout", "100", "1", "1"],
                                                ["Desert Mercenary", "0", "2", "5"], ["Barbarian", "100", "3", "1"]),
                                            encoding="utf-8")
        tm.OUT, tm.D2R = self.out, self.d2r
        self.mig = tm.Migrator.__new__(tm.Migrator)
        self.mig.report = []

    def values(self, bank):
        _, rows = tm.read_tsv(self.out / "data" / "global" / "excel" / bank / "hireling.txt")
        return [(r[0], r[1], r[3]) for r in rows if any(r)]

    def test_value_follows_version(self):
        self.mig.hireling_level_difference()
        for bank in ("base", ""):
            self.assertEqual(self.values(bank), [("Rogue Scout", "0", "5"), ("Rogue Scout", "100", "1"), ("Barbarian", "100", "1")])

    def test_report(self):
        self.mig.hireling_level_difference()
        self.assertIn("HiringMaxLevelDifference by Version", self.mig.report[-1])
        self.assertIn("base 3", self.mig.report[-1])

    def test_not_a_constant_or_needed_column_any_more(self):
        self.assertNotIn("HiringMaxLevelDifference", tm.CONSTANTS["hireling"])
        self.assertNotIn("HiringMaxLevelDifference", tm.NEEDED_FROM_D2R.get("hireling", set()))


if __name__ == "__main__":
    unittest.main()
