"""The Stat Book's data (tools/statbook.py): the page file's checks, the book records, the plain D2R book compiled into the
plugin kept up to date, and the D2R-XL 2012 book's stats all in the built mod."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import projtemp  # noqa: E402,F401  (temp files stay inside the project, tools/projtemp.py)
import statbook as sb  # noqa: E402

IDS = {"a": 1, "b": 2, "maxb": 3, "item_addclassskills": 83}


def recs(rows):
    dropped = []
    return sb.page_records([r.split("\t") for r in rows], IDS, dropped), dropped


class Formats(unittest.TestCase):
    def test_allowed(self):
        sb.check_format("%+d%%", 1)
        sb.check_format("%d-%d", 2)
        sb.check_format("yesno", 1)

    def test_refused(self):
        for fmt, n in (("%s", 1), ("%d", 2), ("%d %d", 1), ("%x%%", 1), ("yesno", 2)):
            with self.assertRaises(ValueError, msg=fmt):
                sb.check_format(fmt, n)


class Records(unittest.TestCase):
    def test_row_record(self):
        out, dropped = recs(["page\tp\tP", "section\tp\tS", "row\tp\tB\tb,maxb\t%d%% (max %d%%)\tr\t75+maxb<=95\t0,75"])
        self.assertEqual(out, ["page\tp\tP", "section\tS", "row\tB\t2,3\t%d%% (max %d%%)\tr\t75+3<=95\t0,75\tf"])
        self.assertEqual(dropped, [])

    def test_half_and_class_param(self):
        out, _ = recs(["page\tp\tP", "section\tp\tS", "row\tp\tSkills\titem_addclassskills:class\t%+d\tblue"])
        self.assertEqual(out[-1], "row\tSkills\t83:c\t%+d\tblue\t-\t-\th")

    def test_missing_stats_drop_rows_sections_pages(self):
        out, dropped = recs(["page\tp\tP", "section\tp\tS", "row\tp\tA\ta\t%d\tw", "section\tp\tGone", "row\tp\tX\tnope\t%d\tw",
                             "page\tq\tQ", "section\tq\tS", "row\tq\tY\tnope\t%d\tw"])
        self.assertEqual(out, ["page\tp\tP", "section\tS", "row\tA\t1\t%d\tw\t-\t-\th"])
        self.assertEqual(dropped, ["X", "Y"])

    def test_bad_rows(self):
        for row in ("row\tp\tA\ta\t%d\tpink", "row\tp\tA\ta,b,maxb\t%d %d %d\tw", "row\tp\tA\ta\t%d\tw\t\t0,1",
                    "row\tp\tA\ta:2\t%d\tw", "row\tp\tA\ta\t%d\tw\t75+b"):
            with self.assertRaises(ValueError, msg=row):
                recs(["page\tp\tP", "section\tp\tS", row])
        with self.assertRaises(ValueError):
            recs(["page\tp\tP", "section\tq\tS"])


class Books(unittest.TestCase):
    def test_default_book_up_to_date(self):
        try:
            isc = sb.d2r_isc()
        except Exception as e:  # noqa: BLE001
            self.skipTest(f"no D2R extract: {e}")
        if not isc.is_file():
            self.skipTest("no D2R extract")
        self.assertEqual(sb.main(["check"]), 0)

    def test_pages_file_is_valid(self):
        names = {s.split(":")[0] for r in sb.read_tsv(sb.PAGES_TSV) if r[0] == "row" for s in r[3].split(",")}
        ids = {n: i for i, n in enumerate(sorted(names | {"maxfireresist"}))}
        dropped = []
        out = sb.page_records(sb.read_tsv(sb.PAGES_TSV), {**ids, **{f"max{e}resist": 0 for e in ("fire", "cold", "light", "poison", "magic")}},
                              dropped)
        self.assertEqual(dropped, [])
        self.assertEqual([r.split("\t")[2] for r in out if r.startswith("page\t")],
                         ["Offense", "Spells", "Defense", "Resistances", "Skills & Procs", "Utility"])

    def test_median_book_has_every_row(self):
        if not sb.BUILT_ISC.is_file():
            self.skipTest("no built mod (tools/build.py)")
        dropped = []
        text = sb.book_text(sb.stat_ids(sb.BUILT_ISC), dropped)
        self.assertEqual(dropped, [])
        self.assertTrue(text.startswith("statbook\t1\n"))


if __name__ == "__main__":
    unittest.main()
