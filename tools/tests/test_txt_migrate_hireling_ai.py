"""monstats aip1-4 of the Hireable AI rows from D2R's rows (bug #534): D2R's Hireable AI reads the range type and the basic
attack (Skill[aip2], else mode aip3) from them; Median's 1.13c rows leave them empty, a basic attack in mode 0."""
import importlib.util
import sys
import tempfile
import unittest
import unittest.mock
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))
import projtemp  # noqa: E402,F401  (temp files stay inside the project, tools/projtemp.py)
spec = importlib.util.spec_from_file_location("txt_migrate", TOOLS / "txt_migrate.py")
tm = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tm)

AIP = [f"aip{n}{d}" for n in range(1, 5) for d in ("", "(N)", "(H)")]
COLS = ["Id", "AI", "Skill1", "aidel"] + AIP


def row(mid, ai, skill, aidel, *aip):
    cells = [v for v in aip for _ in range(3)]
    return [mid, ai, skill, aidel] + cells + [""] * (len(AIP) - len(cells))


def tsv(*rows):
    return "\r\n".join("\t".join(r) for r in rows) + "\r\n"


class HirelingAiParamTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        self.out, self.d2r = root / "out", root / "d2r"
        for bank in ("base", ""):
            d = self.out / "data" / "global" / "excel" / bank
            d.mkdir(parents=True, exist_ok=True)
            (d / "monstats.txt").write_text(tsv(
                COLS,
                row("roguehire", "Hireable", "RogueMissile", "3"),
                row("act2hire", "Hireable", "Jab", "3", "1"),
                row("skeleton1", "Skeleton", "", "3", "40", "20"),
                row("mxlhire", "Hireable", "", "3", "1")), encoding="utf-8")
            e = self.d2r / bank
            e.mkdir(parents=True, exist_ok=True)
            (e / "monstats.txt").write_text(tsv(
                COLS,
                row("roguehire", "Hireable", "RogueMissile", "1", "1", "1", "", "1"),
                row("act2hire", "Hireable", "Jab", "1", "2", "", "4"),
                row("skeleton1", "Skeleton", "", "1", "50", "10")), encoding="utf-8")
        tm.OUT, tm.D2R = self.out, self.d2r
        self.mig = tm.Migrator.__new__(tm.Migrator)
        self.mig.report = []

    def rows(self, bank):
        h, rows = tm.read_tsv(self.out / "data" / "global" / "excel" / bank / "monstats.txt")
        return {r[0]: dict(zip(h, r)) for r in rows if any(r)}

    def test_hireable_rows_take_d2r_params(self):
        self.mig.hireling_ai_params()
        for bank in ("base", ""):
            r = self.rows(bank)
            self.assertEqual([r["roguehire"][f"aip{n}(H)"] for n in range(1, 5)], ["1", "1", "", "1"])
            self.assertEqual([r["act2hire"][f"aip{n}"] for n in range(1, 5)], ["2", "", "4", ""])
            self.assertEqual(r["act2hire"]["aip3(N)"], "4")

    def test_other_columns_and_rows_stay(self):
        self.mig.hireling_ai_params()
        r = self.rows("")
        self.assertEqual((r["roguehire"]["aidel"], r["act2hire"]["Skill1"]), ("3", "Jab"))
        self.assertEqual((r["skeleton1"]["aip1"], r["skeleton1"]["aip2"]), ("40", "20"))
        self.assertEqual(r["mxlhire"]["aip1"], "1")  # no D2R row of that Id: left alone

    def test_switch_off_keeps_median(self):
        with unittest.mock.patch.dict(tm.os.environ, {"MXL2012_HIRELING_AIP": "0"}):
            self.mig.hireling_ai_params()
        self.assertEqual(self.rows("")["act2hire"]["aip1"], "1")
        self.assertIn("kept Median's", self.mig.report[-1])

    def test_report(self):
        self.mig.hireling_ai_params()
        self.assertIn("Hireable aip1-4", self.mig.report[-1])
        self.assertIn("base roguehire, act2hire", self.mig.report[-1])


if __name__ == "__main__":
    unittest.main()
