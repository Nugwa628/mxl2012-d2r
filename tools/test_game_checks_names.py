"""Check-name validation of game_checks.run_all (lane ied-vanish); no game is started and no run folder is made."""
import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import projtemp  # noqa: E402,F401  (temp files stay inside the project, tools/projtemp.py)
os.environ.setdefault("MXL_SLOT", "2")  # importing game_ctl needs a slot; nothing here starts a game
import game_checks


class UnknownCheckNames(unittest.TestCase):
    def test_known_and_marker_names_pass(self):
        known = [name for name, _ in game_checks.CHECKS]
        self.assertEqual(game_checks.unknown_checks(known), [])
        self.assertEqual(game_checks.unknown_checks(["-"]), [])
        self.assertEqual(game_checks.unknown_checks(None), [])
        self.assertEqual(game_checks.unknown_checks([]), [])

    def test_misspelt_name_is_listed(self):
        self.assertEqual(game_checks.unknown_checks(["mxl2012", "tooltip", "itemevent"]), ["tooltip", "itemevent"])

    def test_run_all_refuses_before_run_folder_lock_and_game(self):
        with patch.object(game_checks, "new_run", side_effect=AssertionError("made a run folder")), \
                patch.object(game_checks, "lock", side_effect=AssertionError("took the lock")):
            self.assertEqual(game_checks.run_all(["mxl2012", "tooltip"]), 2)

    def test_check_names_are_unique(self):
        names = [name for name, _ in game_checks.CHECKS]
        self.assertEqual(sorted(set(names)), sorted(names))


    def test_plugin_plan_10_1_checks_are_there(self):
        names = {name for name, _ in game_checks.CHECKS}
        for n in ("mxl2012", "rockshock", "srvhit6spawn", "srvhit23", "cltdo83", "skillprog", "cltdostub", "pandewp", "terrorzones"):
            self.assertIn(n, names)


class Parsers(unittest.TestCase):
    def test_missiles_seen(self):
        lines = ["mis id=1 class=0 mode=3 at 4950,4663 dist=5",
                 "missiles live=0 seen=67 tracking=on [class 1359 x1, class 2210 x1, class 2209 x64]"]
        self.assertEqual(game_checks.missiles_seen(lines), {1359: 1, 2210: 1, 2209: 64})
        self.assertEqual(game_checks.missiles_seen(["missiles live=0 seen=0 tracking=off (missiles reset starts it) []"]), {})

    def test_engine_issues_known_and_new_asserts(self):
        log = ("| Message : BC_ASSERT: nIndex >= 0 && size_t(nIndex) < dataTable->uniqueItemsTbl.size()            |\n"
               "| Location: D2Common\\include\\D2Common\\CmnAccess.h:1881                                             |\n"
               "| Message : BC_ASSERT: nMissile >= 0 && nMissile < DataTablesGetNumMissileStats(ver)               |\n"
               "| Location: D2Client\\src\\Skills\\SkillsNec.cpp:60                                                   |\n")
        mark = {"loader": 0, "mxl": 0, "crashes": set()}
        with patch.object(game_checks.g, "_read_from", side_effect=lambda p, off: log if p == game_checks.g.LOADER_LOG else ""), \
                patch.object(game_checks.os.path, "isdir", return_value=False):
            self.assertEqual([loc.split("\\")[-1] for _, loc in game_checks.engine_asserts(mark)], ["CmnAccess.h:1881", "SkillsNec.cpp:60"])
            bad, known = game_checks.engine_issues(mark, ["missile FAIL crashed (exception in the game call)"])
        self.assertEqual(len(known), 1)
        self.assertIn("bug #7", known[0])
        self.assertEqual(len(bad), 2)
        self.assertIn("SkillsNec.cpp:60", bad[0])
        self.assertIn("FAIL crashed", bad[1])


if __name__ == "__main__":
    unittest.main()
