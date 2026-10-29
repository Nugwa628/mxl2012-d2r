"""missiles.txt SrcDamage as D2R reads it (tools/srcdamage.py, lane srcdamage)."""
import sys
import tempfile
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))
import projtemp  # noqa: E402,F401  (temp files stay inside the project, tools/projtemp.py)
import srcdamage as sd  # noqa: E402


class StoredByte(unittest.TestCase):
    def test_low_byte(self):
        self.assertEqual(sd.stored_byte(""), 0)
        self.assertEqual(sd.stored_byte("96"), 96)
        self.assertEqual(sd.stored_byte("192"), 192)  # unsigned: not -64
        self.assertEqual(sd.stored_byte("255"), 255)
        self.assertEqual(sd.stored_byte("-1"), 255)
        self.assertEqual(sd.stored_byte("256"), 0)
        self.assertIsNone(sd.stored_byte("x"))


class WeaponShare(unittest.TestCase):
    def test_own_byte_without_skill(self):
        self.assertEqual(sd.weapon_share("192", False), 192)
        self.assertEqual(sd.weapon_share("255", False), 255)
        self.assertEqual(sd.weapon_share("-1", False), 255)  # -1 is 199% on a missile without a skill
        self.assertEqual(sd.weapon_share("", False), 0)

    def test_skill_row_uses_the_skill(self):
        self.assertEqual(sd.weapon_share("192", True, "64"), 64)  # the missile's own value is ignored
        self.assertEqual(sd.weapon_share("", True, "160"), 160)
        self.assertEqual(sd.weapon_share("255", True, "160"), 0)  # 255 / -1 = no weapon damage
        self.assertEqual(sd.weapon_share("-1", True, "160"), 0)


class Rows(unittest.TestCase):
    def test_table(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)
            (p / "missiles.txt").write_text(
                "Missile\tSkill\tMissileSkill\tSrcDamage\tHalf2HSrc\n"
                "a\t\t\t192\t\nb\tFoo\t\t96\t1\nc\t\t1\t-1\t\nd\t\t\t\t\nExpansion\t\t\t\t\n", encoding="utf-8")
            (p / "skills.txt").write_text("skill\tSrcDam\nFoo\t160\n", encoding="utf-8")
            got = {r["missile"]: (r["share"], r["has_skill"], r["half2h"]) for r in sd.rows(p)}
        self.assertEqual(got, {"a": (192, False, False), "b": (160, True, True), "c": (0, True, False)})


class Problems(unittest.TestCase):
    def test_out_of_range(self):
        h = ["Missile", "SrcDamage"]
        rows = [["ok1", "-1"], ["ok2", "255"], ["ok3", ""], ["big", "256"], ["neg", "-2"], ["text", "x"]]
        self.assertEqual([p[2] for p in sd.problems(h, rows)], ["big", "neg", "text"])
        self.assertTrue(all(p[0] == "warn" and p[1] == "SrcDamage" for p in sd.problems(h, rows)))


if __name__ == "__main__":
    unittest.main()
