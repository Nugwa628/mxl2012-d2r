"""Bug #51: a skill on D2R's client nova (cltdofunc 25) without a cltmissilea asserts `nMissile >= 0` and draws nothing; skill_rules
empties its cltdofunc. Rows with a client missile keep the function."""
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
        "cltmissilea", "aura", "passivestate", "passivestat1", "anim", "seqtrans", "rightskill"]


def tsv(*rows):
    return "\r\n".join("\t".join(r) for r in rows) + "\r\n"


def row(name, sid, cltdo, cltmis):
    r = dict.fromkeys(COLS, "")
    r.update({"skill": name, "*Id": sid, "srvdofunc": "68", "cltdofunc": cltdo, "cltmissilea": cltmis, "anim": "SC", "seqtrans": "SC"})
    return [r[c] for c in COLS]


class ClientNovaTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        root = Path(self.temp.name)
        tm.OUT, tm.D2R = root / "out", root / "d2r"
        for bank in ("base", ""):
            d = tm.OUT / "data" / "global" / "excel" / bank
            d.mkdir(parents=True, exist_ok=True)
            (d / "skills.txt").write_text(tsv(COLS, row("Nova", "48", "25", "nova"), row("Black Mass", "615", "25", ""),
                                              row("Other", "700", "31", "")), encoding="utf-8")
            e = tm.D2R / bank
            e.mkdir(parents=True, exist_ok=True)
            (e / "skills.txt").write_text(tsv(COLS, row("Nova", "48", "25", "nova")), encoding="utf-8")
        self.mig = tm.Migrator.__new__(tm.Migrator)
        self.mig.report = []

    def test_nova_without_client_missile_loses_the_function(self):
        self.mig.skill_rules()
        for bank in ("base", ""):
            _, rows = tm.read_tsv(tm.OUT / "data" / "global" / "excel" / bank / "skills.txt")
            got = {r[0]: r[COLS.index("cltdofunc")] for r in rows if r[0]}
            self.assertEqual(got, {"Nova": "25", "Black Mass": "", "Other": "31"})
        self.assertIn("Black Mass", " ".join(self.mig.report))


if __name__ == "__main__":
    unittest.main()
