"""The `acts` game check's walks, talk spots and stage bookkeeping (lane acts2); no game is started: the harness calls are
replaced by a fake game."""
import os
import sys
import unittest
from unittest import mock

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
import projtemp  # noqa: E402,F401  (temp files stay inside the project, tools/projtemp.py)
os.environ.setdefault("MXL_SLOT", "2")  # importing game_ctl needs a slot; nothing here starts a game
import game_checks as gc


class FakeGame:
    """`state` / `presets` / `move` / `moveto` / `place` answers for a player that walks only where `blocked` allows."""

    def __init__(self, x=100, y=100, area=40, mons=(), presets=(), blocked=lambda x, y: False):
        self.x, self.y, self.area = x, y, area
        self.mons = list(mons)  # (id, class, x, y)
        self.presets = list(presets)  # (type, class, x, y)
        self.blocked = blocked
        self.calls = []

    def H(self, cmd, timeout=15):
        self.calls.append(cmd)
        w = cmd.split()
        if w[0] == "state":
            lines = ["player id=1 class=4 level=93 life=100/100 area=%d x=%d y=%d mode=5" % (self.area, self.x, self.y)]
            for i, c, mx, my in self.mons:
                d = max(abs(mx - self.x), abs(my - self.y))
                if d <= 40:
                    lines.append("mon id=%d class=%d mode=1 dist=%d life=10/10 mx=%d my=%d area=%d" % (i, c, d, mx, my, self.area))
            return True, lines
        if w[0] == "presets":
            want = int(w[1]) if len(w) > 1 else None
            return True, ["preset type=%d class=%d x=%d y=%d" % p for p in self.presets if want is None or p[0] == want]
        if w[0] == "move":
            tx, ty = int(w[1]), int(w[2])
            if not self.blocked(tx, ty):
                self.x, self.y = tx, ty
            return True, ["move OK"]
        if w[0] == "place":
            self.x, self.y = int(w[1]), int(w[2])
            return True, ["place OK"]
        if w[0] == "moveto":
            cls = int(w[2]) if w[1] == "nearest" else None
            for i, c, mx, my in self.mons:
                if (cls is not None and c == cls) or (cls is None and i == int(w[1])):
                    return True, ["moveto unit id=%d class=%d at %d,%d: code 0, mode now 3" % (i, c, mx, my)]
            return False, ["moveto FAIL moveto: no such live monster"]
        return True, []


class ActsWalks(unittest.TestCase):
    def setUp(self):
        self.sleep = mock.patch.object(gc.time, "sleep", lambda s: None)
        self.sleep.start()
        gc.STATE.pop("walk_spots", None)
        gc.STATE["unkillable"] = set()

    def tearDown(self):
        self.sleep.stop()

    def run_with(self, game, fn, *a, **kw):
        with mock.patch.object(gc, "H", game.H), mock.patch.object(gc, "Hl", lambda cmd, log, timeout=15: game.H(cmd)):
            return fn(*a, **kw)

    def test_stuck_walk_turns_its_detours(self):
        # a wall east of x=100 that ends at y=40: the first detour (north-east) runs into it, a later one gets round
        game = FakeGame(x=100, y=100, blocked=lambda x, y: x > 100 and y >= 40)
        ok = self.run_with(game, gc.acts_walk, 160, 30, reach=6, timeout=20)
        self.assertTrue(ok)
        detours = [c for c in game.calls if c.startswith("move ")]
        self.assertGreater(len(set(detours)), 3)

    def test_town_sweep_records_npc_spots(self):
        game = FakeGame(x=5153, y=5203, mons=[(31, 210, 5213, 5078), (22, 201, 5080, 5151), (9, 999, 5150, 5200)])
        spots = self.run_with(game, gc.acts_town_sweep, 2, [])
        self.assertEqual(spots.get(201), (5080, 5151))
        self.assertEqual(spots.get(210), (5213, 5078))
        self.assertNotIn(999, spots)  # only the town's NPCs
        self.assertNotIn("walk_spots", gc.STATE)

    def test_tyrael_spot_from_duriel_preset(self):
        game = FakeGame(area=73, presets=[(1, 211, 22635, 15718)])
        spots = self.run_with(game, gc.acts_talk_spots, "tyrael", [])
        self.assertEqual(spots, [(22635 + gc.DURIEL_TO_TYRAEL[0], 15718 + gc.DURIEL_TO_TYRAEL[1])])
        self.assertEqual(gc.DURIEL_TO_TYRAEL, (78 - 135, 88 - 218))  # Median's duriel.ds1: tyrael1 (78, 88), duriel (135, 218)

    def test_jerhyn_spots_inside_first(self):
        game = FakeGame(presets=[(2, 121, 5147, 5191), (2, 122, 5071, 5148), (2, 286, 1, 1)])
        self.assertEqual(self.run_with(game, gc.acts_talk_spots, "jerhyn", []), [(5071, 5148), (5147, 5191)])

    def test_close_in_walks_only_when_far(self):
        game = FakeGame(x=17591, y=8072, area=102, mons=[(76, 242, 17541, 8068)])
        self.assertTrue(self.run_with(game, gc.acts_close_in, 76))
        self.assertLessEqual(abs(game.x - 17541), gc.ACTS_MELEE_REACH)
        game2 = FakeGame(x=17545, y=8070, area=102, mons=[(76, 242, 17541, 8068)])
        self.run_with(game2, gc.acts_close_in, 76)
        self.assertFalse([c for c in game2.calls if c.startswith("move ")])


class BridgeGame(FakeGame):
    """Durance 3: Mephisto's bridge (object 341) rises once the player stands closer than 18 (1.14d's bridge event 7)."""

    def __init__(self, **kw):
        super().__init__(area=102, **kw)
        self.bridge = [119, 341, 0, 17599, 8070]

    def H(self, cmd, timeout=15):
        w = cmd.split()
        if w[0] == "objects":
            b = self.bridge
            if max(abs(self.x - b[3]), abs(self.y - b[4])) < gc.BRIDGE_REACH:
                b[2] = 2
            d = max(abs(self.x - b[3]), abs(self.y - b[4]))
            self.calls.append(cmd)
            return True, ["object id=%d class=%d mode=%d dist=%d at %d,%d" % (b[0], b[1], b[2], d, b[3], b[4])]
        return super().H(cmd, timeout)


class ActsRoutes(ActsWalks):
    def test_bridge_rises_when_walked_up_to(self):
        game = BridgeGame(x=17557, y=8020)
        note = self.run_with(game, gc.acts_raise_bridge, [], walk_s=0.2)
        self.assertIn("-> 2", note)
        self.assertEqual(game.bridge[2], 2)

    def test_bridge_out_of_reach_is_named(self):
        game = BridgeGame(x=17557, y=8020, blocked=lambda x, y: x > 17560)  # the lava: no walk closer
        note = self.run_with(game, gc.acts_raise_bridge, [], walk_s=0.2)
        self.assertIn("stayed in mode 0", note)

    def test_routes_inside_their_levels(self):
        for pts, (x0, y0, w, h) in ((gc.THRONE_ROUTE, (15000, 5000, 205, 265)), (gc.BAAL_ROUTE, (15000, 5760, 280, 280))):
            for x, y in pts:
                self.assertTrue(x0 <= x < x0 + w and y0 <= y < y0 + h, (x, y))

    def test_search_walk_gets_round_a_wall(self):
        # a wall at x 110-114 from y 60 down; the only way east is round its north end
        wall = lambda x, y: 110 <= x <= 114 and y >= 60
        game = FakeGame(x=100, y=100, area=108)

        def move_blocked(x0, y0, x1, y1):  # the move stops at the wall: no leg crosses it
            n = max(abs(x1 - x0), abs(y1 - y0), 1)
            return any(wall(x0 + (x1 - x0) * i / n, y0 + (y1 - y0) * i / n) for i in range(n + 1))
        real_h = game.H

        def H(cmd, timeout=15):
            w = cmd.split()
            if w[0] == "move" and move_blocked(game.x, game.y, int(w[1]), int(w[2])):
                game.calls.append(cmd)
                return True, ["move OK"]
            return real_h(cmd, timeout)
        game.H = H
        gc.STATE.pop("walk_map", None)
        ok = self.run_with(game, gc.acts_search_walk, 130, 100, [], budget_s=5, fight=False)
        self.assertTrue(ok)
        self.assertLessEqual(abs(game.x - 130), 8)
        gc.STATE.pop("walk_map", None)

    def test_walk_map_links_only_real_moves(self):
        gc.STATE.pop("walk_map", None)
        gc.walk_map_link(108, (100, 100), (110, 100))
        gc.walk_map_link(108, (110, 100), (200, 100))  # a `place`: no link
        e = gc.walk_map(108)["edges"]
        self.assertIn(gc.walk_cell(110, 100), e[gc.walk_cell(100, 100)])
        self.assertNotIn(gc.walk_cell(200, 100), e)
        gc.STATE.pop("walk_map", None)

    def test_route_places_a_refused_leg(self):
        game = FakeGame(x=15103, y=5213, area=131, blocked=lambda x, y: y < 5150)
        out = self.run_with(game, gc.acts_route, gc.THRONE_ROUTE, [], walk_s=0.2)
        self.assertEqual(out["legs"], len(gc.THRONE_ROUTE))
        self.assertGreater(out["placed"], 0)
        self.assertEqual(out["end"], gc.THRONE_ROUTE[-1])


class GlacialWarps(unittest.TestCase):
    def test_torch_pairs_give_the_warps(self):
        # IceNahead01: torches 480 at 41,51 and 41,61 beside the warp; a lone torch and the other torch class are no warp
        pres = [{"type": 2, "class": 480, "x": 1041, "y": 2051}, {"type": 2, "class": 481, "x": 1038, "y": 2027},
                {"type": 2, "class": 480, "x": 1041, "y": 2061}, {"type": 2, "class": 480, "x": 1300, "y": 2300},
                {"type": 2, "class": 480, "x": 1556, "y": 2027}, {"type": 2, "class": 480, "x": 1566, "y": 2027}]
        self.assertEqual(gc.glacial_warp_spots(pres), [(1041, 2056), (1561, 2027)])

    def test_known_exit_first_way_in_last(self):
        spots = [(10291, 7677), (10276, 7466), (10180, 7340)]
        at = (10180, 7345)
        self.assertEqual(gc.glacial_spot_order(spots, at), [(10180, 7340), (10276, 7466), (10291, 7677)])
        self.assertEqual(gc.glacial_spot_order(spots, at, came_at=(10181, 7342)), [(10276, 7466), (10291, 7677), (10180, 7340)])
        self.assertEqual(gc.glacial_spot_order(spots, at, exit_at=(10276, 7466))[0], (10276, 7466))

    def test_warps_listed_once_stay_known(self):
        known = [(10276, 7466)]
        self.assertIs(gc.glacial_merge_spots(known, [(10277, 7467), (10291, 7677)]), known)
        self.assertEqual(known, [(10276, 7466), (10291, 7677)])


class ActsTables(unittest.TestCase):
    def test_wave_bosses_and_walls(self):
        self.assertEqual(gc.WAVE_CLASSES, (1289, 1148, 803, 1290, 1281))
        self.assertIn("BoneWall", gc.WALL_AIS)
        self.assertEqual(gc.DIABLO_SEALS, (392, 393, 394, 395, 396))

    def test_end_talks_need_tyrael_then_jerhyn(self):
        self.assertEqual([(a, w) for a, w, _k, _q in gc.ACT_END_TALKS["travel23"]], [(73, 251), (40, 201)])
        self.assertEqual(gc.TOWN_NPC_SPOTS[(40, 210)], (5213, 5078))


if __name__ == "__main__":
    unittest.main()
