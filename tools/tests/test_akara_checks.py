"""Pure helpers of the akararespec check (tools/akara_checks.py)."""
import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import projtemp  # noqa: E402,F401  (temp files stay inside the project, tools/projtemp.py)
os.environ.setdefault("MXL_SLOT", "2")  # importing game_ctl needs a slot; nothing here starts a game
import akara_checks as ak  # noqa: E402


class AkaraChecksTest(unittest.TestCase):
    def test_packets(self):
        self.assertEqual(ak.respec_packet(0x12345678), "39 78 56 34 12")
        self.assertEqual(ak.respec_packet(7), "39 07 00 00 00")
        self.assertEqual(ak.skill_packet(0x102), "3b 02 01 00 00")

    def test_line(self):
        menu = {"npc": 148, "lines": [(0, 0xfb1, "image+0x1"), (1, 0x2ba0, "image+0x112d40")]}
        self.assertTrue(ak.has_line(menu))
        self.assertFalse(ak.has_line({"npc": 148, "lines": [(0, 0xfb1, "x")]}))
        self.assertFalse(ak.has_line(None))

    def test_refunded(self):
        self.assertTrue(ak.refunded((145, 30, 29), (145, 30, 29)))
        self.assertFalse(ak.refunded((145, 30, 29), (146, 30, 29)), "a doubled point")
        self.assertFalse(ak.refunded((145, 30, 29), (142, 33, 27)), "nothing given back")
        self.assertFalse(ak.refunded((145, 30, 29), (145, None, 29)))

    def test_first_skill(self):
        rows = [{"charclass": "", "skill": "Attack", "reqlevel": "1"},
                {"charclass": "bar", "skill": "B", "reqlevel": "6", "reqskill1": ""},
                {"charclass": "bar", "skill": "C", "reqlevel": "1", "reqskill1": "B"},
                {"charclass": "bar", "skill": "D", "reqlevel": "1", "reqskill1": ""}]
        self.assertEqual(ak.first_skill(rows, "bar"), (3, "D"))
        self.assertEqual(ak.first_skill(rows, "sor"), (None, None))

    def test_shown_count(self):
        self.assertEqual(ak.shown_count("akararespec ...; respecs 6, packets left to D2R 3, Akara menus with the line 14, without"), 14)
        self.assertIsNone(ak.shown_count("no akararespec line in `mxl2012`"))

    def test_hidden_count(self):
        self.assertEqual(ak.hidden_count("akararespec ...; last menu level 101; menus without the line above 100 4; opener calls 9"), 4)
        self.assertIsNone(ak.hidden_count("no akararespec line in `mxl2012`"))


if __name__ == "__main__":
    unittest.main()
