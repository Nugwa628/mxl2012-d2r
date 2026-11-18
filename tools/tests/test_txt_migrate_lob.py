"""Bugs #614 / #618: Laughing Ghost and Rising Dawn land at the click. lob_skills sets skills.txt `lob` 1 on their rows (D2R's
lob path flies to the target point); lob_missiles lets Rising Dawn reach it and draws its legacy art on the ground. Pyroblast
and Balefire are left as they are (they explode on the first monster they hit)."""
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

HEADER = ["skill", "*Id", "lob", "srvmissile"]


def rows():
    return [["Laughing Ghost", "381", "", "laughingghostemerge"],
            ["Thunderstone", "462", "1", "buzzorb"],
            ["Rising Dawn", "440", "", "risingdawn"],
            ["Pyroblast", "454", "", "pbthunder"],
            ["Balefire", "312", "", "balefireball"]]


class LobSkillTests(unittest.TestCase):
    def test_two_skills_lob(self):
        r = rows()
        self.assertEqual(tm.lob_skills(HEADER, r), ["Laughing Ghost", "Rising Dawn"])
        self.assertEqual(r[0][2], "1")

    def test_other_rows_untouched(self):
        r = rows()
        tm.lob_skills(HEADER, r)
        self.assertEqual(r[1], rows()[1])
        self.assertTrue(all(row[2] == "1" for row in r if row[0] in tm.LOB_SKILLS))

    def test_short_row_is_padded(self):
        r = [["Laughing Ghost", "381"]]
        tm.lob_skills(HEADER, r)
        self.assertEqual(r[0][2], "1")

    def test_no_lob_column(self):
        r = rows()
        self.assertEqual(tm.lob_skills(["skill", "*Id"], r), [])

    def test_the_list(self):
        self.assertEqual(tm.LOB_SKILLS, ("Laughing Ghost", "Rising Dawn"))

    def test_pyroblast_and_balefire_untouched(self):
        r = rows()
        tm.lob_skills(HEADER, r)
        self.assertEqual(r[3:], rows()[3:])
        self.assertNotIn("pbthunder", tm.LOB_MISSILES)
        self.assertNotIn("balefireball", tm.LOB_MISSILES)
        h = ["Missile", "CollideType", "CollideKill"]
        m = [["pbthunder", "3", "1"], ["balefireball", "3", "1"]]
        tm.lob_missiles(h, m)
        self.assertEqual(m, [["pbthunder", "3", "1"], ["balefireball", "3", "1"]])

    def test_rising_dawn_reaches_click_and_keeps_explosion(self):
        h = ["Missile", "Accel", "CollideType", "CollideKill", "Vel", "Range", "AlwaysExplode", "HitSubMissile1"]
        r = [[name, "-250" if name == "risingdawn" else "", "3", "1", "24", "60", "1", "explosion"]
             for name in ("risingdawn", "other")]
        other = r[-1].copy()
        tm.lob_missiles(h, r)
        self.assertEqual(r[0][1:4], ["0", "0", "1"])
        self.assertEqual(r[0][4:], ["24", "60", "1", "explosion"])
        self.assertEqual(r[-1], other)
        once = [row.copy() for row in r]
        tm.lob_missiles(h, r)
        self.assertEqual(r, once)

    def test_carrier_short_row(self):
        r = [["risingdawn"]]
        tm.lob_missiles(["Missile", "Accel", "CollideType"], r)
        self.assertEqual(r, [["risingdawn", "0", "0"]])

    def test_rising_dawn_art_on_the_ground(self):
        h = ["Missile", "zoffset", "Accel"]
        r = [["risingdawn", "-150", "-250"], ["risingdawnexplo", "-170", ""], ["risingdawnbuff", "-190", "-1000"],
             ["risingdawnmine", "-20", ""], ["pbthunder", "-40", ""]]
        tm.lob_missiles(h, r)
        self.assertEqual([row[1] for row in r], ["0", "0", "0", "-20", "-40"])
        self.assertEqual(r[2][2], "-1000")


if __name__ == "__main__":
    unittest.main()
