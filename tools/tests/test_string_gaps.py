"""tools/string_gaps.py: the actions of data/string_gaps.tsv and the committed decisions (docs/text-audit.md)."""
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import projtemp  # noqa: E402,F401  (temp files stay inside the project, tools/projtemp.py)
import string_gaps as sg  # noqa: E402
import text_audit  # noqa: E402

HEAD = "table\tcolumn\tkey\taction\ttext\tcells\treason\n"


def tsv(d: Path, *rows: str) -> Path:
    p = d / "gaps.tsv"
    p.write_text(HEAD + "".join(r + "\n" for r in rows), encoding="utf-8")
    return p


class Loading(unittest.TestCase):
    def test_actions_texts_and_fixes(self):
        with tempfile.TemporaryDirectory() as d:
            rows = sg.load(tsv(Path(d),
                               "monstats\tnamestr\tCouatlInhibitor\ttext\tCouatl Inhibitor\t\tMedian's typo",
                               "objects\tname\tZoo\ttext\tZoo\t\tthe key is the word",
                               "\t\tPortalKombat\tfix\tPortal Kombat\t\tno space",
                               "monstats\tNameStr\tId=boneprison1\tcell\tskillname88\t\tblank name",
                               "misc\tspelldescstr\tGone\tempty\t\t\told"))
            self.assertEqual(sg.texts(rows), {"CouatlInhibitor": "Couatl Inhibitor", "Zoo": "Zoo"})
            self.assertEqual(sg.fixes(rows), {"PortalKombat": "Portal Kombat"})

    def test_bad_rows_are_refused(self):
        bad = ["monstats\tnamestr\tK\traw\tK\t\twhy",               # the old action: key as text is not allowed any more
               "monstats\tnamestr\tK\ttext\t\t\twhy",                # no text
               "monstats\tnamestr\tK\ttext\tK2\t\t",                 # no reason
               "monstats\tNameStr\tboneprison1\tcell\tx\t\twhy",     # cell key without column=value
               "monstats\tnamestr\tPortalKombat\tfix\tx\t\twhy"]     # fix names a table
        for row in bad:
            with tempfile.TemporaryDirectory() as d:
                with self.assertRaises(ValueError, msg=row):
                    sg.load(tsv(Path(d), row))

    def test_one_key_two_texts_is_refused(self):
        with tempfile.TemporaryDirectory() as d:
            with self.assertRaises(ValueError):
                sg.load(tsv(Path(d), "monstats\tnamestr\tK\ttext\tA\t\twhy", "pettype\tname\tK\ttext\tB\t\twhy"))

    def test_the_same_key_in_two_tables_may_repeat_its_text(self):
        with tempfile.TemporaryDirectory() as d:
            rows = sg.load(tsv(Path(d), "monstats\tnamestr\tK\ttext\tA\t\twhy", "pettype\tname\tK\ttext\tA\t\twhy"))
            self.assertEqual(sg.texts(rows), {"K": "A"})


class Applying(unittest.TestCase):
    def table(self, d: Path, name: str, lines: list[str]) -> Path:
        p = d / f"{name}.txt"
        p.write_bytes(("\r\n".join(lines) + "\r\n").encode("utf-8"))
        return p

    def test_cell_rows_set_one_cell_of_the_matching_row(self):
        with tempfile.TemporaryDirectory() as d:
            p = self.table(Path(d), "monstats", ["Id\tNameStr\tCode", "boneprison1\t\t67", "boneprison2\t\t66", "zombie\tZombie\t01"])
            rows = [{"table": "monstats", "column": "NameStr", "key": "Id=boneprison1", "action": "cell", "text": "skillname88",
                     "cells": "", "reason": "r"}]
            done = sg.apply_empty(Path(d), rows)
            self.assertEqual(done["monstats.namestr"], 1)
            self.assertEqual(p.read_bytes().decode().split("\r\n")[1:4], ["boneprison1\tskillname88\t67", "boneprison2\t\t66", "zombie\tZombie\t01"])
            self.assertEqual(sg.apply_empty(Path(d), rows)["monstats.namestr"], 0)   # idempotent

    def test_text_rows_with_cells_set_the_function_cells_of_the_line(self):
        with tempfile.TemporaryDirectory() as d:
            p = self.table(Path(d), "itemstatcost",
                           ["Stat\tdgrpfunc\tdgrpval\tdgrpstrpos\tdgrpstrneg", "a\t3\t0\tmxl2012:ModitemPeril\tmxl2012:ModitemPeril",
                            "b\t3\t0\tOther\tOther"])
            rows = [{"table": "itemstatcost", "column": c, "key": "ModitemPeril", "action": "text", "text": "to Melee Damage",
                     "cells": "dgrpfunc=4;dgrpval=1", "reason": "r"} for c in ("dgrpstrpos", "dgrpstrneg")]
            sg.apply_empty(Path(d), rows)
            self.assertEqual(p.read_bytes().decode().split("\r\n")[1:3],
                             ["a\t4\t1\tmxl2012:ModitemPeril\tmxl2012:ModitemPeril", "b\t3\t0\tOther\tOther"])

    def test_empty_still_empties_a_line_with_its_function_cells(self):
        with tempfile.TemporaryDirectory() as d:
            p = self.table(Path(d), "itemstatcost", ["Stat\tdescfunc\tdescval\tdescstrpos\tdescstrneg", "a\t1\t1\tGone\tGone"])
            rows = [{"table": "itemstatcost", "column": c, "key": "Gone", "action": "empty", "text": "", "cells": "", "reason": "r"}
                    for c in ("descstrpos", "descstrneg")]
            sg.apply_empty(Path(d), rows)
            self.assertEqual(p.read_bytes().decode().split("\r\n")[1], "a\t\t\t\t")


    def test_empty_matches_a_key_the_migration_qualified(self):
        with tempfile.TemporaryDirectory() as d:
            p = self.table(Path(d), "misc", ["code\tspelldesc\tspelldescstr", "0g3\t1\tmxl2012:PotFireReloadedDesc", "0g1\t1\tmxl2012:Kept"])
            rows = [{"table": "misc", "column": "spelldescstr", "key": "PotFireReloadedDesc", "action": "empty", "text": "", "cells": "",
                     "reason": "r"},
                    {"table": "misc", "column": "spelldesc", "key": "code=0g3", "action": "cell", "text": "0", "cells": "", "reason": "r"}]
            sg.apply_empty(Path(d), rows)
            self.assertEqual(p.read_bytes().decode().split("\r\n")[1:3], ["0g3\t0\t", "0g1\t1\tmxl2012:Kept"])

class CommittedDecisions(unittest.TestCase):
    rows = sg.load()

    def test_no_raw_row_is_left_and_every_row_has_a_reason(self):
        self.assertEqual({r["action"] for r in self.rows} - set(sg.ACTIONS), set())
        self.assertTrue(all(r["reason"].strip() for r in self.rows))

    def test_the_46_names_and_the_description_lines_are_all_text_rows(self):
        names = {r["key"] for r in self.rows if r["action"] == "text" and (r["table"], r["column"]) in {
            ("monstats", "namestr"), ("montype", "strplur"), ("objects", "name"), ("pettype", "name"), ("superuniques", "name"),
            ("levels", "levelwarp"), ("misc", "namestr")}}
        self.assertEqual(len(names), 46)
        lines = {r["key"] for r in self.rows if r["action"] == "text" and r["column"] in {"descstrpos", "descstrneg", "dgrpstrpos", "dgrpstrneg", "spelldescstr", "descstr"}}
        self.assertEqual(lines, {"ModitemColdSkills", "ModitemLevReq", "ModitemPeril", "mon_dark_ones"})

    def test_the_greater_elixirs_show_no_line_as_in_the_original(self):
        """Bug #104: Median's Greater Elixirs of Strength / Dexterity / Energy / Vitality name description keys no .tbl defines; the
        original's tooltip builder skips the line (1.14d 0x4863a8 compares the string with 5382), so the port shows none."""
        empty = {(r["table"], r["column"], r["key"]) for r in self.rows if r["action"] == "empty"}
        self.assertEqual(empty, {("misc", "spelldescstr", k) for k in (
            "PotFireReloadedDesc", "PotColdReloadedDex", "PotLtngReloadedDesc", "PotPoisReloadedDesc")})
        off = {r["key"] for r in self.rows if r["action"] == "cell" and r["column"] == "spelldesc" and r["text"] == "0"}
        self.assertEqual(off, {"code=0g3", "code=0g4", "code=0g5", "code=0g6"})
        nospell = {r["key"] for r in self.rows if r["action"] == "cell" and r["column"] == "pSpell" and r["text"] == "0"}
        self.assertEqual(nospell, off)  # the use does nothing, as the original's pSpell 9 handler with state -1 (D2R asserts and uses it up)
        self.assertFalse([r for r in self.rows if r["key"].startswith("PotFire") and r["action"] == "text"])

    def test_no_decision_reads_like_a_key(self):
        for key, text in {**sg.texts(self.rows), **sg.fixes(self.rows)}.items():
            self.assertFalse(text_audit.key_like(text, key), f"{key} -> {text!r}")
            self.assertFalse(text_audit.is_placeholder(text), f"{key} -> {text!r}")

    def test_the_stat_lines_name_a_wording_for_the_value(self):
        peril = [r for r in self.rows if r["key"] == "ModitemPeril"]
        self.assertTrue(peril and all(r["cells"] == "dgrpfunc=4;dgrpval=1" for r in peril))

    def test_docs_table_lists_every_decision(self):
        t = sg.docs_table(self.rows)
        for key in ("CouatlInhibitor", "ModitemLevReq", "New2PortalKombat", "Id=boneprison1"):
            self.assertIn(f"`{key}`", t)


if __name__ == "__main__":
    unittest.main()
