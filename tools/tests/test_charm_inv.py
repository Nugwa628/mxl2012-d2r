"""tools/charm_inv.py: CharmInv's tables (bundled plugin) from the built itemtypes.txt."""
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import projtemp  # noqa: E402,F401  (temp files stay inside the project, tools/projtemp.py)
import charm_inv as ci  # noqa: E402

# The rows that matter of Median XL 2012's itemtypes.txt (ItemType, Code, Equiv1, Equiv2)
ROWS = [("Amulet", "amul", "misc", ""), ("Charm", "char", "misc", ""), ("Jewel", "jewl", "sock", ""),
        ("Small Charm", "scha", "char", ""), ("Medium Charm", "mcha", "char", ""), ("Large Charm", "lcha", "char", ""),
        ("Colossal Jewel", "cjwl", "jewl", ""), ("Crafted Sunder Charm", "csch", "char", ""),
        ("Scroll of Summoning", "summ", "char", ""), ("Reward Charm", "grtz", "char", ""),
        *((f"Challenge Charm {i}", f"ara{c}", "char", "") for i, c in enumerate("abcdefg", 1)),
        ("Affix Crystal", "asaa", "", ""), ("Miscellaneous", "misc", "", ""), ("Socket Filler", "sock", "misc", "")]
MEDIAN_CHARMS = ["char", "scha", "mcha", "lcha", "csch", "summ", "grtz", "araa", "arab", "arac", "arad", "arae", "araf", "arag"]


def rows(data=ROWS):
    return [{"ItemType": a, "Code": b, "Equiv1": c, "Equiv2": d} for a, b, c, d in data]


class CharmInvTests(unittest.TestCase):
    def test_median_charm_types(self):
        types = ci.charm_types(rows())
        self.assertEqual(types, MEDIAN_CHARMS)
        for not_charm in ("jewl", "cjwl", "amul", "asaa", "misc", "sock"):  # jewels are socket fillers in Median, not charms
            self.assertNotIn(not_charm, types)

    def test_chain_through_equiv2_and_loops(self):
        data = [("Charm", "char", "", ""), ("Trophy", "trph", "misc", "char"), ("Deep", "deep", "trph", ""),
                ("Loop A", "lpa", "lpb", ""), ("Loop B", "lpb", "lpa", "")]
        self.assertEqual(ci.charm_types(rows(data)), ["char", "trph", "deep"])

    def test_tables_are_strict_tsv(self):
        t = ci.tables(MEDIAN_CHARMS)
        self.assertEqual(t["charminv.txt"], "Id\tgridX\tgridY\ncharm-inv\t10\t4\n")  # the plugin's art has 10 x 4 cells
        lines = t["charminvtypes.txt"].split("\n")
        self.assertEqual(lines[0], "itemType")
        self.assertEqual(lines[1:-1], MEDIAN_CHARMS)
        self.assertEqual(lines[-1], "")  # ends with a line feed
        for text in t.values():
            self.assertNotIn("\r", text)
            text.encode("ascii")
        self.assertEqual(len(set(MEDIAN_CHARMS)), len(MEDIAN_CHARMS))  # CharmInv refuses a repeated itemType

    def test_bad_input_is_refused(self):
        for types, grid in (([], ci.GRID), (["toolong"], ci.GRID), (["a b"], ci.GRID), (["char"], (17, 4)), (["char"], (10, 0))):
            with self.assertRaises(SystemExit):
                ci.tables(types, grid)

    def test_apply_writes_the_mod_override_paths(self):
        mod = Path(tempfile.mkdtemp())
        self.addCleanup(lambda: shutil.rmtree(mod, ignore_errors=True))
        excel = mod / "data" / "global" / "excel"
        excel.mkdir(parents=True)
        head = "ItemType\tCode\tEquiv1\tEquiv2\tRepair\n"
        (excel / "itemtypes.txt").write_text(head + "".join(f"{a}\t{b}\t{c}\t{d}\t0\n" for a, b, c, d in ROWS), "utf-8")
        self.assertEqual(ci.apply(mod), MEDIAN_CHARMS)
        out = mod / "data" / "global" / "excel" / "d2rloader" / "charm-inv"  # RotW bank path of plugin charm-inv's tables
        self.assertEqual(sorted(p.name for p in out.iterdir()), ["charminv.txt", "charminvtypes.txt"])
        self.assertEqual((out / "charminvtypes.txt").read_bytes(), ci.tables(MEDIAN_CHARMS)["charminvtypes.txt"].encode())
        self.assertEqual(ci.apply(mod), MEDIAN_CHARMS)  # idempotent


if __name__ == "__main__":
    unittest.main()
