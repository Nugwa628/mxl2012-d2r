"""The release candidate's town check of game_checks (lane relprep, `relp_town`): registered, and its code drives the character by
clicks only (no harness move, talk, menu or pick-up verb, no god mode or item grants); no game is started."""
import inspect
import os
import re
import sys
import unittest

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import projtemp  # noqa: E402,F401  (temp files stay inside the project, tools/projtemp.py)
os.environ.setdefault("MXL_SLOT", "2")  # importing game_ctl needs a slot; nothing here starts a game
import game_checks as gc  # noqa: E402
import release_install  # noqa: E402

RELP = ("check_relp_town", "relp_town_class", "relp_talk", "relp_walk_out", "relp_walk_out_search", "relp_click_walk",
        "relp_wait_loaded", "relp_walkmap", "relp_plan", "relp_follow", "relp_walk_to", "relp_merge", "relp_known_wm",
        "relp_npc_spot", "relp_walk_level")


class RelpTown(unittest.TestCase):
    def test_registered(self):
        self.assertIn("relp_town", [n for n, _ in gc.CHECKS])

    def test_clicks_only(self):
        src = "".join(inspect.getsource(getattr(gc, f)) for f in RELP)
        for pat in (r"Tank\(", r"god 1", r"\"item ", r"\"kill ", r"\"spawn ", r"\"move ", r"\"moveto ", r"\"interact ",
                    r"\"menu ", r"\"pickup ", r"\"gold set", r"\"xp ", r"\"packclear", r"\"waypoint n"):
            m = re.search(pat, src)
            self.assertIsNone(m, "relp_town uses a harness shortcut: %s" % (m.group(0) if m else ""))

    def test_classes_known(self):
        import playthrough
        for cls in gc.RELP_CLASSES:
            self.assertIn(cls, playthrough.CLASS_NAMES)


def walkmap(rows, others=None, x0=100, y0=200, step=4):
    return {"grid": rows, "x0": x0, "y0": y0, "step": step, "level": 1, "others": others or {}}


# a camp: a palisade (#) with one gate (the gap in the right wall), the Blood Moor (A = level 2) beyond it
CAMP = ["##########",
        "#........#",
        "#........#AA",
        "#.........AA",
        "#........#AA",
        "##########"]


class RelpPlan(unittest.TestCase):
    def test_through_the_gate(self):
        path, kind = gc.relp_plan(walkmap(CAMP, {"A": 2}), (104, 204), 2)
        self.assertEqual(kind, "level")
        self.assertEqual(path[0], (104, 204))
        self.assertIn((136, 212), path)  # the gate cell (column 9, row 3)
        self.assertEqual(path[-1], (140, 212))

    def test_frontier_when_moor_not_loaded(self):
        rows = [r.replace("A", "?") for r in CAMP]
        path, kind = gc.relp_plan(walkmap(rows), (104, 204), 2)
        self.assertEqual(kind, "frontier")
        self.assertEqual(path[-1], (136, 212))  # the farthest reachable cell beside unknown ground: the gate
        path2, why = gc.relp_plan(walkmap(rows), (104, 204), 2, avoid=[(136, 212), (132, 204), (132, 216)])
        self.assertNotIn((136, 212), path2 or [])

    def test_no_corner_cutting(self):
        rows = [".#",
                "#."]  # the free cell diagonal to the start is closed off by two posts: no path squeezes between them
        path, kind = gc.relp_plan(walkmap(rows, x0=0, y0=0, step=10), (0, 0), None, target=(10, 10))
        self.assertNotEqual(kind, "target")
        self.assertNotIn((10, 10), path or [])

    def test_target(self):
        path, kind = gc.relp_plan(walkmap(CAMP, {"A": 2}), (104, 204), None, target=(128, 216))
        self.assertEqual(kind, "target")
        self.assertLessEqual(abs(path[-1][0] - 128) + abs(path[-1][1] - 216), 10)

    def test_merged_map(self):
        # two answers of one room each: the left one has the camp's inside, the right one (taken later, further on) the gate
        left = walkmap(["#####", "#....", "#....", "#....", "#####"], x0=100, y0=200)
        right = walkmap(["#####", "...#A", "....A", "...#A", "#####"], {"A": 2}, x0=117, y0=201)  # off the 4-grid: snapped
        known = gc.relp_merge(gc.relp_merge({}, left), right)
        wm = gc.relp_known_wm(known)
        self.assertEqual((wm["x0"], wm["y0"]), (100, 200))
        self.assertIn(2, wm["others"].values())
        path, kind = gc.relp_plan(wm, (104, 208), 2)
        self.assertEqual(kind, "level")
        self.assertGreaterEqual(path[-1][0], 132)
        self.assertIsNone(gc.relp_known_wm({}))

    def test_waypoints(self):
        self.assertEqual(gc.relp_waypoints([(i, 0) for i in range(8)], 3), [(3, 0), (6, 0), (7, 0)])
        self.assertEqual(gc.relp_waypoints([], 3), [])


class PackageInstall(unittest.TestCase):
    def test_package_needs_manifest(self):
        with self.assertRaises(SystemExit):
            release_install.package_manifest(os.path.join(os.path.dirname(__file__), "no-such-dir", "D2R-XL-2012-0.0.0.7z"))


if __name__ == "__main__":
    unittest.main()
