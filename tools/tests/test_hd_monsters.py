"""Unit tests of the HD monster stand-in tools on synthetic data (no game files, no Median files).
Run: py -3 -I -m unittest discover -s tools/tests -p "test_hd_monsters.py" """
import json
import sys
import tempfile
import unittest
from argparse import Namespace
from pathlib import Path
from types import SimpleNamespace

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import projtemp  # noqa: E402,F401  (temp files stay inside the project, tools/projtemp.py)
import hd_donors  # noqa: E402
import hd_monsters as hm  # noqa: E402
import hd_units  # noqa: E402

ROOT = Path(__file__).resolve().parents[2]
MS_HEAD = ["Id", "NameStr", "MonStatsEx", "Code", "TransLvl", "MonType", "AI", "npc", "enabled"]
MS2_HEAD = ["Id", "BaseW", "Rav", "TR", "TRv", "RA", "mDT", "mNU", "mWL", "mA1", "mKB", "mDD"]


def tsv(path: Path, head: list[str], rows: list[list[str]]):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text("\n".join("\t".join(r) for r in [head, *rows]) + "\n", encoding="latin-1")


def touch(path: Path, data: bytes = b"x"):
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)


class Tables(unittest.TestCase):
    def test_read_rows_keeps_quotes_and_skips_separators(self):
        with tempfile.TemporaryDirectory() as t:
            tsv(Path(t) / "monstats.txt", MS_HEAD, [["a", "A", "a", "ZZ", "", "", "", "", "1"],
                                                    ["Expansion", "", "", "", "", "", "", "", ""], ["", "", "", "", "", "", "", "", ""]])
            tsv(Path(t) / "monstats2.txt", MS2_HEAD, [["a", "hth", '"x,y"', "1", '"lit,med"', "1", "1", "1", "1", "1", "", "1"]])
            ms, ms2 = hm.monstats(Path(t))
            self.assertEqual(list(ms), ["a"])
            self.assertEqual(ms2["a"]["TRv"], '"lit,med"')

    def test_slots_accept_the_rav_lav_spelling(self):
        row = {"TR": "1", "TRv": '"lit,med"', "RA": "1", "Rav": "axe", "RH": "1", "RHv": "nil"}
        slots = hu = hd_units.slots_of(row)
        self.assertEqual(slots["TR"], ["lit", "med"])
        self.assertEqual(hu["RA"], ["axe"])          # a lookup of `RAv` gets lit
        self.assertEqual(slots["RH"], ["lit"])       # nil only -> default

    def test_missing_cofs_ignores_kb_sq_and_dd_falls_back_to_hth(self):
        row = {"BaseW": "bow", "mNU": "1", "mA1": "1", "mKB": "1", "mSQ": "1", "mDD": "1"}
        cofs = {"xxnubow", "xxddhth"}
        self.assertEqual(hm.missing_cofs("xx", row, cofs), ["xxa1bow"])
        self.assertEqual(hm.missing_cofs("xx", row, cofs | {"xxa1bow"}), [])


class Prior(unittest.TestCase):
    REPORT = "\n".join([
        "# HD monster looks", "", "| Stats | |", "|---|---|", "| high | 3 |", "",
        "| Median Id | Name | Code | Donor | Scale | Colour | Confidence | Why |", "|---|---|---|---|---|---|---|---|",
        "| a_1 | A | Q1 | wolf | 0.85 | hue +0.00 sat -0.10 val +0.00 | high | family canine |",
        "| a_2 | A | q1 | wolf | 0.85 | hue +0.00 sat -0.10 val +0.00 | medium | family canine |",
        "| b_1 | B | Q1 | bear | 1 | none | high | family beast |",
        "| c_1 | C | Q2 | - | - | - | vanilla | same Id and code in D2R |",
        "| d_1 | D | Q3 | wolf | - | - | kept | graphics borrowed from XX |",
    ])

    def paths(self, tmp: Path):
        p = SimpleNamespace(s_hd=tmp / "none")   # no prior unit files: colour falls back to none
        return p

    def test_parse_report(self):
        with tempfile.TemporaryDirectory() as t:
            f = Path(t) / "r.md"
            f.write_text(self.REPORT, encoding="utf-8")
            rows = hm.parse_prior_report(f)
        self.assertEqual([r["id"] for r in rows], ["a_1", "a_2", "b_1", "c_1", "d_1"])
        self.assertEqual(rows[0]["donor"], "wolf")

    def test_prior_entry_weights_donors_by_confidence_and_ignores_vanilla_kept(self):
        with tempfile.TemporaryDirectory() as t:
            f = Path(t) / "r.md"
            f.write_text(self.REPORT, encoding="utf-8")
            rows = [r for r in hm.parse_prior_report(f) if r["code"].lower() == "q1"]
            e = hm.prior_entry(self.paths(Path(t)), rows, {})
            self.assertEqual(e["donor"], "wolf")             # 3 + 2 against 3
            self.assertEqual(e["scale"], 0.85)
            self.assertAlmostEqual(e["agree"], 0.62, places=2)
            self.assertEqual(e["alternatives"], {"bear": 1})
            self.assertEqual(e["adjust"], [0.0, 0.0, 0.0, 1.0])
            vanilla_only = [r for r in hm.parse_prior_report(f) if r["code"] in ("Q2", "Q3")]
            self.assertIsNone(hm.prior_entry(self.paths(Path(t)), vanilla_only, {}))


class Classify(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        t = Path(self.tmp.name)
        mod = t / "mod"
        # 2012 monstats: VA vanilla (D2R has all its cofs), SI prior art, NW new art, NA no art, FX mixed, DF art differs
        ms = [["va1", "x", "va1", "VA", "", "", "", "", "1"], ["si1", "x", "si1", "SI", "", "", "", "", "1"],
              ["nw1", "x", "nw1", "NW", "", "", "", "", "1"], ["na1", "x", "na1", "NA", "", "", "", "", "1"],
              ["fx1", "x", "fx1", "FX", "", "", "", "", "1"], ["fx2", "x", "fx2", "FX", "", "", "", "", "1"],
              ["df1", "x", "df1", "DF", "", "", "", "", "1"]]
        tsv(mod / "excel" / "monstats.txt", MS_HEAD, ms)
        full = ["hth", "", "1", "lit", "", "1", "1", "1", "1", "", "1"]       # DT NU WL A1 DD
        nu_a1 = ["hth", "", "1", "lit", "", "", "1", "", "1", "", ""]         # NU A1 only
        rows2 = [[i, *full] for i in ("va1", "si1", "nw1", "na1", "df1", "fx2")] + [["fx1", *nu_a1]]
        tsv(mod / "excel" / "monstats2.txt", MS2_HEAD, rows2)
        for tok, names in {"si": ["sia1hth.cof", "sinuhth.cof"], "nw": ["nwnuhth.cof"], "fx": ["fxnuhth.cof"],
                           "df": ["dfnuhth.cof"], "zz": ["zznuhth.cof"]}.items():
            for n in names:
                touch(mod / "monsters" / tok / "cof" / n, b"2012-" + tok.encode())
        sis = t / "prior"
        for tok, data in {"si": b"2012-si", "df": b"other-df", "fx": b"2012-fx"}.items():
            touch(sis / "assets/median/data/global/monsters" / tok / "cof" / f"{tok}nuhth.cof", data)
        touch(sis / "assets/median/data/global/monsters/si/cof/sia1hth.cof", b"2012-si")
        d2r = sis / "extract/d2r/93847"
        d2r.mkdir(parents=True)
        # D2R has every mode cof of VA, and NU / A1 of FX (FX1 needs only those: vanilla; FX2 also WL, DT, DD: not)
        (d2r / "filelist.txt").write_text("\n".join(
            f"data:data/global/monsters/{c[:2]}/cof/{c}.cof" for c in
            ["vanuhth", "vaa1hth", "vaddhth", "vadthth", "vawlhth", "fxnuhth", "fxa1hth"]) + "\n", encoding="utf-8")
        touch(sis / "work/mod/hd_monsters.md", ("\n".join([
            "| Median Id | Name | Code | Donor | Scale | Colour | Confidence | Why |", "|---|---|---|---|---|---|---|---|",
            "| s_1 | S | SI | wolf | 1 | none | high | x |", "| d_1 | D | DF | bear | 1 | none | high | x |"])).encode())
        self.paths = hm.Paths(Namespace(mod_global=str(mod), reference=str(sis), work=str(t / "work"),
                                        tokens=str(t / "tokens.json"), pins=str(t / "pins.json")))

    def tearDown(self):
        self.tmp.cleanup()

    def test_classes(self):
        c = hm.classify(self.paths)
        cls = {k: v["class"] for k, v in c.items()}
        self.assertEqual(cls["va"], "vanilla")
        self.assertEqual(cls["si"], "reused")
        self.assertEqual(cls["na"], "noart")
        self.assertEqual(cls["zz"], "unused")        # art folder, no monstats row
        self.assertEqual(cls["nw"], "new")           # art, no prior folder
        self.assertEqual(cls["df"], "new")           # prior folder exists, but its content differs: not the same art
        self.assertEqual(cls["fx"], "mixed")         # D2R has the art for one of its Ids, not for the other
        self.assertEqual(c["df"]["art_vs_prior"]["relation"], "differs")
        self.assertEqual(c["si"]["art_vs_prior"]["relation"], "identical")

    def test_art_compare_extra_files_in_prior(self):
        mod = {"t/cof/a.cof": self.paths.mod / "monsters/si/cof/sinuhth.cof"}
        sis = {"t/cof/a.cof": self.paths.mod / "monsters/si/cof/sinuhth.cof",
               "t/cof/b.cof": self.paths.mod / "monsters/si/cof/sinuhth.cof"}
        self.assertEqual(hm.art_compare("t", mod, sis)["relation"], "identical, the prior set has extra files")


class Units(unittest.TestCase):
    def test_remap_parts_folds_donor_parts_into_the_single_torso_slot(self):
        rows, notes = hd_units.remap_parts({"torso": ["lit"], "head": ["lit"], "rhand": ["axe"]}, {"TR": ["lit", "med"]})
        self.assertIn(("torso", "lit", "torso", "lit"), rows)
        self.assertIn(("head", "lit", "torso", "med"), rows)     # no head slot: goes to the torso slot
        self.assertEqual(notes, ["rhand dropped"])

    def test_variant_table_has_eight_entries_of_three_transforms(self):
        t = hd_units.variant_table("v", {"dependencies": {}}, (0.1, 0.0, 0.0, 1.0), (0.0, 0.0, 0.0, 0.0))
        self.assertEqual(len(t["entries"]), 8)
        self.assertTrue(all(len(e["transforms"]) == 3 for e in t["entries"]))

    def test_state_machine_gets_the_weapon_class_binding(self):
        sm = {"name": "d", "states": [{"animationBindings": {"hth": ["a"], "bow": []}}]}
        out = hd_units.adapt_state_machine(sm, "bow", "n")
        self.assertEqual(out["states"][0]["animationBindings"]["bow"], ["a"])
        self.assertEqual(sm["states"][0]["animationBindings"]["bow"], [])   # the donor's own is untouched

    def test_colour_fit_and_scale(self):
        c = {"rgb": (0.5, 0.5, 0.5), "hue": 0.1, "hue_conf": 1.0, "sat": 0.5, "val": 0.5, "w": 10, "h": 10}
        self.assertEqual(hd_donors.tint_of(c, c)[2], "none")
        self.assertEqual(hm.scale_of(1.03), 1.0)
        self.assertEqual(hm.scale_of(9.0), 2.5)
        self.assertEqual(hm.scale_of(0.1), 0.5)


def tr(x=0.0, y=0.0, z=0.0, w=1.0, tint=(0.0, 0.0, 0.0, 0.0)):
    return hd_units.color_transform("t", (x, y, z, w), tint)


class StandInColour(unittest.TestCase):
    """Lane tints2: the hue turns fully or not at all, and a stand-in table keeps the donor's own level0 look."""

    @staticmethod
    def col(hue, sat, conf=1.0, val=0.4):
        return {"rgb": (0.3, 0.3, 0.3), "hue": hue, "hue_conf": conf, "sat": sat, "val": val}

    def test_coherent_hue_turns_all_the_way_even_with_much_grey(self):
        # Inarius: blue armour beside much grey and white (mean sat 0.09) on the olive Doom Knight: the weight-scaled turn of
        # +0.11 stopped on green; the whole turn is blue
        adj, _, _ = hd_donors.tint_of(self.col(0.633, 0.09, 0.7), self.col(0.194, 0.41, 0.75))
        self.assertAlmostEqual(adj[0], 0.439, places=3)
        self.assertLess(adj[1], -0.25)   # and greyer, as the art is

    def test_grey_art_gets_no_hue_turn(self):
        self.assertEqual(hd_donors.tint_of(self.col(0.583, 0.02, 0.86), self.col(0.06, 0.4))[0][0], 0.0)  # grey dragon
        self.assertEqual(hd_donors.tint_of(self.col(0.1, 0.5), self.col(0.51, 0.04, 0.92))[0][0], 0.0)    # grey donor
        self.assertEqual(hd_donors.tint_of(self.col(0.5, 0.5, 0.3), self.col(0.1, 0.5))[0][0], 0.0)       # hues disagree

    def test_well_defined_hues_turn_all_the_way(self):
        adj, _, _ = hd_donors.tint_of(self.col(0.5, 0.6, 0.8), self.col(0.1, 0.6, 0.8))
        self.assertAlmostEqual(adj[0], 0.4, places=3)
        adj, _, _ = hd_donors.tint_of(self.col(0.05, 0.6), self.col(0.1, 0.6))
        self.assertAlmostEqual(adj[0], 0.95, places=3)   # -0.05 written as a turn

    def test_level0_entry_only_when_it_changes_the_look(self):
        ident = {"entries": [{}, {}, {"transforms": [tr(), tr(), tr()]}]}
        self.assertIsNone(hd_units.level0_entry(ident))
        self.assertIsNone(hd_units.level0_entry(None))
        lit = {"entries": [{}, {}, {"transforms": [tr(z=-0.34), tr(), tr()]}]}
        self.assertIs(hd_units.level0_entry(lit), lit["entries"][2])
        tinted = {"entries": [{}, {}, {"transforms": [tr(tint=(1.0, 0.5, 0.0, 0.6))]}]}
        self.assertIsNotNone(hd_units.level0_entry(tinted))

    def test_shift_sits_on_the_donor_level0_transform(self):
        base = {"transforms": [tr(0.98, 0.95, -0.34, 0.67, (1.0, 0.8, 0.5, 1.0)), tr(y=10.0)]}
        t = hd_units.variant_table("v", {"dependencies": {}}, (0.04, 0.2, 0.2, 1.0), (0.0, 0.0, 0.0, 0.0), base)
        self.assertEqual(len(t["entries"]), 8)
        a0 = t["entries"][3]["transforms"][0]
        self.assertAlmostEqual(a0["colorAdjustment"]["x"], 0.02)    # hue turns add around the circle
        self.assertAlmostEqual(a0["colorAdjustment"]["y"], 1.0)     # clipped
        self.assertAlmostEqual(a0["colorAdjustment"]["z"], -0.14)
        self.assertAlmostEqual(a0["colorAdjustment"]["w"], 0.67)    # the donor's weight
        self.assertAlmostEqual(a0["colorTint"]["w"], 1.0)           # no tint of ours: the donor's stays
        self.assertAlmostEqual(t["entries"][0]["transforms"][1]["colorAdjustment"]["y"], 10.2)  # D2R's own y 10 is not clipped
        self.assertEqual(t["entries"][0]["transforms"][2]["colorAdjustment"],
                         {"x": 0.04, "y": 0.2, "z": 0.2, "w": 1.0})  # a mask the donor's entry lacks: the plain shift

    def test_own_tint_wins_over_the_donor_tint(self):
        base = {"transforms": [tr(tint=(1.0, 0.8, 0.5, 1.0))]}
        t = hd_units.variant_table("v", {"dependencies": {}}, (0.0, 0.0, 0.0, 1.0), (0.2, 0.4, 0.6, 0.5), base)
        self.assertEqual(t["entries"][2]["transforms"][0]["colorTint"], {"x": 0.2, "y": 0.4, "z": 0.6, "w": 0.5})


class ColourTables(unittest.TestCase):
    """hd_monsters.colour_tables: donors with a level0 look get tables of their own, most used first, within the limit."""

    @staticmethod
    def ent(donor, h, ids=1):
        return {"class": "reused", "ids": ids, "donor": donor, "adjust": [h, 0.0, 0.0, 1.0], "tint": [0.0, 0.0, 0.0, 0.0]}

    def test_based_donors_get_own_tables_and_plain_ones_share(self):
        m = {"a": self.ent("plain", 0.0, 5), "b": self.ent("lit", 0.0, 3), "c": self.ent("plain", 0.02)}
        out = hm.colour_tables(m, {"lit"}, tol=0.2, limit=30)
        key = json.dumps([[0.0, 0.0, 0.0, 1.0], [0.0, 0.0, 0.0, 0.0]])
        self.assertEqual(out["a"], (None, key))
        self.assertEqual(out["c"], (None, key))          # shared with a
        self.assertEqual(out["b"], ("lit", key))         # same colour, but on lit's own level0

    def test_limit_keeps_the_most_used_based_tables(self):
        m = {"a": self.ent("plain", 0.0, 9), "b": self.ent("lit", 0.0, 5), "c": self.ent("lit2", 0.0, 1)}
        out = hm.colour_tables(m, {"lit", "lit2"}, tol=0.2, limit=2)
        self.assertEqual(out["b"][0], "lit")
        self.assertEqual(out["c"], out["a"])             # over the limit: the plain table of its colour
        self.assertEqual(len(set(out.values())), 2)

    def test_levelled_token_gets_its_own_table_within_the_limit(self):
        # bug #435: a token whose stand-in Ids are on several TransLvl levels gets a table of its own (never shared), and
        # it competes with the based tables, most used first, for the room under the limit
        m = {"a": self.ent("plain", 0.0, 9), "q": self.ent("plain", 0.0, 6), "b": self.ent("lit", 0.0, 2)}
        out = hm.colour_tables(m, {"lit"}, tol=0.2, limit=3, levelled={"q"})
        key = json.dumps([[0.0, 0.0, 0.0, 1.0], [0.0, 0.0, 0.0, 0.0]])
        self.assertEqual(out["q"], (hm.LEVELS + "q", key))
        self.assertEqual(out["b"], ("lit", key))
        self.assertEqual(len(set(out.values())), 3)
        out = hm.colour_tables(m, {"lit"}, tol=0.2, limit=2, levelled={"q"})
        self.assertEqual(out["q"], (hm.LEVELS + "q", key))   # 6 Ids beat lit's 2
        self.assertEqual(out["b"], out["a"])
        out = hm.colour_tables(m, {"lit"}, tol=0.2, limit=1, levelled={"q"})
        self.assertEqual(out["q"], out["a"])                 # no room: the plain table, levels stay level 0


class HandColours(unittest.TestCase):
    """A pin's `adjust` (a colour set by hand after an in-game look, lane hdmonlook) is the committed entry's colour."""

    def test_committed_entries_carry_the_hand_colour(self):
        pins = hm.load_pins(hm.ROOT / "tools" / "data" / "hd_monster_pins.json")["tokens"]
        tokens = json.loads(hm.TOKENS_JSON.read_text("utf-8"))["tokens"]
        hand = {t: p for t, p in pins.items() if "adjust" in p}
        self.assertTrue(hand)
        for t, p in hand.items():
            self.assertEqual(tokens[t]["adjust"], [float(x) for x in p["adjust"]][:3] + [1.0], t)
            self.assertTrue(tokens[t]["colour"].endswith("(hand)"), t)

    def test_label(self):
        self.assertEqual(hm.colour_label([0.42, -0.1, 0.05, 1.0], [0.0, 0.0, 0.0, 0.0]), "hue +0.42 sat -0.10 val +0.05")


class SharedColours(unittest.TestCase):
    """Close stand-in colours share one VariantTransformTable (bugs.md #360: D2R's cache holds 128)."""
    NONE = json.dumps([[0.0, 0.0, 0.0, 1.0], [0.0, 0.0, 0.0, 0.0]])

    @staticmethod
    def key(h, s, v, tint=(0.0, 0.0, 0.0, 0.0)):
        return json.dumps([[h, s, v, 1.0], list(tint)])

    def test_distance_is_circular_in_hue_and_counts_hue_twice(self):
        a = json.loads(self.key(0.98, 0.0, 0.0))
        b = json.loads(self.key(0.03, 0.0, 0.0))
        self.assertAlmostEqual(hm.colour_distance(a, b), 0.1)
        self.assertAlmostEqual(hm.colour_distance(json.loads(self.key(0.0, 0.3, -0.1)), json.loads(self.NONE)), 0.3)

    def test_tint_keeps_colours_apart(self):
        a = json.loads(self.key(0.0, 0.0, 0.0, (1.0, 0.5, 0.5, 0.4)))
        self.assertAlmostEqual(hm.colour_distance(a, json.loads(self.NONE)), 1.0)

    def test_close_colours_take_the_most_used_one(self):
        near, far = self.key(0.02, 0.1, -0.1), self.key(0.0, 0.5, 0.0)
        out = hm.share_colours({self.NONE: 10, near: 2, far: 1}, tol=0.2)
        self.assertEqual(out, {self.NONE: self.NONE, near: self.NONE, far: far})

    def test_ties_are_stable_and_tolerance_zero_keeps_all(self):
        w = {self.key(0.0, 0.1, 0.0): 1, self.key(0.0, 0.2, 0.0): 1}
        self.assertEqual(hm.share_colours(w, tol=0.0), {k: k for k in w})
        self.assertEqual(hm.share_colours(w, tol=0.2), hm.share_colours(dict(reversed(list(w.items()))), tol=0.2))

    def test_weights_count_ids_of_standin_classes_only(self):
        c = [[0.1, 0.0, 0.0, 1.0], [0.0, 0.0, 0.0, 0.0]]
        mapping = {"aa": {"class": "reused", "ids": 3, "adjust": c[0], "tint": c[1]},
                   "bb": {"class": "mixed", "ids": 9, "stand_in_ids": ["x"], "adjust": c[0], "tint": c[1]},
                   "cc": {"class": "vanilla", "ids": 50}}
        self.assertEqual(dict(hm.colour_weights(mapping)), {json.dumps(c): 4})
        # a vanilla token with pinned stand-in Ids (bug #431, `s7`) counts its stand-in Ids
        mapping["dd"] = {"class": "vanilla", "ids": 13, "stand_in_ids": ["q1", "q2"], "adjust": c[0], "tint": c[1]}
        self.assertEqual(dict(hm.colour_weights(mapping)), {json.dumps(c): 6})

    def test_committed_mapping_has_few_colour_tables(self):
        mapping = json.loads(hm.TOKENS_JSON.read_text("utf-8"))["tokens"]
        shared = hm.share_colours(hm.colour_weights(mapping))
        self.assertLessEqual(len(set(shared.values())), 30)  # 93 colours before bug #360; Act 1 preloads up to 40 of them
        # with the tables of donors that keep their level0 look (lane tints2), every donor counted as one: the most there can be
        donors = {e["donor"] for e in mapping.values() if hm.has_standin(e)}
        self.assertLessEqual(len(set(hm.colour_tables(mapping, donors).values())), hm.COLOUR_TABLE_LIMIT)
        for k, v in shared.items():
            self.assertLessEqual(hm.colour_distance(json.loads(k), json.loads(v)), hm.COLOUR_SHARE_TOL + 1e-9)


class Committed(unittest.TestCase):
    """The committed mapping and the pins agree with each other (no game or Median files needed)."""

    @classmethod
    def setUpClass(cls):
        cls.tokens = json.loads((ROOT / "tools/data/hd_monster_tokens.json").read_text("utf-8"))["tokens"]
        cls.pins = json.loads((ROOT / "tools/data/hd_monster_pins.json").read_text("utf-8"))

    def test_every_standin_has_a_full_mapping(self):
        for tok, e in self.tokens.items():
            if e["class"] in ("reused", "new", "noart"):
                self.assertTrue(e["donor"] and e["reason"], tok)
                self.assertEqual(len(e["adjust"]), 4, tok)
                self.assertEqual(len(e["tint"]), 4, tok)
                self.assertTrue(0.5 <= e["scale"] <= 2.5, tok)
                self.assertIn(e["confidence"], ("high", "medium", "low"), tok)

    def test_pins_are_used_and_new_tokens_are_all_pinned(self):
        for tok, p in self.pins["tokens"].items():
            self.assertEqual(self.tokens[tok]["donor"], p["donor"], tok)
            self.assertEqual(self.tokens[tok]["source"], "pin", tok)
        for tok, e in self.tokens.items():
            if e["class"] == "new":
                self.assertIn(tok, self.pins["tokens"])
            if e["class"] == "noart":
                self.assertIn(tok, self.pins["noart"])
        for p in list(self.pins["tokens"].values()) + list(self.pins["noart"].values()):
            self.assertTrue(p["reason"])

    def test_quill_bears_draw_a_stand_in(self):
        # bug #431: D2R's unit quillbear1 names a model D2R does not ship, so the Quill Bears drew nothing in HD
        e = self.tokens["s7"]
        self.assertEqual(e["class"], "vanilla")
        self.assertEqual(e["donor"], "quillrat1")
        for i in ("quillbear1", "quillbear2", "quillbear3", "quillbear4", "quillbear5"):
            self.assertIn(i, e["stand_in_ids"])
        self.assertTrue(hm.has_standin(e))

    def test_committed_tables_stay_at_the_limit_with_the_quill_bear_levels(self):
        # bug #435: the Quill Bears' levelled table fits under COLOUR_TABLE_LIMIT (30, docs/hd-monsters.md)
        donors = {e["donor"] for e in self.tokens.values() if hm.has_standin(e)}
        out = hm.colour_tables(self.tokens, donors, levelled={"s7"})
        self.assertEqual(out["s7"][0], hm.LEVELS + "s7")
        self.assertLessEqual(len(set(out.values())), hm.COLOUR_TABLE_LIMIT)

    def test_doc_table_has_a_row_per_token(self):
        table = hm.token_table(self.tokens)
        for tok in self.tokens:
            self.assertIn(f"| `{tok}` ", table)  # a hand row may say what the token was ("| `hn` (was ...) |")


class Proposals(unittest.TestCase):
    """Stand-in proposals (lane standin, tools/data/hd_monster_proposals.json): off until the owner switches one on; a trial
    build for the owner's review can use them anyway."""

    MAP = {"9!": {"class": "reused", "ids": 3, "donor": "clawviper1", "scale": 1.3, "adjust": [0.0, -0.9, 0.3, 1.0],
                  "tint": [1.0, 1.0, 1.0, 0.45], "colour": "x (hand)", "confidence": "low", "source": "pin", "reason": "r"},
           "zz": {"class": "vanilla", "ids": 1, "d2r_units": {"zombie1": 1}}}

    def data(self, file_on=False, entry_on=False):
        return {"enabled": file_on, "tokens": {"9!": {"donor": "goatman1", "scale": 1.2, "adjust": [0.0, -0.5, 0.2],
                                                       "tint": [1, 1, 1, 0.3], "enabled": entry_on, "why": "a horned spear beast"}}}

    def test_off_unless_file_and_entry_are_on(self):
        for f, e in ((False, False), (True, False), (False, True)):
            self.assertEqual(hm.with_proposals(self.MAP, self.data(f, e)), self.MAP, (f, e))
        on = hm.with_proposals(self.MAP, self.data(True, True))["9!"]
        self.assertEqual((on["donor"], on["scale"], on["adjust"], on["source"]), ("goatman1", 1.2, [0.0, -0.5, 0.2, 1.0], "proposal"))
        self.assertEqual(on["tint"], [1.0, 1.0, 1.0, 0.3])
        self.assertEqual(on["ids"], 3)
        self.assertTrue(on["colour"].endswith("(proposal)"))

    def test_trial_uses_named_or_all_proposals_whatever_the_switches(self):
        self.assertEqual(hm.with_proposals(self.MAP, self.data(), "all")["9!"]["donor"], "goatman1")
        self.assertEqual(hm.with_proposals(self.MAP, self.data(), "9!")["9!"]["donor"], "goatman1")
        self.assertEqual(hm.proposal_report(self.data(), "all"), ["`9!` goatman1 x1.2 (TRIAL)"])
        self.assertEqual(hm.proposal_report(self.data()), ["`9!` goatman1 x1.2 (off: owner review)"])
        self.assertEqual(hm.proposal_report(self.data(True, True)), ["`9!` goatman1 x1.2 (ON)"])
        with self.assertRaises(SystemExit):
            hm.with_proposals(self.MAP, self.data(), "ab")

    def test_a_token_without_a_stand_in_is_refused(self):
        d = {"enabled": True, "tokens": {"zz": {"donor": "goatman1", "enabled": True, "why": "w"}}}
        with self.assertRaises(SystemExit):
            hm.with_proposals(self.MAP, d)

    def test_committed_proposals_are_the_approved_ones_and_complete(self):
        d = hm.load_proposals(hm.PROPOSALS_JSON)
        # owner, 2026-10-30: these eight on; Dark Fey, Fungus, Magma Demon and Crystal wait for a closer look
        self.assertEqual(sorted(hm.used_proposals(d)), sorted(["9!", "&b", "0n", "08", "5$", "g7", "#m", "#q"]))
        tokens = json.loads(hm.TOKENS_JSON.read_text("utf-8"))["tokens"]
        trial = hm.with_proposals(tokens, d, "all")
        for t, p in d["tokens"].items():
            self.assertTrue(p["why"] and p["donor"], t)
            self.assertTrue(0.5 <= float(p.get("scale", 1.0)) <= 2.5, t)
            self.assertEqual(len(p.get("adjust", [0, 0, 0])), 3, t)
            self.assertEqual(trial[t]["donor"], p["donor"], t)
        donors = {e["donor"] for e in trial.values() if hm.has_standin(e)}
        self.assertLessEqual(len(set(hm.colour_tables(trial, donors, levelled={"s7"}).values())), hm.COLOUR_TABLE_LIMIT)


class NoModelUnits(unittest.TestCase):
    """A vanilla token whose D2R unit ships no model (bug #431): a pinned token gives those Ids a stand-in; without a pin
    they keep D2R's unit (D2R's own invisible helpers and traps)."""

    def entry(self, pins):
        from unittest import mock
        ctx = SimpleNamespace(dms={"own1": {}, "own2": {}, "helper": {}}, no_model=["nomodel1", "trap1"])
        c = {"class": "vanilla", "ids": ["own1", "own2", "helper"], "id_state": dict.fromkeys(["own1", "own2", "helper"],
                                                                                              "vanilla"),
             "art_vs_prior": {"relation": "no mod folder"}}
        units = {"own1": ("nomodel1", "same Id and code in D2R"), "own2": ("nomodel1", "only unit of the code"),
                 "helper": ("withmodel", "same Id and code in D2R")}
        got = {}

        def donor(ctx_, paths, tok, c_, todo, pin, srows, smj):
            got["todo"] = list(todo)
            return {"donor": pin["donor"], "adjust": [0.0, 0.0, 0.0, 1.0], "tint": [0.0] * 4}
        with mock.patch.object(hm, "vanilla_units", lambda ctx_, ids, pins_: {i: units[i] for i in ids}),                 mock.patch.object(hm, "donor_entry", donor):
            return hm.token_entry(ctx, None, "zz", c, pins, {}, {}), got

    def test_pinned_token_gives_no_model_ids_a_stand_in(self):
        e, got = self.entry({"tokens": {"zz": {"donor": "rat", "reason": "r"}}, "noart": {}})
        self.assertEqual(e["stand_in_ids"], ["own1", "own2"])
        self.assertEqual(got["todo"], ["own1", "own2"])
        self.assertTrue(hm.has_standin(e))
        self.assertEqual(hm.standin_weight(e), 2)

    def test_without_a_pin_the_d2r_unit_stays(self):
        e, got = self.entry({"tokens": {}, "noart": {}})
        self.assertNotIn("stand_in_ids", e)
        self.assertEqual(got, {})
        self.assertFalse(hm.has_standin(e))


class DocRoundTrip(unittest.TestCase):
    def test_doc_command_leaves_the_committed_doc_unchanged(self):
        text = (ROOT / "docs" / "hd-monsters.md").read_text("utf-8")
        mapping = json.loads(hm.TOKENS_JSON.read_text("utf-8"))["tokens"]
        b, e = "<!-- tokens:begin -->", "<!-- tokens:end -->"
        self.assertEqual(text[text.index(b) + len(b):text.index(e)], "\n\n" + hm.token_table(mapping) + "\n")


class WorldVfx(unittest.TestCase):
    """Bug #500: a moved totem left the lightning spire's glass orb (a world-space particle) at its cast spot."""

    UNIT = {"name": "lightningspire", "entities": [
        {"name": "root", "components": [{"type": "ModelDefinitionComponent", "filename": "spire.model"}]},
        {"name": "vfx", "components": [{"type": "VfxDefinitionComponent",
                                        "filename": "data/hd/vfx/fx_lightningspire_ambient_ball.particles"}]},
        {"name": "zap", "components": [{"type": "VfxDefinitionComponent", "filename": "data/hd/vfx/zap.particles"}]}],
        "dependencies": {"particles": [{"path": "data/hd/vfx/fx_lightningspire_ambient_ball.particles"},
                                       {"path": "data/hd/vfx/zap.particles"}]}}

    def test_copy_drops_only_the_world_space_vfx(self):
        d = hm.without_world_vfx(self.UNIT, "fx_lightningspire_ambient_ball", "mxl_lightningspire_moved")
        self.assertEqual(d["name"], "mxl_lightningspire_moved")
        self.assertEqual([e["name"] for e in d["entities"]], ["root", "zap"])
        self.assertEqual(d["dependencies"]["particles"], [{"path": "data/hd/vfx/zap.particles"}])
        self.assertEqual(len(self.UNIT["entities"]), 3)   # D2R's unit itself is left alone

    def test_a_stale_particle_name_fails(self):
        with self.assertRaises(SystemExit):
            hm.without_world_vfx(self.UNIT, "no_such_ball", "x")

    def test_skill_summons_reads_the_summon_column(self):
        with tempfile.TemporaryDirectory() as t:
            tsv(Path(t) / "skills.txt", ["skill", "*Id", "summon"], [["Deaths Fury Totem", "488", "totem1"], ["Fire", "1", ""]])
            self.assertEqual(hm.skill_summons(Path(t)), {"totem1"})


if __name__ == "__main__":
    unittest.main()
