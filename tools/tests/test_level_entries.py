"""Bug #120: levels.txt LevelEntry (the red "Entering ..." banner) must not be blank on a named level: D2R draws "Missing string"
(the Rogue Encampment on game start). txt_migrate.level_entries fills it, text_audit's blank-key finds a blank one."""
import importlib.util
import sys
import tempfile
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))
import projtemp  # noqa: E402,F401  (temp files stay inside the project, tools/projtemp.py)
import text_audit as ta  # noqa: E402

spec = importlib.util.spec_from_file_location("txt_migrate", TOOLS / "txt_migrate.py")
tm = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tm)

HEAD = ["Name", "Id", "LevelName", "LevelWarp", "LevelEntry"]


def tsv(*rows):
    return ("\r\n".join("\t".join(r) for r in rows) + "\r\n").encode("utf-8")  # bytes: write_text would make \r\r\n


class LevelEntriesMigrate(unittest.TestCase):
    def setUp(self):
        temp = tempfile.TemporaryDirectory()
        self.addCleanup(temp.cleanup)
        root = Path(temp.name)
        self.out, d2r = root / "out", root / "d2r"
        for bank in ("base", ""):
            d = self.out / "data" / "global" / "excel" / bank
            d.mkdir(parents=True, exist_ok=True)
            (d / "levels.txt").write_bytes(tsv(HEAD, ["Null", "0", "", "", ""],
                                              ["Act 1 - Town", "1", "Rogue Encampment", "To The Rogue Encampment", ""],
                                              ["Act 1 - Wilderness 1", "2", "Bloody Moor", "", ""],
                                              ["Act 5 - Summit", "3", "ColossalSummit", "", "EnteringTheColossalSummit"],
                                              ["Median Town", "4", "Caldeum", "", ""]))
            (d2r / bank).mkdir(parents=True, exist_ok=True)
            (d2r / bank / "levels.txt").write_bytes(tsv(HEAD, ["Null", "0", "", "", ""],
                                                       ["Act 1 - Town", "1", "Rogue Encampment", "", "EnteringTheRogueEncampment"],
                                                       ["Act 1 - Wilderness 1", "2", "Blood Moor", "", "EnteringTheBloodMoor"]))
        self._old = tm.OUT, tm.D2R
        self.addCleanup(lambda: (setattr(tm, "OUT", self._old[0]), setattr(tm, "D2R", self._old[1])))
        tm.OUT, tm.D2R = self.out, d2r
        self.mig = tm.Migrator.__new__(tm.Migrator)
        self.mig.report = []

    def entries(self, bank):
        _, rows = tm.read_tsv(self.out / "data" / "global" / "excel" / bank / "levels.txt")
        return {r[1]: r[4] for r in rows}

    def test_blank_entries_are_filled(self):
        self.mig.level_entries()
        for bank in ("base", ""):
            e = self.entries(bank)
            self.assertEqual(e["1"], "EnteringTheRogueEncampment")  # D2R's level, same name: D2R's key
            self.assertEqual(e["2"], "Bloody Moor")  # renamed level: D2R's text would name another place
            self.assertEqual(e["3"], "EnteringTheColossalSummit")  # a set cell stays
            self.assertEqual(e["4"], "Caldeum")  # Median-only level: its name
            self.assertEqual(e["0"], "")  # the Null row has no name and no banner
        self.assertIn("2 with D2R's key", " ".join(self.mig.report))  # one per bank


class LevelEntriesAudit(unittest.TestCase):
    def test_blank_entry_of_a_named_level_is_a_finding(self):
        with tempfile.TemporaryDirectory() as t:
            folder = Path(t)
            (folder / "levels.txt").write_bytes(tsv(HEAD, ["Null", "0", "", "", ""],
                                                   ["Act 1 - Town", "1", "Rogue Encampment", "To The Rogue Encampment", ""],
                                                   ["Act 1 - Wilderness 1", "2", "Blood Moor", "", "EnteringTheBloodMoor"]))
            strings = ta.Strings({"Rogue Encampment": "Rogue Encampment", "To The Rogue Encampment": "To The Rogue Encampment",
                                  "Blood Moor": "Blood Moor", "EnteringTheBloodMoor": "Entering The Blood Moor"}, own=set())
            found = ta.audit_table(folder / "levels.txt", "levels", "rotw", strings, ta.Counter())
        self.assertEqual([(f.kind, f.column, f.where) for f in found], [("blank-key", "levelentry", "rotw levels.txt row 3")])


if __name__ == "__main__":
    unittest.main()
