"""The Stat Book game check's helpers (tools/statbook_checks.py): the `statbook host` status line and the sheet's click points."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import projtemp  # noqa: E402,F401  (temp files stay inside the project, tools/projtemp.py)
import statbook_checks as sc  # noqa: E402

LINE = ('host bound 1 (PC), tab 7 of 8, query "fire"; visible flag +0x51 bit 0x01, sheet open 1; ticks 1336, opens 1, tab changes 10, '
        'clicks 8 (missed 0), arrows 1, typed reads 66, box clicked 1 focus 1; names missing 0, handles 163 (fails 0)')


class HostStatus(unittest.TestCase):
    def test_parse(self):
        st = sc.parse_host("statbook host\n" + LINE + "\n")
        self.assertEqual((st["bound"], st["layout"], st["tab"], st["tabs"], st["query"]), (1, "PC", 7, 8, "fire"))
        self.assertEqual((st["opens"], st["clicks"], st["arrows"], st["reads"]), (1, 8, 1, 66))
        self.assertIn("sheet open 1", st["calib"])

    def test_empty_query_and_none(self):
        self.assertEqual(sc.parse_host(LINE.replace('"fire"', '""'))["query"], "")
        self.assertEqual(sc.parse_host("statbook: unknown"), {})


class SheetPoints(unittest.TestCase):
    def test_origin_and_scale(self):
        x, y = sc.sheet_xy(0, 0)
        self.assertAlmostEqual(x * 1600, 236 * 1600 / 3840)
        self.assertAlmostEqual(y * 900, 208.4 * 900 / 2160)
        x2, _ = sc.sheet_xy(3840 - 236, 0)
        self.assertAlmostEqual(x2, 1.0)

    def test_layout_rects(self):
        root = Path(__file__).resolve().parents[2]
        if not (root / "work" / "mod" / "data" / "hd" / "global" / "ui" / "panel" / "statbook" / "statbook-layout.json").exists():
            self.skipTest("no built mod")
        pc = sc.layout_rects(str(root))
        self.assertEqual(len(pc["tabs"]), 8)
        self.assertEqual(len(pc["search"]), 4)


if __name__ == "__main__":
    unittest.main()
