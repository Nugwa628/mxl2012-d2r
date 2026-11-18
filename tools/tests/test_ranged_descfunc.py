"""Bug #617: D2R's ranged mod string (Ctrl stat ranges) has no case for descfuncs 5, 10, 11, 17, 18, 22 and 23 and logs
"Tried to get a ranged mod string on an invalid DescFunc type" (mods.cpp:998) for them. Median keeps its stats on those
descfuncs (item_reanimate 23 "Reanimate as:", item_howl 5, item_replenish_durability 11), whose Ctrl lines came out blank.
The plugin part `rangedesc` (plugin/src/ranged_desc_logic.h) builds them from D2R's plain line at min and max. These tests
keep the data and the part together: a built stat on such a descfunc needs the part to cover its descfunc, and the Reanimate
line keeps Median's descfunc and text."""
import csv
import re
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(ROOT / "tools"))
import projtemp  # noqa: E402,F401  (temp files stay inside the project, tools/projtemp.py)
EXCEL = ROOT / "work" / "mod" / "data" / "global" / "excel"
LOGIC = ROOT / "plugin" / "src" / "ranged_desc_logic.h"
CORE = ROOT / "plugin" / "src" / "mxl2012_core.cpp"
# descfuncs 1-29 of D2R's jump table 0x2d8b44 that go to the assert block 0x2d8aa4 (read in the 93847 dump)
NO_RANGE_CASE = {5, 10, 11, 17, 18, 22, 23}


def stat_rows():
    paths = [p for p in (EXCEL / "itemstatcost.txt", EXCEL / "base" / "itemstatcost.txt") if p.is_file()]
    if not paths:
        raise unittest.SkipTest("work/mod not built (tools/build.py)")
    out = {}
    for p in paths:
        with p.open(encoding="utf-8", newline="") as f:
            out[p] = list(csv.DictReader(f, delimiter="\t"))
    return out


def as_int(v):
    v = (v or "").strip()
    return int(v) if re.fullmatch(r"-?\d+", v) else 0


class RangedDescfuncTest(unittest.TestCase):
    def covered(self):
        text = LOGIC.read_text(encoding="utf-8")
        m = re.search(r"NoRangeCase\(int descfunc\) noexcept -> bool \{\s*return ([^;]*);", text)
        self.assertIsNotNone(m, "NoRangeCase in ranged_desc_logic.h")
        return {int(v) for v in re.findall(r"descfunc == (\d+)", m.group(1))}

    def test_part_covers_every_descfunc_without_a_range_case(self):
        self.assertEqual(self.covered(), NO_RANGE_CASE)
        core = CORE.read_text(encoding="utf-8")
        self.assertIn('if (!Off("rangedesc"))', core)
        self.assertIn("InstallRangedDesc(", core)

    def test_built_stats_on_those_descfuncs_are_covered(self):
        covered = self.covered()
        for path, rows in stat_rows().items():
            used = {as_int(r.get(c)) for r in rows for c in ("descfunc", "dgrpfunc")} & NO_RANGE_CASE
            self.assertLessEqual(used, covered, path.name)
            self.assertIn(23, used, "%s: item_reanimate on descfunc 23" % path.name)

    def test_reanimate_keeps_its_descfunc_and_text(self):
        for path, rows in stat_rows().items():
            row = next((r for r in rows if r["Stat"] == "item_reanimate"), None)
            self.assertIsNotNone(row, path)
            self.assertEqual(as_int(row["descfunc"]), 23, path)
            self.assertEqual(row["descstrpos"], "Moditemreanimas", path)


if __name__ == "__main__":
    unittest.main()
