"""Bug #614: Laughing Ghost's missile always exploded 12 frames out, wherever the player clicked. lob_skills sets skills.txt
`lob` 1 on its row, so D2R makes the missile on its lob path (to the click); other rows are untouched."""
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
            ["Rising Dawn", "440", "", "risingdawn"]]


class LobSkillTests(unittest.TestCase):
    def test_laughing_ghost_lobs(self):
        r = rows()
        self.assertEqual(tm.lob_skills(HEADER, r), ["Laughing Ghost"])
        self.assertEqual(r[0][2], "1")

    def test_other_rows_untouched(self):
        r = rows()
        tm.lob_skills(HEADER, r)
        self.assertEqual(r[1:], rows()[1:])

    def test_short_row_is_padded(self):
        r = [["Laughing Ghost", "381"]]
        tm.lob_skills(HEADER, r)
        self.assertEqual(r[0][2], "1")

    def test_no_lob_column(self):
        r = rows()
        self.assertEqual(tm.lob_skills(["skill", "*Id"], r), [])

    def test_the_list(self):
        self.assertEqual(tm.LOB_SKILLS, ("Laughing Ghost",))


if __name__ == "__main__":
    unittest.main()
