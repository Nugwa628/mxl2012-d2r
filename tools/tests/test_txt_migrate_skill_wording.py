"""Bug #396: skill tooltip text cells. median_skill_wording gives a blank mana cost label (type 1) the row's 1.13c `str mana`
and points the text of an appending line type at the mod's own words (<key>_mxl) when D2R's text of the key is a printf format."""
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

COLS = ["skilldesc", "descline1", "desctexta1", "desctextb1", "descline2", "desctexta2", "desctextb2", "dsc2line1", "dsc2texta1",
        "dsc2textb1"]


def tsv(*rows):
    return "\r\n".join("\t".join(r) for r in rows) + "\r\n"


class SkillWordingTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        tm.OUT, tm.NAMED = root / "out", root / "named"
        tm.NAMED.mkdir(parents=True)
        (tm.NAMED / "skilldesc.txt").write_text(tsv(["skilldesc", "str mana"], ["fire wall", "StrSkill3"], ["own label", "StrSkill3"],
                                                    ["no mana", ""]), encoding="utf-8")
        for bank in ("base", ""):
            d = tm.OUT / "data" / "global" / "excel" / bank
            d.mkdir(parents=True, exist_ok=True)
            (d / "skilldesc.txt").write_text(tsv(
                COLS,
                ["fire wall", "1", "", "", "30", "StrSkill82", "", "75", "StrSkill82", "StrSkill82"],
                ["own label", "1", "Mine", "", "", "", "", "", "", ""],
                ["no mana", "1", "", "", "", "", "", "", "", ""]), encoding="utf-8")
        self.m = tm.Migrator.__new__(tm.Migrator)
        self.m.report = []
        self.m.smap = {"kept_alias": {"StrSkill82": "mxl2012:StrSkill82_mxl"}}
        self.m.skilldesc_renames = {}

    def rows(self, bank=""):
        h, rows = tm.read_tsv(tm.OUT / "data" / "global" / "excel" / bank / "skilldesc.txt")
        return {r[0]: dict(zip(h, r)) for r in rows}

    def test_fire_wall(self):
        self.m.median_skill_wording()
        for bank in ("base", ""):
            r = self.rows(bank)["fire wall"]
            self.assertEqual(r["desctexta1"], "StrSkill3")  # the mana cost label 1.13c read from `str mana`
            self.assertEqual(r["desctexta2"], "mxl2012:StrSkill82_mxl")  # type 30 appends: the mod's "Fire Duration: "
            self.assertEqual((r["dsc2texta1"], r["dsc2textb1"]), ("StrSkill82", "mxl2012:StrSkill82_mxl"))  # 75 formats text A
        self.assertIn("2 mana cost lines", self.m.report[-1])

    def test_a_label_of_its_own_and_a_row_without_str_mana_are_kept(self):
        self.m.median_skill_wording()
        r = self.rows()
        self.assertEqual(r["own label"]["desctexta1"], "Mine")
        self.assertEqual(r["no mana"]["desctexta1"], "")


if __name__ == "__main__":
    unittest.main()
