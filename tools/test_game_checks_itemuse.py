"""The lane unported checks in game_checks.py (unported.md "Item use pSpell 3 / 10", ME9 mercenary level): registration and Median's calcs
(no game is started)."""
import os
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("MXL_SLOT", "2")  # importing game_ctl needs a slot; nothing here starts a game
import projtemp  # noqa: E402,F401
import game_checks as gc  # noqa: E402


class ItemUse(unittest.TestCase):
    def test_registered(self):
        self.assertIn("iu_use", [n for n, _ in gc.CHECKS])
        self.assertEqual(gc.unknown_checks(["iu_use"]), [])

    def test_learning_caps(self):
        self.assertEqual(gc.iu_expected("zkq", 30, {}), {"statpts": 1, "potion_stat_cap": 1})
        self.assertEqual(gc.iu_expected("zkq", 30, {"potion_stat_cap": 500}), {"statpts": 0, "potion_stat_cap": 1})
        self.assertEqual(gc.iu_expected("zkq", 30, {"potion_stat_cap": 501}), {"statpts": 0, "potion_stat_cap": 0})
        self.assertEqual(gc.iu_expected("zky", 30, {"potion_stat_cap": 1}), {"statpts": 25, "potion_stat_cap": 25})
        self.assertEqual(gc.iu_expected("zky", 30, {"potion_stat_cap": 1000}), {"statpts": 5, "potion_stat_cap": 5})

    def test_level_calcs(self):
        self.assertEqual(gc.iu_expected("zku", 30, {}), {"experience": 7500})
        self.assertEqual(gc.iu_expected("zkw", 30, {"gold": 0}), {"gold": 4500})
        self.assertEqual(gc.iu_expected("zkw", 30, {"gold": 299000}), {"gold": 1000})  # the carry limit level x 10,000
        self.assertEqual(gc.iu_expected("zog", 30, {}), {"hitpoints": 300})
        self.assertEqual(gc.iu_expected("!@B", 30, {"potion_skill_cap": 3}), {"newskills": 0, "potion_skill_cap": 1})
        self.assertNotIn("dog", gc.IU_ITEMS)  # the Apple's effect is not in its misc row (bugs.md 499)

    def test_verdict(self):
        zero = {n: 0 for n in gc.IU_STATS}
        ok = dict(zero, statpts=1, potion_stat_cap=1)
        self.assertEqual(gc.iu_verdict("zkq", 30, zero, ok), [])
        self.assertEqual(len(gc.iu_verdict("zkq", 30, zero, dict(ok, gold=5))), 1)
        self.assertEqual(gc.iu_verdict("zog", 30, zero, dict(zero, hitpoints=300.4)), [])  # life in 1/256: rounding allowed
        self.assertEqual(len(gc.iu_verdict("zog", 30, zero, dict(zero, hitpoints=300 / 256.0))), 1)  # raw add, not life points

    def test_items_are_median_rows(self):
        for code in gc.IU_ITEMS:
            gc.iu_expected(code, 1, {})


class MercLevel(unittest.TestCase):
    def test_registered(self):
        self.assertIn("ml_merc", [n for n, _ in gc.CHECKS])

    def test_start_is_rc_setup_formula(self):
        import rc_setup
        for lv in gc.ML_STEPS:
            self.assertEqual(gc.ml_start(lv), rc_setup.merc_exp_for_level(lv, 1))  # Median's Exp/Lvl is 1 on every row
        self.assertEqual(gc.ml_start(100), 1010000)

    def test_capped_by_player(self):
        self.assertEqual(gc.ml_want(110, 120), 110)
        self.assertEqual(gc.ml_want(110, 105), 105)
        self.assertEqual(gc.ml_want(120, 120), 119)  # one below experience.txt's MaxLvl, as 98 under 99 in 1.13c


if __name__ == "__main__":
    unittest.main()
