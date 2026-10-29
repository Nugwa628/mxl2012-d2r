"""Item rules lane rules-items2 (docs/median-rules-audit.md, items): misc `auto prefix` kept for D2R's shared item field
list (bug #310) and cube inputs that name nothing emptied as 1.13c compiles them (bug #311)."""
import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))
import projtemp  # noqa: E402,F401  (temp files stay inside the project, tools/projtemp.py)
from cube_reference_audit import unresolved_inputs  # noqa: E402
spec = importlib.util.spec_from_file_location("txt_migrate", TOOLS / "txt_migrate.py")
tm = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tm)


def write(path: Path, header: list[str], *rows: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(("\r\n".join("\t".join(r) for r in [header, *rows]) + "\r\n").encode("utf-8"))


class ExtraColumnsTests(unittest.TestCase):
    def test_misc_gets_auto_prefix_before_eol(self):
        h, rows = tm.with_extra_columns("misc", ["name", "code", "*eol"], [["Amulet", "amu", "0"]])
        self.assertEqual(h, ["name", "code", "auto prefix", "*eol"])
        self.assertEqual(rows, [["Amulet", "amu", "", "0"]])

    def test_without_eol_appends(self):
        h, rows = tm.with_extra_columns("misc", ["name", "code"], [["Amulet", "amu"]])
        self.assertEqual((h, rows), (["name", "code", "auto prefix"], [["Amulet", "amu", ""]]))

    def test_other_tables_and_present_columns_unchanged(self):
        for table, h in (("weapons", ["code", "auto prefix", "*eol"]), ("misc", ["code", "auto prefix", "*eol"])):
            rows = [["axe", "1", "0"]]
            self.assertEqual(tm.with_extra_columns(table, h, rows), (h, rows))


class CubeInputTests(unittest.TestCase):
    KNOWN = {"l@l", "m@m", "o@o", "jew", "weap", "BossKillerRing"}

    def test_only_inputs_naming_nothing(self):
        rows = [{"input 1": "l@l", "input 2": "m@m", "input 3": "o^o", "input 6": "BossKillerRing", "output": "nothing"},
                {"input 1": '"jew,qty=3"', "input 2": '"weap,noe,uni"', "output": "useitem"}]
        self.assertEqual(unresolved_inputs(rows, self.KNOWN), [(1, "input 3", "o^o")])

    def test_migrate_step_empties_the_cell_in_both_banks(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp)
            ch = ["description", "numinputs", "input 1", "input 2", "input 3", "output"]
            for bank in ("base", ""):
                d = out / "data" / "global" / "excel" / bank
                write(d / "cubemain.txt", ch, ["upgrade dark ring", "3", "l@l", "o^o", "m@m", "r@r"],
                      ["gems", "2", '"jew,qty=2"', "", "", "jew"])
                write(d / "misc.txt", ["name", "code"], ["a", "l@l"], ["b", "m@m"], ["c", "jew"])
                for t in ("weapons", "armor"):
                    write(d / f"{t}.txt", ["name", "code"])
                write(d / "itemtypes.txt", ["ItemType", "Code"], ["Jewel", "jewl"])
                write(d / "uniqueitems.txt", ["index", "code"])
                write(d / "setitems.txt", ["index", "item"])
            m = tm.Migrator.__new__(tm.Migrator)
            m.report = []
            old, tm.OUT = tm.OUT, out
            try:
                m.cube_unresolved_inputs()
            finally:
                tm.OUT = old
            for bank in ("base", ""):
                h, rows = tm.read_tsv(out / "data" / "global" / "excel" / bank / "cubemain.txt")
                self.assertEqual(rows[0], ["upgrade dark ring", "3", "l@l", "", "m@m", "r@r"])  # numinputs kept
                self.assertEqual(rows[1], ["gems", "2", '"jew,qty=2"', "", "", "jew"])
            self.assertEqual(len(m.report), 1)
            self.assertIn("row 1 (upgrade dark ring) input 2 'o^o'", m.report[0])


if __name__ == "__main__":
    unittest.main()
