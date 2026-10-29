"""Lane rulescheck2 build rules in txt_migrate: CH13 (1.13c's `delay` fills both D2R delay columns) and DF11 (the Fire
Enchanted explosion percentages 1.13c keeps in code)."""
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


def tsv(*rows):
    return "\r\n".join("\t".join(r) for r in rows) + "\r\n"


class DelayColumnsTests(unittest.TestCase):
    def test_delay_feeds_local_and_global(self):
        mig = tm.Migrator.__new__(tm.Migrator)
        out = mig.column_map("skills", ["skill", "delay"], ["skill", "localdelay", "globaldelay"])
        self.assertEqual(out["localdelay"], "delay")
        self.assertEqual(out["globaldelay"], "delay")

    def test_no_plain_rename_left(self):  # a rename would map localdelay only (the round-1 build)
        self.assertNotIn("delay", tm.RENAMES.get("skills", {}))


class FireEnchantedTests(unittest.TestCase):
    COLS = ["Name", "DeathExpPenalty", "MonsterFireEnchantExplosionDamagePercent"]

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.out = Path(self.temp.name) / "out"
        for bank in ("base", ""):
            d = self.out / "data" / "global" / "excel" / bank
            d.mkdir(parents=True, exist_ok=True)
            (d / "difficultylevels.txt").write_text(tsv(self.COLS, ["Normal", "0", "75"], ["Nightmare", "1", "50"],
                                                        ["Hell", "1", "13"]), encoding="utf-8")
        self.old_out = tm.OUT
        tm.OUT = self.out
        self.addCleanup(setattr, tm, "OUT", self.old_out)
        self.mig = tm.Migrator.__new__(tm.Migrator)
        self.mig.report = []

    def values(self, bank):
        h, rows = tm.read_tsv(self.out / "data" / "global" / "excel" / bank / "difficultylevels.txt")
        i = h.index("MonsterFireEnchantExplosionDamagePercent")
        return {r[0]: r[i] for r in rows if r and r[0]}

    def test_nightmare_two_thirds(self):
        self.mig.difficulty_code_rules()
        for bank in ("base", ""):
            self.assertEqual(self.values(bank), {"Normal": "75", "Nightmare": "67", "Hell": "13"})
        self.assertIn("rotw 1", self.mig.report[-1])

    def test_other_columns_untouched(self):
        self.mig.difficulty_code_rules()
        h, rows = tm.read_tsv(self.out / "data" / "global" / "excel" / "difficultylevels.txt")
        self.assertEqual([r[h.index("DeathExpPenalty")] for r in rows if r and r[0]], ["0", "1", "1"])


if __name__ == "__main__":
    unittest.main()
