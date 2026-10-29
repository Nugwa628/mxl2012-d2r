"""Bug #20: modifierlist_skill (stat 350) must carry enough Send Bits for Median's skill ids (Blackstorm 514 > 9 bits)."""
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


def tsv(*rows):
    return "\r\n".join("\t".join(r) for r in rows) + "\r\n"


class StatSendBitsTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        self.out = Path(self.temp.name) / "out"
        self.make(1109)
        tm.OUT = self.out
        self.mig = tm.Migrator.__new__(tm.Migrator)
        self.mig.report = []

    def make(self, top_id, bits="9"):
        for bank in ("base", ""):
            d = self.out / "data" / "global" / "excel" / bank
            d.mkdir(parents=True, exist_ok=True)
            (d / "skills.txt").write_text(tsv(["skill", "*Id"], ["Attack", "0"], ["Blackstorm", "514"], ["Last", str(top_id)]), encoding="utf-8")
            (d / "itemstatcost.txt").write_text(tsv(["Stat", "*ID", "Send Bits"], ["modifierlist_castid", "202", ""],
                                                    ["modifierlist_skill", "350", bits], ["modifierlist_level", "351", "8"]), encoding="utf-8")

    def bits(self, bank):
        _, rows = tm.read_tsv(self.out / "data" / "global" / "excel" / bank / "itemstatcost.txt")
        return {r[0]: r[2] for r in rows}

    def test_skill_stat_gets_the_bits_of_the_highest_skill_id(self):
        self.mig.stat_send_bits()
        for bank in ("base", ""):
            b = self.bits(bank)
            self.assertEqual(b["modifierlist_skill"], "11")  # 1109 needs 11 bits
            self.assertEqual(b["modifierlist_level"], "8")
            self.assertEqual(b["modifierlist_castid"], "")
        self.assertIn("9 -> 11", " ".join(self.mig.report))

    def test_wide_enough_value_is_kept(self):
        self.make(300, bits="12")
        self.mig.stat_send_bits()
        self.assertEqual(self.bits("base")["modifierlist_skill"], "12")
        self.assertEqual(self.mig.report, [])


if __name__ == "__main__":
    unittest.main()
