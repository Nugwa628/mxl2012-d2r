"""Pure helpers of the lifetext check (tools/lifetext_checks.py)."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import projtemp  # noqa: E402,F401  (temp files stay inside the project, tools/projtemp.py)
import lifetext_checks as lt  # noqa: E402


class LifetextChecksTest(unittest.TestCase):
    def test_judge(self):
        bad = []
        lt.judge({"life": (46, 140, 46, 140), "mana": (11, 25, 12, 25)}, "hd town", bad)
        self.assertEqual(bad, [])
        lt.judge({"life": (323, 970, 970, 970), "mana": (25, 25, 25, 25)}, "legacy zombies", bad)
        self.assertEqual(bad, ["legacy zombies life: server 323/970, client 970/970"])
        bad = []
        lt.judge({"life": (46, 140, None, 140)}, "x", bad)
        lt.judge({"life": (46, 140, 46, 170)}, "y", bad)
        self.assertEqual(len(bad), 2)

    def test_state_on(self):
        class Gc:
            def __init__(self, lines):
                self.lines = lines

            def Hl(self, cmd, log):
                return True, self.lines
        on = Gc(["client state 100: bit=1 list=none", "client states: 1 set (ids below 101)"])
        self.assertEqual(lt.state_on(on, "cstates", 100, []), 1)
        self.assertEqual(lt.state_on(Gc(["server states: 0 set (ids below 101)"]), "states", 100, []), 0)
        self.assertIsNone(lt.state_on(Gc(["FAIL"]), "states", 100, []))


if __name__ == "__main__":
    unittest.main()
