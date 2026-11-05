"""Bug #541: belt columns. 1.13c keeps a potion in a column of the same code or of its fixed group (hp1-hp5, mp1-mp5, rvs / rvl);
D2R compares item type ids, so Median's own belt potions that share a type (elixirs as `hpot`) get an item type of their own."""
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

TYPE_H = ["ItemType", "Code", "Equiv1", "Equiv2", "Beltable"]
TYPES = [["Potion", "poti", "misc", "", "1"], ["Healing Potion", "hpot", "poti", "", "1"], ["Mana Potion", "mpot", "poti", "", "1"],
         ["Rejuv Potion", "rpot", "hpot", "mpot", "1"], ["Stamina Potion", "spot", "poti", "", "1"], ["Scroll", "scro", "misc", "", "1"],
         ["Herb", "herb", "misc", "", "0"]]
MISC_H = ["name", "code", "type"]
D2R = {"hpo", "mpo", "hpf", "mpf", "vps", "rvs", "rvl", "tsc", "isc", "hrb"} | {f"hp{i}" for i in range(1, 6)} | {f"mp{i}" for i in range(1, 6)}


def misc(*rows):
    return [[f"name {c}", c, t] for c, t in rows]


class BeltColumnTests(unittest.TestCase):
    def fix(self, rows, types=TYPES, d2r=D2R):
        return tm.belt_potion_types(TYPE_H, [list(r) for r in types], MISC_H, misc(*rows), d2r)

    def test_elixirs_leave_the_healing_type(self):
        rows = [(f"hp{i}", "hpot") for i in range(1, 6)] + [("hpo", "hpot"), ("ey2", "hpot"), ("0g1", "hpot"), ("b@b", "hpot")]
        self.assertEqual(self.fix(rows), {"ey2": ("bey2", "hpot"), "0g1": ("b0g1", "hpot"), "b@b": ("bb@b", "hpot")})

    def test_classic_groups_and_d2r_rows_stay(self):
        rows = [(f"hp{i}", "hpot") for i in range(1, 6)] + [(f"mp{i}", "mpot") for i in range(1, 6)] + \
               [("rvs", "rpot"), ("rvl", "rpot"), ("vps", "spot"), ("tsc", "scro"), ("isc", "scro")]
        self.assertEqual(self.fix(rows), {})

    def test_own_median_type_alone_stays(self):
        self.assertEqual(self.fix([("c@c", "poti")]), {})
        self.assertEqual(self.fix([("c@c", "poti"), ("dog", "poti")]), {"c@c": ("bc@c", "poti"), "dog": ("bdog", "poti")})

    def test_not_beltable_and_scrolls_are_left(self):
        self.assertEqual(self.fix([("hrb", "herb"), ("zz1", "herb"), ("tsc", "scro"), ("zz2", "scro")]), {})

    def test_taken_code_is_refused(self):
        types = TYPES + [["Taken", "bey2", "", "", "0"]]
        with self.assertRaises(SystemExit):
            self.fix([("hp1", "hpot"), ("ey2", "hpot")], types=types)


if __name__ == "__main__":
    unittest.main()
