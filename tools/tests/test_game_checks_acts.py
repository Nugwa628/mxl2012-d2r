"""Parsers of game_checks' `acts` check (lane acts) on harness answer lines; no game is started.
Run: py -3 -I -m unittest discover -s tools/tests -p "test_game_checks_acts.py" """
import os
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import projtemp  # noqa: E402,F401  (temp files stay inside the project, tools/projtemp.py)
os.environ.setdefault("MXL_SLOT", "2")  # importing game_ctl needs a slot; nothing here starts a game
import game_checks as gc  # noqa: E402


class Menu(unittest.TestCase):
    LINES = ["menu npc id=12 class=155 row=3 lines=2 (+ Cancel)",
             "  line 0 string=0xc7a handler=image+0x10f230",
             "  line 1 string=0xd4e handler=image+0x111a90",
             "menu OK"]

    def test_lines(self):
        m = gc.parse_menu(self.LINES)
        self.assertEqual(m["npc"], 155)
        self.assertEqual(m["lines"], [(0, 0xc7a, "image+0x10f230"), (1, 0xd4e, "image+0x111a90")])

    def test_no_menu(self):
        self.assertIsNone(gc.parse_menu(["menu FAIL menu: no NPC menu is open"]))
        self.assertIsNone(gc.parse_menu([]))

    def test_new_lines(self):
        before = gc.parse_menu(self.LINES[:2])
        after = gc.parse_menu(self.LINES)
        self.assertEqual(gc.new_menu_lines(before, after), [(1, 0xd4e)])
        self.assertEqual(gc.new_menu_lines(None, before), [(0, 0xc7a)])
        self.assertEqual(gc.new_menu_lines(after, None), [])


class Answers(unittest.TestCase):
    def test_quest_dump(self):
        self.assertEqual(gc.parse_quest_dump(["quest 6 bits0-15 1000000000000100", "quest OK"]), (6, "1000000000000100"))
        self.assertIsNone(gc.parse_quest_dump(["quest FAIL no quest record"]))
        self.assertIsNone(gc.parse_quest_dump(["quest 6 bits0-15 10"]))

    def test_presets(self):
        p = gc.parse_presets(["preset type=1 class=156 x=22510 y=9870", "preset type=2 class=546 x=1 y=2", "presets level 37 rooms 9 units 2"])
        self.assertEqual(p, [{"type": 1, "class": 156, "x": 22510, "y": 9870}, {"type": 2, "class": 546, "x": 1, "y": 2}])

    def test_objects(self):
        o = gc.parse_objects(["object id=7 class=119 mode=0 dist=12 at 5040,5520", "objects 1"])
        self.assertEqual(o, [{"id": 7, "class": 119, "mode": 0, "dist": 12, "x": 5040, "y": 5520}])

    def test_xp(self):
        self.assertEqual(gc.parse_xp(["xp level=31 experience=1200000 statpoints=150 skillpoints=30", "xp OK"]),
                         {"level": 31, "experience": 1200000, "statpoints": 150, "skillpoints": 30})
        self.assertEqual(gc.parse_xp(["xp FAIL usage"]), {})


class Walk(unittest.TestCase):
    def test_short_leg_goes_all_the_way(self):
        self.assertEqual(gc.step_towards(100, 100, 130, 140, step=60), (130, 140))

    def test_long_leg_is_cut(self):
        self.assertEqual(gc.step_towards(0, 0, 300, 400, step=50), (30, 40))
        self.assertEqual(gc.step_towards(500, 500, 500, 100, step=60), (500, 440))


    def test_hostiles_near(self):
        st = {"mons": [{"id": 1, "class": 5, "dist": 12}, {"id": 2, "class": 156, "dist": 3}, {"id": 3, "class": 5, "dist": 30}]}
        self.assertEqual([m["id"] for m in gc.hostiles_near(st, 14, unkillable=set())], [2, 1])
        self.assertEqual([m["id"] for m in gc.hostiles_near(st, 14, skip=(156,), unkillable=set())], [1])
        st["mons"].append({"id": 4, "class": 5, "dist": 1, "life": 0})
        self.assertEqual([m["id"] for m in gc.hostiles_near(st, 14, unkillable=set())], [2, 1], "a monster at 0 life is not fought again")


class Cards(unittest.TestCase):
    def test_visible_cards_only(self):
        self.assertAlmostEqual(gc.card_y(1), 0.076)
        self.assertAlmostEqual(gc.card_y(gc.MAX_CARDS), 0.076 + 0.091 * (gc.MAX_CARDS - 1))
        self.assertLess(gc.card_y(gc.MAX_CARDS), 0.9)
        self.assertIsNone(gc.card_y(gc.MAX_CARDS + 1))
        self.assertIsNone(gc.card_y(17))
        self.assertIsNone(gc.card_y(0))

    def test_enter_game_refuses_an_off_list_card(self):
        from unittest.mock import patch
        with patch.object(gc.g, "click", side_effect=AssertionError("clicked")):
            self.assertFalse(gc.enter_game(17))


    def test_unkillable_are_not_fought(self):
        st = {"mons": [{"id": 1, "class": 401, "dist": 2}, {"id": 2, "class": 242, "dist": 30}]}
        self.assertEqual([m["id"] for m in gc.hostiles_near(st, 40, unkillable={401})], [2])

    def test_moveto(self):
        self.assertEqual(gc.parse_moveto(["moveto unit id=88 class=242 at 17540,8065: code 0, mode now 3", "moveto OK"]),
                         {"id": 88, "class": 242, "x": 17540, "y": 8065})
        self.assertIsNone(gc.parse_moveto(["moveto FAIL moveto: no such live monster"]))


class Stages(unittest.TestCase):
    def test_default_is_every_stage_in_order(self):
        self.assertEqual(gc.acts_stages(""), [s for s in gc.ACTS_STAGES if s not in gc.ACTS_ASKED_ONLY])

    def test_build_runs_only_when_asked(self):
        self.assertEqual(gc.acts_stages("build,mephisto"), ["build", "mephisto"])

    def test_subset_keeps_the_run_order_and_drops_unknown(self):
        self.assertEqual(gc.acts_stages("baal, towns,nosuch"), ["towns", "baal"])

    def test_tables_agree(self):
        self.assertEqual(set(gc.ACT_TOWNS.values()), {1, 40, 75, 103, 109})
        for stage in list(gc.ACT_BOSSES) + list(gc.ACT_TRAVEL):
            self.assertIn(stage, gc.ACTS_STAGES)
        for frm, npc, dest in gc.ACT_TRAVEL.values():
            act = next(a for a, t in gc.ACT_TOWNS.items() if t == frm)
            self.assertIn(npc, gc.TOWN_NPCS[act])
            self.assertIn(dest, gc.ACT_TOWNS.values())
        self.assertIn("acts", {n for n, _ in gc.CHECKS})


if __name__ == "__main__":
    unittest.main()
