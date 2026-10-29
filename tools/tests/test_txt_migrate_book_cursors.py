"""Bug #485: a Scroll / Tome of Identify right clicked did nothing on D2R. 1.13c takes a scroll's or tome's cursor from books.txt
`SpellIcon` (0 = identify cursor), D2R from misc `spellicon`, where Median XL 2012 writes -1. book_spell_icons maps the books rows
to the misc codes; the build gives `isc` / `ibk` spellicon 0 and keeps -1 for the Town Portal pair."""
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

# Median XL 2012's books.txt (merged by row; the build drops Namco / Completed)
HEADER = ["Name", "ScrollSpellCode", "BookSpellCode", "pSpell", "SpellIcon", "ScrollSkill", "BookSkill", "BaseCost", "CostPerCharge"]
ROWS = [["unused", "tsc", "tbk", "2", "-1", "Scroll of Townportal", "Book of Townportal", "250", "50"],
        ["unused", "isc", "ibk", "1", "0", "Scroll of Identify", "Book of Identify", "200", "40"],
        ["unused", "", "", "", "-1", "", "", "500", "100"]]


class BookCursorTests(unittest.TestCase):
    def test_identify_pair_gets_the_identify_cursor(self):
        icons = tm.book_spell_icons(HEADER, ROWS)
        self.assertEqual(icons["isc"], "0")
        self.assertEqual(icons["ibk"], "0")

    def test_town_portal_pair_keeps_no_cursor(self):
        icons = tm.book_spell_icons(HEADER, ROWS)
        self.assertEqual((icons["tsc"], icons["tbk"]), ("-1", "-1"))

    def test_row_without_codes_names_nothing(self):
        self.assertEqual(set(tm.book_spell_icons(HEADER, ROWS)), {"tsc", "tbk", "isc", "ibk"})

    def test_blank_or_text_icon_is_skipped(self):
        rows = [["x", "isc", "ibk", "1", "", "", "", "", ""], ["y", "tsc", "", "2", "abc", "", "", "", ""]]
        self.assertEqual(tm.book_spell_icons(HEADER, rows), {})

    def test_no_spellicon_column(self):
        self.assertEqual(tm.book_spell_icons(["Name", "ScrollSpellCode"], [["a", "isc"]]), {})

    def test_built_misc_rows(self):
        """The built tables (when tools/build.py ran in this checkout): isc / ibk 0, tsc / tbk -1, as D2R's own rows."""
        excel = TOOLS.parent / "work" / "mod" / "data" / "global" / "excel"
        for bank in ("base", ""):
            misc = excel / bank / "misc.txt"
            if not misc.exists():
                self.skipTest("no build in work/mod")
            h, rows = tm.read_tsv(misc)
            got = {r[h.index("code")]: r[h.index("spellicon")] for r in rows if r and r[h.index("code")] in ("isc", "ibk", "tsc", "tbk")}
            self.assertEqual(got, {"isc": "0", "ibk": "0", "tsc": "-1", "tbk": "-1"}, bank or "rotw")


if __name__ == "__main__":
    unittest.main()
