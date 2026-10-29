"""Unit tests for tools/idmap.py. Synthetic tables only, except IntegrationTest (skipped without the extracted data).

  py -3 -I -m unittest discover -s tools -p "test_idmap.py" -v
"""
import os
import sys
import tempfile
import unittest
from unittest import mock
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import projtemp  # noqa: E402,F401  (temp files stay inside the project, tools/projtemp.py)
import idmap as I  # noqa: E402


def write(folder: Path, name: str, header: list[str], rows: list[list[str]]) -> None:
    folder.mkdir(parents=True, exist_ok=True)
    (folder / f"{name}.txt").write_text("\r\n".join("\t".join(r) for r in [header, *rows]) + "\r\n", encoding="utf-8",
                                       newline="")


class ReadTest(unittest.TestCase):
    def test_split_row_is_rejoined_and_expansion_rule(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "objects.txt"
            p.write_text("Name\tdescription\tId\r\na\tfirst part\r\nsecond part\t1\r\nExpansion\t\t\r\n\tExpansion\t\r\nb\tx\t3\r\n",
                         encoding="latin-1", newline="")
            h, rows = I.read_tsv(p)
            self.assertEqual(rows[0], ["a", "first part second part", "1"])
            recs = I.records(rows)
            # "Expansion" in the first column is a separator; elsewhere the row is a (blank-key) record
            self.assertEqual([r[0] for r in recs], ["a", "", "b"])

    def test_bin_records(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "skills.bin").write_bytes((7).to_bytes(4, "little") + b"\0" * 8)
            self.assertEqual(I.bin_records(Path(d) / "skills.txt"), 7)
            self.assertIsNone(I.bin_records(Path(d) / "states.txt"))


class SpaceTest(unittest.TestCase):
    # 1.13c: 4 rows (row 2 unused); D2R: filled row 2 and appended 2 rows
    V113 = ["attack", "kick", "unused2", "Sword Mastery"]
    D2R = ["attack", "kick", "cooldown", "Blade Mastery", "interact", "warlock_skill"]

    def test_rules(self):
        mod = ["attack", "spinkick", "mystat", "Sword Mastery", "fireball", "interact", "nova"]
        sm = I.map_space("skills", mod, self.D2R, self.V113)
        ids = {r.key: (r.id, r.kind, r.name) for r in sm.rows}
        self.assertEqual(ids["attack"], (0, "vanilla", "attack"))
        self.assertEqual(ids["spinkick"], (1, "repurposed", "spinkick"))
        self.assertEqual(ids["mystat"][:2], (6, "moved"))           # D2R filled the unused slot
        self.assertEqual(ids["Sword Mastery"], (3, "vanilla", "Blade Mastery"))  # D2R's spelling adopted
        self.assertEqual(ids["fireball"][:2], (7, "new"))
        self.assertEqual(ids["interact"], (8, "new", "interact_mxl"))  # collides with a D2R-added key
        self.assertEqual(sm.collisions, ["interact"])
        order = sm.order()
        self.assertEqual(order[2], ("d2r", 2))
        self.assertEqual(order[4:6], [("d2r", 4), ("d2r", 5)])   # D2R's own additions (e.g. Warlock) stay put
        self.assertEqual(order[6], ("mod", 2))
        self.assertEqual(sm.renames(), {"Sword Mastery": "Blade Mastery", "interact": "interact_mxl"})

    def test_first_rows_get_low_ids(self):
        mod = ["attack", "kick", "unused2", "Sword Mastery", "a", "b", "c"]
        sm = I.map_space("skills", mod, self.D2R, self.V113, first={6})
        self.assertEqual({r.key: r.id for r in sm.rows if r.kind == "new"}, {"c": 6, "a": 7, "b": 8})

    def test_no_113c_count_means_d2r_count(self):
        sm = I.map_space("playerclass", ["Amazon", "Sorceress"], ["Amazon", "Sorceress", "Warlock"], None)
        self.assertEqual(sm.order(), [("mod", 0), ("mod", 1), ("d2r", 2)])


class ItemTypeTest(unittest.TestCase):
    def tables(self):
        d2r_h = ["ItemType", "Code"]
        codes = [f"t{i}" for i in range(67)] + ["warl", "h2h"] + [f"u{i}" for i in range(69, 108)]
        codes[73], codes[75], codes[77] = "pelt", "rune", "hpot"
        codes[81], codes[82], codes[83], codes[84], codes[96] = "apot", "wpot", "scha", "mcha", "gem4"
        d2r_rows = [["x", c] for c in codes]
        mod_h = ["ItemType", "*comment", "Code"]
        mod_codes = [c for c in codes if c != "warl"] + ["mxl1", "mxl2"]
        mod_codes[5] = ""  # a blank row where D2R has t5
        mod_rows = [["m", "", c] for c in mod_codes]
        return mod_h, mod_rows, d2r_h, d2r_rows

    def test_mod_ids_are_off_by_one_before_alignment(self):
        mod_h, mod_rows, d2r_h, d2r_rows = self.tables()
        errs = I.check_item_type_ids(mod_h, mod_rows)
        self.assertTrue(any("rune: id 74" in e for e in errs))

    def test_align_puts_d2r_rows_at_d2r_numbers(self):
        mod_h, mod_rows, d2r_h, d2r_rows = self.tables()
        out, rep = I.align_item_types(mod_h, mod_rows, d2r_h, d2r_rows)
        self.assertEqual(I.check_item_type_ids(mod_h, out, (d2r_h, d2r_rows)), [])
        ids = I.type_ids(mod_h, out)
        self.assertEqual((ids["warl"], ids["rune"], ids["mxl1"], ids["mxl2"]), (67, 75, 108, 109))
        self.assertEqual(out[5][2], "t5")  # the blank mod row gave way to D2R's type
        self.assertIn("warl 67", rep["d2r_inserted"])

    def test_check_built_fails(self):
        mod_h, mod_rows, _dh, _dr = self.tables()
        with tempfile.TemporaryDirectory() as d:
            write(Path(d), "itemtypes", mod_h, mod_rows)
            self.assertTrue(I.check_built(Path(d), None))


class SlotTest(unittest.TestCase):
    H = ["skill", "srvstfunc", "srvdofunc", "cltstfunc", "cltdofunc"]

    def test_plan_and_apply(self):
        rows = [["MonFrenzy", "64", "109", "", ""], ["BloodLordFrenzy", "37", "109", "", ""], ["Zeal", "37", "17", "", ""],
                ["Baal Corpse Explode", "", "", "82", ""], ["Rock Shock", "", "", "", "22"], ["NewThing", "", "160", "", ""],
                ["Throw", "65", "3", "", ""]]
        moves = I.plan_slots("skills", self.H, rows)
        got = {(m.column, m.old): m.new for m in moves}
        self.assertEqual(got[("srvdofunc", "109")], "9")
        self.assertEqual(got[("srvstfunc", "64")], "67")
        self.assertEqual(got[("cltstfunc", "82")], "")
        self.assertEqual(got[("cltdofunc", "22")], "113")
        self.assertEqual(got[("srvdofunc", "160")], "172")     # D2R's 153-171 -> first free plugin slot
        self.assertNotIn(("srvstfunc", "65"), got)              # Throw's start: same in both games
        I.apply_slot_moves("skills", self.H, rows, moves)
        self.assertEqual(rows[0][1:3], ["67", "9"])
        self.assertEqual(rows[1][1:3], ["67", "9"])               # 37 + 109 -> D2R's BloodLordFrenzy row
        self.assertEqual(rows[2][1:3], ["37", "17"])              # Zeal keeps 37
        self.assertEqual(rows[3][3], "")
        self.assertEqual(rows[4][4], "113")
        self.assertEqual(rows[5][2], "172")

    def test_client_hit_numbers_kept(self):
        h = ["Missile", "pCltHitFunc"]
        rows = [["immolationarrow", "12"], ["fistoftheheavensdelay", "26"]]
        moves = I.plan_slots("missiles", h, rows)
        self.assertTrue(all(m.new == m.old for m in moves))
        I.apply_slot_moves("missiles", h, rows, moves)
        self.assertEqual([r[1] for r in rows], ["12", "26"])

    def test_client_hit_11_blanked(self):  # bug #14: D2R's client hit slot 11 is empty, D2R blanked desertfireball
        h = ["Missile", "pCltHitFunc"]
        rows = [["desertfireball", "11"], ["immolationarrow", "12"]]
        moves = I.plan_slots("missiles", h, rows)
        self.assertEqual({(m.column, m.old): m.new for m in moves}[("pCltHitFunc", "11")], "")
        I.apply_slot_moves("missiles", h, rows, moves)
        self.assertEqual([r[1] for r in rows], ["", "12"])


class RemapTest(unittest.TestCase):
    """IdMap.build on a tiny mod + D2R pair, then remap_table on the mod's tables."""

    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        root = Path(self.tmp.name)
        self.mod, d2r = root / "mod", root / "d2r"
        base = d2r / "base"
        # monstats: 1.13c count is 734 in reality; use D2R rows = 1.13c rows + 2 appended by giving D2R more rows
        # than the mod's vanilla part. ROW_COUNTS_113C["monstats"] = 735 raw rows: build 735 vanilla + 2 D2R rows.
        van = [f"m{i}" for i in range(734)]
        write(base, "monstats", ["Id", "hcIdx"], [[k, str(i)] for i, k in enumerate(van[:723])] + [["Expansion", ""]] +
              [[k, str(i)] for i, k in enumerate(van[723:], 723)] + [["horse", "734"], ["cowking", "735"]])
        write(base, "states", ["state", "id", "gfxtype", "gfxclass"],
              [[f"s{i}", str(i), "", ""] for i in range(185)] + [["cooldown", "185", "", ""]])
        stats = [[f"st{i}", str(i), "", "", "", "0", ""] for i in range(359)]
        isc_h = ["Stat", "ID", "descfunc", "Encode", "Save Param Bits", "Save Bits", "Saved"]
        write(base, "itemstatcost", isc_h, stats + [["skill_cooldown", "359", "", "", "", "0", ""]])
        write(base, "levels", ["Name", "Id", "Vis0", "Depend"],
              [[f"l{i}", str(i), "0", "0"] for i in range(137)] + [["Expansion", "", "", ""]])
        # mod
        write(self.mod, "monstats", ["Id", "hcIdx"], [[k, str(i)] for i, k in enumerate(van[:723])] + [["Expansion", ""]] +
              [[k, str(i)] for i, k in enumerate(van[723:], 723)] + [["mxlboss", "734"], ["mxlminion", "735"]])
        write(self.mod, "states", ["state", "id", "gfxtype", "gfxclass"],
              [[f"s{i}", str(i), "", ""] for i in range(185)] +
              [["wereowl", "185", "1", "734"], ["plain", "186", "0", "734"]])
        write(self.mod, "missiles", ["Missile", "Id", "pSrvHitFunc", "sHitPar1"],
              [["spawner", "0", "6", "735"], ["other", "1", "5", "735"]])
        write(self.mod, "cubemain", ["description", "op", "param"],
              [["r1", "16", "359"], ["r2", "", "359"], ["r3", "16", "12"]])
        write(self.mod, "itemstatcost", isc_h, stats + [["var", "359", "", "", "", "0", ""]])
        self.m = I.IdMap.build(self.mod, d2r)

    def tearDown(self):
        self.tmp.cleanup()

    def remap(self, table):
        h, rows = I.read_tsv(self.mod / f"{table}.txt")
        n = self.m.remap_table(table, h, rows)
        return h, I.records(rows), n

    def test_ids(self):
        self.assertEqual(self.m.new_id("monstats", 734), 736)
        self.assertEqual(self.m.order("monstats")[734:738], [("d2r", 734), ("d2r", 735), ("mod", 734), ("mod", 735)])
        self.assertEqual(self.m.new_id("states", 185), 186)
        self.assertEqual(self.m.new_id("itemstatcost", 359), 360)

    def test_hidden_numeric_columns(self):
        _h, rows, _n = self.remap("missiles")
        self.assertEqual([r[3] for r in rows], ["737", "735"])        # sHitPar1 only for hit 6
        _h, rows, _n = self.remap("states")
        self.assertEqual((rows[185][3], rows[186][3]), ("736", "734"))  # gfxclass only when gfxtype 1
        self.assertEqual(rows[185][1], "186")                        # own id column
        _h, rows, _n = self.remap("cubemain")
        self.assertEqual([r[2] for r in rows], ["360", "359", "12"])  # cube op param = stat id
        _h, rows, _n = self.remap("monstats")
        self.assertEqual(rows[-1][1], "737")

    def test_conflicts_clean(self):
        c = self.m.conflicts()
        self.assertEqual(c.get("error", []), [])


class ParamOverflowTest(unittest.TestCase):
    def test_state_param_fits_after_low_id_ordering(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            mod, base = root / "mod", root / "d2r" / "base"
            write(base, "states", ["state"], [[f"s{i}"] for i in range(185)] + [[f"d2r{i}"] for i in range(47)])
            # mod: 70 new states; the property names the 70th (row 254 -> 301 without reordering, 8 bits max 255)
            write(mod, "states", ["state"], [[f"s{i}"] for i in range(185)] + [[f"x{i}"] for i in range(70)])
            isc_h = ["Stat", "descfunc", "Encode", "Save Param Bits"]
            write(mod, "itemstatcost", isc_h, [["state", "", "", "8"]])
            write(mod, "properties", ["code", "func1", "stat1"], [["state", "8", "state"]])
            write(mod, "uniqueitems", ["index", "prop1", "par1", "min1", "max1"], [["Ring", "state", "254", "1", "1"]])
            m = I.IdMap.build(mod, root / "d2r")
            self.assertEqual(m.new_id("states", 254), 232)
            self.assertEqual(m.conflicts().get("error", []), [])
            h, rows = I.read_tsv(mod / "uniqueitems.txt")
            m.remap_table("uniqueitems", h, rows)
            self.assertEqual(rows[0][2], "232")


class RelocateTest(unittest.TestCase):
    """Repurposed vanilla states on ids D2R's code names (D2R_FIXED_STATES): "move" ids get new ids and D2R's row keeps the
    id (map_space's relocate); "keep" ids stay where 1.13c had them (lane statefaith)."""

    def test_map_space(self):
        v113 = ["none", "blaze", "freeze", "dodge"]
        d2r = v113 + ["cooldown"]
        mod = ["none", "shellshock", "frost", "dodge", "x1", "x2"]
        sm = I.map_space("states", mod, d2r, v113, relocate={1, 3})
        got = {r.key: (r.id, r.kind) for r in sm.rows}
        self.assertEqual(got["shellshock"], (7, "relocated"))   # after the mod's other new rows
        self.assertEqual(got["frost"], (2, "repurposed"))       # id 2 is not one D2R's code names: stays
        self.assertEqual(got["dodge"], (3, "vanilla"))          # the mod kept the vanilla row: nothing moves
        self.assertEqual((got["x1"], got["x2"]), ((5, "new"), (6, "new")))
        self.assertEqual(sm.order()[1], ("d2r", 1))             # D2R's blaze comes back at 1
        self.assertEqual(sm.restored_keys(), {"blaze"})

    def test_first_wins_over_relocation_order(self):
        v113 = ["none", "blaze"]
        sm = I.map_space("states", ["none", "shellshock", "x1"], v113 + ["cooldown"], v113, first={1}, relocate={1})
        self.assertEqual({r.key: r.id for r in sm.rows if r.id >= 3}, {"shellshock": 3, "x1": 4})

    def test_build_and_remap(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            mod, base = root / "mod", root / "d2r" / "base"
            van = [f"s{i}" for i in range(185)]
            van[13], van[68], van[143] = "blaze", "evade", "attached"
            write(base, "states", ["state", "*ID"], [[k, str(i)] for i, k in enumerate(van + ["cooldown"])])
            mst = list(van)
            mst[13], mst[68] = "shellshock", "necroshadowspirit"   # 143 'attached' kept by the mod: stays
            write(mod, "states", ["state", "id"], [[k, str(i)] for i, k in enumerate(mst + ["newstate"])])
            write(mod, "skills", ["skill", "aurastate", "auratargetstate", "charclass"],
                  [["Force Shout", "shellshock", "shellshock", "sor"], ["SpiderLay", "blaze", "", ""],
                   ["Imp", "attached", "", ""]])
            write(mod, "misc", ["code", "state", "cstate1"], [["x", "blaze", "necroshadowspirit"]])
            write(mod, "itemstatcost", ["Stat", "descfunc", "Encode", "Save Param Bits"], [["state", "", "", "8"]])
            write(mod, "properties", ["code", "func1", "stat1"], [["state", "8", "state"]])
            write(mod, "monprop", ["Id", "prop1", "par1", "min1", "max1", "prop2", "par2", "min2", "max2"],
                  [["pet", "state", "68", "1", "1", "state", "blaze", "1", "1"]])
            with mock.patch.dict(I.RELOCATE, {"states": {13, 68}}):
                m = I.IdMap.build(mod, root / "d2r")
            self.assertEqual(m.new_id("states", 68), 186)             # named by the 8-bit `state` param: first
            self.assertEqual(m.new_id("states", 185), 187)
            self.assertEqual(m.new_id("states", 13), 188)             # after the mod's new rows
            self.assertEqual(m.new_id("states", 143), 143)
            order = m.order("states")
            self.assertEqual((order[13], order[68], order[143]), (("d2r", 13), ("d2r", 68), ("mod", 143)))
            self.assertEqual(m.conflicts().get("error", []), [])
            h, rows = I.read_tsv(mod / "states.txt")
            m.remap_table("states", h, rows)
            self.assertEqual((rows[13][1], rows[68][1]), ("188", "186"))
            h, rows = I.read_tsv(mod / "skills.txt")
            n = m.remap_table("skills", h, rows)
            self.assertEqual(rows[0][1:3], ["shellshock", "shellshock"])  # names follow the row
            self.assertEqual(rows[1][1], "")     # 'blaze' named no row in 1.13c: it must not reach D2R's row now
            self.assertEqual(rows[2][1], "attached")
            self.assertEqual(n["aurastate (vanilla name the mod had no row for: emptied)"], 1)
            h, rows = I.read_tsv(mod / "misc.txt")
            m.remap_table("misc", h, rows)
            self.assertEqual(rows[0][1:], ["", "necroshadowspirit"])
            h, rows = I.read_tsv(mod / "monprop.txt")
            m.remap_table("monprop", h, rows)
            self.assertEqual((rows[0][2], rows[0][6]), ("186", ""))   # numeric state param remapped, name emptied

    def test_fixed_states_are_vanilla_ids(self):
        self.assertTrue(all(0 <= i < I.ROW_COUNTS_113C["states"] for i in I.D2R_FIXED_STATES))
        self.assertTrue({13, 22, 65, 66, 68} <= set(I.D2R_FIXED_STATES))

    def test_fixed_state_table(self):  # lane statefaith: every id has a decision, the code on both sides and a reason
        for i, (key, decision, d2r_code, code_114d, reason) in I.D2R_FIXED_STATES.items():
            self.assertTrue(key and d2r_code and code_114d and reason, i)
            self.assertIn(decision, I.STATE_DECISIONS, i)
        self.assertEqual(I.RELOCATE["states"], {i for i, v in I.D2R_FIXED_STATES.items() if v[1] == "move"})
        self.assertEqual(I.FIXED_IDS["states"], set(I.D2R_FIXED_STATES))
        # every one of the 15 has a 1.14d counterpart doing the same: all kept
        self.assertEqual(len(I.D2R_FIXED_STATES), 15)
        self.assertEqual(I.RELOCATE["states"], set())

    def test_kept_row_stays_and_names_still_emptied(self):
        v113 = ["none", "blaze", "freeze"]
        sm = I.map_space("states", ["none", "shellshock", "frost", "x1"], v113 + ["cooldown"], v113, fixed={1})
        got = {r.key: (r.id, r.kind) for r in sm.rows}
        self.assertEqual(got["shellshock"], (1, "repurposed"))  # kept: as 1.13c had it
        self.assertEqual(got["x1"], (4, "new"))
        self.assertEqual(sm.order()[1], ("mod", 1))
        self.assertEqual(sm.restored_keys(), {"blaze"})          # 'blaze' named nothing in 1.13c: still emptied
        sm = I.map_space("states", ["none", "shellshock", "frost", "x1"], v113 + ["cooldown"], v113)
        self.assertEqual(sm.restored_keys(), set())              # not a fixed id: names are left alone

    def test_build_keeps_by_default(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d)
            mod, base = root / "mod", root / "d2r" / "base"
            van = [f"s{i}" for i in range(185)]
            van[13], van[184] = "blaze", "uberminion"
            write(base, "states", ["state", "*ID"], [[k, str(i)] for i, k in enumerate(van + ["cooldown"])])
            mst = list(van)
            mst[13], mst[184] = "shellshock", "porkulator"
            write(mod, "states", ["state", "id"], [[k, str(i)] for i, k in enumerate(mst + ["newstate"])])
            write(mod, "skills", ["skill", "aurastate", "charclass"], [["Force Shout", "shellshock", "sor"], ["BlazeMon", "blaze", ""]])
            m = I.IdMap.build(mod, root / "d2r")
            self.assertEqual((m.new_id("states", 13), m.new_id("states", 184), m.new_id("states", 185)), (13, 184, 186))
            order = m.order("states")
            self.assertEqual((order[13], order[184], order[185]), (("mod", 13), ("mod", 184), ("d2r", 185)))
            self.assertEqual(m.conflicts().get("error", []), [])
            self.assertTrue(any("kept as 1.13c ran them" in x for x in m.conflicts()["info"]))
            h, rows = I.read_tsv(mod / "skills.txt")
            m.remap_table("skills", h, rows)
            self.assertEqual((rows[0][1], rows[1][1]), ("shellshock", ""))


class RegistryTest(unittest.TestCase):
    def test_registry_targets_are_known(self):
        for _t, _c, e, _cond in I.NUMERIC_REFS:
            self.assertIn(e, I.ENTITIES)
        for _t, _c, e in I.NAME_REFS:
            for x in e.split("|"):
                self.assertTrue(x in I.ENTITIES or x == "skilldesc", x)

    def test_ref_columns(self):
        refs = I.ref_columns({"levels": ["Name", "Vis0", "Warp0", "mon1"], "missiles": ["sHitPar1", "SubMissile1"]})
        self.assertIn(("levels", "Vis0", "levels", "id"), refs)
        self.assertIn(("missiles", "sHitPar1", "monstats", "id if pSrvHitFunc"), refs)
        self.assertIn(("missiles", "SubMissile1", "missiles", "name"), refs)


def _mod_excel():
    """MXL2012_MOD_EXCEL, else assets/median (the asset pack), else the coordinator layout (<root>/mxl2012-runs/extract-mpq
    next to the worktrees); None when none exists (the CI checkout sits at /w, with no such parent), which skips the
    integration tests."""
    env = os.environ.get("MXL2012_MOD_EXCEL")
    if env:
        return Path(env)
    pack = Path(__file__).resolve().parent.parent / "assets" / "median" / "data" / "global" / "excel"
    if (pack / "skills.txt").exists():
        return pack
    parents = Path(__file__).resolve().parents
    if len(parents) > 3:
        return parents[3] / "mxl2012-runs" / "extract-mpq" / "data" / "global" / "excel"
    return None


MOD = _mod_excel()


@unittest.skipUnless(MOD and (MOD / "skills.txt").exists() and I.find_d2r(None), "Median 2012 / D2R tables not extracted")
class IntegrationTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.m = I.IdMap.build(MOD, I.find_d2r(None))

    def test_no_errors_and_bin_counts(self):
        c = self.m.conflicts()
        self.assertEqual(c.get("error", []), [])
        self.assertEqual(self.m.bin_mismatch, {})

    def test_warlock_and_d2r_rows_stay(self):
        sk = self.m.spaces["skills"]
        self.assertTrue(all(sk.order()[i] == ("d2r", i) for i in range(357, 429)))
        self.assertEqual(self.m.order("playerclass")[7], ("d2r", 7))

    def test_fixed_states_keep_median_rows(self):  # lane statefaith (was relocated by lane states, bugs #50 #52 #53)
        st = self.m.spaces["states"]
        order = st.order()
        self.assertTrue(all(order[i] == ("mod", i) for i in I.D2R_FIXED_STATES))
        ids = {r.key: r.id for r in st.rows}
        self.assertEqual([ids[k] for k in ("shellshock", "raptured", "shamanstrance", "broadsided", "necroshadowspirit",
                                           "resonance", "porkulator")], [13, 22, 65, 66, 68, 143, 184])

    def test_engine_slot_cells(self):  # engine-triage #1 #2 #7 (lane triage): the 1.13c slots D2R renumbered, on Median's rows
        def cells(table, cols):
            h, rows = self.m.mod[table]
            rows = [list(r) for r in rows]
            I.apply_slot_moves(table, h, rows, self.m.slot_moves)
            for t, j, c, old, new, _key in self.m._cell_moves():
                if t == table:
                    I.records(rows)[j][I.col(h, c)] = new
            key = I.col(h, I.ENTITIES[table].key)
            return {r[key]: tuple(r[I.col(h, c)] for c in cols) for r in I.records(rows)}
        sk = cells("skills", ("srvstfunc", "srvdofunc"))
        self.assertEqual([sk[k] for k in ("MonFrenzy", "BloodLordFrenzy", "Feral Strike")], [("67", "9")] * 3)
        self.assertEqual(sk["Massacre"], ("37", "13"))  # Zeal's start without do 109 stays
        mi = cells("missiles", ("pCltDoFunc",))
        self.assertEqual((mi["corpseexplosion"], mi["vine beast death"]), (("69",), ("70",)))
        self.assertEqual({mi[k] for k in ("poisoncorpseexplosion", "monstercorpseexplode", "grimwardsmallstop", "recycler explosion")},
                         {("11",)})  # D2R's own vanilla rows of these are on 11 too

    def test_item_types_aligned(self):
        h, rows = self.m.mod["itemtypes"]
        out, _rep = I.align_item_types(h, rows, *self.m.d2r.largest("itemtypes"))
        self.assertEqual(I.check_item_type_ids(h, out, self.m.d2r.largest("itemtypes")), [])
        self.assertEqual(I.type_ids(h, out)["csch"], 108)  # RotW's last type; Median's own types start at 109


if __name__ == "__main__":
    unittest.main()
