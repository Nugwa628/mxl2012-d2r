"""Bug #527: D2R's charge release takes the finishing skill's `prgchargesconsumed` off the charges (a D2R-only column, blank = 0),
so Median's finishers (Attack included) never spent Batstrike's charges. skill_rules gives every finishing row without a value
all charges (1.13c's rule); a row that has a value and non-finishing rows keep theirs."""
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

COLS = ["skill", "*Id", "srvstfunc", "srvdofunc", "srvstopfunc", "srvmissile", "srvmissilea", "cltstfunc", "cltdofunc", "cltstopfunc",
        "cltmissilea", "aura", "passivestate", "passivestat1", "anim", "seqtrans", "rightskill", "finishing", "progressive",
        "prgchargesconsumed"]


def tsv(*rows):
    return "\r\n".join("\t".join(r) for r in rows) + "\r\n"


def row(name, sid, finishing="", progressive="", consumed=""):
    r = dict.fromkeys(COLS, "")
    r.update({"skill": name, "*Id": sid, "srvdofunc": "1", "anim": "A1", "seqtrans": "A1", "finishing": finishing,
              "progressive": progressive, "prgchargesconsumed": consumed})
    return [r[c] for c in COLS]


class FinishingConsumesTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        tm.OUT, tm.D2R = root / "out", root / "d2r"
        for bank in ("base", ""):
            d = tm.OUT / "data" / "global" / "excel" / bank
            d.mkdir(parents=True, exist_ok=True)
            (d / "skills.txt").write_text(tsv(COLS, row("Attack", "0", finishing="1"), row("Crucify", "400", finishing="1", consumed="0"),
                                              row("Kept", "401", finishing="1", consumed="2"),
                                              row("Batstrike", "326", progressive="1")), encoding="utf-8")
            e = tm.D2R / bank
            e.mkdir(parents=True, exist_ok=True)
            (e / "skills.txt").write_text(tsv(COLS, row("Attack", "0", finishing="1", consumed="1")), encoding="utf-8")
        self.mig = tm.Migrator.__new__(tm.Migrator)
        self.mig.report = []

    def test_finishers_spend_all_charges(self):
        self.mig.skill_rules()
        for bank in ("base", ""):
            _, rows = tm.read_tsv(tm.OUT / "data" / "global" / "excel" / bank / "skills.txt")
            got = {r[0]: r[COLS.index("prgchargesconsumed")] for r in rows if r[0]}
            self.assertEqual(got, {"Attack": "3", "Crucify": "3", "Kept": "2", "Batstrike": ""})
        self.assertIn("2 finishing rows given prgchargesconsumed 3", " ".join(self.mig.report))


if __name__ == "__main__":
    unittest.main()
