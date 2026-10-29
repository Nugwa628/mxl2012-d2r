"""tools/skill_use_audit.py (lane skilluse): D2R's skill usability test (0x33f360) on small tables; and the verdicts of the
player-path check `su_use` (game_checks.su_verdicts). No game is started.
Run: py -3 -I -m unittest discover -s tools/tests -p "test_skill_use_audit.py" """
import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import projtemp  # noqa: E402,F401  (temp files stay inside the project, tools/projtemp.py)
import skill_use_audit as sua  # noqa: E402


def T(code, e1="", e2="", cls="", shoots=""):
    return {"Code": code, "Equiv1": e1, "Equiv2": e2, "Class": cls, "Shoots": shoots}


ITEMTYPES = [T("weap"), T("mele", "weap"), T("miss", "weap"), T("axe", "mele"), T("swor", "mele"), T("taxe", "axe", "thro"),
             T("thro", "weap"), T("bow", "miss", shoots="bowq"), T("bowq"), T("shie"), T("shld", "shie"),
             T("assn", cls="ass"), T("h2h", "mele", "assn", cls="ass"), T("abow", "bow", cls="ama", shoots="bowq")]
WEAPONS = [{"name": "Axe", "code": "axe", "type": "axe"}, {"name": "Sword", "code": "ssd", "type": "swor"},
           {"name": "Bow", "code": "sbw", "type": "bow", "2handed": "1"}, {"name": "Claw", "code": "ktr", "type": "h2h"},
           {"name": "Throwing Axe", "code": "tax", "type": "taxe"}]
ARMOR = [{"name": "Buckler", "code": "buc", "type": "shld"}]
MISC = [{"name": "Arrows", "code": "aqv", "type": "bowq"}]
STATES = [{"state": "form", "restrict": "1"}, {"state": "buff", "restrict": ""}, {"state": "lock", "restrict": "1"}]


def skill(sid, name, cls, **kw):
    row = {"*Id": str(sid), "skill": name, "charclass": cls, "skilldesc": "d%d" % sid, "InGame": "1", "restrict": "1"}
    row.update(kw)
    return row


def tables(skills, misc=MISC):
    return {"skills": skills, "skilldesc": [{"skilldesc": s["skilldesc"], "SkillPage": "1"} for s in skills],
            "states": STATES, "itemtypes": ITEMTYPES, "weapons": WEAPONS, "armor": ARMOR, "misc": misc}


def kinds(found, sid):
    return sorted(f["kind"] for f in found if f["id"] == sid)


class WeaponTest(unittest.TestCase):
    def setUp(self):
        self.types = sua.Types(ITEMTYPES)
        self.items = {i.code: i for i in sua.bases(self.types, WEAPONS, ARMOR, MISC)}

    def test_two_melee_weapons(self):
        bh = {"itypea1": "mele", "itypeb1": "mele"}  # Blood Hatred / Frenzy
        axe, sword, shield = self.items["axe"], self.items["ssd"], self.items["buc"]
        self.assertFalse(sua.weapon_ok(bh, axe, None))  # the b list wants an item in the other hand
        self.assertFalse(sua.weapon_ok(bh, axe, shield))
        self.assertTrue(sua.weapon_ok(bh, axe, sword))
        self.assertTrue(sua.weapon_ok(bh, sword, axe))

    def test_empty_hand_rule_of_a_plain_melee_skill(self):
        row = {"itypea1": "mele"}
        self.assertTrue(sua.weapon_ok(row, self.items["axe"], None))
        self.assertTrue(sua.weapon_ok(row, self.items["axe"], self.items["buc"]))
        self.assertTrue(sua.weapon_ok(row, None, None))  # bare hands count as melee (types weap / mele / h2h)
        self.assertFalse(sua.weapon_ok(row, None, self.items["sbw"]))  # ... not with a non-melee weapon in the other hand

    def test_bow_needs_its_quiver_unless_noammo(self):
        row = {"itypea1": "miss"}
        bow, quiver = self.items["sbw"], self.items["aqv"]
        self.assertFalse(sua.weapon_ok(row, bow, None))
        self.assertTrue(sua.weapon_ok(row, bow, quiver))
        self.assertTrue(sua.weapon_ok(dict(row, noammo="1"), bow, None))

    def test_excluded_type(self):
        self.assertFalse(sua.weapon_ok({"itypea1": "mele", "etypea1": "h2h"}, self.items["ktr"], None))

    def test_requiresweapon(self):
        self.assertFalse(sua.weapon_ok({"etypea1": "h2h", "requiresweapon": "1"}, None, self.items["buc"]))

    def test_loadouts_dual_wield_only_barbarian_and_assassin_claws(self):
        def lefts(cls):
            return {(r.code if r else None, l.code if l else None) for r, l in sua.loadouts(cls, list(self.items.values()))}
        self.assertIn(("axe", "ssd"), lefts("bar"))
        self.assertNotIn(("axe", "ssd"), lefts("pal"))
        self.assertIn(("ktr", "ktr"), lefts("ass"))
        self.assertNotIn(("axe", "ssd"), lefts("ass"))
        self.assertNotIn("ktr", {r for r, _l in lefts("bar")})  # claws are an assassin item type
        self.assertNotIn(("sbw", "buc"), lefts("ama"))  # a two-handed bow leaves no hand for a shield


class Audit(unittest.TestCase):
    def test_kinds(self):
        rows = [skill(1, "Blood Hatred", "bar", itypea1="mele", itypeb1="mele"),
                skill(2, "Pal Frenzy", "pal", itypea1="mele", itypeb1="mele"),
                skill(3, "Arrow", "ama", itypea1="miss"),
                skill(4, "Bash", "bar", itypea1="mele"),
                skill(5, "Rat Bite", "dru", restrict="2", State1="form"),
                skill(6, "Buff Bite", "dru", restrict="2", State1="buff"),
                skill(7, "Lock Giver", "nec", restrict="1", aurastate="lock"),
                skill(8, "Bolt", "nec", restrict=""),
                skill(9, "Off", "sor", InGame=""),
                skill(10, "Odd", "sor", itypea1="zzzz"),
                skill(11, "Passive", "sor", passive="1", itypea1="zzzz"),
                skill(12, "Stance", "ama", restrict="5")]
        found = sua.audit(tables(rows))
        self.assertEqual(kinds(found, 1), ["dual_wield"])
        self.assertEqual(kinds(found, 2), ["never"])  # a paladin holds no weapon in the left hand
        self.assertEqual(kinds(found, 3), ["gear"])  # bow + arrows (not every outfit)
        self.assertEqual(kinds(found, 4), ["gear"])
        self.assertEqual(kinds(found, 5), ["form"])
        self.assertEqual(kinds(found, 6), ["never"])  # restrict 2 on a state without states.txt `restrict`
        self.assertEqual(kinds(found, 7), [])
        self.assertEqual(kinds(found, 8), ["locked_by"])
        self.assertEqual(kinds(found, 9), ["never"])
        self.assertEqual(kinds(found, 10), ["never"])
        self.assertEqual(kinds(found, 11), ["never"])  # an unknown item type is reported even on a passive
        self.assertEqual(kinds(found, 12), ["unrestricted"])
        bh = next(f for f in found if f["id"] == 1)
        self.assertIn("Axe + Sword", bh["ok_with"])

    def test_bow_without_quivers_is_never(self):
        found = sua.audit(tables([skill(3, "Arrow", "ama", itypea1="miss")], misc=[]))
        self.assertEqual(kinds(found, 3), ["never"])

    def test_function_slot_past_the_table(self):
        found = sua.audit(tables([skill(13, "Far", "sor", srvdofunc="191"), skill(14, "Near", "sor", srvdofunc="190")]))
        self.assertEqual(kinds(found, 13), ["never"])
        self.assertEqual(kinds(found, 14), [])

    def test_not_tree_skills_are_left_out(self):
        rows = [skill(15, "Monster", "", InGame="")]
        self.assertEqual(sua.audit(tables(rows)), [])


class Verdicts(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        os.environ.setdefault("MXL_SLOT", "2")  # importing game_ctl needs a slot; nothing here starts a game
        import game_checks
        cls.gc = game_checks

    def test_all_steps(self):
        plain = {"modes": [7, 7, 1], "mana_spent": 0, "damage": 300, "own_missiles": []}
        sq = {"modes": [18, 18, 1], "mana_spent": 13, "damage": 900, "own_missiles": []}
        cast = {"modes": [11], "mana_spent": 4, "damage": 0, "own_missiles": [5]}
        refused = {"modes": [7], "mana_spent": 0, "damage": 100, "own_missiles": []}
        r = {"bh_one_axe": [plain] * 3, "bh_two_axes": [plain, sq, sq], "bc_stance": [refused] * 2, "stance_on": True,
             "bc_free": [cast, cast], "stance_off": True, "fortress": [dict(cast, modes=[10])], "fort_state": True,
             "fort_state_at_bc": True, "bc_fort": [refused]}
        v = self.gc.su_verdicts(r)
        self.assertEqual(len(v), 6)
        self.assertTrue(all(v.values()), v)
        v = self.gc.su_verdicts(dict(r, bh_one_axe=[plain, sq, plain]))
        self.assertFalse(v["Blood Hatred, one axe: no SQ, no mana"])
        v = self.gc.su_verdicts(dict(r, bc_stance=[cast, refused]))
        self.assertFalse(v["Bear Claw under Bear Stance (state 47): refused"])
        self.assertEqual(len(self.gc.su_verdicts({"bh_one_axe": [plain], "bh_two_axes": [sq]})), 2)


class ManaCost(unittest.TestCase):
    """1.13c's mana cost of a skills.txt row and the `su_mana` verdicts (Median v005 rows)."""

    @classmethod
    def setUpClass(cls):
        os.environ.setdefault("MXL_SLOT", "2")
        import game_checks
        cls.gc = game_checks

    def test_median_rows(self):
        cost = self.gc.skill_mana_cost
        fire_wall = {"mana": "176", "lvlmana": "2", "manashift": "6", "minmana": "2"}
        self.assertEqual(cost(fire_wall, 1), 44)  # the tooltip's "Mana Cost: 44" (lane skilltips)
        frigid = {"mana": "36", "lvlmana": "12", "manashift": "7", "minmana": "0"}
        self.assertEqual([cost(frigid, lv) for lv in (1, 10, 14, 20)], [18, 72, 96, 132])
        self.assertEqual(cost({"mana": "40", "lvlmana": "10", "manashift": "7", "minmana": "0"}, 10), 65)  # Tempest
        ricochet = {"mana": "30", "lvlmana": "-2", "manashift": "7", "minmana": "5"}
        self.assertEqual([cost(ricochet, lv) for lv in (1, 10, 20)], [15, 6, 5])  # falls to the minmana floor
        self.assertEqual(cost({"mana": "100", "lvlmana": "0", "manashift": "3", "minmana": ""}, 1), 3.125)  # Screaming Eagle

    def test_bracket(self):
        br = self.gc.sm_bracket
        # Frigid Sphere level 10 on slot 4: 200 -> 144 at frame +9, then +13 a look of 9 frames
        click = {"f0": 100, "m0": 200, "looks": [(104, 200), (109, 144), (118, 157), (127, 170), (136, 183)]}
        lo, hi = br(click)
        self.assertEqual(lo, 56)
        self.assertAlmostEqual(hi, 56 + 13 / 9 * 9)
        self.assertIsNone(br({"f0": 100, "m0": 200, "looks": [(104, 200), (109, 200)]}))  # no drop
        self.assertEqual(br({"f0": 100, "m0": 200, "looks": [(109, 198), (118, 200)]}), (2, 2))  # back at max: no rate

    def test_verdicts(self):
        def click(drop, frames=9, rate=1.5):
            return {"f0": 0, "m0": 200, "looks": [(frames, 200 - drop), (frames + 9, 200 - drop + int(rate * 9))]}
        ok = self.gc.sm_verdicts({(530, 10): (72, [click(58), click(60), click(72, 1)])})
        self.assertEqual(ok, {"skill 530 level 10 costs 72": True})
        self.assertFalse(all(self.gc.sm_verdicts({(530, 10): (72, [click(0), click(0), click(3)])}).values()))  # free casts
        self.assertFalse(all(self.gc.sm_verdicts({(530, 10): (72, [click(70), click(70), click(144)])}).values()))  # twice
        self.assertFalse(all(self.gc.sm_verdicts({(535, 10): (65, [click(60), {}, click(20)])}).values()))

if __name__ == "__main__":
    unittest.main()
