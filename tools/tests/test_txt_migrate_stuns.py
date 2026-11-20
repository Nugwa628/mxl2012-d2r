"""Bug #580: missiles.txt pSrvDmgFunc 7 with dParam1 0 takes the stun length from the skill; D2R reads it from the skill's
calc4, so stun_calc4 writes calc4 `ln12` (Param1 + Param2 * (lvl - 1), as 1.13c computes it)."""
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

SH = ["skill", "srvdofunc", "srvmissile", "srvmissilea", "calc4", "Param1", "Param2"]
MH = ["Missile", "pSrvDmgFunc", "SubMissile1", "HitSubMissile1", "Skill", "dParam1"]


def skill(name, dofunc="", srv="", srva="", calc4="", p1="15", p2="5"):
    return [name, dofunc, srv, srva, calc4, p1, p2]


def missile(name, dmg="", sub="", hitsub="", sk="", d1=""):
    return [name, dmg, sub, hitsub, sk, d1]


def calc4(rows, name):
    return next(r[SH.index("calc4")] for r in rows if r[0] == name)


class StunCalc4Tests(unittest.TestCase):
    def run_rule(self, skills, missiles):
        return tm.stun_calc4(SH, skills, MH, missiles)

    def test_blink_nova_through_center(self):
        # Blink: srvmissilea blinkcenter, whose sub-missile blinknova stuns (7, dParam1 0)
        skills = [skill("Blink", "27", srva="blinkcenter")]
        missiles = [missile("blinkcenter", sub="blinknova"), missile("blinknova", "7", d1="0")]
        self.assertEqual(self.run_rule(skills, missiles), ["Blink"])
        self.assertEqual(calc4(skills, "Blink"), "ln12")

    def test_empty_dparam_counts_as_zero_and_hit_submissile_depth(self):
        skills = [skill("Cherub", "", srva="center")]
        missiles = [missile("center", sub="delay"), missile("delay", hitsub="bolt"), missile("bolt", "7", d1="")]
        self.assertEqual(self.run_rule(skills, missiles), ["Cherub"])

    def test_missile_skill_column(self):
        skills = [skill("Mon Stampede", "8")]
        missiles = [missile("monstambolt", "7", sk="Mon Stampede", d1="0")]
        self.assertEqual(self.run_rule(skills, missiles), ["Mon Stampede"])

    def test_own_stun_length_is_left_alone(self):
        skills = [skill("Mythal", srv="nova")]
        missiles = [missile("nova", "7", d1="50")]
        self.assertEqual(self.run_rule(skills, missiles), [])
        self.assertEqual(calc4(skills, "Mythal"), "")

    def test_set_calc4_elemental_dofunc_and_no_params_kept(self):
        skills = [skill("Has", srv="m", calc4="3"), skill("Leap", "78", srv="m"), skill("Bare", srv="m", p1="", p2="0")]
        missiles = [missile("m", "7", d1="0")]
        self.assertEqual(self.run_rule(skills, missiles), [])
        self.assertEqual([calc4(skills, n) for n in ("Has", "Leap", "Bare")], ["3", "", ""])

    def test_other_damage_function_and_loop(self):
        skills = [skill("Fire", srv="a")]
        missiles = [missile("a", "1", sub="b"), missile("b", "", sub="a")]  # a -> b -> a, no stun missile
        self.assertEqual(self.run_rule(skills, missiles), [])


if __name__ == "__main__":
    unittest.main()
