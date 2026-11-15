"""The character sheet's Advanced Stats panel lists the itemstatcost rows with `advdisplay` 1 (always) or 2 (while not 0).
txt_migrate.advanced_stats sets the column from data/advanced_stats.tsv: Laz's PlugY stat pages plus the vanilla rows that mean
the same in Median. The plugin part advstats lists the same file in groups with headings (tools/advanced_stats.py ->
statbook/src/advstats_table.h) and adds its own rows (Avoid, elemental adds, skill speeds)."""
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
import advanced_stats as advs  # noqa: E402

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


class Groups(unittest.TestCase):
    """bugs #581 / #582: the grouped panel's table."""

    def setUp(self):
        self.rows = advs.read_rows()

    def test_every_group_has_rows_in_display_order(self):
        order = list(advs.GROUPS)
        groups = [r["group"] for r in self.rows]
        self.assertEqual(sorted(set(groups), key=order.index), order)
        self.assertEqual(groups, sorted(groups, key=order.index), "rows sorted by group")
        self.assertEqual(groups[0], "offense")
        self.assertEqual(groups[-1], "other")

    def test_plain_rows_are_the_advdisplay_rows(self):
        plain = {r["stats"][0] for r in self.rows if not r["kind"]}
        self.assertEqual(plain, set(tm.read_advanced_stats()))
        always = {r["stats"][0] for r in self.rows if r["always"]}
        self.assertEqual(always, {k for k, v in tm.read_advanced_stats().items() if v == "1"})

    def where(self, stat):
        return next(r for r in self.rows if stat in r["stats"])

    def test_avoid_and_own_rows(self):
        avoid = self.where("passive_dodge")
        self.assertEqual((avoid["kind"], avoid["stats"], avoid["group"]), ("avoid", advs.AVOID_STATS, "defense"))
        for stat, key in (("firemindam", "AdvStatsAddsFire"), ("lightmindam", "AdvStatsAddsLightning"),
                          ("coldmindam", "AdvStatsAddsCold"), ("magicmindam", "AdvStatsAddsMagic")):
            r = self.where(stat)
            self.assertEqual((r["kind"], r["key"], r["group"], len(r["stats"])), ("range", key, "offense", 2), stat)
        for stat in ("attackrate", "velocitypercent"):
            r = self.where(stat)
            self.assertEqual((r["kind"], r["group"]), ("value", "speed"), stat)

    def test_new_stats(self):
        for stat, group in (("armorclass_vs_hth", "defense"), ("armorclass_vs_missile", "defense"), ("armor_override_percent", "defense"),
                            ("item_tohit_percent", "offense"), ("item_maxhp_percent", "lifemana"), ("item_maxmana_percent", "lifemana"),
                            ("item_manawhenstruck", "lifemana"), ("item_allskills", "skills"), ("enr_factor_percent", "spell"),
                            ("str_factor", "spell"), ("maxfireresist", "resist"), ("item_absorbcold", "resist")):
            self.assertEqual(self.where(stat)["group"], group, stat)

    def test_left_out(self):
        listed = {s for r in self.rows for s in r["stats"]}
        # poison adds (per-item merge rules), defense / block / attack rating (the character sheet shows the real values)
        for stat in ("poisonmindam", "poisonmaxdam", "toblock", "armorclass", "tohit", "item_singleskill", "item_addclassskills"):
            self.assertNotIn(stat, listed)

    def test_header_lists_the_file(self):
        """statbook/src/advstats_table.h is generated from the file: same rows, same order, same kinds."""
        text = advs.HEADER.read_text("utf-8")
        names = [line.rsplit('"', 2)[-2] for line in text.splitlines() if line.strip().startswith("{") and "Kind::" in line]
        self.assertEqual(names, [",".join(r["stats"]) for r in self.rows])
        kinds = [line.split("Kind::")[1].split(",")[0] for line in text.splitlines() if "Kind::" in line and line.strip().startswith("{")]
        self.assertEqual(kinds, [advs.KINDS[r["kind"]][0] for r in self.rows])

    @unittest.skipUnless(NAMED.exists(), "needs work/named/itemstatcost.txt (stat ids)")
    def test_header_is_up_to_date(self):
        self.assertEqual(advs.header_text(self.rows, advs.stat_ids(NAMED)), advs.HEADER.read_text("utf-8"))

    def test_strings_cover_every_key_in_every_language(self):
        strings = advs.strings()
        keys = {s["Key"] for s in strings}
        self.assertTrue({k for k, _ in advs.GROUPS.values()} | set(advs.TEXTS) | set(advs.AVOID_TEXTS) <= keys)
        for s in strings:
            self.assertEqual(set(s) - {"Key"}, set(advs.LANGS), s["Key"])
            self.assertEqual(len(set(s[lang] for lang in advs.LANGS)), 1, "English in every language")
        logic = (advs.ROOT / "statbook" / "src" / "advstats_logic.h").read_text("utf-8")
        for key, text in advs.AVOID_TEXTS.items():
            self.assertIn('{"%s", "%s"}' % (key, text), logic, "AvoidTexts match the strings")

    def test_bad_rows_are_refused(self):
        import tempfile
        head = "stat\tshow\tgroup\trow\tsource\n"
        bad = (head + "fireresist\tnonzero\tnosuch\t\tx\n",  # no such group
               head + "firemindam\tnonzero\toffense\trange:AdvStatsAddsFire\tx\n",  # a range needs two stats
               head + "fireresist\tnonzero\tresist\t\tx\n" * 2)  # listed twice
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "a.tsv"
            for text in bad:
                p.write_text(text, encoding="utf-8")
                with self.assertRaises(ValueError, msg=text):
                    advs.read_rows(p)

    def test_write_strings(self):
        import json
        import tempfile
        with tempfile.TemporaryDirectory() as d:
            paths = advs.write_strings(Path(d))
            self.assertEqual([p.relative_to(d).as_posix() for p in paths],
                             ["local/lng/strings/mxl2012/advanced_stats.json", "local/lng/strings-legacy/mxl2012/advanced_stats.json"])
            self.assertEqual(json.loads(paths[0].read_text("utf-8"))[0]["enUS"], "Offense")


if __name__ == "__main__":
    unittest.main()
