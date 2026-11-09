"""Unit tests of tools/skill_looks.py (every skill's visual chain in HD) on synthetic rows, plus the check of the built mod when one exists.
Run: py -3 -m unittest discover -s tools/tests -p "test_skill_looks.py" """
import os
import subprocess
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import projtemp  # noqa: E402,F401  (temp files stay inside the project, tools/projtemp.py)
import effects_hd as fx  # noqa: E402
import fxpaths  # noqa: E402
import missile_looks as ml  # noqa: E402
import skill_looks as sl  # noqa: E402

ORANGE = {"n": 12, "w": 60, "h": 60, "rgb": [200, 110, 40], "hsv": [0.07, 0.8, 0.8], "hue": [100] + [0] * 11}
ROOT_ONLY = {"entities": [{"components": [{"type": "UnitRootComponent"}]}, {"components": [{"type": "TransformDefinitionComponent"}]}]}
DRAWS = {"entities": [{"components": [{"type": "VfxDefinitionComponent", "filename": "x.particles"}]}]}


def filtered(*skills):
    return {"entities": [{"components": [{"type": "VfxDefinitionComponent", "filename": f"{s or 'def'}.particles"},
                                         {"type": "UnitSourceSkillFilterComponent", "sourceSkill": s}]} for s in skills]}


def row(name, art_name="", art=None, **cols):
    return fx.Prof("missile", name, art_name, {"Missile": name, **cols}, art)


def overlay(name, art_name="", art=None, folder="common", **cols):
    p = fx.Prof("overlay", name, art_name, {"overlay": name, "Character": folder, **cols}, art)
    p.folder = folder
    return p


class FakeModels(ml.Models):
    def __init__(self, defs):
        super().__init__()
        self.memo = dict(defs)


class FakeHd:
    """What `Hd` offers the scan, from dictionaries."""

    def __init__(self, current, models, overlays=None):
        self.current = current
        self.models = FakeModels(models)
        self.overlays = overlays or {}

    def model_of(self, r):
        return self.current.get(fx.norm_key(r), self.current.get(r.lower()))

    def overlay_definition(self, folder, r):
        return self.overlays.get(f"{folder.lower()}/{fx.norm_key(r)}")


def tables(skills=(), missiles=(), overlays=(), states=None, d2r_missiles=(), d2r_overlays=()):
    return sl.Tables(skills=list(skills), missiles={m.name: m for m in missiles}, overlays={o.name: o for o in overlays},
                     states={k.lower(): v for k, v in (states or {}).items()}, d2r_missiles={m.name: m for m in d2r_missiles},
                     d2r_overlays={o.name: o for o in d2r_overlays}, d2r_states={})


def scan(t, hd, picks=frozenset(), tinted=None):
    return sl.Scan(t, hd, picks, tinted, d2r_map={})


def skill(name, **cols):
    return {"skill": name, **cols}


# A D2R library for the missile side of the scan: vanilla rows that say what each model is for
VANILLA = [row("firebolt", "firebolt", ORANGE, Vel="20", Range="30", LoopAnim="1"),
           row("boom", "boom", ORANGE, Range="12", LoopAnim="0"),
           row("wall", "wall", ORANGE, Range="90", LoopAnim="1")]
MAP = {"firebolt": "firebolt", "boom": "fire_boom", "wall": "ground_fire"}
MODELS = {"firebolt": DRAWS, "fire_boom": DRAWS, "ground_fire": DRAWS, "stub": ROOT_ONLY}


def scanner(t, current):
    s = sl.Scan.__new__(sl.Scan)
    s.t, s.hd = t, FakeHd(current, MODELS)
    s.hand_arts, s.tinted = frozenset(), {}
    s.d2r_map = {}
    s.lib = ml.learn_d2r(t.d2r_missiles or {m.name: m for m in VANILLA}, MAP, s.hd.models)
    s.usable = ml.usable_for(s.lib)
    s.carried = ml.carried_pieces(t.missiles)
    s.own_m = frozenset()
    return s


class Definitions(unittest.TestCase):
    def test_a_filtered_entity_draws_only_for_its_skill(self):
        d = filtered("Hex Bane")
        self.assertFalse(sl.definition_draws(d))
        self.assertTrue(sl.definition_draws(d, "Hex Bane"))
        self.assertTrue(sl.named_only(d))

    def test_the_empty_filter_is_every_other_skill(self):
        d = filtered("", "Fire Wall")
        self.assertTrue(sl.definition_draws(d))
        self.assertTrue(sl.definition_draws(d, "Fire Wall"))
        self.assertFalse(sl.named_only(d))

    def test_a_named_entity_without_a_file_draws_nothing_for_that_skill(self):
        d = {"entities": [{"components": [{"type": "VfxDefinitionComponent", "filename": ""}, {"type": "UnitSourceSkillFilterComponent", "sourceSkill": "Lightning"}]},
                          {"components": [{"type": "VfxDefinitionComponent", "filename": "x"}, {"type": "UnitSourceSkillFilterComponent", "sourceSkill": ""}]}]}
        self.assertTrue(sl.definition_draws(d))
        self.assertFalse(sl.entity_draws(d["entities"][0], "Lightning"))

    def test_a_stub_draws_nothing(self):
        self.assertFalse(sl.definition_draws(ROOT_ONLY))
        self.assertFalse(sl.definition_draws({"entities": [{"components": []}]}))


class Walk(unittest.TestCase):
    def test_the_whole_chain(self):
        hit = row("hit", "boom", ORANGE)
        puff = row("puff", "boom", ORANGE)
        boom = row("boom", "boom", ORANGE)
        bolt = row("bolt", "firebolt", ORANGE, Vel="20", HitSubMissile1="hit", CltSubMissile1="puff", ExplosionMissile="boom", ProgOverlay="prog")
        t = tables(missiles=[bolt, hit, puff, boom], overlays=[overlay("cast_o"), overlay("prog"), overlay("state_o")],
                   states={"st": {"state": "st", "overlay1": "state_o"}})
        items, missing = sl.walk(skill("S", srvmissile="bolt", castoverlay="cast_o", aurastate="st"), t)
        got = {(k, n): (r, g) for k, n, r, g in items}
        self.assertEqual(got[("missile", "bolt")][0], "missile")
        self.assertEqual(got[("missile", "hit")][0], "sub")
        self.assertEqual(got[("missile", "puff")][0], "clt")
        self.assertEqual(got[("missile", "boom")][0], "explode")
        self.assertEqual(got[("overlay", "prog")][0], "progressive")
        self.assertEqual(got[("overlay", "cast_o")][0], "cast")
        self.assertEqual(got[("overlay", "state_o")], ("state", "st"))
        self.assertEqual(missing, [])

    def test_a_loop_of_missiles_ends(self):
        a, b = row("a", SubMissile1="b"), row("b", SubMissile1="a")
        items, _ = sl.walk(skill("S", srvmissile="a"), tables(missiles=[a, b]))
        self.assertEqual({n for _, n, _, _ in items}, {"a", "b"})

    def test_a_name_no_table_has_is_reported(self):
        items, missing = sl.walk(skill("S", srvmissile="ghost", aurastate="nostate"), tables())
        self.assertIn("missile ghost", missing)
        self.assertIn("state nostate", missing)


class MissileNodes(unittest.TestCase):
    def chain(self, missiles, current, **cols):
        t = tables(skills=[skill("S", **cols)], missiles=missiles, d2r_missiles=VANILLA)
        return scanner(t, current).chain(t.skills[0])

    def test_a_flying_row_on_a_stub_is_a_gap(self):
        c = self.chain([row("bolt", "firebolt", ORANGE, Vel="20", Range="30")], {"bolt": "stub"}, srvmissile="bolt")
        self.assertEqual((c.nodes[0].status, c.nodes[0].code, c.status), ("gap", "stub", "invisible"))

    def test_a_flying_row_on_an_explosion_is_a_gap_that_draws(self):
        c = self.chain([row("bolt", "firebolt", ORANGE, Vel="20", Range="30")], {"bolt": "fire_boom"}, srvmissile="bolt")
        self.assertEqual((c.nodes[0].status, c.nodes[0].code), ("gap", "play_once"))

    def test_a_row_that_stays_on_a_play_once_model_is_a_gap(self):
        c = self.chain([row("mine", "boom", ORANGE, Range="125", LoopAnim="1")], {"mine": "fire_boom"}, srvmissile="mine")
        self.assertEqual((c.nodes[0].status, c.nodes[0].code), ("gap", "play_once"))

    def test_a_row_that_plays_its_art_once_is_a_burst_whatever_loopanim_says(self):
        art = dict(ORANGE, n=29)
        c = self.chain([row("boom2", "boom", art, Range="29", LoopAnim="1")], {"boom2": "fire_boom"}, srvmissile="boom2")
        self.assertEqual(c.nodes[0].status, "draws")

    def test_a_piece_the_flying_row_carries_is_accepted(self):
        piece = row("puff", "boom", ORANGE, Range="30", LoopAnim="0")
        piece.sub = True
        bolt = row("bolt", "firebolt", ORANGE, Vel="20", CltSubMissile1="puff")
        c = self.chain([bolt, piece], {"bolt": "firebolt", "puff": "stub"}, srvmissile="bolt")
        by = {n.name: n.status for n in c.nodes}
        self.assertEqual(by, {"bolt": "draws", "puff": "accepted"})

    def test_a_logic_row_without_a_picture_is_blank(self):
        c = self.chain([row("logic", "null", None, Vel="20")], {"logic": "null"}, srvmissile="logic")
        self.assertEqual(c.status, "not visual")

    def test_a_logic_row_with_pieces_is_judged_on_its_pieces(self):
        piece = row("bzzt", "boom", ORANGE, Range="12", LoopAnim="0", NumDirections="32")
        carrier = row("funkybolt", "null", None, Vel="30", CltSubMissile1="bzzt")
        c = self.chain([carrier, piece], {"funkybolt": "firebolt", "bzzt": "stub"}, srvmissile="funkybolt")
        by = {n.name: n.status for n in c.nodes}
        self.assertEqual(by["funkybolt"], "draws")


class OverlayNodes(unittest.TestCase):
    def chain(self, overlays, defs, skills_row, states=None, d2r_overlays=()):
        t = tables(skills=[skills_row], overlays=overlays, states=states, d2r_overlays=d2r_overlays)
        s = scanner(t, {})
        s.hd = FakeHd({}, MODELS, defs)
        return s.chain(t.skills[0])

    def test_a_stub_overlay_is_a_gap(self):
        c = self.chain([overlay("cast", "cast_art", ORANGE)], {"common/cast": {"entities": [{"components": []}]}}, skill("S", castoverlay="cast"))
        self.assertEqual((c.nodes[0].status, c.nodes[0].code, c.status), ("gap", "stub", "invisible"))

    def test_no_definition_is_a_gap(self):
        c = self.chain([overlay("cast", "cast_art", ORANGE)], {}, skill("S", castoverlay="cast"))
        self.assertEqual((c.nodes[0].status, c.nodes[0].code), ("gap", "no_overlay"))

    def test_a_state_with_one_drawing_overlay_is_fine(self):
        states = {"auras": {"state": "auras", "overlay1": "front", "overlay2": "back"}}
        c = self.chain([overlay("front", "a", ORANGE), overlay("back", "b", ORANGE)],
                       {"common/front": DRAWS, "common/back": {"entities": [{"components": []}]}}, skill("S", aurastate="auras"), states)
        by = {n.name: (n.status, n.code) for n in c.nodes}
        self.assertEqual(by["front"], ("draws", ""))
        self.assertEqual(by["back"], ("accepted", "another overlay of the state draws"))
        self.assertEqual(c.status, "ok")

    def test_d2rs_own_stub_is_accepted_while_the_skill_draws(self):
        own = overlay("own", "art", ORANGE)
        c = self.chain([own, overlay("cast", "cast_art", ORANGE)], {"common/own": {"entities": [{"components": []}]}, "common/cast": DRAWS},
                       skill("S", castoverlay="cast", tgtoverlay="own"), d2r_overlays=[own])
        by = {n.name: n.status for n in c.nodes}
        self.assertEqual(by, {"own": "accepted", "cast": "draws"})
        self.assertEqual(c.status, "ok")

    def test_d2rs_own_stub_alone_is_a_gap(self):
        own = overlay("own", "art", ORANGE)
        c = self.chain([own], {"common/own": {"entities": [{"components": []}]}}, skill("S", castoverlay="own"), d2r_overlays=[own])
        self.assertEqual((c.nodes[0].status, c.status), ("gap", "invisible"))

    def test_a_named_only_definition_draws_for_its_skill_and_is_a_gap_for_others(self):
        d = filtered("Hex Bane")
        c = self.chain([overlay("hex", "a", ORANGE)], {"common/hex": d}, skill("Hex Bane", castoverlay="hex"))
        self.assertEqual(c.nodes[0].status, "draws")
        c = self.chain([overlay("hex", "a", ORANGE)], {"common/hex": d}, skill("Other", castoverlay="hex"))
        self.assertEqual(c.nodes[0].code, "filtered")

    def test_a_row_without_art_is_blank(self):
        c = self.chain([overlay("noart", "null")], {}, skill("S", castoverlay="noart"))
        self.assertEqual((c.nodes[0].status, c.status), ("blank", "not visual"))


class Status(unittest.TestCase):
    def chain(self, status):
        return sl.Chain("S", status=status)

    def test_words(self):
        self.assertEqual(sl.final_status(self.chain("invisible"), self.chain("ok")), "fixed")
        self.assertEqual(sl.final_status(self.chain("ok"), self.chain("ok")), "ok")
        self.assertEqual(sl.final_status(self.chain("ok"), self.chain("partial")), "hand")
        self.assertEqual(sl.final_status(self.chain("not visual"), self.chain("not visual")), "not visual")

    def test_invisible_means_something_in_legacy_and_nothing_in_hd(self):
        chains = {"A": sl.Chain("A", status="invisible"), "B": sl.Chain("B", status="invisible"), "C": sl.Chain("C", status="ok")}
        self.assertEqual(sl.invisible_reached(chains, {"a": {"monster"}, "c": {"class:ama"}}), ["A"])


class OverlayRepair(unittest.TestCase):
    def test_a_state_overlay_takes_a_looping_one_and_a_cast_flash_a_one_shot(self):
        loop = overlay("aura_fire", "firearea", ORANGE)
        once = overlay("cast_fire", "firecast", ORANGE)
        p = overlay("mine", "fire", ORANGE)
        c, _, _ = sl.choose_overlay(p, True, [loop, once], {"aura_fire"})
        self.assertIs(c, loop)
        c, _, _ = sl.choose_overlay(p, False, [loop, once], {"aura_fire"})
        self.assertIs(c, once)


class BuiltMod(unittest.TestCase):
    @unittest.skipUnless((fxpaths.MOD / "data" / "hd" / "missiles" / "missiles.json").exists() and fxpaths.TABLES.exists(), "needs a built work/mod")
    def test_no_skill_somebody_can_use_ends_in_nothing_in_hd(self):
        r = subprocess.run([sys.executable, str(fxpaths.ROOT / "tools" / "skill_looks.py"), "--check"], cwd=fxpaths.ROOT,
                           env=dict(os.environ, PYTHONIOENCODING="utf-8"), capture_output=True, text=True, encoding="utf-8", errors="replace")
        self.assertEqual(r.returncode, 0, r.stdout[-1500:] + r.stderr[-500:])


if __name__ == "__main__":
    unittest.main()
