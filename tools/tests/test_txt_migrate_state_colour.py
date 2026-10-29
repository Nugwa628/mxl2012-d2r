"""Bug #496: Median's state meslayer (Veil King) has colorshift 1. Classic draws it through the identity colour-shift table (the
unit's own colours), D2R's HD renderer draws index 1 bright green. The build writes 0 (identity in classic too, no tint in HD)."""
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

HEADER = ["state", "*ID", "overlay1", "colorpri", "colorshift"]


class StateColourShift(unittest.TestCase):
    def test_meslayer_gets_shift_zero_and_others_stay(self):
        rows = [["meslayer", "232", "slayercloud", "80", "1"], ["unfortunate", "58", "", "85", "1"],
                ["cold", "11", "", "90", "108"]]
        self.assertEqual(tm.state_colour_shift_fix(HEADER, rows), ["meslayer"])
        self.assertEqual([r[4] for r in rows], ["0", "1", "108"])

    def test_a_changed_value_is_left_alone(self):
        rows = [["meslayer", "232", "slayercloud", "80", "73"]]
        self.assertEqual(tm.state_colour_shift_fix(HEADER, rows), [])
        self.assertEqual(rows[0][4], "73")


if __name__ == "__main__":
    unittest.main()
