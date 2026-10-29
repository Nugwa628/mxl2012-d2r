"""Unit tests for the HD-effect tools (tools/effects_hd.py, tools/build_effects.py).

Run: py -3 -I tools/test_effects_hd.py   (needs numpy; the last class needs a finished run of tools/build_effects.py)
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import projtemp  # noqa: E402,F401  (temp files stay inside the project, tools/projtemp.py)
import effects_hd as e  # noqa: E402
import fxpaths  # noqa: E402


class Keys(unittest.TestCase):
    def test_norm_key(self):
        # D2R's key: lowercase, spaces as '_', '_' in front of every digit run after a non-digit
        self.assertEqual(e.norm_key("spike1"), "spike_1")
        self.assertEqual(e.norm_key("cyclonearmor1front"), "cyclonearmor_1front")
        self.assertEqual(e.norm_key("Fire Wall"), "fire_wall")
        self.assertEqual(e.norm_key("aura130"), "aura_130")
        self.assertEqual(e.norm_key("firebolt"), "firebolt")

    def test_norm_art(self):
        self.assertEqual(e.norm_art("Extra/FrostNova2.dcc"), "extra" + e.BS + "frostnova2")
        self.assertEqual(e.norm_art("coldfuse"), "coldfuse")

    def test_lookalike_key_uses_backslash(self):
        self.assertIn("extra" + e.BS + "frostnova2", e.LOOKALIKE)


class Words(unittest.TestCase):
    def test_family_and_shape(self):
        fam, shp, _ = e.tags("violetlightning")
        self.assertIn("elec", fam)
        fam, shp, _ = e.tags("blackfiresmall")
        self.assertIn("fire", fam)
        self.assertIn("small", shp)
        fam, shp, _ = e.tags("BlueNovaB")
        self.assertIn("nova", shp)

    def test_skill_words_join(self):
        fam, _, _ = e.tags("missiles_1234", "", "Frozen Orb")
        self.assertIn("ice", fam)

    def test_empty(self):
        self.assertEqual(e.tags("", ""), (set(), set(), set()))


class Scoring(unittest.TestCase):
    def art(self, hsv, w=40, h=40, n=10):
        return dict(n=n, w=w, h=h, rgb=[0, 0, 0], hsv=hsv, hue=[0] * 12)

    def test_colour_dist(self):
        red, blue = self.art([0.0, 0.9, 0.9]), self.art([0.66, 0.9, 0.9])
        self.assertEqual(e.colour_dist(red, red), 0)
        self.assertGreater(e.colour_dist(red, blue), 0.6)
        self.assertLessEqual(e.colour_dist(red, blue), 1.0)

    def test_scale_for(self):
        m = e.Prof("missile", "m", "x", {}, self.art([0, 1, 1], 80, 80))
        c = e.Prof("missile", "c", "y", {}, self.art([0, 1, 1], 80, 80))
        self.assertEqual(e.scale_for(m, c), 1.0)           # same size: left alone
        c.art = self.art([0, 1, 1], 20, 20)
        self.assertEqual(e.scale_for(m, c), 1.8)           # 4x bigger: damped 4**0.7 = 2.6, capped at 1.8
        c.art = self.art([0, 1, 1], 320, 320)
        self.assertEqual(e.scale_for(m, c), 0.6)           # floor
        c.art = self.art([0, 1, 1], 70, 70)
        self.assertEqual(e.scale_for(m, c), 1.0)           # within 15%
        m.art = None
        self.assertEqual(e.scale_for(m, c), 1.0)           # no statistics: no scaling

    def test_pick_prefers_same_element_and_colour(self):
        fire = self.art([0.05, 0.9, 0.9])
        ice = self.art([0.58, 0.8, 0.9])
        m = e.Prof("missile", "flameorb", "flameorb", {"Vel": "10"}, fire)
        cands = [e.Prof("missile", "frozenorb", "iceorb", {"Vel": "10"}, ice),
                 e.Prof("missile", "fireball", "fireball", {"Vel": "10"}, fire)]
        c, _, _, _ = e.pick(m, cands, False)
        self.assertEqual(c.name, "fireball")

    def test_pick_is_deterministic_on_ties(self):
        a = self.art([0.1, 0.5, 0.5])
        m = e.Prof("missile", "zzz", "zzz", {}, a)
        cands = [e.Prof("missile", "one", "one", {}, a), e.Prof("missile", "two", "two", {}, a)]
        self.assertEqual(e.pick(m, cands, False)[0].name, "one")

    def test_recoloured_original_gets_credit(self):
        a = self.art([0.1, 0.5, 0.5])
        m = e.Prof("missile", "purplething", "purplething", {}, a)
        m.prov_art = "bonespirit"
        orig, other = e.Prof("missile", "o", "bonespirit", {}, a), e.Prof("missile", "x", "other", {}, a)
        self.assertLess(e.cost(m, orig, False)[0], e.cost(m, other, False)[0])


class Definitions(unittest.TestCase):
    def test_scaled_definition_scales_transforms_only(self):
        d = {"name": "a", "entities": [{"components": [
            {"type": "TransformDefinitionComponent", "scale": {"x": 1, "y": 2, "z": 1}, "position": {"x": 0, "y": 10, "z": 0}},
            {"type": "VfxDefinitionComponent", "filename": "f.particles"}]}]}
        out = e.scaled_definition(d, "b", 1.5)
        t = out["entities"][0]["components"][0]
        self.assertEqual((out["name"], t["scale"]["y"], t["position"]["y"]), ("b", 3.0, 15.0))
        self.assertEqual(d["entities"][0]["components"][0]["scale"]["y"], 2)  # the input is not touched
        self.assertEqual(out["entities"][0]["components"][1]["filename"], "f.particles")


class Tables(unittest.TestCase):
    def test_read_tsv_crlf_and_short_rows(self):
        with tempfile.TemporaryDirectory() as t:
            p = Path(t) / "x.txt"
            p.write_bytes(b"a\tb\tc\r\n1\t2\r\n3\t4\t5\r\n")
            h, rows = e.read_tsv(p)
            self.assertEqual(h, ["a", "b", "c"])
            self.assertEqual(rows, [["1", "2", ""], ["3", "4", "5"]])

    def test_overlay_character_rewrite_keeps_line_endings(self):
        with tempfile.TemporaryDirectory() as t:
            ex, out = Path(t) / "excel", Path(t) / "out"
            ex.mkdir()
            (ex / "overlay.txt").write_bytes(b"overlay\tFilename\tCharacter\r\nfoo\tx\tall\r\nbar\ty\tPaladin\r\nbaz\tz\tdruid\r\n")
            n = e.write_overlay_character(out, ex, {"foo": "common", "bar": "paladin", "baz": "druid"})
            self.assertEqual(n, 2)
            got = (out / "global" / "excel" / "overlay.txt").read_bytes()
            self.assertEqual(got, b"overlay\tFilename\tCharacter\r\nfoo\tx\tcommon\r\nbar\ty\tpaladin\r\nbaz\tz\tdruid\r\n")


class InPlace(unittest.TestCase):
    def test_migrated_tables_are_edited_in_both_banks(self):
        with tempfile.TemporaryDirectory() as t:
            out = Path(t) / "data"
            ex = out / "global" / "excel"
            (ex / "base").mkdir(parents=True)
            body = b"overlay\tCharacter\nfoo\tall\n"
            (ex / "overlay.txt").write_bytes(body)
            (ex / "base" / "overlay.txt").write_bytes(body)
            e.write_overlay_character(out, ex, {"foo": "common"})
            for p in (ex / "overlay.txt", ex / "base" / "overlay.txt"):
                self.assertEqual(p.read_bytes(), b"overlay\tCharacter\nfoo\tcommon\n")


class PriorRules(unittest.TestCase):
    def rows(self):
        return e.Prior({
            ("missile", "row_a"): dict(art="art1", effect="mxl_ice_bolt_s130", scale=1.3, cls="variant", conf="medium",
                                       why="x", row="row_a"),
            ("missile", "row_b"): dict(art="art1", effect="fire_bolt", scale=1.0, cls="stand-in", conf="high", why="y", row="row_b"),
            ("missile", "row_c"): dict(art="art1", effect="mxl_fire_bolt_c0a1b2c", scale=1.0, cls="stand-in", conf="high",
                                       why="tinted", row="row_c"),
            ("missile", "row_d"): dict(art="art2", effect="ice_bolt", scale=1.0, cls="stand-in", conf="low",
                                       why="palette shift 5 (moves the colour by 0.3), chosen by the shifted colour", row="row_d"),
            ("missile", "row_e"): dict(art="art3", effect="ice_bolt", scale=1.0, cls="exact", conf="high", why="z", row="row_e"),
        })

    def test_adoptable(self):
        s = self.rows()
        self.assertTrue(e.adoptable(s.rows[("missile", "row_a")]))
        self.assertFalse(e.adoptable(s.rows[("missile", "row_c")]))   # gradient-tinted copy: not buildable here
        self.assertFalse(e.adoptable(s.rows[("missile", "row_d")]))   # chosen by a PalShift 1.13c does not have
        self.assertFalse(e.adoptable(s.rows[("missile", "row_e")]))   # exact: recomputed from D2R's own rows

    def test_variant_name_parse(self):
        v = e.PRIOR_VARIANT.match("mxl_ice_bolt_s130")
        self.assertEqual((v["base"], v["pct"]), ("ice_bolt", "130"))
        self.assertTrue(e.PRIOR_TINT.match("mxl_fire_bolt_c0a1b2c"))
        self.assertFalse(e.PRIOR_TINT.match("mxl_ice_bolt_s130"))

    def test_prior_pick_same_row_and_closest(self):
        s = self.rows()
        art = dict(n=10, w=40, h=40, rgb=[0, 0, 0], hsv=[0.05, 0.9, 0.9], hue=[0] * 12)
        ice = e.Prof("missile", "i", "iceart", {}, dict(art, hsv=[0.58, 0.8, 0.9]))
        ice.model = "ice_bolt"
        fire = e.Prof("missile", "f", "fireart", {}, art)
        fire.model = "fire_bolt"
        by = {"ice_bolt": ice, "fire_bolt": fire}
        m = e.Prof("missile", "row_a", "art1", {}, art)
        c, scale, conf, why = e.prior_pick(s, "missile", m, "identical", by)       # the same row: its own choice
        self.assertEqual((c.model, scale), ("ice_bolt", 1.3))
        m = e.Prof("missile", "other_row", "art1", {}, art)                          # no same row: closest of its choices
        c, scale, _, _ = e.prior_pick(s, "missile", m, "identical", by)
        self.assertEqual(c.model, "fire_bolt")
        self.assertIsNone(e.prior_pick(s, "missile", m, "differs", by))             # other bytes: not the same art
        self.assertIsNone(e.prior_pick(s, "missile", e.Prof("missile", "q", "art2", {}, art), "identical", by))
        self.assertIsNotNone(e.prior_pick(s, "missile", m, "base", by))             # base-game art is D2R's own file


class Picks(unittest.TestCase):
    """data/hd-effects-picks.tsv: hand-picked stand-ins (docs/hd-effects.md section 9)."""
    HEAD = "# comment\nkind\tart\teffect\tscale\tconfidence\treason\n"

    def load(self, body):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "picks.tsv"
            f.write_text(self.HEAD + body, "utf-8")
            return e.load_picks(f)

    def test_load(self):
        got = self.load("missile\tExtra/CurseMissle\tfirebolt\tauto\tmedium\tstar with a flame tail\n\n"
                        "overlay\tmooncast\tnecro/cast_familiar\t1.5\thigh\twhite sparkle\n")
        self.assertEqual(set(got), {("missile", "extra" + e.BS + "cursemissle"), ("overlay", "mooncast")})
        self.assertIsNone(got[("missile", "extra" + e.BS + "cursemissle")]["scale"])   # auto: by art size
        self.assertEqual(got[("overlay", "mooncast")]["scale"], 1.5)
        self.assertEqual(got[("overlay", "mooncast")]["line"], 5)
        self.assertEqual(e.load_picks(None), {})

    def test_bad_lines(self):
        for body in ("missile\tx\tfirebolt\tauto\tmedium\n",                      # no reason column
                     "missile\tx\tfirebolt\tauto\tsure\twhy\n",                   # bad confidence
                     "monster\tx\tfirebolt\tauto\thigh\twhy\n",                   # bad kind
                     "missile\tx\t\tauto\thigh\twhy\n",                           # no effect
                     "missile\tx\tfirebolt\tauto\thigh\t \n",                     # empty reason
                     "missile\tx\tfirebolt\tauto\thigh\ta\nmissile\tX\tice_bolt\tauto\thigh\tb\n",   # picked twice
                     "missile\tx\tfirebolt\tauto\thigh\ta\tplaid\n",                # unknown tint ramp
                     "missile\tx\tfirebolt\tauto\thigh\ta\t\tr1\nmissile\tx\tice_bolt\tauto\thigh\tb\t\tR1\n",  # row twice
                     "missile\tx\tfirebolt\tauto\thigh\ta\t\t\textra\n"):        # too many columns
            with self.assertRaises(SystemExit, msg=body):
                self.load(body)

    def test_tint_and_rows(self):
        got = self.load("missile\tmart\tfirebolt\tauto\thigh\tall rows\tgold\n"
                        "missile\tmart\tice_bolt\t1\tmedium\ttwo rows\tred\tRowA, rowb\n")
        self.assertEqual(set(got), {("missile", "mart"), ("missile", "mart", "rowa"), ("missile", "mart", "rowb")})
        self.assertEqual(got[("missile", "mart")]["tint"], "gold")
        self.assertEqual(got[("missile", "mart", "rowa")]["rows"], ("rowa", "rowb"))
        art = dict(n=10, w=40, h=40, rgb=[0, 0, 0], hsv=[0.05, 0.9, 0.9], hue=[0] * 12)
        self.assertEqual(e.pick_line(got, "missile", e.Prof("missile", "RowA", "mart", {}, art))["effect"], "ice_bolt")
        self.assertEqual(e.pick_line(got, "missile", e.Prof("missile", "rowc", "mart", {}, art))["effect"], "firebolt")
        self.assertEqual(self.load("missile\tx\tfirebolt\tauto\thigh\ta\n")[("missile", "x")]["tint"], "")

    def test_hand_pick(self):
        art = dict(n=10, w=40, h=40, rgb=[0, 0, 0], hsv=[0.05, 0.9, 0.9], hue=[0] * 12)
        fire = e.Prof("missile", "firebolt", "fireart", {}, art)
        fire.model = "firebolt"
        m = e.Prof("missile", "row", "mart", {}, art)
        picks = {("missile", "mart"): dict(effect="firebolt", scale=None, conf="medium", why="flame tail", line=7)}
        c, scale, conf, why = e.hand_pick(picks, "missile", m, [fire], False)
        self.assertEqual((c.model, conf), ("firebolt", "medium"))
        self.assertEqual(scale, e.scale_for(m, fire))
        self.assertIn("flame tail", why)
        self.assertEqual(e.hand_pick(picks, "missile", m, [fire], True)[1], 1.0)   # --no-scale
        self.assertIsNone(e.hand_pick(picks, "overlay", m, [fire], False))           # other kind: no pick
        with self.assertRaises(SystemExit):                                          # unknown effect is an error
            e.hand_pick(picks, "missile", m, [], False)

    def test_committed_picks_resolve(self):
        """Every committed pick names an effect D2R has and an art file of the mod or the base game."""
        picks = e.load_picks(fxpaths.PICKS_TSV)
        self.assertGreater(len(picks), 30)
        for (kind, art, *_row), hp in picks.items():
            self.assertTrue(((e.HDM if kind == "missile" else e.HDO) / f"{hp['effect']}.json").exists(), hp)
            rel = Path(kind + "s") / (art.replace(e.BS, "/") + ".dcc")
            self.assertTrue(any((root / rel).exists() for root in (fxpaths.MXL, fxpaths.D2R_DATA / "global")),
                            f"{kind} {art}: no art file")

    def test_overlay_picks_not_empty(self):
        """No overlay pick names one of D2R's empty HD stubs (bug #507: it draws nothing in HD)."""
        picks = e.load_picks(fxpaths.PICKS_TSV)
        n = 0
        for (kind, art, *_row), hp in picks.items():
            if kind == "overlay":
                n += 1
                self.assertFalse(e.empty_definition(e.load_json(e.HDO / f"{hp['effect']}.json")), f"{art}: {hp['effect']}")
        self.assertGreaterEqual(n, 23)  # 7 before lane fxpick + its 16 (bug #507)


@unittest.skipUnless((fxpaths.MOD / "effects_hd.md").exists() and fxpaths.MAP_TSV.exists(),
                     "no finished run of tools/build_effects.py")
class Output(unittest.TestCase):
    def test_check_passes(self):
        import build_effects
        self.assertEqual(build_effects.check(fxpaths.MOD, fxpaths.MAP_TSV), [])

    def test_picks_applied(self):
        import build_effects
        by_key = {(r["kind"], r["art"]): r for r in build_effects.read_map(fxpaths.MAP_TSV)}
        self.assertEqual(build_effects.check_picks(by_key, e.load_picks(fxpaths.PICKS_TSV), fxpaths.MOD), [])
        x = dict(scale=None, conf="high", why="x", tint="", rows=())
        wrong = {("missile", "bonfire"): dict(x, effect="ice_bolt", line=1),       # other effect
                 ("missile", "no_such_art"): dict(x, effect="ice_bolt", line=2),   # no row
                 ("missile", "teethexplode", "magicmissile"): dict(x, effect="ice_bolt", line=3)}  # row pick not applied
        self.assertEqual(len(build_effects.check_picks(by_key, wrong, fxpaths.MOD)), 3)

    def test_no_stub_stand_ins(self):
        """Only D2R's own (exact) rows and the arts no skill / state uses may draw an empty D2R stub (bug #507)."""
        import build_effects
        unused = {"extra/aurablue", "extra/aurared", "extra/aurast_bl", "extra/aurast_rd"}  # bloodthorned* / fury* rows: no state
        bad = [r["art"] for r in build_effects.read_map(fxpaths.MAP_TSV)
               if r["kind"] == "overlay" and r["class"] != "exact" and r["effect"] and r["art"] not in unused
               and e.empty_definition(e.load_json(e.HDO / f"{r['effect']}.json"))]
        self.assertEqual(bad, [])

    def test_in_use_arts_decided(self):
        """Every in-use missile / overlay art (a row of the mod's tables with an art file) is D2R's own or in the table."""
        import build_effects
        by_key = {(r["kind"], r["art"]): r for r in build_effects.read_map(fxpaths.MAP_TSV)}
        self.assertEqual(build_effects.check_in_use(by_key, fxpaths.MOD), [])
        del by_key[("missile", "bonfire")]
        self.assertTrue(any("bonfire" in b for b in build_effects.check_in_use(by_key, fxpaths.MOD)))

    def test_every_mod_dcc_in_table(self):
        import build_effects
        have = {(r["kind"], r["art"]) for r in build_effects.read_map(fxpaths.MAP_TSV)}
        n = 0
        for folder, kind in (("missiles", "missile"), ("overlays", "overlay")):
            for p in (fxpaths.MXL / folder).rglob("*.dcc"):
                n += 1
                self.assertIn((kind, p.relative_to(fxpaths.MXL / folder).with_suffix("").as_posix().lower()), have)
        self.assertEqual(n, 208)  # 145 missile + 63 overlay DCCs (docs/graphics-inventory.md)

    def test_overlay_character_is_a_d2r_folder(self):
        folders = {p.name for p in e.HDO.iterdir() if p.is_dir()}
        h, rows = e.read_tsv(fxpaths.OUT / "global" / "excel" / "overlay.txt")
        ci = h.index("Character")
        bad = {r[ci] for r in rows if r[ci] not in folders}
        self.assertLessEqual(len(bad), 5, bad)  # rows we left alone (no HD effect: no art) keep the 1.13c value

    def test_variant_files_are_json(self):
        for p in (fxpaths.OUT / "hd" / "missiles").glob("mxl_*.json"):
            self.assertEqual(json.loads(p.read_text("utf-8"))["name"], p.stem)


if __name__ == "__main__":
    unittest.main()
