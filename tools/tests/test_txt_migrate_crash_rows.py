"""Crash rows that hit Median 2012 (docs/crash-audit.md): C1 skilldesc line strings, C11 item skills without a
skilldesc, C15 Raven AI hit counters."""
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
    return "\n".join("\t".join(r) for r in rows) + "\n"


SD_HEAD = ["skilldesc", "IconCel", "str name"] + [f"{n}{i}" for i in (1, 2, 3) for n in
                                                  ("descline", "desctexta", "desctextb", "desccalca", "desccalcb")]


class CrashRowTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.out, self.d2r, self.named = root / "out", root / "d2r", root / "named"
        self.named.mkdir()
        for bank in ("base", ""):
            d = self.out / "data" / "global" / "excel" / bank
            d.mkdir(parents=True, exist_ok=True)
            (self.d2r / bank).mkdir(parents=True, exist_ok=True)
            # D2R's own rows: type 13 always "StrSkill42", type 7 never used
            (self.d2r / bank / "skilldesc.txt").write_text(tsv(
                SD_HEAD,
                ["valkyrie", "1", "x", "13", "StrSkill42", "", "par1", "", "74", "StrSkill21", "", "a", "", "", "", "", "", ""],
                ["firegolem", "2", "y", "13", "StrSkill42", "", "par1", "", "74", "StrSkill22", "", "b", "", "", "", "", "", ""]),
                encoding="utf-8")
            (d / "skilldesc.txt").write_text(tsv(
                SD_HEAD,
                ["valkyrie", "1", "x", "1", "", "", "", "", "13", "", "", "par1*(lvl-1)", "", "", "", "", "", ""],
                ["lionstance", "3", "z", "7", "", "", "max(ln34,25)", "", "2", "StrSkill4", "StrSkill23", "ln12", "", "", "", "", "", ""],
                ["boltz", "4", "w", "40", "Sksyn", "", "", "", "", "", "", "", "", "", "", "", "", ""]), encoding="utf-8")
            (d / "skills.txt").write_text(tsv(
                ["skill", "*Id", "charclass", "skilldesc", "Param1", "Param2", "calc3"],
                ["Wolf Companion", "0", "bar", "wolf", "-2", "", ""],
                ["SorcFamiliar", "1", "sor", "cat", "-2", "", "ln34"],
                ["Raven", "2", "dru", "raven", "", "", ""],
                ["Heal Mana Aura", "3", "", "", "", "", ""],
                ["Item Thunderfury", "4", "", "", "", "", ""],
                ["Mon Hit Monster Effect", "5", "", "", "", "", ""],
                ["Holy Bolt", "6", "pal", "holy bolt", "", "", ""]), encoding="utf-8")
            (d / "properties.txt").write_text(tsv(["code", "func1", "stat1"], ["aura", "", "item_aura"],
                                                  ["hit-skill", "", "item_skillonhit"], ["str", "1", "strength"]),
                                              encoding="utf-8")
            (d / "itemstatcost.txt").write_text(tsv(["Stat", "*ID", "descfunc", "Encode"], ["strength", "0", "1", ""],
                                                    ["item_aura", "1", "16", ""], ["item_skillonhit", "2", "15", "2"]),
                                                encoding="utf-8")
            (d / "uniqueitems.txt").write_text(tsv(["index", "prop1", "par1", "min1", "max1", "prop2", "par2", "min2", "max2"],
                                                   ["Book", "aura", "Heal Mana Aura", "1", "1", "str", "", "5", "5"],
                                                   ["Blade", "hit-skill", "4", "5", "10", "aura", "Holy Bolt", "1", "1"]),
                                               encoding="utf-8")
            (d / "monprop.txt").write_text(tsv(["Id", "prop1", "par1", "min1", "max1"], ["boss", "hit-skill", "5", "1", "1"]),
                                           encoding="utf-8")
        (self.named / "monstats.txt").write_text(tsv(
            ["Id", "AI", "Skill1"], ["companion", "Raven", "Wolf Companion"], ["devilcat", "Raven", "SorcFamiliar"],
            ["druidhawk", "Raven", "Raven"], ["zombie1", "Zombie", "Holy Bolt"]), encoding="utf-8")
        tm.OUT, tm.D2R, tm.NAMED = self.out, self.d2r, self.named
        self.mig = tm.Migrator.__new__(tm.Migrator)
        self.mig.report = []

    def table(self, name, bank="base"):
        h, rows = tm.read_tsv(self.out / "data" / "global" / "excel" / bank / f"{name}.txt")
        return {r[0]: dict(zip(h, r)) for r in rows}

    # crash-audit C1
    def test_hard_coded_line_text_comes_from_d2r(self):
        self.mig.skilldesc_lines()
        for bank in ("base", ""):
            v = self.table("skilldesc", bank)["valkyrie"]
            self.assertEqual((v["descline2"], v["desctexta2"], v["desccalca2"]), ("13", "StrSkill42", "par1*(lvl-1)"))
            self.assertEqual(v["descline1"], "1")  # type 1 needs no string

    def test_line_without_a_known_text_is_dropped(self):
        self.mig.skilldesc_lines()
        r = self.table("skilldesc")
        self.assertEqual((r["lionstance"]["descline1"], r["lionstance"]["desccalca1"]), ("", ""))
        self.assertEqual(r["lionstance"]["desctexta2"], "StrSkill4")  # complete line kept
        self.assertEqual((r["boltz"]["descline1"], r["boltz"]["desctexta1"]), ("", ""))  # type 40 needs text B
        self.assertIn("1 lines given the text", self.mig.report[-1])
        self.assertIn("2 lines D2R can't draw dropped", self.mig.report[-1])

    # crash-audit C11
    def test_item_named_skills_get_the_blank_skilldesc(self):
        self.mig.blank_item_skilldesc()
        for bank in ("base", ""):
            s = self.table("skills", bank)
            self.assertEqual(s["Heal Mana Aura"]["skilldesc"], "mxl_blank")   # by name
            self.assertEqual(s["Item Thunderfury"]["skilldesc"], "mxl_blank")  # by id
            self.assertEqual(s["Mon Hit Monster Effect"]["skilldesc"], "")    # monprop only
            self.assertEqual(s["Holy Bolt"]["skilldesc"], "holy bolt")         # has its own
            d = self.table("skilldesc", bank)["mxl_blank"]
            self.assertEqual((d["str name"], d["IconCel"]), ("", ""))
        self.assertIn("2 skills named by item properties", self.mig.report[-1])

    def test_blank_row_added_once(self):
        self.mig.blank_item_skilldesc()
        self.mig.blank_item_skilldesc()
        h, rows = tm.read_tsv(self.out / "data" / "global" / "excel" / "base" / "skilldesc.txt")
        self.assertEqual(sum(1 for r in rows if r[0] == "mxl_blank"), 1)

    # crash-audit C15
    def test_raven_counter_calc3(self):
        self.mig.raven_counts()
        for bank in ("base", ""):
            s = self.table("skills", bank)
            self.assertEqual(s["Wolf Companion"]["calc3"], "ln12")
            self.assertEqual(s["SorcFamiliar"]["calc3"], "ln34")  # own calc3 kept
            self.assertEqual(s["Raven"]["calc3"], "")             # no params: 0 either way
            self.assertEqual(s["Holy Bolt"]["calc3"], "")         # not a Raven AI skill
        self.assertIn("on Wolf Companion; own calc3 kept: SorcFamiliar (ln34)", self.mig.report[-1])


if __name__ == "__main__":
    unittest.main()
