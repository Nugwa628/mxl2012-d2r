"""Bug #487: Elvensong's spirit hit like a curse and never charmed. Skill server do 51 (the conversion of Mind Blast, Median's
charms) reads its chance from Param5 / Param6 (dm56) and its length from Param3 in 1.13c, but from calc1 / calc2 in D2R, where
Median's rows are blank. conversion_calcs fills the blank cells with 1.13c's values and keeps a cell a row already sets."""
import importlib.util
import sys
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))
import projtemp  # noqa: E402,F401  (temp files stay inside the project, tools/projtemp.py)
spec = importlib.util.spec_from_file_location("txt_migrate", TOOLS / "txt_migrate.py")
tm = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tm)

HEADER = ["skill", "*Id", "srvdofunc", "calc1", "calc2", "Param3", "Param5", "Param6"]


def rows():
    return [["Elvensong Spell", "1095", "51", "", "", "75", "100", "100"],
            ["Black Sleep", "504", "51", "100", "", "100", "66", "66"],
            ["Elvensong", "469", "119", "", "ulvl", "249", "", ""]]


class ConversionCalcTests(unittest.TestCase):
    def test_blank_cells_take_the_1_13c_chance_and_length(self):
        r = rows()
        tm.conversion_calcs(HEADER, r)
        self.assertEqual(r[0][3:5], ["dm56", "par3"])

    def test_a_set_calc_is_kept(self):
        r = rows()
        tm.conversion_calcs(HEADER, r)
        self.assertEqual(r[1][3:5], ["100", "par3"])

    def test_other_functions_untouched(self):
        r = rows()
        tm.conversion_calcs(HEADER, r)
        self.assertEqual(r[2], rows()[2])

    def test_report_lines(self):
        self.assertEqual(tm.conversion_calcs(HEADER, rows()),
                         ["1095 Elvensong Spell: calc1 dm56, calc2 par3", "504 Black Sleep: calc2 par3"])

    def test_short_row_is_padded(self):
        r = [["Charm", "854", "51"]]
        tm.conversion_calcs(HEADER, r)
        self.assertEqual(r[0][3:5], ["dm56", "par3"])

    def test_no_calc_columns(self):
        self.assertEqual(tm.conversion_calcs(["skill", "srvdofunc"], [["a", "51"]]), [])

    def test_built_rows(self):
        """The built tables (when tools/build.py ran in this checkout): every srvdofunc 51 row has a chance and a length."""
        excel = TOOLS.parent / "work" / "mod" / "data" / "global" / "excel"
        for bank in ("base", ""):
            p = excel / bank / "skills.txt"
            if not p.exists():
                self.skipTest("no build in work/mod")
            h, rs = tm.read_tsv(p)
            got = {r[h.index("skill")]: (r[h.index("calc1")], r[h.index("calc2")]) for r in rs
                   if len(r) > h.index("calc2") and r[h.index("srvdofunc")] == "51"}
            self.assertEqual(got.get("Elvensong Spell"), ("dm56", "par3"), bank or "rotw")
            self.assertTrue(all(a and b for a, b in got.values()), (bank or "rotw", got))


if __name__ == "__main__":
    unittest.main()
