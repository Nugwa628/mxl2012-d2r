"""Bug #390: a pet on D2R's Raven AI dies on its first think unless its monstats Skill1 skill has a calc3 (the hit counter; 1.13c
read Param1 + (lvl - 1) * Param2). raven_counts gives Wolf Companion and SorcFamiliar calc3 ln12; others are left alone."""
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

SKILL_COLS = ["skill", "*Id", "calc3", "Param1", "Param2"]
MON_COLS = ["Id", "AI", "Skill1"]


def tsv(*rows):
    return "\r\n".join("\t".join(r) for r in rows) + "\r\n"


class RavenCountTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        tm.OUT, tm.NAMED = root / "out", root / "named"
        tm.NAMED.mkdir(parents=True)
        (tm.NAMED / "monstats.txt").write_text(tsv(MON_COLS, ["companion", "Raven", "Wolf Companion"],
                                                    ["devilcat", "Raven", "SorcFamiliar"], ["hawk", "Raven", "Own Calc"],
                                                    ["bare", "Raven", "No Params"], ["zombie", "Zombie", "Other"]), encoding="utf-8")
        for bank in ("base", ""):
            d = tm.OUT / "data" / "global" / "excel" / bank
            d.mkdir(parents=True, exist_ok=True)
            (d / "skills.txt").write_text(tsv(SKILL_COLS, ["Wolf Companion", "438", "", "-2", ""], ["SorcFamiliar", "544", "", "-2", ""],
                                              ["Own Calc", "600", "ln56", "1", "1"], ["No Params", "601", "", "", ""],
                                              ["Other", "602", "", "5", "1"]), encoding="utf-8")
        self.m = tm.Migrator.__new__(tm.Migrator)
        self.m.report = []

    def calc3(self, bank=""):
        h, rows = tm.read_tsv(tm.OUT / "data" / "global" / "excel" / bank / "skills.txt")
        return {r[0]: r[h.index("calc3")] for r in rows}

    def test_raven_pets_get_the_counter(self):
        self.m.raven_counts()
        for bank in ("base", ""):
            c = self.calc3(bank)
            self.assertEqual(c["Wolf Companion"], "ln12")
            self.assertEqual(c["SorcFamiliar"], "ln12")
            self.assertEqual(c["Own Calc"], "ln56")  # its own calc3 kept
            self.assertEqual(c["No Params"], "")  # 0 either way
            self.assertEqual(c["Other"], "")  # not on the Raven AI
        self.assertIn("SorcFamiliar, Wolf Companion", self.m.report[-1])
        self.assertIn("Own Calc (ln56)", self.m.report[-1])


if __name__ == "__main__":
    unittest.main()
