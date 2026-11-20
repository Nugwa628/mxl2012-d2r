"""Bug #32: a monprop event property whose skill has no ItemEffect is removed (D2R asserts `ptSkill->nItemEffect != 0`); bug #620:
the properties after it move up, since D2R stops at a row's first empty property."""
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


PROP_COLS = [f"{n}{i}{s}" for s in ("", " (N)") for i in (1, 2) for n in ("prop", "chance", "par", "min", "max")]


class MonpropEventSkillTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.out = Path(self.temp.name) / "out"
        for bank in ("base", ""):
            d = self.out / "data" / "global" / "excel" / bank
            d.mkdir(parents=True, exist_ok=True)
            (d / "properties.txt").write_text(tsv(["code", "stat1", "stat2"], ["death-skill", "item_skillondeath", ""],
                                                  ["hit-skill", "item_skillonhit", ""], ["aura", "item_aura", ""]), encoding="utf-8")
            (d / "skills.txt").write_text(tsv(["skill", "*Id", "ItemEffect"], ["Attack", "0", "1"], ["Living Flame", "1", ""],
                                              ["Laz Resist Aura", "2", ""], ["Devouring Acid", "3", "1"]), encoding="utf-8")
            row = ["hornedgods", "death-skill", "", "1", "100", "5", "hit-skill", "", "3", "100", "1",
                   "death-skill", "", "Living Flame", "100", "5", "aura", "", "2", "1", "1"]
            (d / "monprop.txt").write_text(tsv(["Id"] + PROP_COLS, row), encoding="utf-8")
        tm.OUT = self.out
        self.mig = tm.Migrator.__new__(tm.Migrator)
        self.mig.report = []

    def row(self, bank):
        h, rows = tm.read_tsv(self.out / "data" / "global" / "excel" / bank / "monprop.txt")
        return dict(zip(h, rows[0]))

    def test_event_on_a_skill_without_item_effect_is_removed(self):
        self.mig.monprop_event_skills()
        for bank in ("base", ""):
            r = self.row(bank)
            self.assertNotIn("death-skill", [r["prop1"], r["prop2"], r["prop1 (N)"], r["prop2 (N)"]])  # by id and by skill name
            self.assertEqual([r["prop2"], r["chance2"], r["par2"], r["min2"], r["max2"]], ["", "", "", "", ""])
            self.assertEqual([r["prop2 (N)"], r["par2 (N)"]], ["", ""])

    def test_other_events_and_non_event_props_stay_and_move_up(self):
        self.mig.monprop_event_skills()
        r = self.row("base")
        self.assertEqual([r["prop1"], r["par1"], r["min1"], r["max1"]], ["hit-skill", "3", "100", "1"])  # its skill has an ItemEffect
        self.assertEqual([r["prop1 (N)"], r["par1 (N)"], r["min1 (N)"]], ["aura", "2", "1"])  # not an event (bug #31's aura is a plugin guard)

    def test_no_gap_before_later_properties(self):
        """dark_master1 (Imperius) in Hell: hit-skill, the emptied att-skill, aura, death-skill -> no empty place before the last
        property (D2R stopped at the gap: no aura, no death skill, bug #620)."""
        cols = [f"{n}{i} (H)" for i in (1, 2, 3, 4, 5, 6) for n in ("prop", "chance", "par", "min", "max")]
        row = ["dark_master1", "hit-skill", "", "3", "100", "1", "", "", "", "", "", "aura", "", "2", "12", "12",
               "death-skill", "", "3", "100", "3", "", "", "", "", "", "", "", "", "", ""]
        tm.monprop_close_gaps(["Id"] + cols, row, " (H)")
        r = dict(zip(["Id"] + cols, row))
        self.assertEqual([r[f"prop{i} (H)"] for i in range(1, 7)], ["hit-skill", "aura", "death-skill", "", "", ""])
        self.assertEqual([r["par3 (H)"], r["min3 (H)"], r["max3 (H)"]], ["3", "100", "3"])

    def test_report(self):
        self.mig.monprop_event_skills()
        self.assertIn("emptied: 2: hornedgods prop1 death-skill 1, hornedgods prop1 (N) death-skill Living Flame", self.mig.report[-1])


if __name__ == "__main__":
    unittest.main()
