"""Lane acts25 in game_checks.py: the click-entry routes of an act, the `reassign` counter line, the boss and travel tables (no game
is started)."""
import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("MXL_SLOT", "2")  # importing game_ctl needs a slot; nothing here starts a game
import projtemp  # noqa: E402,F401
import game_checks as gc  # noqa: E402

LEVELS = [{"Id": "40", "Act": "1", "Vis0": "47", "Warp0": "19", "Vis1": "47", "Warp1": "20", "Vis2": "41", "Warp2": "-1"},
          {"Id": "47", "Act": "1", "Vis0": "40", "Warp0": "22", "Vis1": "48", "Warp1": "23"},
          {"Id": "48", "Act": "1", "Vis0": "47", "Warp0": "22"},
          {"Id": "75", "Act": "2", "Vis0": "76", "Warp0": "-1"},
          {"Id": "107", "Act": "3", "Vis0": "106", "Warp0": "70", "Vis1": "108", "Warp1": "-1"}]


class Routes(unittest.TestCase):
    def test_pairs_once_tiles_only(self):
        with patch.object(gc, "table", return_value=LEVELS):
            self.assertEqual(gc.a25_routes(2), [(40, 47), (47, 48)])  # 40-41 is an outdoor edge (Warp -1): no tile
            self.assertEqual(gc.a25_routes(3), [])
            self.assertEqual(gc.a25_routes(4), [(106, 107)])


class Reassign(unittest.TestCase):
    def test_counter_line(self):
        text = "mxl2012 ...\nreassign on: guard; commands 53, units left without a room 11, the player without a room 0\n"
        with patch.object(gc, "mxl_text", return_value=text):
            self.assertEqual(gc.a25_reassign(), (53, 11, 0))

    def test_no_line(self):
        with patch.object(gc, "mxl_text", return_value="mxl2012 ...\n"):
            self.assertIsNone(gc.a25_reassign())


class Tables(unittest.TestCase):
    def test_last_boss_opens_next_act(self):
        for act, bosses in gc.A25_BOSSES.items():
            self.assertTrue(bosses[-1][3], act)
            self.assertEqual(sum(1 for b in bosses if b[3]), 1, act)

    def test_travel_and_revivers(self):
        self.assertTrue(all(a in gc.A25_REVIVERS for a in (2, 3, 4, 5)))
        self.assertNotEqual(gc.A25_TALK, 0)

    def test_hireling_not_a_target(self):
        st = {"mons": [{"id": 46, "class": 338, "dist": 3, "life": 5120000}, {"id": 7, "class": 5, "dist": 4, "life": 10}]}
        self.assertEqual([m["id"] for m in gc.hostiles_near(st, 10, unkillable=set())], [7])

    def test_registered(self):
        self.assertIn("acts25", [n for n, _f in gc.CHECKS])


class Nmhell4Fixes(unittest.TestCase):
    """Lane nmhell4: the harness gaps lane acts25 left (walk cap, waypoint target, pickup gates, the stalled melee cast)."""

    def test_nearest_waypoint_not_first(self):
        lines = ["object id=220 class=119 mode=2 dist=5250 at 10028,14821", "object id=9 class=5 mode=0 dist=3 at 1,1",
                 "object id=31 class=156 mode=0 dist=14 at 5100,5100", "object id=40 class=119 mode=0 dist=60 at 5150,5120"]
        self.assertEqual(gc.nearest_waypoint(lines, {119, 156}), (31, 156, 14))
        self.assertIsNone(gc.nearest_waypoint(lines[:2], {156}))

    def test_find_waypoint_near_limit(self):
        far = (True, ["object id=220 class=119 mode=2 dist=5250 at 10028,14821"])
        with patch.object(gc, "table", return_value=[{"*ID": "119", "OperateFn": "23"}]), patch.object(gc, "H", return_value=far):
            self.assertIsNone(gc.find_waypoint_object(near=gc.WP_NEAR))
            self.assertEqual(gc.find_waypoint_object(), (220, 119, 5250))

    def test_approach_walk_budget(self):
        self.assertEqual(gc.approach_walk_s(None), 60)
        with patch.object(gc.time, "time", return_value=1000.0):
            self.assertEqual(gc.approach_walk_s(1020.0), 20.0)
            self.assertEqual(gc.approach_walk_s(990.0), 0)
            self.assertEqual(gc.approach_walk_s(5000.0), 60)

    def test_talk_walk_is_capped(self):
        clock = [0.0]

        def slow_approach(_cls, budget_s=None):
            self.assertLessEqual(budget_s, gc.TALK_WALK_S)
            clock[0] += budget_s  # the walk used its whole budget
            return False
        far = (True, ["interact 359 distance 97.0"])
        with patch.object(gc.time, "time", side_effect=lambda: clock[0]), patch.object(gc, "Hl", return_value=far),                 patch.object(gc, "close_menu"), patch.object(gc, "acts_approach", side_effect=slow_approach) as ap,                 patch.object(gc.time, "sleep"), patch.object(gc, "wait_menu", return_value=None):
            log = []
            self.assertIsNone(gc.talk(359, log))
        self.assertEqual(ap.call_count, 1)  # the second walk had no budget left: the copy fixture came next
        self.assertTrue(any("fixture: a copy of NPC 359" in ln for ln in log))

    def test_cast_stall(self):
        stalled = ["cast checks: usable=0 (0 ok) skill mode=7 unit mode=1",
                   "cast skill 0 (level 1) at monster id=324 class=526 dist 9: mode now 1, mana 1145 -> 1145"]
        self.assertEqual(gc.cast_stall(stalled), 9)
        self.assertIsNone(gc.cast_stall(["cast skill 0 (level 1) at monster id=324 class=526 dist 2: mode now 1, mana 5 -> 5"]))
        self.assertIsNone(gc.cast_stall(["cast skill 0 (level 1) at monster id=324 class=526 dist 9: mode now 7, mana 5 -> 5"]))
        self.assertIsNone(gc.cast_stall([]))
        run = ["cast skill 0 (level 1) at monster id=1589 class=1101 dist 11: mode now 3, mana 805 -> 805"]
        self.assertEqual(gc.cast_stall(run), 11)  # Nightmare Creature of Flame: running, never closing in

    def test_hire_gold_covers_nightmare(self):
        self.assertGreater(gc.HIRE_GOLD, 50560)

    def test_failed_walk_places_at_once(self):
        clock = [0.0]

        def walk(_mid, reach=14, timeout=90, fight=True):
            self.assertEqual(timeout, gc.ACTS_UNSTICK_WALK_S)
            self.assertFalse(fight)  # past the guards
            clock[0] += timeout
            return False
        st = {"player": {"area": 108, "life": 100, "mode": 1}, "mons": []}
        with patch.object(gc.time, "time", side_effect=lambda: clock[0]), patch.object(gc.time, "sleep"),                 patch.object(gc, "hstate", return_value=st), patch.object(gc, "player_dead", return_value=False),                 patch.object(gc, "acts_mon_life", return_value=5000000), patch.object(gc, "acts_close_in", side_effect=walk),                 patch.object(gc, "acts_unstick", return_value="unstick: SET-UP place") as un, patch.dict(gc.STATE, {}, clear=False):
            gc.STATE.pop("acts_build", None)
            killed, deaths, _t = gc.acts_fight(201, timeout=60, unstick=True)
        self.assertFalse(killed)
        self.assertEqual(deaths, 0)
        self.assertEqual(un.call_count, 2)  # every failed walk, not every second one

    def test_deep_find_walks_without_fighting(self):
        walks = []
        rooms = ["room x=%d y=5400" % x for x in (12500, 12900)]

        def H(cmd):
            return (True, rooms if cmd == "presets rooms" else [])
        with patch.object(gc, "H", side_effect=H), patch.object(gc, "hstate", return_value={"player": {"x": 12727, "y": 5223}}),                 patch.object(gc, "acts_search_walk", side_effect=lambda *a, **k: walks.append(k) or False),                 patch.object(gc, "parse_moveto", return_value=None), patch.object(gc, "player_dead", return_value=False):
            self.assertIsNone(gc.a25_deep_find(526, [], 420))
        self.assertTrue(walks)
        self.assertTrue(all(k.get("fight") is False for k in walks))

    def test_unstick_tries_wider_rings(self):
        tried = []

        def H(cmd):
            if cmd.startswith("moveto"):
                return (True, ["moveto unit id=783 class=544 at 15135,5920: code 0, mode now 3"])
            tried.append(cmd)
            return (cmd == "place 15141 5920", [])
        with patch.object(gc, "H", side_effect=H), patch.object(gc.time, "sleep"), patch.dict(gc.STATE, {}, clear=False):
            self.assertEqual(gc.acts_unstick(783, 1), "unstick: SET-UP place")
        self.assertEqual(tried[-1], "place 15141 5920")
        self.assertEqual(len(set(gc.UNSTICK_SPOTS)), 15)

    def test_recover_returns_to_the_difficulty_with_god_mode(self):
        diffs = iter([0, 2])
        with patch.object(gc, "rp_recover", return_value=True), patch.object(gc, "game_alive", return_value=True),                 patch.object(gc, "hstate", side_effect=lambda: {"player": {"difficulty": next(diffs)}}),                 patch.object(gc, "leave_and_reenter") as re, patch.object(gc, "enable_debug"),                 patch.object(gc, "cheat") as ch, patch.dict(gc.STATE, {"a25_diff": "hell"}):
            note = gc.a25_recover("entry 106-107", [])
        re.assert_called_once_with(difficulty="hell")
        ch.assert_called_once_with("god 1")
        self.assertIn("difficulty 2 (want 2)", note)

    def test_far_rooms(self):
        rooms = [(0, 0), (100, 0), (105, 0), (0, 200), (50, 50)]
        self.assertEqual(gc.far_rooms(rooms, 0, 0, n=3), [(0, 200), (105, 0), (50, 50)])

    def test_pickup_gates(self):
        self.assertEqual(set(gc.A25_PICKUP_SETUP), {"ass", "xyz", "tr2", "g34"})
        self.assertEqual(gc.A25_PICKUP_SETUP["ass"], ("quest 9 5 set",))
        self.assertIn("quest 20 5 set", gc.A25_PICKUP_SETUP["xyz"])
        self.assertEqual(gc.A25_PICKUP_SETUP["tr2"], ("quest 37 8 set", "quest 37 7 clear"))
        items = [c for codes in gc.A25_ITEMS.values() for c, _t in codes]
        self.assertLess(items.index("j34"), items.index("g34"))  # the figurine first: the bird's gate removes it
        self.assertEqual(len(gc.PICK_NUDGE_PX), len(set(gc.PICK_NUDGE_PX)))

    def test_deep_search_stage_is_a_boss(self):
        stages = {b[0] for bs in gc.A25_BOSSES.values() for b in bs}
        self.assertTrue(set(gc.A25_DEEP_SEARCH) <= stages)

    def test_difficulty_ids(self):
        import nmh_checks
        self.assertEqual(gc.DIFF_IDS, nmh_checks.DIFFS)


if __name__ == "__main__":
    unittest.main()
