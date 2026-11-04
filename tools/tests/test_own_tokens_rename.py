"""Unit tests of tools/own_tokens.py `rename` and the numeric token guard (bug #532, the Fell Fiends' `08`), synthetic data.
Run: py -3 -I -m unittest discover -s tools/tests -p "test_own_tokens_rename.py" """
import sys
import tempfile
import unittest
from unittest import mock
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import projtemp  # noqa: E402,F401  (temp files stay inside the project, tools/projtemp.py)
import own_tokens as ot  # noqa: E402
from txt_migrate import read_tsv  # noqa: E402
from test_own_tokens import cof, dcc, put, tsv, TR, MS  # noqa: E402

RENAME = {"mode": "rename", "old": "08", "new": "FZ", "rows": ["fellfiend1", "fellfiend2"], "why": "t"}
OBJ = ["Class", "Id", "Token"]


class RenameTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        t = Path(self.temp.name)
        self.med, self.d2r, self.excel = t / "med", t / "d2r", t / "excel"
        for bank in ("base", ""):
            d = self.excel / bank
            d.mkdir(parents=True, exist_ok=True)
            (d / "monstats.txt").write_text(tsv(MS, ["fellfiend1", "1604", "08", "fellfiend1"],
                                                ["fellfiend2", "1605", "08", "fellfiend2"],
                                                ["putriddefiler1", "45", "45", "putriddefiler1"],
                                                ["Expansion", "", "", ""]), encoding="utf-8")
            (d / "objects.txt").write_text(tsv(OBJ, ["chest", "1", "C1"], ["Expansion", "", ""]), encoding="utf-8")

    def test_row_token_and_art_token(self):
        self.assertEqual(ot.row_token("fellfiend1", "08", [RENAME]), "FZ")
        self.assertEqual(ot.row_token("putriddefiler1", "45", [RENAME]), "45")
        # the HD tools key the art by Median's token: the raw Code and the built one both give 08
        self.assertEqual(ot.art_token("fellfiend1", "08", [RENAME]), "08")
        self.assertEqual(ot.art_token("fellfiend2", "FZ", [RENAME]), "08")
        self.assertEqual(ot.art_token("putriddefiler1", "45", [RENAME]), "45")

    def test_tables_rewrite_the_rows_and_clear_the_guard(self):
        self.assertEqual(len(ot.numeric_tokens(self.excel)), 4)        # two rows, both banks
        lines = ot.apply_tables(self.excel, [RENAME])
        self.assertEqual(len(lines), 2)
        self.assertTrue(all("rename 08 -> FZ" in ln for ln in lines))
        for bank in ("base", ""):
            _, rows = read_tsv(self.excel / bank / "monstats.txt")
            codes = {r[0]: r[2] for r in rows}
            self.assertEqual((codes["fellfiend1"], codes["fellfiend2"], codes["putriddefiler1"]), ("FZ", "FZ", "45"))
        self.assertEqual(ot.numeric_tokens(self.excel), [])
        ot.apply_tables(self.excel, [RENAME])                              # a second run finds them done

    def test_plan_moves_every_median_file_and_animdata_record(self):
        put(self.med, "08/cof/08nuhth.cof", cof(12, [(TR, "hth")]))
        put(self.med, "08/cof/08ddhth.cof", cof(1, [(TR, "hth")]))
        put(self.med, "08/tr/08trlitnuhth.dcc", dcc(12))
        put(self.med, "08/tr/08trlitddhth.dcc", dcc(1))
        put(self.d2r, "zm/cof/zmnuhth.cof", cof(8, [(TR, "hth")]))
        plan = ot.make_plan([RENAME], self.med, self.d2r, self.excel)
        self.assertEqual(sorted(plan.ops), ["fz/cof/fzddhth.cof", "fz/cof/fznuhth.cof", "fz/tr/fztrlitddhth.dcc",
                                            "fz/tr/fztrlitnuhth.dcc"])
        self.assertEqual({o.origin for o in plan.ops.values()}, {"median"})
        self.assertEqual(plan.moved["08/cof/08ddhth.cof"], "fz/cof/fzddhth.cof")
        self.assertEqual({(a.name, a.source, a.frames) for a in plan.anims}, {("FZNUHTH", "08NUHTH", 12), ("FZDDHTH", "08DDHTH", 1)})

    def test_new_token_with_files_is_refused(self):
        put(self.med, "08/cof/08nuhth.cof", cof(12, [(TR, "hth")]))
        put(self.d2r, "fz/cof/fznuhth.cof", cof(8, [(TR, "hth")]))
        with self.assertRaises(SystemExit):
            ot.make_plan([RENAME], self.med, self.d2r, self.excel)


class GuardTests(unittest.TestCase):
    def test_numeric_token(self):
        for tok in ("08", "00", "012", " 08"):
            self.assertTrue(ot.numeric_token(tok), tok)
        for tok in ("45", "40", "0A", "0n", "8", "0", "FZ", "", "8@"):
            self.assertFalse(ot.numeric_token(tok), tok)

    def test_objects_token_is_checked_too(self):
        with tempfile.TemporaryDirectory() as t:
            excel = Path(t)
            (excel / "base").mkdir()
            (excel / "base" / "objects.txt").write_text(tsv(OBJ, ["barrel", "3", "07"], ["chest", "1", "C1"]), encoding="utf-8")
            self.assertEqual(ot.numeric_tokens(excel), ["base/objects.txt barrel: Token 07"])

    def test_tables_command_fails_on_a_numeric_token(self):
        with tempfile.TemporaryDirectory() as t:
            excel = Path(t)
            for bank in ("base", ""):
                (excel / bank).mkdir(exist_ok=True)
                (excel / bank / "monstats.txt").write_text(tsv(MS, ["imp", "9", "07", "imp"]), encoding="utf-8")
            with mock.patch.object(ot, "load", return_value=[]):
                self.assertEqual(ot.main(["tables", "--excel", str(excel)]), 1)

    def test_committed_rename_covers_the_fell_fiends(self):
        e = next(x for x in ot.load() if x["mode"] == "rename" and x["old"] == "08")
        self.assertEqual(sorted(e["rows"]), ["baalset_fellfiend2", "fellfiend1", "fellfiend2"])
        self.assertFalse(ot.numeric_token(e["new"]))
        self.assertEqual(len(e["new"]), 2)
        self.assertFalse(e["new"].isdigit())


if __name__ == "__main__":
    unittest.main()
