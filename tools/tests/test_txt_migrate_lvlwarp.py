"""Bug #260: lvlwarp.txt is merged by row. Keyed by Name, 1.13c's ten Act 5 warp rows named without D2R's " L" / " R" lost
UniqueId / NoInteract and D2R's ten rows were appended a second time (Ids 71-82 twice)."""
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


def conv(mrow, match, _row_id):
    """A stand-in for txt_migrate's convert: the mod's Name and Id, D2R's UniqueId when a D2R row matches."""
    return [mrow[0], mrow[1], match[2] if match is not None else ""]


class LvlwarpByRowTests(unittest.TestCase):
    def test_lvlwarp_is_merged_by_row(self):
        self.assertEqual(tm.Migrator.kind(object.__new__(tm.Migrator), "lvlwarp"), "by_row")

    def test_same_name_rows_take_d2r_row_at_their_position(self):
        mod = [["Act 4 Lava to Mesa", "70", ""], ["Expansion", "", ""], ["Act 5 Ice Caves Up", "73", ""],
               ["Act 5 Ice Caves Up", "73", ""]]
        d2r = [["Act 4 Lava to Mesa", "70", "70"], ["Expansion", "", ""], ["Act 5 Ice Caves Up L", "73", "74"],
               ["Act 5 Ice Caves Up R", "73", "75"]]
        out = tm.by_row_merge(mod, d2r, conv)
        self.assertEqual(len(out), 4)  # no D2R row appended a second time
        self.assertEqual([r[2] for r in out], ["70", "", "74", "75"])
        self.assertEqual(out[1][0], "Expansion")  # the classic bank's expansion marker stays where D2R has it

    def test_d2r_rows_past_the_mod_end_follow(self):
        out = tm.by_row_merge([["a", "1", ""]], [["a", "1", "1"], ["b", "2", "2"]], conv)
        self.assertEqual(out, [["a", "1", "1"], ["b", "2", "2"]])

    def test_mod_separator_without_d2r_separator_is_kept(self):
        out = tm.by_row_merge([["Expansion", "", ""]], [["x", "1", "1"]], conv)
        self.assertEqual(out, [["Expansion", "", ""]])


if __name__ == "__main__":
    unittest.main()
