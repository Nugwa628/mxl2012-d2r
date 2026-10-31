"""Lane harnessgaps in game_checks.py: the boss step's placed / ranged phases, the quest doors before an entry, the town NPC
spots (no game is started)."""
import os
import sys
import unittest
from unittest.mock import patch

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
os.environ.setdefault("MXL_SLOT", "2")  # importing game_ctl needs a slot; nothing here starts a game
import projtemp  # noqa: E402,F401
import game_checks as gc  # noqa: E402


def wm(rows, x0=100, y0=200, step=1):
    return {"grid": rows, "x0": x0, "y0": y0, "step": step, "level": 1, "others": {}}


class FreeCells(unittest.TestCase):
    def test_nearest_free_first_and_ring(self):
        grid = wm(["#####",
                   "#...#",
                   "#.B.#",
                   "##..#",
                   "#####"])  # B (the boss's own cell) is not "." : not a spot
        got = gc.wm_free_near(grid, 102, 202, rmin=1, rmax=1)
        self.assertEqual(len(got), 7)
        self.assertEqual(got[:2], [(101, 202), (102, 201)])  # straight neighbours before the diagonals (ties: x, then y)
        self.assertNotIn((101, 203), got)  # blocked

    def test_rmin_and_no_grid(self):
        self.assertEqual(gc.wm_free_near(None, 0, 0), [])
        grid = wm(["...", "...", "..."], x0=0, y0=0)
        self.assertEqual(gc.wm_free_near(grid, 1, 1, rmin=2, rmax=6), [])
        self.assertEqual(gc.wm_free_near(grid, 0, 0, rmin=2, rmax=2), [(0, 2), (2, 0), (1, 2), (2, 1), (2, 2)])

    def test_step_scales(self):
        grid = wm([".#", ".."], x0=10, y0=20, step=4)
        self.assertEqual(gc.wm_free_near(grid, 10, 20, rmin=1, rmax=4), [(10, 24), (14, 24)])


class PlaceBy(unittest.TestCase):
    def test_walkmap_cell_first_then_rings(self):
        tried = []

        def H(cmd):
            if cmd.startswith("moveto"):
                return True, ["moveto unit id=9 class=526 at 500,600: code 0, mode now 1"]
            tried.append(cmd)
            return cmd == "place 501 600", []
        grid = wm(["..."], x0=500, y0=600)
        with patch.object(gc, "H", side_effect=H), patch.object(gc, "relp_walkmap", return_value=grid), \
                patch.object(gc, "hstate", return_value={"player": {"x": 501, "y": 600}}), patch.object(gc.time, "sleep"):
            self.assertEqual(gc.a25_place_by(9, []), (501, 600))
        self.assertEqual(tried, ["place 501 600"])

    def test_no_spot(self):
        def H(cmd):
            if cmd.startswith("moveto"):
                return True, ["moveto unit id=9 class=242 at 500,600: code 0, mode now 1"]
            return False, []
        log = []
        with patch.object(gc, "H", side_effect=H), patch.object(gc, "relp_walkmap", return_value=None), \
                patch.object(gc, "acts_walk") as walk, patch.object(gc.time, "sleep"):
            self.assertIsNone(gc.a25_place_by(9, log))
        self.assertIn("15 spots tried", log[-1])
        walk.assert_called_once()  # no free cell: a walk toward him first
        self.assertFalse(walk.call_args.kwargs["fight"])

    def test_too_far_after_the_place(self):
        def H(cmd):
            if cmd.startswith("moveto"):
                return True, ["moveto unit id=9 class=526 at 500,600: code 0, mode now 1"]
            return True, []
        with patch.object(gc, "H", side_effect=H), patch.object(gc, "relp_walkmap", return_value=wm(["..."], x0=499, y0=600)), \
                patch.object(gc, "hstate", return_value={"player": {"x": 504, "y": 600}}), patch.object(gc.time, "sleep"):
            self.assertIsNone(gc.a25_place_by(9, []))  # the place answered OK, but 4 from him: a swing from there lands nothing


MOVETO7 = (True, ["moveto unit id=7 class=526 at 500,600: code 0, mode now 1"])


class RouteFilter(unittest.TestCase):
    def test_spec(self):
        self.assertEqual(gc.a25_route_filter("83-100, 128-120"), {(83, 100), (100, 83), (120, 128), (128, 120)})
        self.assertEqual(gc.a25_route_filter(None), set())
        self.assertEqual(gc.a25_route_filter("x-1,"), set())


class ObjectSearch(unittest.TestCase):
    def test_far_rooms_until_the_object_is_built(self):
        seen = iter([[], [{"id": 3, "class": 404, "x": 9, "y": 9}]])
        rooms = ["room x=0 y=0", "room x=500 y=0", "room x=0 y=500"]
        with patch.object(gc, "H", side_effect=lambda c: (True, rooms if c == "presets rooms" else [])), \
                patch.object(gc, "hstate", return_value={"player": {"x": 0, "y": 0}}), \
                patch.object(gc, "acts_search_walk", return_value=False) as walk,                 patch.object(gc, "a25_hop_towards") as hop, patch.object(gc, "parse_objects", side_effect=lambda _l: next(seen)):
            got = gc.a25_object_deep(404, [])
        self.assertEqual(got[0]["id"], 3)
        self.assertEqual(walk.call_count, 2)
        self.assertEqual(hop.call_count, 2)  # each walk that did not arrive: `place` legs there
        self.assertTrue(all(c.kwargs["fight"] is False for c in walk.call_args_list))

    def test_near_falls_back_to_the_search(self):
        with patch.object(gc, "Hl", return_value=(True, [])), patch.object(gc, "parse_objects", return_value=[]), \
                patch.object(gc, "parse_presets", return_value=[]), \
                patch.object(gc, "a25_object_deep", return_value=[{"id": 4}]) as deep:
            self.assertEqual(gc.a25_object_near(404, []), {"id": 4})
        deep.assert_called_once()


class MeleeBack(unittest.TestCase):
    def test_arrows_off_before_the_axe(self):
        cmds = []
        axe = [{"id": 9, "code": gc.ACTS_WEAPON, "body": 4}]
        with patch.object(gc, "H", side_effect=lambda c: cmds.append(c) or (True, [])),                 patch.object(gc, "acts_gear", side_effect=lambda _l: cmds.append("acts_gear")),                 patch.object(gc, "acts_level_up", return_value=84), patch.object(gc, "rc_items", return_value=axe):
            self.assertEqual(gc.a25_melee_back([]), "axe back")
        self.assertEqual(cmds, ["unequip lhand", "acts_gear"])

    def test_not_back_is_named(self):
        log = []
        with patch.object(gc, "H", return_value=(True, [])), patch.object(gc, "acts_gear"),                 patch.object(gc, "acts_level_up", return_value=84), patch.object(gc, "rc_items", return_value=[]):
            self.assertEqual(gc.a25_melee_back(log), "axe NOT back")
        self.assertIn("NOT back", log[-1])


class Hop(unittest.TestCase):
    def test_legs_until_near_shorter_when_refused(self):
        pos = [100, 100]
        cmds = []

        def H(cmd):
            cmds.append(cmd)
            x, y = (int(v) for v in cmd.split()[1:])
            if abs(x - pos[0]) > 6:  # a 10 leg is refused (a wall there), a 6 leg takes
                return False, []
            pos[:] = [x, y]
            return True, []
        with patch.object(gc, "H", side_effect=H), patch.object(gc.time, "sleep"), \
                patch.object(gc, "hstate", side_effect=lambda: {"player": {"x": pos[0], "y": pos[1]}}):
            self.assertTrue(gc.a25_hop_towards(120, 100, []))
        self.assertEqual(cmds, ["place 110 100", "place 106 100", "place 116 100", "place 112 100", "place 120 100", "place 118 100"])

    def test_gives_up_when_no_leg_takes(self):
        log = []
        with patch.object(gc, "H", return_value=(False, [])), patch.object(gc.time, "sleep"), \
                patch.object(gc, "hstate", return_value={"player": {"x": 0, "y": 0}}):
            self.assertFalse(gc.a25_hop_towards(100, 0, log))
        self.assertIn("hopped 0", log[-1])


class BossFight(unittest.TestCase):
    def setUp(self):
        h = patch.object(gc, "H", return_value=MOVETO7)  # nothing here talks to a game
        h.start()
        self.addCleanup(h.stop)

    def test_phases_stop_once_he_lost_life(self):
        lives = iter([1000, 1000, 900, 900])
        with patch.object(gc, "acts_mon_life", side_effect=lambda _i: next(lives)), \
                patch.object(gc, "acts_fight", return_value=(False, 0, 40)), patch.object(gc, "game_alive", return_value=True), \
                patch.object(gc, "a25_reach_fight", return_value=(False, 40, 3, 30, 7)) as reach, \
                patch.object(gc, "acts_gear_ranged") as bow:
            killed, deaths, t, note, mid = gc.a25_boss_fight(7, 40, [])
        reach.assert_called_once()
        self.assertFalse(reach.call_args.kwargs["ranged"])
        self.assertEqual((reach.call_args.kwargs["cls"], reach.call_args.kwargs["last"]), (526, (500, 600)))
        bow.assert_not_called()
        self.assertEqual((killed, deaths, t, mid), (False, 0, 80, 7))
        self.assertIn("placed melee 40 s (3 SET-UP places, 30 casts): 1000 -> 900", note)

    def test_bow_after_placed_melee_landed_nothing(self):
        with patch.object(gc, "acts_mon_life", return_value=1000), \
                patch.object(gc, "acts_fight", return_value=(False, 0, 40)), patch.object(gc, "game_alive", return_value=True), \
                patch.object(gc, "a25_reach_fight", return_value=(False, 40, 0, 0, 7)) as reach, \
                patch.object(gc, "acts_gear_ranged") as bow, patch.object(gc, "acts_level_up", return_value=83), \
                patch.object(gc, "a25_melee_back", return_value="axe back") as back:
            _k, _d, _t, note, _m = gc.a25_boss_fight(7, 40, [])
        self.assertEqual([c.kwargs["ranged"] for c in reach.call_args_list], [False, True])
        bow.assert_called_once()
        back.assert_called_once()  # the melee weapon back after the bow
        self.assertIn("bow 40 s", note)
        self.assertIn("axe back", note)

    def test_walk_kill_skips_the_phases(self):
        with patch.object(gc, "acts_mon_life", return_value=1000), \
                patch.object(gc, "acts_fight", return_value=(True, 0, 12)), patch.object(gc, "a25_reach_fight") as reach:
            self.assertTrue(gc.a25_boss_fight(7, 40, [])[0])
        reach.assert_not_called()

    def test_reach_fight_places_when_he_walks_off(self):
        clock = [0.0]
        far = {"player": {"x": 100, "y": 100, "life": 1, "mode": 1}}
        cmds = []

        def H(cmd):
            cmds.append(cmd)
            clock[0] += 5
            if cmd.startswith("moveto"):
                return True, ["moveto unit id=7 class=526 at 120,100: code 0, mode now 1"]
            return True, []
        with patch.object(gc.time, "time", side_effect=lambda: clock[0]), patch.object(gc.time, "sleep"), \
                patch.object(gc, "H", side_effect=H), patch.object(gc, "hstate", return_value=far), \
                patch.object(gc, "player_dead", return_value=False), patch.object(gc, "acts_mon_life", return_value=500), \
                patch.object(gc, "a25_place_by", return_value=(118, 100)) as place:
            killed, _t, places, casts, mid = gc.a25_reach_fight(7, 40, [])
        self.assertFalse(killed)
        self.assertEqual(mid, 7)
        self.assertGreater(places, 0)
        self.assertEqual(places, place.call_count)
        self.assertEqual(casts, sum(1 for c in cmds if c == "cast 0 unit 7"))

    def test_class_from_the_caller_when_he_is_gone(self):
        lives = {7: None, 8: 0}
        with patch.object(gc, "H", return_value=(False, ["moveto FAIL moveto: no such live monster"])),                 patch.object(gc, "acts_mon_life", side_effect=lambda i: lives[i]),                 patch.object(gc, "a25_refind", return_value=8) as refind, patch.object(gc.time, "sleep"):
            killed, _t, _p, _c, mid = gc.a25_reach_fight(7, 40, [], cls=544, last=(15135, 5920))
        self.assertEqual(refind.call_args.args[:2], (544, (15135, 5920)))
        self.assertTrue(killed)
        self.assertEqual(mid, 8)

    def test_reach_fight_finds_him_again(self):
        lives = {7: None, 8: 0}
        with patch.object(gc, "H", return_value=(True, ["moveto unit id=7 class=544 at 15135,5920: code 0, mode now 1"])), \
                patch.object(gc, "acts_mon_life", side_effect=lambda i: lives[i]), \
                patch.object(gc, "a25_refind", return_value=8) as refind, patch.object(gc.time, "sleep"):
            killed, _t, _p, _c, mid = gc.a25_reach_fight(7, 40, [])
        refind.assert_called_once()
        self.assertEqual(refind.call_args.args[0], 544)
        self.assertTrue(killed)
        self.assertEqual(mid, 8)


class QuestDoors(unittest.TestCase):
    def test_doors_are_act_links(self):
        self.assertEqual(set(gc.A25_QUEST_DOORS), {(83, 100), (120, 128)})
        self.assertEqual(gc.UP_GATE_OBJECTS[(120, 128)], 547)
        self.assertEqual(gc.COMPELLING_ORB, 404)

    def test_quest_step_once_per_run(self):
        with patch.object(gc, "a25_smash_orb", return_value="SET-UP orb: done") as orb, \
                patch.object(gc, "a25_kill_ancients", return_value="SET-UP ancients: done") as anc, \
                patch.dict(gc.STATE, {}, clear=False):
            gc.STATE.pop("a25_doors", None)
            self.assertIsNone(gc.a25_open_quest_door(40, 47, []))
            self.assertEqual(gc.a25_open_quest_door(83, 100, []), "SET-UP orb: done")
            self.assertEqual(gc.a25_open_quest_door(83, 100, []), "SET-UP orb: done")
            self.assertEqual(gc.a25_open_quest_door(120, 128, []), "SET-UP ancients: done")
        orb.assert_called_once()
        anc.assert_called_once()

    def test_gate_object_clicked_before_the_tile(self):
        states = iter([{"player": {"area": 120, "x": 10, "y": 10}}] * 2 + [{"player": {"area": 128, "x": 0, "y": 0}}] * 5)
        with patch.object(gc, "a25_object_near", return_value={"id": 3, "class": 547, "x": 12, "y": 9}), \
                patch.object(gc, "acts_walk"), patch.object(gc, "up_alive", return_value=True), \
                patch.object(gc, "hstate", side_effect=lambda: next(states)), patch.object(gc, "click_object") as click, \
                patch.object(gc, "up_tile_classes", return_value={80}), patch.object(gc.time, "sleep"):
            ok, how = gc.up_click_through(120, 128, [])
        self.assertTrue(ok)
        self.assertIn("gateway object 547", how)
        self.assertEqual(click.call_count, 2)  # until the area reads 128


class HeldCube(unittest.TestCase):
    def test_contents_first_then_the_cube(self):
        held = [{"id": 5, "code": "box", "page": gc.RC_PAGE_INV}, {"id": 6, "code": "qf2", "page": gc.RC_PAGE_CUBE},
                {"id": 1, "code": "hp1", "page": 255}]
        cmds = []
        with patch.object(gc, "rc_items", return_value=held), \
                patch.object(gc, "Hl", side_effect=lambda cmd, _log: cmds.append(cmd) or (True, [])):
            note = gc.a25_drop_held_cube([])
        self.assertEqual(cmds, ["remove id 6", "remove id 5"])
        self.assertIn("1 of 1, 1 items inside", note)

    def test_no_cube_no_setup(self):
        with patch.object(gc, "rc_items", return_value=[]), patch.object(gc, "Hl") as hl:
            self.assertIsNone(gc.a25_drop_held_cube([]))
        hl.assert_not_called()


class TownSpots(unittest.TestCase):
    def test_spots_for_the_npcs_never_found(self):
        for key in ((40, 176), (40, 177), (40, 244), (75, 297), (75, 252)):
            self.assertIn(key, gc.TOWN_NPC_SPOTS)
            self.assertIn(key[1], gc.TOWN_NPCS[{40: 2, 75: 3}[key[0]]])

    def test_quest_placed_npcs_are_act5_npcs(self):
        self.assertTrue(set(gc.TOWN_QUEST_NPCS) <= set(gc.TOWN_NPCS[5]))


if __name__ == "__main__":
    unittest.main()
