"""Unit tests of tools/state_translvl.py (monprop state colours through a free monster level, bugs.md #529) on synthetic
tables (no game or Median files). Run: py -3 -I -m unittest discover -s tools/tests -p "test_state_translvl.py" """
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import projtemp  # noqa: E402,F401  (temp files stay inside the project, tools/projtemp.py)
import hd_translvl as h  # noqa: E402
import state_translvl as s  # noqa: E402
from test_hd_translvl import table, tsv  # noqa: E402

STATES_HEAD = ["state", "*ID", "colorpri", "colorshift", "stat", "*eol"]
PROPS = 4
PROP_HEAD = ["Id"] + [f"{c}{n}{d}" for d in ("", " (N)") for n in range(1, PROPS + 1)
                      for c in ("prop", "chance", "par", "min", "max")]


def prop(i, *cells):
    """A monprop row: (prop, par) pairs for prop1..prop4, the same in Normal and Nightmare."""
    pairs = list(cells) + [("", "")] * (PROPS - len(cells))
    out = [i]
    for _ in range(2):
        for p, par in pairs:
            out += [p, "", par, "1" if p else "", "1" if p else ""]
    return out


class Base(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        r = Path(self.tmp.name)
        self.d2r, self.data = r / "d2r", r / "mod" / "data"
        self.excel = self.data / "global" / "excel"
        states = [[f"s{i}", str(i), "", "", "", "0"] for i in range(53)]
        states[2] = ["dark", "2", "36", "20", "", "0"]
        states[3] = ["frost", "3", "200", "108", "", "0"]    # a colour D2R's HD renderer has itself
        states[4] = ["calm", "4", "80", "0", "", "0"]       # colourless, higher priority than `dark`
        states[52] = ["preventheal", "52", "115", "101", "armorclass", "0"]
        for bank in (self.excel, self.excel / "base"):
            tsv(bank / "states.txt", STATES_HEAD, states)
            tsv(bank / "monprop.txt", PROP_HEAD,
                [prop("darkprop", ("state", "2")), prop("cogprop", ("state", "52"), ("fade", "")),
                 prop("calmprop", ("state", "dark"), ("state", "calm")), prop("coldprop", ("state", "3")),
                 prop("fullprop", ("state", "52"), ("fade", ""))])
            tsv(bank / "monstats.txt", ["Id", "Code", "TransLvl", "MonProp", "enabled"],
                [["shadow", "ZZ", "2", "darkprop", "1"], ["zealot", "ZZ", "0", "", "1"], ["zealot3", "ZZ", "4", "", "1"],
                 ["cog", "FA", "2", "cogprop", "1"], ["fallen", "FA", "0", "", "1"], ["fallen5", "FA", "5", "", "0"],
                 ["calm", "ZZ", "1", "calmprop", "1"], ["cold", "ZZ", "1", "coldprop", "1"]])
        self.mj = {"shadow": "zealot1", "zealot": "zealot1", "zealot3": "zealot1", "cog": "fallen1", "fallen": "fallen1",
                   "fallen5": "fallen1", "calm": "zealot1", "cold": "zealot1"}
        self.tables = {"zealot1": "hd/character/enemy/zealot1/zealot1_variant.json",
                       "fallen1": "hd/character/enemy/fallen1/fallen1_variant.json"}
        for u, t in self.tables.items():
            (self.d2r / "data" / t).parent.mkdir(parents=True, exist_ok=True)
            (self.d2r / "data" / t).write_text(json.dumps(table({2: (0.1, 0.2, 0.0, 1.0), 7: (0.5, 0.5, 0.5, 1.0)})), "utf-8")

    def tearDown(self):
        self.tmp.cleanup()

    def plan(self):
        return s.plan(self.excel, self.mj, self.tables.get)

    def rows(self, name, bank=""):
        return {r["Id"] if "Id" in r else r["state"]: r for r in s.rows_of((self.excel / bank) / name)}


class Plan(Base):
    def test_groups_by_token_and_winning_colour(self):
        p = self.plan()
        self.assertEqual([(g["token"], g["colorshift"], g["state"], g["ids"]) for g in p["groups"]],
                         [("fa", 101, "preventheal", ["cog"]), ("zz", 20, "dark", ["shadow"])])
        # calmprop: `calm` (colorshift 0) wins the colour pick over `dark`; coldprop: HD colours 108 itself

    def test_the_highest_free_level_of_token_and_table(self):
        p = {g["token"]: g for g in self.plan()["groups"]}
        self.assertEqual(p["fa"]["level"], 5)   # fallen5 is disabled: level 5 is free
        self.assertEqual(p["zz"]["level"], 5)   # zz uses 0, 1 (calm, cold) and 4

    def test_no_free_level(self):
        rows = [["shadow", "ZZ", "2", "darkprop", "1"]] + [[f"z{i}", "ZZ", str(i), "", "1"] for i in range(6)]
        tsv(self.excel / "monstats.txt", ["Id", "Code", "TransLvl", "MonProp", "enabled"], rows)
        tsv(self.excel / "base" / "monstats.txt", ["Id", "Code", "TransLvl", "MonProp", "enabled"], rows)
        g = self.plan()["groups"][0]
        self.assertIsNone(g["level"])
        self.assertIn("no free level", g["why"])

    def test_two_tokens_on_one_table_need_two_levels_unless_the_colour_is_the_same(self):
        self.mj["cog"] = "zealot1"    # Cog drawn by the Shadow's table: 101 and 20 cannot share a level there
        p = {g["token"]: g["level"] for g in self.plan()["groups"]}
        self.assertEqual(sorted(p.values()), [3, 5])

    def test_winner_takes_the_lower_id_on_a_tie(self):
        st = s.States([{"state": "a", "colorpri": "5"}, {"state": "b", "colorpri": "5"}, {"state": "c", "colorpri": "1"}])
        self.assertEqual(s.winner({1, 0, 2}, st), 0)


class Apply(Base):
    def test_copy_and_cover_rows(self):
        p = self.plan()
        s.apply_tables(self.excel, p)
        for bank in ("", "base"):
            st = self.rows("states.txt", bank)
            self.assertEqual(st["dark_lvl"]["colorshift"], "0")
            self.assertEqual((st["dark_lvl"]["colorpri"], st["dark_lvl"]["*ID"]), ("36", "53"))  # new rows in state id order: dark first
            cover = st["preventheal_lvl"]    # legacy draws it (highest colorpri): the level
            self.assertEqual((cover["colorpri"], cover["colorshift"], cover["stat"], cover["*ID"]), ("117", "", "", "54"))
            hd = st["preventheal_hd"]          # HD skips colorshift 0 and draws this one: the custom entry
            self.assertEqual((hd["colorpri"], hd["colorshift"], hd["stat"], hd["*ID"]), ("116", "131", "", "55"))
            self.assertEqual(st["preventheal"]["colorshift"], "101")      # the original rows stay for the skills
            mp = self.rows("monprop.txt", bank)
            self.assertEqual((mp["darkprop"]["par1"], mp["darkprop"]["par1 (N)"]), ("53", "53"))
            cog = mp["cogprop"]   # keeps preventheal (D2R tests id 52) and gets both covers in its free columns
            self.assertEqual((cog["par1"], cog["prop2"], cog["par3"], cog["par4"], cog["par4 (N)"]),
                             ("52", "fade", "54", "55", "55"))
            self.assertEqual(mp["fullprop"]["par1"], "52")
            ms = self.rows("monstats.txt", bank)
            self.assertEqual((ms["shadow"]["TransLvl"], ms["cog"]["TransLvl"], ms["calm"]["TransLvl"]), ("5", "5", "1"))

    def test_cover_goes_into_a_free_column(self):
        tsv(self.excel / "monprop.txt", PROP_HEAD, [prop("cogprop", ("state", "52"))])
        s.apply_tables(self.excel, self.plan())
        cog = self.rows("monprop.txt")["cogprop"]
        self.assertEqual((cog["prop2"], cog["par2"], cog["min2"], cog["prop2 (N)"], cog["par2 (N)"], cog["par3"]),
                         ("state", "53", "1", "state", "53", "54"))  # the only new rows: _lvl, then _hd

    def test_no_free_column_is_reported(self):
        tsv(self.excel / "monprop.txt", PROP_HEAD, [prop("cogprop", ("state", "52"), ("fade", ""), ("fade", ""))])
        lines = s.apply_tables(self.excel, self.plan())
        cog = self.rows("monprop.txt")["cogprop"]
        self.assertEqual(cog["par4"], "53")
        self.assertIn("| cogprop | no free prop column for the cover state preventheal_hd |", lines)

    def test_a_copy_and_a_cover_count_as_their_original(self):
        st = s.States([{"state": "a"}, {"state": "a_lvl"}, {"state": "a_hd"}, {"state": "b_hd"}])
        self.assertEqual([st.orig(i) for i in range(4)], [0, 0, 0, 3])

    def test_a_second_run_changes_nothing(self):
        tsv(self.excel / "monprop.txt", PROP_HEAD, [prop("cogprop", ("state", "52")), prop("darkprop", ("state", "dark"))])
        p1 = self.plan()
        s.apply_tables(self.excel, p1)
        before = {f: (self.excel / f).read_bytes() for f in ("states.txt", "monprop.txt", "monstats.txt")}
        p2 = self.plan()
        self.assertEqual([(g["token"], g["level"]) for g in p2["groups"]], [(g["token"], g["level"]) for g in p1["groups"]])
        s.apply_tables(self.excel, p2)
        self.assertEqual(before, {f: (self.excel / f).read_bytes() for f in before})


class Classic(Base):
    @staticmethod
    def pl2(shift: int, act_colour=(0, 0, 0)) -> bytes:
        """A Pal.pl2: grey palette (index 255 = act_colour) and colorshift tables that move every index by `shift`."""
        pal = b"".join(bytes((i, i, i, 0)) for i in range(255)) + bytes((*act_colour, 0))
        b = bytearray(pal + bytes(256 * 1500))
        for cs in (20, 101):
            o = s.PL2_PALETTE + (s.PL2_FIRST_ROW + cs) * 256
            b[o:o + 256] = bytes(min(254, i + shift) for i in range(256))
        return bytes(b)

    def test_table_is_the_state_row(self):
        t, worst = s.pl2_table([self.pl2(3)] * 5, 101)
        self.assertEqual(t[10], 13)
        self.assertEqual(worst, 0)

    def test_acts_that_disagree_get_the_closest_common_target(self):
        a, b = bytearray(self.pl2(3)), bytearray(self.pl2(3))
        o = s.PL2_PALETTE + (s.PL2_FIRST_ROW + 101) * 256
        b[o + 10] = 15          # one act maps index 10 to 15 instead of 13
        t, worst = s.pl2_table([bytes(a)] * 4 + [bytes(b)], 101)
        self.assertEqual(t[10], 13)    # 13 is 0 off in four acts and 2 grey steps off in the fifth
        self.assertEqual(worst, 3 * 2 ** 2)

    def test_palshift_files(self):
        src = self.d2r / "data" / "global" / "monsters" / "fa" / "cof" / "palshift.dat"
        src.parent.mkdir(parents=True)
        src.write_bytes(bytes([7]) * 2048)
        stale = self.data / "global" / "monsters" / "xx" / "cof" / "palshift.dat"
        stale.parent.mkdir(parents=True)
        stale.write_bytes(b"old")
        lines = s.write_palshifts(self.plan(), self.data, self.d2r, [self.pl2(3)] * 5)
        self.assertEqual(len(lines), 2)
        self.assertFalse(stale.exists())
        fa = (self.data / "global" / "monsters" / "FA" / "cof" / "palshift.dat").read_bytes()
        self.assertEqual((len(fa), fa[0], fa[7 * 256 + 10]), (2048, 7, 13))   # D2R's tables, level 5 = table 7
        zz = (self.data / "global" / "monsters" / "ZZ" / "cof" / "palshift.dat").read_bytes()
        self.assertEqual((zz[2 * 256 + 10], zz[7 * 256 + 10]), (10, 13))      # no D2R file: identity elsewhere


class HD(Base):
    def test_level_entry_is_level0_plus_the_colour(self):
        colours = [{"token": "zz", "colorshift": 20, "adj": [0.78, 0.0, 0.0, 1.0], "tint": [0.0] * 4, "label": "x"},
                   {"token": "fa", "colorshift": 101, "label": "none"}]
        rows = s.write_entries(self.plan(), colours, self.data, self.d2r, h.fill_entry, h.dump)
        self.assertEqual({r["state"] for r in rows}, {"written"})
        z = json.loads((self.data / self.tables["zealot1"]).read_text("utf-8"))
        a = z["entries"][7]["transforms"][0]["colorAdjustment"]
        self.assertEqual((a["x"], a["y"]), (0.88, 0.2))     # level0 (0.1, 0.2, 0) + hue 0.78
        f = json.loads((self.data / self.tables["fallen1"]).read_text("utf-8"))
        a = f["entries"][7]["transforms"][0]["colorAdjustment"]
        self.assertEqual((a["x"], a["y"], a["z"]), (0.1, 0.2, 0.0))  # below threshold: level 0, not D2R's entry 7

    def test_hand_colour_wins(self):
        rows = s.write_entries(self.plan(), [], self.data, self.d2r, h.fill_entry, h.dump,
                               {("fa", 101): ([0.08, 0.5, 0.3, 1.0], [0.0] * 4)})
        self.assertIn(("fa", "hand"), {(r["token"], r["shift"]) for r in rows})
        f = json.loads((self.data / self.tables["fallen1"]).read_text("utf-8"))
        self.assertEqual(f["entries"][7]["transforms"][0]["colorAdjustment"]["x"], 0.18)
        # preventheal is ID_KEYED: the same colour as the custom entry of the `_hd` cover's colorshift, once per table
        cust = f["customColorShiftEntries"]
        self.assertEqual([(c["colorShiftIndex"], c["name"]) for c in cust], [(131, "S131")])
        self.assertEqual(cust[0]["entry"]["transforms"][0]["colorAdjustment"], f["entries"][7]["transforms"][0]["colorAdjustment"])
        s.write_entries(self.plan(), [], self.data, self.d2r, h.fill_entry, h.dump, {("fa", 101): ([0.1, 0.5, 0.3, 1.0], [0.0] * 4)})
        f = json.loads((self.data / self.tables["fallen1"]).read_text("utf-8"))
        self.assertEqual([c["entry"]["transforms"][0]["colorAdjustment"]["x"] for c in f["customColorShiftEntries"]], [0.2])
        z = json.loads((self.data / self.tables["zealot1"]).read_text("utf-8"))
        self.assertEqual(z.get("customColorShiftEntries", []), [])    # not for a copied state


class Committed(unittest.TestCase):
    def test_cog_has_a_hand_colour_and_every_id_keyed_state_is_vanilla(self):
        self.assertIn(("fa", 101), h.STATE_HAND)
        self.assertEqual(set(s.ID_KEYED), {52})
        self.assertEqual(s.HD_STATE_SHIFTS, h.HD_STATE_SHIFTS)


if __name__ == "__main__":
    unittest.main()
