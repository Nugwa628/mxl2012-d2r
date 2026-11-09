"""Unit tests of tools/missile_looks.py (HD pictures by what a missile does) on synthetic rows, plus the audit of the built mod when one exists.
Run: py -3 -m unittest discover -s tools/tests -p "test_missile_looks.py" """
import os
import struct
import subprocess
import sys
import unittest
from pathlib import Path
from unittest import mock

from collections import Counter

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import projtemp  # noqa: E402,F401  (temp files stay inside the project, tools/projtemp.py)
import effects_hd as fx  # noqa: E402
import fxpaths  # noqa: E402
import missile_looks as ml  # noqa: E402

ORANGE = {"n": 12, "w": 60, "h": 60, "rgb": [200, 110, 40], "hsv": [0.07, 0.8, 0.8], "hue": [100] + [0] * 11}
BLUE = {"n": 8, "w": 60, "h": 60, "rgb": [60, 80, 200], "hsv": [0.63, 0.7, 0.8], "hue": [0] * 7 + [100] + [0] * 4}
ROOT_ONLY = {"entities": [{"components": [{"type": "UnitRootComponent"}]}, {"components": [{"type": "TransformDefinitionComponent"}]}]}
DRAWS = {"entities": [{"components": [{"type": "VfxDefinitionComponent", "filename": "x"}]}]}


def row(name, art_name="", art=None, **cols):
    return fx.Prof("missile", name, art_name, {"Missile": name, **cols}, art)


class FakeModels(ml.Models):
    def __init__(self, defs):
        super().__init__()
        self.memo = dict(defs)


def d2r_rows():
    """Vanilla: a fire projectile, a blue projectile, an explosion and a ground fire, each on its own model."""
    fire = row("firebolt", "firebolt", ORANGE, Vel="20", Range="30", LoopAnim="1")
    bolt = row("chainlightning", "chainlightning", BLUE, Vel="30", Range="30", LoopAnim="1")
    boom = row("fireexplode", "fireexplode", ORANGE, Range="12", LoopAnim="0")
    flame = row("groundfire", "groundfire", ORANGE, Range="90", LoopAnim="1")
    return {p.name: p for p in (fire, bolt, boom, flame)}


MAP = {"firebolt": "firebolt", "chainlightning": "chain_bolt", "fireexplode": "fire_boom", "groundfire": "ground_fire", "dead": "stub"}
MODELS = {"firebolt": DRAWS, "chain_bolt": DRAWS, "fire_boom": DRAWS, "ground_fire": DRAWS, "stub": ROOT_ONLY}


class Learn(unittest.TestCase):
    def test_a_definition_without_an_effect_draws_nothing(self):
        self.assertFalse(ml.definition_draws(ROOT_ONLY))
        self.assertTrue(ml.definition_draws(DRAWS))
        self.assertFalse(ml.definition_draws(None))

    def test_kinds(self):
        self.assertEqual(ml.kind_of(row("a", Vel="20")), "flight")
        self.assertEqual(ml.kind_of(row("a", Range="12", LoopAnim="0")), "burst")
        self.assertEqual(ml.kind_of(row("a", Range="90", LoopAnim="1")), "ground")
        piece = row("a", Range="12", LoopAnim="1")
        piece.sub = True
        self.assertEqual(ml.kind_of(piece), "trail")

    def test_needs_tells_a_row_that_stays_from_one_that_plays_once(self):
        art = dict(ORANGE, n=20)
        self.assertEqual(ml.needs(row("a", "x", art, Range="90", LoopAnim="1")), "ground")
        self.assertEqual(ml.needs(row("a", "x", art, Range="30", LoopAnim="1")), "burst")
        self.assertEqual(ml.needs(row("a", "x", None, Range="90", LoopAnim="1")), "ground")
        self.assertEqual(ml.needs(row("a", Vel="20")), "flight")

    def test_plays_once_is_a_model_vanilla_only_uses_on_bursts(self):
        self.assertTrue(ml.plays_once(Counter({"burst": 3})))
        self.assertFalse(ml.plays_once(Counter({"burst": 3, "ground": 1})))
        self.assertFalse(ml.plays_once(None))

    def test_one_flying_vanilla_row_does_not_make_an_explosion_a_projectile(self):
        lib = ml.learn_d2r(d2r_rows(), MAP, FakeModels(MODELS))
        usable = ml.usable_for(lib)
        self.assertFalse(ml.travels(usable["fire_boom"]))
        self.assertTrue(ml.travels(usable["firebolt"]))
        usable["fire_boom"]["flight"] += 1
        self.assertFalse(ml.travels(usable["fire_boom"]), "one flight against one burst is not mostly flight")

    def test_stubs_stay_out_of_the_library(self):
        lib = ml.learn_d2r({"dead": row("dead", "dead", ORANGE, Vel="20")}, MAP, FakeModels(MODELS))
        self.assertEqual(lib["flight"], [])


class LegacyPicture(unittest.TestCase):
    def test_a_logic_row_shows_its_trail_pieces(self):
        piece = row("bzzt", "bluething", BLUE, Range="12", LoopAnim="1", NumDirections="32")
        carrier = row("funkybolt", "null", None, Vel="30", CltSubMissile1="bzzt")
        self.assertEqual(ml.legacy_picture(carrier, {"bzzt": piece}), (BLUE, "bluething"))

    def test_an_emitter_shows_nothing_of_its_own(self):
        fire = row("boombolt", "groundfire", ORANGE, Range="15", LoopAnim="1", NumDirections="1")
        emitter = row("maker", "null", None, Vel="12", CltSubMissile1="boombolt")
        self.assertEqual(ml.legacy_picture(emitter, {"boombolt": fire}), (None, ""))


class Decide(unittest.TestCase):
    def run_one(self, profs, current, **kw):
        models = FakeModels(MODELS)
        lib = ml.learn_d2r(d2r_rows(), MAP, models)
        return {d["name"]: d for d in ml.decide(profs, lib, current, models, **kw)}

    def test_a_flying_row_on_an_explosion_gets_a_projectile(self):
        d = self.run_one({"flamefront": row("flamefront", "fireexplode", ORANGE, Vel="24", Range="50")}, {"flamefront": "fire_boom"})
        self.assertEqual((d["flamefront"]["action"], d["flamefront"]["model"]), ("new", "firebolt"))

    def test_a_logic_row_that_draws_in_legacy_gets_a_picture(self):
        piece = row("bzzt", "bluething", BLUE, Range="12", LoopAnim="1", NumDirections="32")
        carrier = row("funkybolt", "null", None, Vel="30", CltSubMissile1="bzzt")
        d = self.run_one({"funkybolt": carrier, "bzzt": piece}, {"funkybolt": "null", "bzzt": "fire_boom"})
        self.assertEqual((d["funkybolt"]["action"], d["funkybolt"]["model"]), ("new", "chain_bolt"))

    def test_a_row_that_already_flies_on_a_projectile_stays(self):
        d = self.run_one({"own": row("own", "firebolt", ORANGE, Vel="20", Range="30")}, {"own": "firebolt"})
        self.assertEqual(d["own"]["action"], "keep")

    def test_a_scaled_or_tinted_projectile_stays(self):
        profs = {"own": row("own", "firebolt", ORANGE, Vel="20"), "tint": row("tint", "firebolt", ORANGE, Vel="20")}
        models = dict(MODELS, mxl_firebolt_s120=DRAWS, mxl_fire_c0ffee=DRAWS)
        fake = FakeModels(models)
        lib = ml.learn_d2r(d2r_rows(), MAP, fake)
        out = {d["name"]: d["action"] for d in ml.decide(profs, lib, {"own": "mxl_firebolt_s120", "tint": "mxl_fire_c0ffee"}, fake,
                                                          tinted={"mxl_fire_c0ffee": "firebolt"})}
        self.assertEqual(out, {"own": "keep", "tint": "keep"})

    def test_a_trail_piece_the_flying_row_carries_may_stay_a_stub(self):
        piece = row("puff", "fireexplode", ORANGE, Range="30", LoopAnim="0")
        piece.sub = True
        carrier = row("ball", "null", None, Vel="16", CltSubMissile1="puff")
        d = self.run_one({"ball": carrier, "puff": piece}, {"ball": "null", "puff": "stub"})
        self.assertEqual(d["puff"]["action"], "keep")
        self.assertEqual(d["ball"]["action"], "new")

    def test_a_row_that_stays_on_the_ground_gets_a_model_that_draws(self):
        d = self.run_one({"pit": row("pit", "groundfire", ORANGE, Range="90", LoopAnim="1")}, {"pit": "stub"})
        self.assertEqual((d["pit"]["action"], d["pit"]["model"]), ("new", "ground_fire"))

    def test_a_hand_pick_is_never_overruled(self):
        p = row("own", "picked", ORANGE, Vel="20")
        d = self.run_one({"own": p}, {"own": "fire_boom"}, hand_arts=frozenset({"picked"}))
        self.assertEqual(d["own"]["action"], "keep")

    def test_a_row_that_stays_gets_a_model_vanilla_keeps_on_screen(self):
        d = self.run_one({"mine": row("mine", "groundfire", ORANGE, Range="125", LoopAnim="1")}, {"mine": "fire_boom"})
        self.assertEqual((d["mine"]["action"], d["mine"]["model"]), ("new", "ground_fire"))
        self.assertIn("stays", d["mine"]["why"])

    def test_a_row_that_stays_on_a_model_it_may_keep_is_left_alone(self):
        d = self.run_one({"pit": row("pit", "groundfire", ORANGE, Range="125", LoopAnim="1")}, {"pit": "ground_fire"})
        self.assertEqual(d["pit"]["action"], "keep")

    def test_a_row_that_plays_its_art_once_is_not_held_to_it(self):
        """LoopAnim 1 with a Range about as long as the art: one pass, it is a burst whatever the column says."""
        art = dict(ORANGE, n=30)
        d = self.run_one({"oneshot": row("oneshot", "groundfire", art, Range="30", LoopAnim="1")}, {"oneshot": "fire_boom"})
        self.assertEqual(d["oneshot"]["action"], "keep")

    def test_a_stub_on_d2r_s_own_row_is_d2r_s_choice(self):
        p = row("dust", "firesmoke", ORANGE, Range="100", LoopAnim="0")
        d = self.run_one({"dust": p}, {"dust": "stub"}, own=frozenset({"dust"}))
        self.assertEqual(d["dust"]["action"], "keep")

    def test_nothing_close_keeps_what_draws_and_is_listed(self):
        grey = {"n": 8, "w": 60, "h": 60, "rgb": [120, 120, 120], "hsv": [0.0, 0.0, 0.47], "hue": [0] * 12}
        d = self.run_one({"odd": row("odd", "thing", grey, Vel="20", Range="30")}, {"odd": "fire_boom"})
        self.assertEqual((d["odd"]["action"], d["odd"]["model"]), ("hand", "fire_boom"))

    def test_rows_without_a_legacy_picture_are_not_looked_at(self):
        self.assertEqual(self.run_one({"logic": row("logic", "null", None, Vel="20")}, {"logic": "null"}), {})


class HandPicks(unittest.TestCase):
    """A line of hd-effects-picks.tsv with `rows` covers those rows; a line for the art covers all of the art's rows."""

    def test_a_line_for_an_art_covers_every_row_of_it(self):
        names = fx.picked_names({("missile", "smoke"): {}})
        self.assertTrue(ml.picked("smoke", "anyrow", names))

    def test_a_line_with_rows_leaves_the_art_s_other_rows_free(self):
        names = fx.picked_names({("missile", "firearrowexplode2", "spazfire"): {}}, "missile")
        self.assertTrue(ml.picked("firearrowexplode2", "SpazFire", names))
        self.assertFalse(ml.picked("firearrowexplode2", "flamefront", names))

    def test_a_row_called_like_its_art_leaves_the_art_s_other_rows_free(self):
        names = fx.picked_names({("missile", "dopplezonexplode", "dopplezonexplode"): {}}, "missile")
        self.assertTrue(ml.picked("dopplezonexplode", "dopplezonexplode", names))
        self.assertFalse(ml.picked("dopplezonexplode", "plasmablast", names))

    def test_the_kind_filter(self):
        names = fx.picked_names({("overlay", "a"): {}, ("missile", "b"): {}}, "missile")
        self.assertEqual(names, frozenset({"b"}))

    def test_the_other_rows_of_a_picked_art_are_still_decided(self):
        models = FakeModels(MODELS)
        lib = ml.learn_d2r(d2r_rows(), MAP, models)
        names = fx.picked_names({("missile", "fireexplode", "spazfire"): {}}, "missile")
        profs = {n: row(n, "fireexplode", ORANGE, Vel="24", Range="50") for n in ("spazfire", "flamefront")}
        d = {x["name"]: x for x in ml.decide(profs, lib, {"spazfire": "fire_boom", "flamefront": "fire_boom"}, models, hand_arts=names)}
        self.assertEqual(d["spazfire"]["action"], "keep")
        self.assertEqual((d["flamefront"]["action"], d["flamefront"]["model"]), ("new", "firebolt"))


class Audit(unittest.TestCase):
    def test_a_flying_row_with_no_picture_is_caught(self):
        models = FakeModels(MODELS)
        usable = ml.usable_for(ml.learn_d2r(d2r_rows(), MAP, models))
        bad = row("bad", "fireexplode", ORANGE, Vel="20")
        boom = row("boom", "fireexplode", ORANGE, Vel="20")
        fine = row("fine", "firebolt", ORANGE, Vel="20")
        unreached = row("alone", "fireexplode", ORANGE, Vel="20")
        for p in (bad, boom, fine):
            p.skills = {"Some Skill"}
        found = ml.audit({"bad": bad, "boom": boom, "fine": fine, "alone": unreached},
                         {"bad": "stub", "boom": "fire_boom", "fine": "firebolt", "alone": "stub"}, models, usable)
        self.assertEqual(found, ["bad: stub", "boom: fire_boom"])

    @unittest.skipUnless((fxpaths.MOD / "data" / "hd" / "missiles" / "missiles.json").exists() and fxpaths.TABLES.exists(),
                         "needs a built work/mod")
    def test_the_built_mod_has_a_picture_for_every_flying_missile_a_skill_reaches(self):
        r = subprocess.run([sys.executable, str(fxpaths.ROOT / "tools" / "missile_looks.py"), "--check"],
                           cwd=fxpaths.ROOT, env=dict(os.environ, PYTHONIOENCODING="utf-8"),
                           capture_output=True, text=True, encoding="utf-8", errors="replace")
        self.assertEqual(r.returncode, 0, r.stdout[-1500:] + r.stderr[-500:])


class ArtStatistics(unittest.TestCase):
    def test_art_left_of_its_anchor_is_art(self):
        """Blast Wave's ring: every pixel at negative offsets, which the statistics used to read as an empty file."""
        art = fx.ArtCache(Path("does-not-exist.json"))
        art.pal = np.full((256, 3), 200, np.float64)
        data = bytearray(19)
        data[2] = 1
        struct.pack_into("<I", data, 3, 1)
        with mock.patch("dcc.decode_direction", return_value=(0, 0, 4, 4, [(-90, -60, 4, 4, bytes([0, 5, 5, 0] * 4))])):
            st = art.stats(bytes(data))
        self.assertIsNotNone(st)
        self.assertEqual((st["n"], st["w"], st["h"]), (1, 2, 4))


if __name__ == "__main__":
    unittest.main()
