"""mxl2012_prep.superunique_separator (bug #362): Median's blank superuniques row 42 becomes an "Expansion" separator again.
Run: py -3 -I -m unittest discover -s tools/tests -p "test_superunique_separator.py" """
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import projtemp  # noqa: E402,F401  (temp files stay inside the project, tools/projtemp.py)
import idmap  # noqa: E402
import mxl2012_prep  # noqa: E402

HEAD = ["Superunique", "Name", "Class", "hcIdx", "MonSound"]


def rows():
    return [["The Feature Creep", "Hephasto the Armorer", "hephasto", "41", ""],
            ["", "Expansion", "", "", ""],
            ["Siege Boss", "Shenk the Overseer", "goatpriest4", "43", ""],
            ["Ancient Barbarian 1", "Talic the Defender", "ancientbarb1", "44", ""]]


class Separator(unittest.TestCase):
    def test_blank_expansion_row_becomes_a_separator(self):
        r = rows()
        self.assertEqual(mxl2012_prep.superunique_separator(HEAD, r), 1)
        self.assertEqual(r[1][0], "Expansion")
        self.assertFalse(idmap.is_record(r[1]))
        recs = idmap.records(r)
        self.assertEqual([x[0] for x in recs], ["The Feature Creep", "Siege Boss", "Ancient Barbarian 1"])
        self.assertEqual(recs.index(r[2]) + 41, 42, "Siege Boss takes vanilla's number 42 when its records are counted")

    def test_other_rows_and_tables_untouched(self):
        r = rows()
        r[1][2] = "somemonster"  # a real blank-key record with a class is kept as a record
        self.assertEqual(mxl2012_prep.superunique_separator(HEAD, r), 0)
        self.assertEqual(mxl2012_prep.superunique_separator(["Name", "Class"], [["", "x"]]), 0)

    def test_idempotent(self):
        r = rows()
        mxl2012_prep.superunique_separator(HEAD, r)
        self.assertEqual(mxl2012_prep.superunique_separator(HEAD, r), 0)


if __name__ == "__main__":
    unittest.main()
