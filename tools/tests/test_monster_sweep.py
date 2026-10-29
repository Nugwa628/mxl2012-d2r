"""tools/monster_sweep.py: the table reader, the d2rloader.log assert parser, the state parsers, the classification and the report."""
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import projtemp  # noqa: E402,F401  (temp files stay inside the project, tools/projtemp.py)
import monster_sweep as ms  # noqa: E402

LOG = """[2026-10-28 04:35:31.988] [EXCEL] reused   mod           data/global/excel/base/misc.txt (reason=already compiled)
[2026-10-28 04:45:28.190] [ERROR]
+--------------------------------------------------------------------------------------------------+
| ASSERTION - a game check failed                                                                  |
| Message : BC_ASSERT: nRadius > 0                                                                 |
| Action  : Continuing because assertion dialogs are disabled. The error is not fixed.             |
| Scope   : mod:mxl2012                                                                            |
| Location: D2Game\\src\\Skills\\Skills.cpp:420                                                       |
| Caller  : D2RLoader-s3.exe+0x7600A                                                               |
| ID      : 79687D9958090F77                                                                       |
|                                                                                                  |
| Stack (most recent call first):                                                                  |
|   [00]: D2RCore.dll+0x360BC4                                                                     |
+--------------------------------------------------------------------------------------------------+
[2026-10-28 04:48:20.358] [ERROR]
+--------------------------------------------------------------------------------------------------+
| ASSERTION - a game check failed                                                                  |
| Message : BC_ASSERT: ptUnit->eType == UNIT_PLAYER                                                |
| Scope   : mod:mxl2012                                                                            |
| Location: D2Common\\src\\Units\\Units.cpp:4666                                                      |
| ID      : 6C989A065E94E0C9                                                                       |
+--------------------------------------------------------------------------------------------------+
[2026-10-28 04:48:21.000] [ERROR] Could not add cof file: IM\\COF\\IMghhth.COF
[2026-10-28 04:48:22.000] [ERROR] Could not add cof file: IM\\COF\\IMghhth.COF
[2026-10-28 04:48:23.000] [INFO] something else
"""

MONSTATS = ("Id\t*hcIdx\tAI\tCode\tAlign\tMonProp\tSkill1\tSkill2\tkillable\tenabled\tLevel\n"
            "zombie1\t0\tZombie\tZZ\t\t\t\t\t1\t1\t3\n"
            "totemZ\t1\tTrap-Poison\tAE\t1\tdeadwalltotems\tTotemic Sacrifices\t\t1\t1\t1\n"
            "jinns\t2\tNecroPet\t!6\t1\t\tSkillX\t\t1\t1\t5\n"
            "dark_kid\t3\tIdle\tzz\t\t\t\t\t\t1\t1\n"
            "Expansion\t4\t\t\t\t\t\t\t\t\t\n")
MONPROP = ("Id\tprop1\tprop2\tprop1 (N)\n"
           "deadwalltotems\tac-miss\treanimate\t\n"
           "plain\tac-miss\t\t\n")
TOKENS = {"zz": {"class": "vanilla", "d2r_units": {"zombie1": 3}}, "ae": {"class": "vanilla", "d2r_units": {"lightningspire": 22}},
          "!6": {"class": "reused", "donor": "firegolem"}, "am": {"class": "noart", "donor": "cr_archer1"},
          "fm": {"class": "mixed", "d2r_units": {"fallenmage1": 2}, "donor": "fallen1"}}


class TableTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        d = Path(self.tmp.name)
        (d / "monstats.txt").write_text(MONSTATS, encoding="latin-1")
        (d / "monprop.txt").write_text(MONPROP, encoding="latin-1")
        self.dir = str(d)

    def tearDown(self):
        self.tmp.cleanup()

    def plan(self):
        return {r["id"]: r for r in ms.plan_rows(self.dir, d2r={"zombie1", "jinns"}, tokens=TOKENS)}

    def test_rows_and_sources(self):
        p = self.plan()
        self.assertEqual(sorted(p), ["dark_kid", "jinns", "totemZ", "zombie1"])  # the "Expansion" separator line is no row
        self.assertEqual(p["zombie1"]["source"], "d2r")
        self.assertEqual(p["totemZ"]["source"], "median")
        self.assertEqual(p["totemZ"]["skills"], ["Totemic Sacrifices"])
        self.assertFalse(p["dark_kid"]["killable"])

    def test_unknown_source_without_d2r_table(self):
        rows = ms.plan_rows(self.dir, d2r=set(), tokens=TOKENS)
        self.assertTrue(all(r["source"] == "?" for r in rows))

    def test_hazard_needs_reanimate_and_align(self):
        p = self.plan()
        self.assertEqual(p["totemZ"]["hazard"], "reanimate")
        self.assertEqual(p["zombie1"]["hazard"], "")
        self.assertTrue(ms.is_solo(p["jinns"]))  # allied
        self.assertFalse(ms.is_solo(p["zombie1"]))

    def test_batches_order(self):
        rows = list(self.plan().values())
        b = ms.make_batches(rows, 2)
        kinds = [k for k, _ in b]
        self.assertEqual(kinds, ["batch", "solo", "hazard"])
        self.assertEqual(sorted(r["id"] for r in b[0][1]), ["dark_kid", "zombie1"])
        self.assertEqual(b[-1][1][0]["id"], "totemZ")

    def test_hd_status(self):
        self.assertEqual(ms.hd_status("ZZ", "zombie1", TOKENS), ("unit", "zombie1"))
        self.assertEqual(ms.hd_status("!6", "jinns", TOKENS), ("stand-in", "firegolem"))
        self.assertEqual(ms.hd_status("AM", "haunt", TOKENS)[0], "stand-in")
        self.assertEqual(ms.hd_status("FM", "fallenmage1", TOKENS), ("unit", "fallenmage1"))
        self.assertEqual(ms.hd_status("FM", "fm_extra", TOKENS), ("stand-in", "fallen1"))
        self.assertEqual(ms.hd_status("QQ", "x", TOKENS)[0], "none")

    def test_hc_list(self):
        self.assertEqual(ms.parse_hc_list("5,10-12, 20"), {5, 10, 11, 12, 20})
        self.assertEqual(ms.parse_hc_list(""), set())


class LogTests(unittest.TestCase):
    def test_parse_asserts(self):
        a = ms.parse_asserts(LOG)
        self.assertEqual([x["message"] for x in a], ["nRadius > 0", "ptUnit->eType == UNIT_PLAYER"])
        self.assertEqual(a[0]["location"], "Skills.cpp:420")
        self.assertEqual(a[0]["id"], "79687D9958090F77")
        self.assertEqual(a[1]["time"], "2026-10-28 04:48:20.358")

    def test_nothing(self):
        self.assertEqual(ms.parse_asserts(""), [])
        self.assertEqual(ms.parse_asserts(None), [])

    def test_other_errors_are_distinct_and_skip_assert_blocks(self):
        e = ms.other_errors(LOG)
        self.assertEqual(e, ["Could not add cof file: IM\\COF\\IMghhth.COF"])


class StateTests(unittest.TestCase):
    def test_spawn(self):
        self.assertEqual(ms.parse_spawn(["spawned class 1307 id=19 at 4951,4669", "spawn OK"]), [(1307, 19, 4951, 4669)])
        self.assertEqual(ms.parse_spawn(["spawn FAIL spawn: nothing spawned"]), [])

    def test_units(self):
        u = ms.parse_units(["mon id=22 class=1307 mode=4 dist=6 life=5/5 mx=4950 my=4666 area=2",
                            "corpse id=12 class=1307 mode=12 dist=6 area=2", "obj id=18 class=37 mode=2 dist=8 at 4940,4669"])
        self.assertEqual(u[22], {"state": "alive", "class": 1307, "mode": 4, "life": 5, "maxlife": 5, "x": 4950, "y": 4666})
        self.assertEqual(u[12]["state"], "corpse")
        self.assertNotIn(18, u)

    def test_player(self):
        self.assertEqual(ms.parse_player_xy(["player id=1 class=4 level=120 life=1/1 mana=1 area=2 x=4945 y=4663 mode=5"]), (4945, 4663))
        self.assertIsNone(ms.parse_player_xy(["skills left=0 right=0"]))

    def test_outcome(self):
        self.assertEqual(ms.outcome_of(False, None), "failed")
        self.assertEqual(ms.outcome_of(True, None), "gone")
        self.assertEqual(ms.outcome_of(True, {"state": "corpse"}), "died")
        self.assertEqual(ms.outcome_of(True, {"state": "alive"}), "alive")


class ClassifyTests(unittest.TestCase):
    def row(self, **kw):
        r = {"hc": 1, "id": "x", "ai": "Idle", "align": "", "hazard": "", "killable": True, "monprop": "", "code": "AA", "source": "median", "hd": "unit", "enabled": True}
        r.update(kw)
        return r

    def test_ownerless_by_assert_and_by_ai(self):
        res = {"spawned": True, "asserts": [{"message": "ptUnit->eType == UNIT_PLAYER", "location": "Units.cpp:4666"}]}
        self.assertEqual([k for k, _ in ms.classify(self.row(ai="NecroPet", align="1"), res)], ["ownerless-pet"])
        later = {"spawned": True, "asserts": []}
        self.assertEqual([k for k, _ in ms.classify(self.row(ai="NecroPet"), later, owner_ais={"NecroPet"})], ["ownerless-pet"])
        self.assertEqual(ms.classify(self.row(ai="NecroPet"), later), [])
        self.assertEqual(ms.problem_keys(self.row(ai="NecroPet"), res), [])  # known: not a new problem

    def test_allied_trap_that_dies(self):
        res = {"spawned": True, "outcome": "died", "asserts": []}
        r = self.row(ai="Trap-Poison", align="1")
        self.assertEqual([k for k, _ in ms.classify(r, res)], ["trap-dies"])
        self.assertEqual(ms.problem_keys(r, res), [])
        self.assertEqual([k for k, _ in ms.classify(self.row(ai="Trap-Missile"), res)], ["trap-dies"])  # a hostile trap dies the same way
        self.assertEqual([k for k, _ in ms.classify(self.row(ai="Trap-Missile"), {"spawned": True, "outcome": "alive", "asserts": []})], [])

    def test_owner_bound_summon(self):
        died = {"spawned": True, "outcome": "died", "asserts": [], "alone": True}
        self.assertEqual([k for k, _ in ms.classify(self.row(ai="BaalTentacle"), died)], ["ownerless-pet"])
        self.assertEqual(ms.problem_keys(self.row(ai="BaalTentacle"), died), [])
        hawk = {"spawned": True, "outcome": "alive", "asserts": [{"message": "player && UnitGetType(player) == UNIT_PLAYER", "location": "CmnAccess.h:780"}]}
        self.assertEqual(ms.problem_keys(self.row(ai="Raven", align="1"), hawk), [])
        self.assertEqual(ms.problem_keys(self.row(ai="Idle"), died), ["died-alone"])

    def test_batch_assert_not_repeated_alone(self):
        res = {"spawned": True, "outcome": "alive", "asserts": [], "attributed": True, "batch_asserts": ["nDirectionIndex < nDirections"]}
        self.assertEqual(ms.problem_keys(self.row(), res), ["assert in a batch, not repeated alone: nDirectionIndex < nDirections"])
        again = dict(res, asserts=[{"message": "nDirectionIndex < nDirections", "location": "MissMode.cpp:2042"}])
        self.assertEqual(ms.problem_keys(self.row(), again), ["assert: nDirectionIndex < nDirections (MissMode.cpp:2042)"])

    def test_known_assert(self):
        res = {"spawned": True, "outcome": "alive", "asserts": [{"message": "nSkillCastId && nSkillCastId != 0xFFFFFFFFU", "location": "Skills.cpp:2009"}]}
        self.assertEqual([k for k, _ in ms.classify(self.row(), res)], ["assert-20"])
        self.assertEqual(ms.problem_keys(self.row(), res), [])

    def test_disabled_row_is_known(self):
        res = {"spawned": False, "outcome": "failed", "asserts": [{"message": "(((BYTE*)(ptStats->pdwFlags))[(MONFLAG_ENABLED) >> 3] &", "location": "SUnit.cpp:587"}]}
        off = self.row(enabled=False)
        self.assertEqual([k for k, _ in ms.classify(off, res)], ["disabled-row"])
        self.assertEqual(ms.problem_keys(off, res), [])
        self.assertEqual(ms.problem_keys(self.row(), res)[0], "spawn-failed")  # an enabled row that fails is a problem

    def test_unkillable(self):
        res = {"spawned": True, "outcome": "alive", "unkillable": True, "asserts": []}
        self.assertEqual([k for k, _ in ms.classify(self.row(killable=False), res)], ["unkillable"])

    def test_problems(self):
        res = {"spawned": True, "outcome": "alive", "asserts": [{"message": "nRadius > 0", "location": "Skills.cpp:420"}], "errors": ["Could not add cof file: X"]}
        self.assertEqual(ms.problem_keys(self.row(), res), ["assert: nRadius > 0 (Skills.cpp:420)", "log: Could not add cof file: X"])
        self.assertEqual(ms.problem_keys(self.row(), {"hang": True, "spawned": True, "outcome": "gone", "asserts": []}), ["hang"])
        self.assertEqual(ms.problem_keys(self.row(), {"spawned": False, "outcome": "failed", "asserts": []}), ["spawn-failed"])
        shot = {"spawned": True, "outcome": "alive", "asserts": [], "shot": True, "drew": False}
        self.assertEqual(ms.problem_keys(self.row(), shot), ["not-drawn"])
        self.assertEqual(ms.problem_keys(self.row(hd="none", hd_detail="no art"), {"spawned": True, "outcome": "alive", "asserts": []}), ["no-hd-art: no art"])
        died = {"spawned": True, "outcome": "died", "asserts": [], "alone": True}
        self.assertEqual(ms.problem_keys(self.row(), died), ["died-alone"])
        self.assertEqual(ms.problem_keys(self.row(), dict(died, alone=False)), [])


class PixelTests(unittest.TestCase):
    def test_screen_xy(self):
        self.assertEqual(ms.screen_xy((100, 100), (100, 100)), (800, 405))
        x, y = ms.screen_xy((4945, 4663), (4951, 4669))  # the default spawn spot: straight below the player
        self.assertEqual(x, 800)
        self.assertEqual(y, 405 + 13.5 * 12)

    def test_box_is_clipped(self):
        self.assertEqual(ms.unit_box((10, 10), (1600, 900)), (0, 0, 90, 40))
        x0, y0, x1, y1 = ms.unit_box((1590, 890), (1600, 900))
        self.assertEqual((x1, y1), (1600, 900))

    def test_changed_pixels(self):
        a = np.zeros((900, 1600, 3), dtype=np.uint8)
        b = a.copy()
        b[500:540, 700:760] = 200
        self.assertEqual(ms.changed_pixels(a, b, (650, 450, 850, 600)), 40 * 60)
        self.assertEqual(ms.changed_pixels(a, b, (0, 0, 100, 100)), 0)
        self.assertEqual(ms.changed_pixels(a, b, (10, 10, 10, 20)), 0)

    def test_drew_threshold(self):
        self.assertFalse(ms.drew(100))
        self.assertTrue(ms.drew(ms.DREW_MIN))
        self.assertFalse(ms.drew(ms.DREW_MIN, noise=ms.DREW_MIN))  # as noisy as the picture: no evidence


class ReportTests(unittest.TestCase):
    def test_report(self):
        plan = [{"hc": 0, "id": "a", "ai": "Idle", "code": "AA", "align": "", "monprop": "", "skills": [], "killable": True, "enabled": True,
                 "source": "d2r", "hd": "unit", "hd_detail": "a", "level": "1", "hazard": ""},
                {"hc": 1, "id": "b", "ai": "NecroPet", "code": "!6", "align": "1", "monprop": "", "skills": [], "killable": True, "enabled": True,
                 "source": "median", "hd": "stand-in", "hd_detail": "firegolem", "level": "1", "hazard": ""},
                {"hc": 2, "id": "c", "ai": "Idle", "code": "ZZ", "align": "", "monprop": "", "skills": [], "killable": True, "enabled": True,
                 "source": "median", "hd": "none", "hd_detail": "no art", "level": "1", "hazard": ""}]
        data = {"started": "t0", "finished": "t1", "area": 2, "batch": 6, "wait": 3, "owner_ais": ["NecroPet"], "notes": ["one note"], "rows": {
            "0": {"id": "a", "spawned": True, "outcome": "alive", "asserts": [], "errors": [], "shot": True, "drew": True},
            "1": {"id": "b", "spawned": True, "outcome": "alive", "asserts": [{"message": "ptUnit->eType == UNIT_PLAYER", "location": "Units.cpp:4666"}], "errors": []},
            "2": {"id": "c", "spawned": True, "outcome": "gone", "hang": True, "asserts": [{"message": "x > 0", "location": "F.cpp:1"}], "errors": []}}}
        text = ms.render_report(plan, data)
        self.assertIn("| rows tested | 3 |", text)
        self.assertIn("| hung the game | 1 |", text)
        self.assertIn("| spawned with HD art in the token table (a D2R unit or a stand-in) | 2 |", text)
        self.assertIn("| spawned with no HD art (`no-hd-art`) | 1 |", text)
        self.assertIn("| judged by a capture: something changed around the unit | 1 |", text)  # row 0 has a capture
        data["rows"]["0"].pop("shot")
        self.assertNotIn("judged by a capture", ms.render_report(plan, data))
        self.assertIn("ownerless-pet", text)
        self.assertIn("| 2 | c | Idle | ZZ none | median | gone (hang) | hang; assert: x > 0 (F.cpp:1); no-hd-art: no art |", text)
        self.assertNotIn("| 1 | b |", text)  # the known class is not a per-row problem
        self.assertIn("- one note", text)


if __name__ == "__main__":
    unittest.main()
