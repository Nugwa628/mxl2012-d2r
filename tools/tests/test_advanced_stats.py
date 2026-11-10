"""The character sheet's Advanced Stats panel lists the itemstatcost rows with `advdisplay` 1 (always) or 2 (while not 0).
txt_migrate.advanced_stats sets the column from data/advanced_stats.tsv: Laz's PlugY stat pages plus the vanilla rows that mean
the same in Median."""
import importlib.util
import os
import sys
import unittest
from pathlib import Path

TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))
import projtemp  # noqa: E402,F401  (temp files stay inside the project, tools/projtemp.py)
import localconfig  # noqa: E402
spec = importlib.util.spec_from_file_location("txt_migrate", TOOLS / "txt_migrate.py")
tm = importlib.util.module_from_spec(spec)
spec.loader.exec_module(tm)

BUILT = TOOLS.parent / "work" / "mod" / "data" / "global" / "excel"
NAMED = TOOLS.parent / "work" / "named" / "itemstatcost.txt"
SRC = Path(os.environ.get("MXL2012_SRC") or localconfig.runs_dir() / "extract-mpq" / "data" / "global" / "excel")
LAZ = SRC.parents[2] / "plugy" / "statsinterface.txt"
# Stats D2R lists whose meaning needs the panel to read a parameter layer (it reads layer 0 only): never listed.
PARAM_FUNCS = {"15", "16", "23", "24", "27", "28"}

HEADER = ["Stat", "*ID", "descfunc", "advdisplay"]


def rows():
    return [["item_fastercastrate", "105", "2", ""], ["fireresist", "39", "4", ""], ["item_aura", "151", "", "2"],
            ["item_pierce_cold_immunity", "187", "19", "2"], ["passive_mag_mastery", "357", "", ""]]


MOD = {"item_fastercastrate", "fireresist", "item_aura", "passive_mag_mastery"}


def read(path):
    table = [line.split("\t") for line in path.read_text("utf-8-sig", errors="replace").splitlines()]
    return table[0], table[1:]


class Fix(unittest.TestCase):
    def test_listed_rows_get_their_value_and_other_mod_rows_none(self):
        r = rows()
        self.assertEqual(tm.advanced_stats_fix(HEADER, r, {"item_fastercastrate": "1", "fireresist": "2"}, MOD), [])
        self.assertEqual([x[3] for x in r], ["1", "2", "", "2", ""])

    def test_a_row_only_d2r_has_keeps_d2r_value(self):
        r = rows()
        tm.advanced_stats_fix(HEADER, r, {}, MOD)
        self.assertEqual(r[3][3], "2")

    def test_problems_are_reported(self):
        problems = tm.advanced_stats_fix(HEADER, rows(), {"passive_mag_mastery": "2", "nosuchstat": "2",
                                                          "item_pierce_cold_immunity": "2"}, MOD)
        self.assertEqual(problems, ["item_pierce_cold_immunity: not a Median stat",
                                    "passive_mag_mastery: no descfunc, the panel would show an empty row",
                                    "nosuchstat: not in itemstatcost"])

    def test_a_table_without_the_column(self):
        self.assertEqual(tm.advanced_stats_fix(["Stat", "descfunc"], [["a", "1"]], {}, set()),
                         ["itemstatcost has no advdisplay column"])


class ListFile(unittest.TestCase):
    def setUp(self):
        self.wanted = tm.read_advanced_stats()

    def test_values(self):
        self.assertTrue(set(self.wanted.values()) <= {"1", "2"})
        always = sorted(k for k, v in self.wanted.items() if v == "1")
        self.assertEqual(always, sorted(["item_magicbonus", "item_goldbonus", "item_fastercastrate", "item_fasterattackrate",
                                         "item_fastergethitrate", "item_fasterblockrate", "item_fastermovevelocity",
                                         "lifedrainmindam", "manadrainmindam", "item_openwounds", "item_crushingblow",
                                         "item_deadlystrike"]))

    @unittest.skipUnless(LAZ.exists(), "needs the v005 MPQ extraction (plugy/statsinterface.txt)")
    def test_every_stat_of_laz_pages_is_listed(self):
        lines = LAZ.read_bytes().decode("latin-1").splitlines()[1:]
        named = [r[0] for r in read(NAMED)[1]] if NAMED.exists() else None
        for line in lines:
            f = line.split("\t")
            name = f[0]
            if named is not None:
                name = named[int(f[7])]  # the stat id is what PlugY reads; its *desc is only a comment
            self.assertIn(name, self.wanted, line)


@unittest.skipUnless((BUILT / "itemstatcost.txt").exists() and NAMED.exists(), "needs a built mod")
class Built(unittest.TestCase):
    def test_both_banks(self):
        wanted = tm.read_advanced_stats()
        mod = {r[0] for r in read(NAMED)[1]}
        for p in (BUILT / "itemstatcost.txt", BUILT / "base" / "itemstatcost.txt"):
            h, table = read(p)
            ad, fn, op = h.index("advdisplay"), h.index("descfunc"), h.index("op")
            per_level = [r[0] for r in table if r[0] in mod and r[ad] and r[op] in {"2", "3", "4", "5"}]
            self.assertEqual(per_level, [], "the player holds per-level stats at 0: such a row never shows (%s)" % p)
            got = {r[0]: r[ad] for r in table if r[0] in mod and r[ad]}
            self.assertEqual(got, wanted, p)
            for r in table:
                if r[ad]:
                    self.assertTrue(r[fn] and r[fn] not in PARAM_FUNCS or r[0] not in mod, (p, r[0], r[fn]))
            self.assertEqual(sum(1 for r in table if r[ad] == "1"), 12, p)

    def test_resistances_and_speeds_keep_their_ids(self):
        """The rows D2R's own panel code also reads by id (79 / 80 / 85 get Battle.net bonus text) are Median's same stats."""
        h, table = read(BUILT / "itemstatcost.txt")
        for i, name in ((39, "fireresist"), (79, "item_goldbonus"), (80, "item_magicbonus"), (85, "item_addexperience"),
                        (105, "item_fastercastrate")):
            self.assertEqual(table[i][0], name)


if __name__ == "__main__":
    unittest.main()
