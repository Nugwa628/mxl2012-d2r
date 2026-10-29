"""Blackstorm progression verdicts without starting a game."""
import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("MXL_SLOT", "2")
import projtemp  # noqa: E402,F401
import game_checks as gc  # noqa: E402


class BlackstormCheck(unittest.TestCase):
    def test_build_signals_and_verdict(self):
        tables = {
            "skills": [{"*Id": "514", "skill": "Blackstorm", "aurastate": "blackstorm",
                        "srvmissilea": "blackstorm1", "cltmissilea": "blackstormexplosion"}],
            "states": [{"state": "blackstorm", "*ID": "43"}],
            "missiles": [{"Missile": "blackstorm%d" % n, "*ID": str(2387 + n), "Skill": "Blackstorm"}
                         for n in range(1, 5)] + [
                             {"Missile": "blackstormexplosion", "*ID": "2393", "Skill": "Corpse Explosion"},
                             {"Missile": "unrelated", "*ID": "1", "Skill": "Attack"}],
        }
        with patch.object(gc, "table", side_effect=tables.__getitem__):
            state, missiles = gc.blackstorm_signals()
        self.assertEqual(state, 43)
        self.assertEqual(set(missiles), {"blackstorm1", "blackstorm2", "blackstorm3", "blackstorm4",
                                         "blackstormexplosion"})
        observed = lambda prg=(0, 0, 0), states=(), seen={}: gc.blackstorm_observed(
            prg, states, seen, state, missiles)
        self.assertTrue(observed(prg=(3, 0, 514)))  # reached, even with zero non-zero returns
        self.assertTrue(observed(states=(43,)))
        for missile in missiles.values():
            with self.subTest(missile=missile):
                self.assertTrue(observed(seen={missile: 1}))
        self.assertFalse(observed())
        self.assertFalse(observed(prg=(None, None, None)))
        self.assertFalse(observed(prg=(3, 3, 326), states=(22,), seen={1: 10, 2388: 0}))
        self.assertFalse(observed(prg=(0, 0, 514)))


if __name__ == "__main__":
    unittest.main()
