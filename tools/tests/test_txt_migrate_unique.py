"""Bug #7: an always-unique item base without a uniqueitems row (the starting kit's Median Statue `zen`) must lose its flag."""
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


class ClearUniqueFlagsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.out, self.d2r = root / "out", root / "d2r"
        for bank in ("base", ""):
            d = self.out / "data" / "global" / "excel" / bank
            d.mkdir(parents=True, exist_ok=True)
            (d / "uniqueitems.txt").write_text(tsv(["index", "code"], ["The Boulder", "hst"], ["Expansion", ""]), encoding="utf-8")
            (d / "weapons.txt").write_text(tsv(["name", "code", "unique"], ["Horadric Staff", "hst", "1"], ["Gidbinn", "g33", "1"],
                                               ["Dagger", "dgr", "0"]), encoding="utf-8")
            (d / "armor.txt").write_text(tsv(["name", "code", "unique"], ["Cap", "cap", ""]), encoding="utf-8")
            (d / "misc.txt").write_text(tsv(["name", "code", "unique"], ["Median Statue", "zen", "1"], ["Bark Scroll", "bks", "1"],
                                            ["Rune", "r01", "0"]), encoding="utf-8")
            e = self.d2r / bank
            e.mkdir(parents=True, exist_ok=True)
            (e / "weapons.txt").write_text(tsv(["name", "code", "unique"], ["Gidbinn", "g33", "1"]), encoding="utf-8")
            (e / "misc.txt").write_text(tsv(["name", "code", "unique"], ["Bark Scroll", "bks", "1"]), encoding="utf-8")
        tm.OUT, tm.D2R = self.out, self.d2r
        self.mig = tm.Migrator.__new__(tm.Migrator)
        self.mig.report = []

    def cells(self, bank, table):
        _, rows = tm.read_tsv(self.out / "data" / "global" / "excel" / bank / f"{table}.txt")
        return {r[1]: r[2] for r in rows}

    def test_flag_without_row_cleared_in_both_banks(self):
        self.mig.clear_unique_flags()
        for bank in ("base", ""):
            self.assertEqual(self.cells(bank, "misc")["zen"], "0")

    def test_d2r_flagged_quest_bases_and_rows_with_a_unique_stay(self):
        self.mig.clear_unique_flags()
        for bank in ("base", ""):
            self.assertEqual(self.cells(bank, "misc")["bks"], "1")      # D2R flags it itself
            self.assertEqual(self.cells(bank, "weapons")["g33"], "1")   # D2R flags it itself
            self.assertEqual(self.cells(bank, "weapons")["hst"], "1")   # has a uniqueitems row
            self.assertEqual(self.cells(bank, "weapons")["dgr"], "0")
            self.assertEqual(self.cells(bank, "armor")["cap"], "")

    def test_report_names_the_cleared_base(self):
        self.mig.clear_unique_flags()
        self.assertIn("misc:zen", self.mig.report[-1])


class CarryNumbersTests(unittest.TestCase):
    """Bug #280: D2R compares carry1 as a number; Median's 1 on every carry1 row made one relic block all the others."""

    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.out = Path(self.temp.name) / "out"
        for bank in ("base", ""):
            d = self.out / "data" / "global" / "excel" / bank
            d.mkdir(parents=True, exist_ok=True)
            (d / "uniqueitems.txt").write_text(tsv(["index", "code", "carry1"], ["Plain", "cap", ""], ["Expansion", "", ""],
                                                   ["Relic A", "cm1", "1"], ["Zero", "cm2", "0"], ["Relic B", "cm3", "1"],
                                                   ["Relic C", "cm1", "1"]), encoding="utf-8", newline="")
        tm.OUT = self.out
        self.mig = tm.Migrator.__new__(tm.Migrator)
        self.mig.report = []

    def carry(self, bank):
        _, rows = tm.read_tsv(self.out / "data" / "global" / "excel" / bank / "uniqueitems.txt")
        return [r[2] for r in rows]

    def test_each_carry_row_gets_its_record_index_plus_one(self):
        self.mig.carry_numbers()
        for bank in ("base", ""):
            # records (Expansion lines are not records): Plain 0, Relic A 1, Zero 2, Relic B 3, Relic C 4
            self.assertEqual(self.carry(bank), ["", "", "2", "0", "4", "5"])

    def test_numbers_are_distinct_and_a_second_run_changes_nothing(self):
        self.mig.carry_numbers()
        first = self.carry("base")
        self.mig.carry_numbers()
        self.assertEqual(self.carry("base"), first)
        nums = [v for v in first if v not in ("", "0")]
        self.assertEqual(len(nums), len(set(nums)))
        self.assertIn("0 carry1 cells", self.mig.report[-1])


if __name__ == "__main__":
    unittest.main()
