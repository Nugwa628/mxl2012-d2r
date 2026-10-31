"""Single values D2R renamed (txt_migrate D2R_RENAMED, bug #518): objects Token "sl" (UnfoldingStairLeft) is D2R's "9c"; the
cell takes D2R's value only where it still holds 1.13c's and the D2R row holds the new one."""
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


class RenamedValueTests(unittest.TestCase):
    def test_stair_token_takes_d2r_value(self):
        self.assertTrue(tm.d2r_renamed("objects", "Token", "sl", "9c"))

    def test_median_own_tokens_stay(self):
        # Median's deliberate changes in the same column (rows 45, 277, 361: other art D2R has) are not renames
        self.assertFalse(tm.d2r_renamed("objects", "Token", "S1", "SS"))
        self.assertFalse(tm.d2r_renamed("objects", "Token", "cg", "cj"))
        self.assertFalse(tm.d2r_renamed("objects", "Token", "9c", "9c"))

    def test_only_where_d2r_holds_the_new_value(self):
        self.assertFalse(tm.d2r_renamed("objects", "Token", "sl", "sv"))
        self.assertFalse(tm.d2r_renamed("objects", "Token", "sl", ""))

    def test_other_tables_and_columns(self):
        self.assertFalse(tm.d2r_renamed("objects", "Name", "sl", "9c"))
        self.assertFalse(tm.d2r_renamed("monstats", "Token", "sl", "9c"))


if __name__ == "__main__":
    unittest.main()
