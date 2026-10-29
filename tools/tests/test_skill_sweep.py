"""tools/skill_sweep.py: the parsers of the harness answers, the signal attribution, the verdict and the report."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import projtemp  # noqa: E402,F401  (temp files stay inside the project, tools/projtemp.py)
import skill_sweep as ss  # noqa: E402

MISSILES = [
    {"Missile": "arrow", "*ID": "0"},
    {"Missile": "bolt", "*ID": "1"},
    {"Missile": "sweepcenter", "*ID": "1119", "SubMissile1": "sweepring"},
    {"Missile": "sweepring", "*ID": "1121", "HitSubMissile1": "sweepspark"},
    {"Missile": "sweepspark", "*ID": "1122", "ExplosionMissile": "sweepdeep"},
    {"Missile": "sweepdeep", "*ID": "1123"},
    {"Missile": "Expansion", "*ID": "Expansion"},
]


def snap(mana=100, target=50, mode=1, states=(), missiles=None, mons=()):
    return {"mana": mana, "target": target, "mode": mode, "states": set(states), "missiles": missiles or {}, "mons": set(mons)}


def skill(buttons=("left", "right"), signals=None, **kw):
    r = {"id": 1, "name": "X", "buttons": list(buttons), "select": {b: "ok" for b in buttons}, "asserts": [],
         "target": {b: {"clicked": True, "signals": list(signals or [])} for b in buttons}, "notarget": {"usable": 0, "code": 0}}
    r.update(kw)
    return r


class TableTest(unittest.TestCase):
    def test_own_missiles_two_levels(self):
        row = {"srvmissile": "sweepcenter", "cltmissile": "sweepcenter"}
        self.assertEqual(ss.own_missiles(row, MISSILES), {1119, 1121, 1122})
        self.assertEqual(ss.own_missiles(row, MISSILES, depth=3), {1119, 1121, 1122, 1123})
        self.assertEqual(ss.own_missiles({}, MISSILES), set())

    def test_weapon_missiles(self):
        weapons = [{"missiletype": "0"}, {"missiletype": ""}, {"missiletype": "1"}, {"missiletype": "9999"}]
        self.assertEqual(ss.weapon_missiles(weapons, MISSILES), {0, 1})

    def test_watch_slot(self):
        self.assertEqual(ss.watch_slot({"cltdofunc": "83", "cltprgfunc1": "25"}), 83)
        self.assertEqual(ss.watch_slot({"cltdofunc": "", "cltprgfunc1": "25"}), 25)  # Batstrike
        self.assertIsNone(ss.watch_slot({"cltdofunc": "0"}))
        self.assertIsNone(ss.watch_slot({"cltdofunc": "130"}))  # beyond the client do bound

    def test_buttons_and_itypes(self):
        self.assertEqual(ss.buttons({"leftskill": "1", "rightskill": ""}), ["left"])
        self.assertEqual(ss.itypes({"itypea1": "spea", "restrict": "2", "State1": "wolf"}), ["spea", "state wolf"])


class ParseTest(unittest.TestCase):
    def test_parse_watch(self):
        self.assertEqual(ss.parse_watch(["watch cltdo 83: calls=3 nonzero=1 last=546", "watch OK"]), (3, 1, 546))
        self.assertEqual(ss.parse_watch(["watch (none): calls=0 nonzero=0 last=-1"]), (0, 0, -1))
        self.assertEqual(ss.parse_watch(["watch FAIL no answer in 8 s (not in a game?)"]), (None, None, None))

    def test_screen_spot(self):
        p = {"x": 100, "y": 200}
        self.assertEqual(ss.screen_spot(p, (100, 200)), (0.5, 0.45))
        fx, fy = ss.screen_spot(p, (104, 200))  # 4 sub-tiles east: right of and below the player
        self.assertAlmostEqual(fx, (800 + 108) / 1600)
        self.assertAlmostEqual(fy, (405 + 54) / 900)

    def test_parse_selected(self):
        lines = ["skill left=546 right=0", "skill OK"]
        self.assertEqual(ss.parse_selected(lines, "left"), 546)
        self.assertEqual(ss.parse_selected(lines, "right"), 0)
        self.assertIsNone(ss.parse_selected(["skill FAIL refused"], "left"))


class SignalTest(unittest.TestCase):
    def test_attack_only_is_damage(self):
        # Attack (primed on the button): melee damage, mode A1: no sign of the skill
        sig = ss.signals(snap(), snap(target=40, mode=7), 5)
        self.assertEqual(sig, ["damage"])
        self.assertFalse(ss.proven(sig))

    def test_own_and_other_missiles(self):
        own = {1119}
        self.assertIn("missile", ss.signals(snap(), snap(missiles={1119: 1, 7: 1}), None, own, {0}))
        self.assertEqual(ss.signals(snap(), snap(missiles={7: 2}), None, own, {0}), ["other missile"])
        self.assertEqual(ss.signals(snap(), snap(missiles={0: 2}), None, own, {0}), [])  # the bow's own arrow: Attack

    def test_other_signs(self):
        sig = ss.signals(snap(states={1}), snap(mana=90, target=None, mode=13, states={1, 2}, mons={9}), 5)
        self.assertEqual(sig, ["mana", "target gone", "state", "mode", "summon"])
        self.assertTrue(ss.proven(sig))
        self.assertTrue(ss.proven(["cltdo"]))
        self.assertTrue(ss.proven(["warp", "damage"]))

    def test_warped(self):
        self.assertTrue(ss.warped((10, 10), (1, 13, 10)))  # Spirit Walk: standing 3 sub-tiles away at once
        self.assertFalse(ss.warped((10, 10), (2, 13, 10)))  # walking (Attack to its target)
        self.assertFalse(ss.warped((10, 10), (7, 13, 10)))  # Attack already hitting
        self.assertFalse(ss.warped((10, 10), (1, 11, 10)))  # one sub-tile: not a teleport
        self.assertFalse(ss.warped((10, 10), (None, None, None)))


class VerdictTest(unittest.TestCase):
    def test_ok(self):
        self.assertEqual(ss.verdict(skill(signals=["cltdo", "damage"])), "ok")
        self.assertEqual(ss.verdict(skill(buttons=("right",), signals=[], aura_states={"right": [43]})), "ok")

    def test_unproven_and_broken(self):
        self.assertEqual(ss.verdict(skill(signals=["damage"])), "unproven")
        self.assertEqual(ss.verdict(skill(signals=[])), "broken")
        self.assertEqual(ss.verdict(skill(signals=["mana"], crash=True)), "broken")
        self.assertEqual(ss.verdict(skill(signals=["mana"], hang=True)), "broken")
        r = skill(signals=["mana"])
        r["select"]["left"] = "refused"
        self.assertEqual(ss.verdict(r), "broken")

    def test_blocked_only_without_a_sign(self):
        self.assertEqual(ss.verdict(skill(signals=[], notarget={"usable": 5})), "blocked")
        self.assertEqual(ss.verdict(skill(signals=["damage"], itypes=["spea"], notarget={"usable": 2})), "blocked")
        self.assertEqual(ss.verdict(skill(signals=[], notarget={"usable": 2})), "broken")  # code 2 without item needs
        self.assertEqual(ss.verdict(skill(signals=["missile"], notarget={"usable": 5})), "ok")

    def test_server_signals_never_make_ok(self):
        r = skill(signals=[])
        r["target"]["left"]["server"] = ["mana", "missile"]  # an old sweep.json's server cast at the target
        r["notarget"] = {"usable": 0, "code": 0, "signals": ["missile"]}
        self.assertEqual(ss.verdict(r), "broken")

    def test_passive_and_assert(self):
        self.assertEqual(ss.verdict(skill(buttons=())), "passive")
        self.assertEqual(ss.verdict(skill(buttons=(), asserts=["BC_ASSERT: x | a.cpp"])), "assert")
        self.assertEqual(ss.verdict(skill(signals=["mana"], asserts=["BC_ASSERT: x | a.cpp"])), "assert")


class ReportTest(unittest.TestCase):
    def test_target_text(self):
        self.assertEqual(ss.target_text({"clicked": True, "signals": ["cltdo", "mana"], "watch": {"slot": 19}}), "cltdo+mana")
        self.assertEqual(ss.target_text({"clicked": True, "signals": ["damage"], "second": True,
                                         "watch": {"slot": 83, "calls": 0, "last": -1}}),
                         "damage (cltdo 83: 0 calls, last -1) (2nd click)")
        self.assertEqual(ss.target_text({"clicked": False, "signals": []}), "no click")
        self.assertEqual(ss.target_text({"crash": True}), "CRASH")

    def test_asserts_and_bugs(self):
        a = "BC_ASSERT: nDirectionIndex < nDirections | D2Game\\src\\Missiles\\MissMode.cpp:120 | 1 2"
        self.assertEqual(ss.short_assert(a), "`BC_ASSERT: nDirectionIndex < nDirections` (MissMode.cpp:120)")
        self.assertEqual(ss.bug_of(ss.short_assert(a)), "#54")
        self.assertEqual(ss.bug_of("`other` (x.cpp)"), "-")

    def test_render(self):
        data = {"started": "s", "finished": "f", "classes": {"sor": {"char": "SweepSorceress", "skills": {
            "546": dict(skill(signals=["cltdo", "missile"]), id=546, name="Mana Sweep", watch_slot=83),
            "524": dict(skill(buttons=()), id=524, name="Living Flame"),
            "525": dict(skill(signals=["damage"]), id=525, name="Flamestrike", hang=True),
        }}}}
        text = ss.render(data, {"546": {"cltdofunc": "83"}})
        self.assertIn("| sorceress | 3 | 1 | 0 | 1 | 0 | 0 | 1 | 1 of 1 |", text)
        self.assertIn("| hang | - | 1: 525 Flamestrike |", text)
        self.assertIn("| 546 | Mana Sweep | left/right | left ok, right ok | left: cltdo+missile; right: cltdo+missile |", text)
        self.assertIn("| 525 | Flamestrike |", text)
        self.assertIn("| HANG | broken |", text)


if __name__ == "__main__":
    unittest.main()
