"""tools/level_sweep.py: the plan, the character, the walk and the report (pure parts; no game)."""
import os
import random
import sys
import tempfile
import unittest

os.environ.setdefault("MXL_SLOT", "2")  # importing game_ctl needs a slot; nothing here starts a game
TOOLS = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, TOOLS)
import level_sweep as L  # noqa: E402
import projtemp  # noqa: E402,F401  (temp files stay inside the project, tools/projtemp.py)


def level(lid, name, act=0, drlg=2, ltype=1, wp="255", vis=(), **kw):
    r = {"Id": str(lid), "Name": name, "LevelName": name, "Act": str(act), "DrlgType": str(drlg), "LevelType": str(ltype), "Waypoint": wp}
    for k, v in enumerate(vis):
        r["Vis%d" % k] = str(v)
    r.update(kw)
    return r


LEVELS = [level(0, "Null"), level(1, "Act 1 - Town", wp="0", vis=(2,)), level(2, "Act 1 - Wilderness 1", drlg=3, vis=(1, 8)),
          level(3, "Act 1 - Wilderness 2", drlg=3, wp="1"), level(8, "Act 1 - Cave 1", drlg=1, vis=(2,)),
          level(17, "Act 1 - Graveyard", drlg=3, wp="17"), level(46, "Act 2 - Valley", act=1, drlg=3, wp="17"),
          level(111, "Act 5 - Barricade 1", act=4, drlg=3), level(125, "Act 5 - Hell 1", act=4),
          level(133, "Act 5 - Pandemonium 1", act=4, drlg=1, vis=(17,))]


class PlanTests(unittest.TestCase):
    def setUp(self):
        self.plan = {p["id"]: p for p in L.plan_levels(levels=LEVELS)}

    def test_row_zero_is_not_a_level(self):
        self.assertNotIn(0, self.plan)
        self.assertEqual(len(self.plan), len(LEVELS) - 1)

    def test_routes(self):
        self.assertIn("from 2 (warp tile)", self.plan[8]["routes"])
        self.assertIn("from 1 (outdoor edge)", self.plan[2]["routes"])  # the town's edge
        self.assertIn("from 2 (outdoor edge)", self.plan[3]["routes"])
        self.assertIn("red portal in 111", self.plan[125]["routes"])
        self.assertIn("town (the act's start)", self.plan[1]["routes"])
        self.assertEqual(self.plan[133]["routes"], [])  # its Vis points out of it: nothing leads in

    def test_shared_waypoint_is_named(self):
        self.assertIn("waypoint 17 (shared with Act 2 - Valley)", self.plan[17]["routes"])

    def test_run_order_is_by_act_then_id(self):
        order = [p["id"] for p in L.run_order(list(self.plan.values()), "normal")]
        self.assertEqual(order, sorted(order, key=lambda i: (self.plan[i]["act"], i)))


class DifficultyTests(unittest.TestCase):
    def test_same_generation_is_normal_only(self):
        r = {"SizeX": "10", "SizeX(N)": "10", "SizeX(H)": "10", "mon1": "a", "nmon1": "a"}
        self.assertEqual(L.difficulties(r), ["normal"])

    def test_other_monster_list_adds_hell(self):
        self.assertEqual(L.difficulties({"mon1": "a", "nmon1": "b"}), ["normal", "hell"])

    def test_nightmare_size_of_its_own_adds_nightmare(self):
        r = {"SizeX": "10", "SizeX(N)": "20", "SizeX(H)": "30"}
        self.assertEqual(L.difficulties(r), ["normal", "nightmare", "hell"])

    def test_monster_level_alone_does_not_count(self):
        self.assertEqual(L.difficulties({"MonLvl": "1", "MonLvl(N)": "30", "MonLvl(H)": "60"}), ["normal"])


class CharacterTests(unittest.TestCase):
    CS = {"class": "Barbarian", "str": "30", "dex": "20", "int": "10", "vit": "25", "hpadd": "30", "LifePerLevel": "8",
          "LifePerVitality": "16", "ManaPerLevel": "4", "StatPerLevel": "5"}

    def test_points_are_spent_as_the_game_gives_them(self):
        c = L.normal_character(self.CS, level=120)
        self.assertEqual(c[0] + c[1] + c[2] + c[3], 30 + 20 + 10 + 25 + 5 * 119)
        self.assertEqual((c[0], c[2], c[1]), (250, 150, 10))

    def test_life_and_mana_from_charstats(self):
        c = L.normal_character(self.CS, level=120)
        self.assertEqual(c[7], 25 + 30 + (8 * 119 + 16 * (c[3] - 25)) // 4)
        self.assertEqual(c[6], c[7])
        self.assertEqual(c[9], 10 + (4 * 119) // 4)
        self.assertEqual(c[12], 120)


class WalkTests(unittest.TestCase):
    def test_keeps_direction_while_moving_mostly(self):
        rng = random.Random(1)
        same = sum(L.next_direction(3, 10, rng) == 3 for _ in range(600))
        self.assertGreater(same, 400)

    def test_turns_when_stuck(self):
        rng = random.Random(2)
        self.assertTrue(all(L.next_direction(3, 0, rng) != 3 for _ in range(100)))

    def test_screen_frac_centre(self):
        self.assertEqual(L.screen_frac(0, 0), (0.5, 405 / 900))
        x, y = L.screen_frac(8, 0)
        self.assertGreater(x, 0.5)
        self.assertGreater(y, 405 / 900)

    def test_cells(self):
        self.assertEqual(L.cell_of(17, 8), (2, 1))


class ParseTests(unittest.TestCase):
    STATE = ["player id=1 class=4 level=120 life=4385/4385 mana=1195 area=111 x=5000 y=4000 mode=1 difficulty=2 frame=7",
             "obj id=55 class=60 mode=0 dist=12 at 5010,4005 dest=125", "obj id=56 class=2 mode=0 dist=4 at 1,2",
             "mon id=9 class=12 mode=1 dist=8 life=10/10 mx=5003 my=4001 area=111"]

    def test_player(self):
        p = L.parse_player(self.STATE)
        self.assertEqual((p["area"], p["x"], p["life"], p["life_max"], p["difficulty"]), (111, 5000, 4385, 4385, 2))
        self.assertFalse(L.player_dead(p))
        self.assertTrue(L.player_dead({"mode": 17, "life": 5}))
        self.assertTrue(L.player_dead({"mode": 1, "life": 0}))

    def test_portals(self):
        self.assertEqual(L.parse_portals(self.STATE), [(55, 60, 125)])

    def test_objects(self):
        self.assertEqual(L.parse_objects(["object id=7 class=119 mode=0 dist=5 at 1,2", "objects 1"]), [(7, 119, 5)])


class ReportTests(unittest.TestCase):
    def test_automap_on_a_death_screen(self):
        self.assertIsNone(L.automap_of({"automap_px": 300, "automap_dead": True}))
        self.assertTrue(L.automap_of({"automap_px": 900, "automap_dead": True}))
        self.assertFalse(L.automap_of({"automap_px": 300}))
        self.assertEqual(L.problem_keys({"reached": True, "walked": 40, "deaths": 7, "automap_px": 300, "automap_dead": True}), [])

    def test_object_pos(self):
        lines = ["object id=12 class=119 mode=0 dist=31 at 5120,5200", "object id=13 class=2 mode=0 dist=4 at -3,7", "objects 2"]
        self.assertEqual(L.object_pos(lines, 12), (5120, 5200))
        self.assertEqual(L.object_pos(lines, 13), (-3, 7))
        self.assertIsNone(L.object_pos(lines, 1))

    def test_route_verdict(self):
        self.assertEqual(L.route_verdict({"ok": True}), "ok")
        self.assertEqual(L.route_verdict({"ok": None}), "not judged")
        self.assertEqual(L.route_verdict({"ok": False}), "**FAIL**")

    def test_tp_rejudge(self):
        none = {"ok": False, "note": "no portal after the scroll was used"}
        self.assertTrue(L.tp_rejudge(none, True)["ok"])
        self.assertFalse(L.tp_rejudge(none, False)["ok"])
        self.assertFalse(L.tp_rejudge({"ok": False, "note": "level not reached"}, True)["ok"])

    def test_portal_rejudge(self):
        note = "no red portal (objects.txt 60) found in level 112 after 480 s of walking (5 8x8 cells, %d deaths)"
        self.assertIsNone(L.portal_rejudge({"ok": False, "note": note % 35})["ok"])
        self.assertFalse(L.portal_rejudge({"ok": False, "note": note % 1})["ok"])
        self.assertTrue(L.portal_rejudge({"ok": True, "note": "red portal id 172"})["ok"])

    def test_merge_runs_keeps_the_out_order(self):
        old = {"levels": {"normal": {"14": {"reached": True, "deaths": 0}}}}
        new = {"levels": {"normal": {"14": {"reached": True, "deaths": 7}}}}
        self.assertEqual(L.merge_runs({"z-old": old, "a-new": new})["levels"]["normal"]["14"]["deaths"], 7)

    def test_routes_of_rows_with_another_acts_tiles(self):
        # 134 Pandemonium 2: an act 5 outdoor row drawn with the Valley's (act 2) tiles and the Valley's waypoint number: neither
        # an outdoor edge of act 5 nor a waypoint route (bugs.md #13)
        rows = [level(109, "Act 5 - Town", act=4, ltype=29, wp="38"), level(117, "Act 5 - Barricade 3", act=4, drlg=3, ltype=31),
                level(134, "Act 5 - Pandemonium 2", act=4, drlg=3, ltype=16, wp="17")]
        plan = {p["id"]: p for p in L.plan_levels(levels=rows, tile_acts={29: 4, 31: 4, 16: 1})}
        self.assertEqual(plan[134]["routes"], [])
        self.assertEqual(plan[117]["routes"], ["from 109 (outdoor edge)"])

    def test_cow_verdict(self):
        self.assertEqual(L.cow_verdict([(77, 60, 39)], 39), (True, 77))
        self.assertEqual(L.cow_verdict([(77, 60, 39)], 1), (False, 77))  # the portal opened, entering it failed
        self.assertEqual(L.cow_verdict([(78, 59, 1)], None), (False, None))
        self.assertEqual(L.cow_verdict([], None), (False, None))

    def test_problem_keys(self):
        self.assertEqual(L.problem_keys({"reached": False}), ["unreachable"])
        self.assertEqual(L.problem_keys({"reached": False, "hang": True}), ["hang"])
        res = {"reached": True, "walked": 0, "automap": False, "errors": ["x"],
               "asserts": [{"message": "AssetCache.h grow", "location": "a"}, {"message": "boom", "location": "b.cpp"}]}
        self.assertEqual(L.problem_keys(res), ["assert: boom (b.cpp)", "log: x", "no-walk (the character never moved)", "automap-empty"])
        self.assertEqual(L.problem_keys({"reached": True, "walked": 40, "automap": True}), [])
        self.assertEqual(L.problem_keys({"reached": True, "walked": 0, "deaths": 7, "automap": True}), [])  # killed on arrival
        # killed on arrival: judged on the load, the dead character's empty automap is no problem; an assert still is
        self.assertEqual(L.problem_keys({"reached": True, "walked": 0, "deaths": 5, "automap_px": 48}), [])
        self.assertTrue(L.killed_on_arrival({"reached": True, "walked": 0, "deaths": 2}))
        self.assertFalse(L.killed_on_arrival({"reached": True, "walked": 0, "deaths": 1}))
        self.assertFalse(L.killed_on_arrival({"reached": True, "walked": 3, "deaths": 4}))
        self.assertEqual(L.problem_keys({"reached": True, "walked": 0, "deaths": 1, "automap": True}), ["no-walk (the character never moved)"])
        self.assertEqual(L.problem_keys({"reached": True, "walked": 0, "deaths": 3, "automap": False,
                                         "asserts": [{"message": "boom", "location": "b.cpp"}]}), ["assert: boom (b.cpp)"])
        # the stored pixel count wins over the stored verdict (a new threshold re-judges old runs)
        self.assertEqual(L.problem_keys({"reached": True, "walked": 40, "automap": False, "automap_px": 900}), [])
        self.assertEqual(L.problem_keys({"reached": True, "walked": 40, "automap": True, "automap_px": 10}), ["automap-empty"])

    def test_render(self):
        plan = L.plan_levels(levels=LEVELS)
        data = {"levels": {"normal": {"2": {"reached": True, "load_s": 3.1, "walked": 50, "explored": 9, "monsters": 4, "automap": True},
                                      "8": {"reached": False, "hang": True}}},
                "waypoints": {"3": {"ok": True, "note": "fine"}}, "portals": {"111:125": {"ok": False, "note": "none"}},
                "mapmem": [{"when": "t", "visited": 2, "files": {".map": 10}}], "notes": ["n"]}
        text = L.render_report(plan, data)
        self.assertIn("| hang | 1 | N 8 |", text)
        self.assertIn("3.1 s / 9 / 4 / A / 0", text)
        self.assertIn("**hang**", text)
        self.assertIn("| 111:125 Act 5 - Barricade 1 | **FAIL** | none |", text)
        self.assertIn("| t | 2 | .map 10 |", text)


class MergeTests(unittest.TestCase):
    def test_batches_merge(self):
        a = {"levels": {"normal": {"1": {"reached": True}}}, "notes": ["x"], "walk": 30, "build": "abc",
             "mapmem": [{"when": "t", "visited": 0, "files": {}}], "runs": {"normal": {"started": "s"}}}
        b = {"levels": {"normal": {"2": {"reached": True}}, "hell": {"2": {}}}, "waypoints": {"3": {"ok": True}}, "walk": 30, "build": "abc"}
        m = L.merge_runs({"act1": a, "act2": b})
        self.assertEqual(sorted(m["levels"]["normal"]), ["1", "2"])
        self.assertIn("hell", m["levels"])
        self.assertEqual(m["waypoints"], {"3": {"ok": True}})
        self.assertEqual((m["walk"], m["build"]), ("30", "abc"))
        self.assertEqual(m["notes"], ["act1: x"])
        self.assertEqual(m["mapmem"][0]["when"], "act1 t")
        self.assertIn("act1 normal", m["runs"])


class SaveTests(unittest.TestCase):
    def test_progression_byte_and_checksum(self):
        import game_checks as gc  # noqa: F401  (MXL_SLOT is needed at import)
        with tempfile.TemporaryDirectory() as d:
            p = os.path.join(d, "x.d2s")
            body = bytearray(0x40)
            body[0:4] = b"\x55\xaa\x55\xaa"
            with open(p, "wb") as f:
                f.write(bytes(body))
            self.assertTrue(L.set_progression(p, "hell"))
            with open(p, "rb") as f:
                s = f.read()
            self.assertEqual(s[0x15], 10)  # the v105 header's progression byte (rc_setup), not 1.x's 0x25
            self.assertEqual(s[0x25], 0)
            self.assertEqual(s, gc._checksum(s))
            self.assertFalse(L.set_progression(p, "hell"))


if __name__ == "__main__":
    unittest.main()
