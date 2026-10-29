"""Item uses 1.13c runs by item code and D2R by misc pSpell (docs/median-rules-audit.md SK9, QU2): Book of Skill, Potion of
Life, Malah's scroll and the Token of Absolution (Median's respec token) take D2R's pSpell when Median's cell is empty."""
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

MI = {"name": 0, "code": 1, "pSpell": 2, "spelldesc": 3}


class ItemUseRowsTests(unittest.TestCase):
    def test_hard_coded_uses_take_d2r_pspell(self):
        for code in ("toa", "ass", "xyz", "tr2", "toa "):
            self.assertTrue(tm.d2r_when_empty("misc", "pSpell", ["x", code, "", ""], MI), code)

    def test_only_pspell_of_those_rows(self):
        self.assertFalse(tm.d2r_when_empty("misc", "spelldesc", ["x", "toa", "", ""], MI))  # 1.13c shows no use line
        self.assertFalse(tm.d2r_when_empty("misc", "pSpell", ["x", "bkd", "", ""], MI))     # not usable in 1.13c
        self.assertFalse(tm.d2r_when_empty("misc", "pSpell", ["x", "r01", "", ""], MI))     # D2R's -1 "no spell"
        self.assertFalse(tm.d2r_when_empty("weapons", "pSpell", ["x", "toa", "", ""], MI))

    def test_table_wide_rule_still_applies(self):
        self.assertTrue(tm.d2r_when_empty("overlay", "Character", ["x"], {"overlay": 0}))
        self.assertFalse(tm.d2r_when_empty("overlay", "Filename", ["x"], {"overlay": 0}))

    def test_codes_are_vanilla_quest_items(self):
        _, codes, cols = tm.D2R_WHEN_EMPTY_ROWS["misc"]
        self.assertEqual(codes, {"ass", "xyz", "tr2", "toa"})
        self.assertEqual(cols, {"pSpell"})


if __name__ == "__main__":
    unittest.main()
