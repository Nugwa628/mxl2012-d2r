"""Bug #490: item use lines (misc spelldesc 2). 1.13c drew spelldescstr, a space and the value; D2R formats spelldescstr with
the value as printf, so Median's texts without a placeholder get `<key>_val` (text + " %d") and the misc cells name it."""
import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))
import projtemp  # noqa: E402,F401  (temp files stay inside the project, tools/projtemp.py)
import strings_ns  # noqa: E402
spec = importlib.util.spec_from_file_location("txt_migrate", TOOLS / "txt_migrate.py")
tm = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tm)

COLS = ["name", "code", "spelldesc", "spelldescstr", "spelldesccalc"]


def tsv(*rows):
    return "\r\n".join("\t".join(r) for r in rows) + "\r\n"


ROWS = [["Signet of Gold", "zkw", "2", "Signet1desc", "150*stat('level'.accr)"],
        ["Life Pack", "zl1", "2", "LifePakDesc", "stat('level'.accr)*10"],
        ["Minor Healing Potion", "hp1", "2", "ItemStats1q", "30"],
        ["Book of Skill", "ass", "1", "UseBookOfSkill", ""],
        ["Rejuvenation Potion", "rvs", "4", "ItemStatsrejuv1", "35"]]


class SpellValueTextTests(unittest.TestCase):
    def test_text_space_value(self):
        self.assertEqual(strings_ns.spell_value_text("Right-click: Gold in Bank:"), "Right-click: Gold in Bank: %d")

    def test_literal_percent_is_doubled(self):
        self.assertEqual(strings_ns.spell_value_text("Heals 5% more:"), "Heals 5%% more: %d")

    def test_keys_of_spelldesc_2_rows_only(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "misc.txt").write_text(tsv(COLS, *ROWS), encoding="cp1252")
            self.assertEqual(strings_ns.spell_value_keys(d), {"Signet1desc", "LifePakDesc", "ItemStats1q"})
        self.assertEqual(strings_ns.spell_value_keys(None), set())


class MiscSpellValuesTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        tm.OUT = Path(self.temp.name) / "out"
        for bank in ("base", ""):
            d = tm.OUT / "data" / "global" / "excel" / bank
            d.mkdir(parents=True, exist_ok=True)
            (d / "misc.txt").write_text(tsv(COLS, *ROWS), encoding="utf-8")
        self.m = tm.Migrator.__new__(tm.Migrator)
        self.m.report = []
        # tbl2json writes an alias only for Median-only texts without a placeholder (not D2R's "Points: %d")
        self.m.smap = {"value_alias": {"Signet1desc": "Signet1desc_val", "LifePakDesc": "LifePakDesc_val",
                                       "UseBookOfSkill": "UseBookOfSkill_val"}}

    def rows(self, bank=""):
        h, rows = tm.read_tsv(tm.OUT / "data" / "global" / "excel" / bank / "misc.txt")
        return {r[1]: dict(zip(h, r)) for r in rows}

    def test_cells_name_the_value_text(self):
        self.m.misc_spell_values()
        for bank in ("base", ""):
            r = self.rows(bank)
            self.assertEqual(r["zkw"]["spelldescstr"], "Signet1desc_val")
            self.assertEqual(r["zl1"]["spelldescstr"], "LifePakDesc_val")
            self.assertEqual(r["hp1"]["spelldescstr"], "ItemStats1q")  # D2R's own format text
            self.assertEqual(r["ass"]["spelldescstr"], "UseBookOfSkill")  # spelldesc 1: the text alone
        self.assertIn("2 rows", self.m.report[-1])


if __name__ == "__main__":
    unittest.main()
