"""Chronicle step and the inventory "larger grid" rule on synthetic tables (no game files).
Run: py -3 -I -m unittest discover -s tools/tests -p "test_chronicle.py" """
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import projtemp  # noqa: E402,F401  (temp files stay inside the project, tools/projtemp.py)
import chronicle  # noqa: E402
import txt_migrate  # noqa: E402
import ui_check  # noqa: E402

TYPES_HEAD = ["ItemType", "Code", "Equiv1", "Equiv2", "UICategory", "RunewordCategory1", "RunewordCategory2"]


def write(path: Path, head: list[str], rows: list[list[str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join("\t".join(r) for r in [head, *rows]) + "\n", encoding="utf-8")


class ChronicleTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.mod, self.d2r = root / "mod", root / "d2r"
        x, d = self.mod / chronicle.EXCEL, self.d2r / chronicle.EXCEL
        write(d / "itemtypes.txt", TYPES_HEAD, [
            ["Weapon", "weap", "", "", "", "r_mis", "r_mel"], ["Melee", "mele", "weap", "", "", "r_mel", ""],
            ["Sword", "swor", "mele", "", "sword", "r_mel", ""], ["Armor", "tors", "armo", "", "armor", "r_arm", ""],
            ["Any Armor", "armo", "", "", "", "r_arm", ""], ["Charm", "char", "misc", "", "charm", "", ""],
            ["Misc", "misc", "", "", "", "", ""], ["Quest", "ques", "", "", "", "", ""]])
        write(x / "itemtypes.txt", TYPES_HEAD, [
            ["Weapon", "weap", "", "", "", "", ""], ["Melee", "mele", "weap", "", "", "", ""],
            ["Sword", "swor", "mele", "", "", "", ""], ["2h sword", "2hsd", "swor", "", "", "", ""],
            ["Armor", "tors", "armo", "", "", "", ""], ["Any Armor", "armo", "", "", "", "", ""],
            ["Armor (Sacred)", "qtor", "tors", "ct2a", "", "", ""], ["Charm", "char", "misc", "", "", "", ""],
            ["Reward Charm", "grtz", "char", "", "", "", ""], ["Misc", "misc", "", "", "", "", ""],
            ["Mega Ring", "kill", "misc", "", "", "", ""], ["Odd", "oddt", "misc", "", "", "", ""],
            ["Grimoire", "grim", "", "", "warlo", "", ""], ["Quest", "ques", "", "", "", "", ""]])
        base = ["name", "code", "type", "quest", "UICatOverride"]
        write(x / "weapons.txt", base, [["Sword", "ssd", "swor", "", ""], ["Flamberge", "flb", "2hsd", "", ""],
                                         ["Quest staff", "hst", "swor", "1", ""]])
        write(x / "armor.txt", base, [["Sacred plate", "q01", "qtor", "", ""]])
        write(x / "misc.txt", base, [["Shadowfang", "sf1", "grtz", "", ""], ["Boss ring", "bkr", "kill", "", ""],
                                      ["Odd thing", "odd", "oddt", "", ""], ["Override", "ovr", "oddt", "", "rings"]])
        write(x / "uniqueitems.txt", ["index", "spawnable", "disableChronicle", "code"], [
            ["Edge", "1", "", "ssd"], ["Big", "1", "", "flb"], ["Plate", "1", "", "q01"], ["Fang", "1", "", "sf1"],
            ["Killer", "1", "", "bkr"], ["Odd", "1", "", "odd"], ["Ovr", "1", "", "ovr"], ["Staff", "1", "", "hst"],
            ["Placeholder", "", "", "ssd"], ["Off", "0", "", "ssd"], ["Gone", "1", "", "zzz"], ["", "", "", ""]])
        write(x / "setitems.txt", ["index", "spawnable", "disableChronicle", "item"], [
            ["Set A", "1", "1", "ssd"], ["Set B", "1", "", "lrg"], ["Expansion", "", "", ""]])
        write(x / "runes.txt", ["Name", "complete"], [["Fennec", "1"], ["Fennec", "1"], ["Off", ""]])
        self.lines = chronicle.run(self.mod, self.d2r)
        self.x = x

    def tearDown(self):
        self.tmp.cleanup()

    def column(self, table: str, key: str, col: str) -> dict[str, str]:
        t = chronicle.Table(self.x / f"{table}.txt")
        return {t.get(r, t.col(key)): t.get(r, t.col(col)) for r in t.rows if t.get(r, t.col(key))}

    def test_categories_from_d2r_and_equiv_chain(self):
        ui = self.column("itemtypes", "Code", "UICategory")
        self.assertEqual(ui["swor"], "sword")      # D2R's value for D2R's code
        self.assertEqual(ui["2hsd"], "sword")      # inherited up the Equiv chain
        self.assertEqual(ui["qtor"], "armor")
        self.assertEqual(ui["grtz"], "charm")
        self.assertEqual(ui["kill"], "rings")      # EXTRA_CATEGORIES
        self.assertEqual(ui["oddt"], "")           # nothing to inherit
        self.assertEqual(ui["grim"], "warlo")      # existing value kept

    def test_runeword_categories_resolve_as_a_pair(self):
        c1, c2 = (self.column("itemtypes", "Code", c) for c in ("RunewordCategory1", "RunewordCategory2"))
        self.assertEqual((c1["swor"], c2["swor"]), ("r_mel", ""))   # not weap's second category
        self.assertEqual((c1["2hsd"], c2["2hsd"]), ("r_mel", ""))
        self.assertEqual((c1["weap"], c2["weap"]), ("r_mis", "r_mel"))
        self.assertEqual(c1["qtor"], "r_arm")

    def test_disable_chronicle(self):
        dc = self.column("uniqueitems", "index", "disableChronicle")
        self.assertEqual({k: v for k, v in dc.items() if v == "0"}, {"Edge": "0", "Big": "0", "Plate": "0", "Fang": "0",
                                                                      "Killer": "0", "Ovr": "0"})
        for name in ("Odd", "Staff", "Placeholder", "Off", "Gone"):  # no category, quest, unspawnable x2, no base
            self.assertEqual(dc[name], "1", name)
        sets = self.column("setitems", "index", "disableChronicle")
        self.assertEqual(sets, {"Set A": "0", "Set B": "1", "Expansion": ""})

    def test_idempotent_and_report(self):
        again = chronicle.run(self.mod, self.d2r)
        self.assertFalse([line for line in again if line.startswith("wrote")])
        self.assertIn("runes: 2 complete rows, 1 names (each row is one Chronicle entry)", self.lines)
        self.assertTrue((self.mod / "chronicle_report.md").exists())


class LargerGridTests(unittest.TestCase):
    def test_txt_migrate_rule(self):
        self.assertTrue(txt_migrate.larger_grid(("10", "6"), ("10", "4")))
        self.assertFalse(txt_migrate.larger_grid(("10", "10"), ("10", "10")))   # tie: D2R's
        self.assertFalse(txt_migrate.larger_grid(("6", "4"), ("10", "4")))
        self.assertFalse(txt_migrate.larger_grid(("-1", "-1"), ("0", "0")))

    def test_panel_choices(self):
        mod = {"Amazon": (10, 6), "Transmogrify Box Page 1": (10, 8), "Big Bank Page 1": (10, 10)}
        d2r = {"Amazon": (10, 4), "Transmogrify Box Page 1": (3, 4), "Big Bank Page 1": (10, 10), "Monster": (10, 10)}
        rows = {p: c for p, _m, _d, c in ui_check.panel_choices(mod, d2r)}
        self.assertEqual(rows["Player inventory"], "10 x 6 (Median)")
        self.assertEqual(rows["Horadric Cube"], "10 x 8 (Median)")
        self.assertEqual(rows["Personal stash"], "10 x 10 (D2R)")
        self.assertEqual(rows["Vendor"], "10 x 10 (D2R)")


if __name__ == "__main__":
    unittest.main()
