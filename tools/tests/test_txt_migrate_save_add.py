"""Lane savefmt: item values below -Save Add (Median's light radius -20 / +life -250) get a Save Add that holds them."""
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
    return "\r\n".join("\t".join(str(c) for c in r) for r in rows) + "\r\n"


class StatSaveAddTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.out = Path(self.temp.name) / "out"
        tm.OUT = self.out
        self.mig = tm.Migrator.__new__(tm.Migrator)
        self.mig.report = []

    def make(self, light=(-20, -20), hp=(-250, 1500), hp_bits=11):
        fh = ["code", "*Id"] + [f"{k}{i}" for i in range(1, 8) for k in ("func", "stat", "set", "val")]
        pad = lambda r: r + [""] * (len(fh) - len(r))  # noqa: E731
        for bank in ("base", ""):
            d = self.out / "data" / "global" / "excel" / bank
            d.mkdir(parents=True, exist_ok=True)
            (d / "itemstatcost.txt").write_text(tsv(
                ["Stat", "*ID", "Save Bits", "Save Add", "Save Param Bits"],
                ["maxhp", 7, hp_bits, 150, ""], ["item_lightradius", 89, 8, 5, ""], ["strength", 0, 11, 32, ""],
                ["item_singleskill", 107, 5, 1, 11]), encoding="utf-8")
            (d / "properties.txt").write_text(tsv(fh, pad(["light", 1, 1, "item_lightradius"]), pad(["hp", 2, 1, "maxhp"]),
                                                  pad(["str", 3, 1, "strength"]), pad(["skill", 4, 22, "item_singleskill"])),
                                              encoding="utf-8")
            (d / "uniqueitems.txt").write_text(tsv(
                ["index", "code", "prop1", "par1", "min1", "max1", "prop2", "par2", "min2", "max2"],
                ["Dark", "56!", "light", "", light[0], light[1], "str", "", 10, 20],
                ["Angel", "@61", "hp", "", hp[0], hp[0], "skill", "Fire", -99, -99],
                ["Big", "@62", "hp", "", hp[1], hp[1], "", "", "", ""]), encoding="utf-8")

    def cols(self, bank=""):
        h, rows = tm.read_tsv(self.out / "data" / "global" / "excel" / bank / "itemstatcost.txt")
        return {r[0]: (r[h.index("Save Bits")], r[h.index("Save Add")]) for r in rows}

    def test_add_raised_to_the_lowest_value(self):
        self.make()
        self.mig.stat_save_add()
        for bank in ("base", ""):
            c = self.cols(bank)
            self.assertEqual(c["item_lightradius"], ("8", "20"))
            self.assertEqual(c["maxhp"], ("11", "250"))  # 1500 + 250 < 2048
            self.assertEqual(c["strength"], ("11", "32"))
            self.assertEqual(c["item_singleskill"], ("5", "1"))  # a stat with a parameter is not summed / changed
        self.assertIn("item_lightradius Save Add 5 -> 20", " ".join(self.mig.report))

    def test_bits_widened_when_the_top_no_longer_fits(self):
        self.make(hp=(-250, 1900))
        self.mig.stat_save_add()
        self.assertEqual(self.cols()["maxhp"], ("12", "250"))

    def test_fitting_values_change_nothing(self):
        self.make(light=(-5, 10), hp=(-150, 100))
        self.mig.stat_save_add()
        self.assertEqual(self.cols()["item_lightradius"], ("8", "5"))
        self.assertEqual(self.cols()["maxhp"], ("11", "150"))
        self.assertEqual(self.mig.report, [])


if __name__ == "__main__":
    unittest.main()
