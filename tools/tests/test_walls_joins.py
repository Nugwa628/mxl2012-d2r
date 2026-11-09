"""Tests of the sprite <-> D2R joins (walls_scene.join_points / Kit.join_fit / place_joins, walls_hd.build_scene) and of the
sprite atlas colour match (walls_sprite.match_colour / pool_stats, walls_hd.sprite_neighbours)."""
import json
import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import projtemp  # noqa: E402,F401  (temp files stay inside the project, tools/projtemp.py)

import walls_hd  # noqa: E402
import walls_scene  # noqa: E402
import walls_sprite  # noqa: E402

K = "act3/kurast"
D = "act3/docktown"
J = "act2/ruin"
POST = "data/hd/env/model/act3/kurast/post01.model"
TALL = "data/hd/env/model/act3/docktown/pillar01.model"
OTHER = "data/hd/env/model/act2/ruin/pillar01.model"
CORNER = "data/hd/env/model/act3/docktown/stone_ruin_corner01.model"
BOXES = {POST: ((-1, 0, -1), (1, 2.0, 1)), TALL: ((-1, 0, -1), (1, 10.0, 1)), OTHER: ((-1, 0, -1), (1, 9.0, 1)),
         CORNER: ((-5, 0, -5), (5, 10.0, 5))}


def kit():
    """A kit with a low joint for act3/kurast, a tall one for act3/docktown and one for act2/ruin (no D2R maps needed)."""
    k = walls_scene.Kit(BOXES.get, walls_hd.model_of)
    for folder, model in ((K, POST), (D, TALL), (J, OTHER)):
        jid = (folder, ((model, 0),))
        k.joints[folder][jid] += 1
        k.joint_defs[jid] = [{"entity": {"components": [{"type": "TransformDefinitionComponent"},
                                                         {"type": "ModelDefinitionComponent", "filename": model}]},
                              "model": model, "du": 0.0, "dv": -2.0, "dy": 0.0, "yaw": 0.0, "scale": (1.0, 1.0, 1.0)}]
    return k


class JoinPointsTest(unittest.TestCase):
    def test_in_line_and_at_a_corner(self):
        sprite = {("x", 5, 3): (8.0, K), ("x", 5, 4): (9.0, K)}         # a sprite wall on row 5, x 3-4
        d2r = {("x", 5, 5): K, ("z", 3, 5): D, ("x", 5, 4): K}         # D2R: x 5 in line, a left wall at the corner (3, 5)
        pts = walls_scene.join_points(sprite, d2r)
        self.assertEqual([p[0] for p in pts], [(3, 5), (5, 5)])
        self.assertEqual(pts[1], ((5, 5), "x", 9.0, [K]))
        self.assertEqual(pts[0][3], [D, K])                             # the D2R side's tile set first
        self.assertEqual(walls_scene.join_points(sprite, {("x", 7, 9): K}), [])   # nothing shared: no join

    def test_edge_points(self):
        self.assertEqual(walls_scene.edge_points("x", 5, 3), ((3, 5), (4, 5)))
        self.assertEqual(walls_scene.edge_points("z", 5, 3), ((5, 3), (5, 4)))


class JoinFitTest(unittest.TestCase):
    def test_own_joint_scaled_to_the_sprite(self):
        jid, s, how = kit().join_fit([D], 12.0)
        self.assertEqual((jid[0], how), (D, "own"))
        self.assertAlmostEqual(s, 1.2)

    def test_a_low_joint_takes_a_similar_kits(self):
        jid, s, how = kit().join_fit([K], 10.0)        # the kurast post is 2 high: 5 times, out of JOIN_SCALE
        self.assertEqual((jid[0], how), (D, "similar"))  # the same act's, not act2's 9-high one
        self.assertAlmostEqual(s, 1.0)

    def test_only_posts(self):
        k = kit()
        jid = ("act3/sewer", ((CORNER, 0),))
        k.joints["act3/sewer"][jid] += 50                # used more, the right height, but 10 x 10: a corner, not a post
        k.joint_defs[jid] = [dict(k.joint_defs[next(iter(k.joints[D]))][0], model=CORNER)]
        self.assertEqual(k.joint_foot(jid), (10.0, 10.0))
        got = k.join_fit(["act3/sewer"], 10.0)
        self.assertEqual((got[0][0], got[2]), (D, "similar"))

    def test_none_when_nothing_fits(self):
        self.assertIsNone(kit().join_fit([K], 40.0))
        self.assertIsNone(kit().join_fit(["act5/siege"], 10.0))

    def test_place_joins(self):
        k = kit()
        pts = [((5, 5), "x", 12.0, [D]), ((3, 5), "z", 12.0, [D]), ((8, 8), "x", 50.0, [K])]
        groups, left = walls_scene.place_joins(pts, k, taken={(3, 5)})
        self.assertEqual(left, [(8, 8)])
        self.assertEqual(len(groups), 1)
        placed = groups[0]
        _e, x, _y, z, _yaw, scale = placed[0]
        self.assertEqual((x, z), (50.0, 48.0))         # on the point, the joint's own offset across the run kept
        self.assertAlmostEqual(scale[1], 1.2)          # sized to the sprite wall's top
        ents = walls_scene.entities(placed, "mxj", id_base=walls_hd.JOIN_ID_BASE)
        self.assertEqual(ents[0]["id"], walls_hd.JOIN_ID_BASE)
        self.assertEqual(walls_scene.joint_points(placed, k), {(5, 5)})


class BudgetTest(unittest.TestCase):
    def groups(self, n, members=2):
        g, _left = walls_scene.place_joins([((i, 0), "x", 10.0, [D]) for i in range(n)], kit())
        return [p * members for p in g]

    def test_all_fit(self):
        ents = walls_hd.budget_joins(self.groups(4), 100, 10 ** 6)
        self.assertEqual(len(ents), 8)
        self.assertEqual([e["id"] - walls_hd.JOIN_ID_BASE for e in ents], list(range(8)))
        self.assertEqual(len({e["name"] for e in ents}), 8)

    def test_whole_joints_spread_within_the_room(self):
        ents = walls_hd.budget_joins(self.groups(8), 7, 10 ** 6)       # room for 3 whole joints of 2 members
        kept = sorted({int(e["name"].split("_")[1]) for e in ents})
        self.assertEqual(len(ents), 6)
        self.assertEqual(kept, [2, 4, 6])                              # spread() ranks highest: every other one
        self.assertEqual(walls_hd.budget_joins(self.groups(8), 0, 10 ** 6), [])

    def test_bytes_room(self):
        one = walls_hd.budget_joins(self.groups(1), 10, 10 ** 6)
        size = sum(len(json.dumps(e, separators=(",", ":"))) + 1 for e in one)
        self.assertEqual(len(walls_hd.budget_joins(self.groups(3), 10, 2 * size + 10)), 4)


class BuildSceneJoinTest(unittest.TestCase):
    def test_a_joint_between_a_sprite_cell_and_a_d2r_cell(self):
        lib = walls_hd.Library()
        k_wall = ((D, 2, 2, 0),)
        for m in ("m1", "m2", "m3"):
            lib.learn(m, {(0, 0): k_wall}, {"entities": [{"name": "e", "components": [
                {"type": "TransformDefinitionComponent", "position": {"x": 5, "y": 0, "z": 5}},
                {"type": "ModelDefinitionComponent", "filename": "data/hd/env/model/act3/docktown/wall01.model"}]}]})
        lib.kit = kit()

        class Tiles:
            arches = frozenset()

            def entities(self, xy, serial, only=None):
                return [walls_sprite.entity(walls_sprite.model_path("m", k), xy[0], xy[1], 0, serial) for k in sorted(only)]

            def forced(self, xy):
                return False

            def floor_entities(self):
                return []

            def box(self, key):
                return (0, 0, 0), (10, 11.0, 0)

        fill = walls_hd.SpriteFill({(2, 2)}, {(2, 2): 100, (3, 2): 100}, Tiles(), lambda m: ((0, 0, 0), (1, 1.0, 1)))
        text, st = walls_hd.build_scene({(2, 2): k_wall, (3, 2): k_wall}, lib, "act3_kurast", sprites=fill)
        ents = json.loads(text)["entities"]
        joints = [e for e in ents if e["name"].startswith("mxj")]
        self.assertEqual((st["sprite_cells"], st["joins"], st["joins_own"]), (1, 1, 1))
        t = walls_hd.transform(joints[0])
        self.assertEqual((t["position"]["x"], t["position"]["z"]), (30.0, 18.0))   # between x 2 and 3 on row 2
        self.assertAlmostEqual(t["scale"]["y"], 1.1)
        self.assertEqual(st["joins_left_at"], [])


class ColourTest(unittest.TestCase):
    def atlas(self):
        rng = np.random.default_rng(7)
        a = np.zeros((32, 32, 4), np.uint8)
        a[4:28, 4:28, :3] = rng.integers(20, 120, (24, 24, 3))
        a[4:28, 4:28, 3] = 255
        return a

    def test_full_strength_reaches_the_target(self):
        target = (np.array([150.0, 130.0, 110.0]), np.array([30.0, 25.0, 20.0]))
        out = walls_sprite.match_colour(self.atlas(), target, 1.0)
        m, s, n = walls_sprite.colour_stats(out[out[..., 3] > 0][:, :3])
        np.testing.assert_allclose(m, target[0], atol=1.0)
        np.testing.assert_allclose(s, target[1], atol=1.0)
        self.assertEqual(n, 24 * 24)

    def test_alpha_transparent_pixels_and_determinism(self):
        a = self.atlas()
        target = (np.array([150.0, 130.0, 110.0]), np.array([30.0, 25.0, 20.0]))
        out = walls_sprite.match_colour(a, target)
        np.testing.assert_array_equal(out[..., 3], a[..., 3])
        np.testing.assert_array_equal(out[:4], a[:4])                       # transparent: untouched
        np.testing.assert_array_equal(out, walls_sprite.match_colour(a, target))
        np.testing.assert_array_equal(walls_sprite.match_colour(a, None), a)

    def test_partial_strength_and_spread_clamp(self):
        a = self.atlas()
        ms, ss, _n = walls_sprite.colour_stats(a[a[..., 3] > 0][:, :3])
        target = (ms + 40.0, ss * 10.0)
        out = walls_sprite.match_colour(a, target, 0.5)
        m, s, _n = walls_sprite.colour_stats(out[out[..., 3] > 0][:, :3])
        np.testing.assert_allclose(m, ms + 20.0, atol=1.0)                  # half way
        np.testing.assert_allclose(s, ss * (1 + walls_sprite.SPREAD_RANGE[1]) / 2, rtol=0.03)   # ratio clamped to 2

    def test_pool_equals_the_pixels_put_together(self):
        rng = np.random.default_rng(3)
        x, y = rng.integers(0, 255, (100, 3)), rng.integers(0, 255, (300, 3))
        sx, sy = walls_sprite.colour_stats(x), walls_sprite.colour_stats(y)
        m, s, n = walls_sprite.pool_stats([(sx[0], sx[1], 100), (sy[0], sy[1], 300)])
        mw, sw, _n = walls_sprite.colour_stats(np.vstack([x, y]))
        np.testing.assert_allclose(m, mw)
        np.testing.assert_allclose(s, sw)
        self.assertEqual(n, 400)
        self.assertIsNone(walls_sprite.pool_stats([]))

    def test_neighbours_are_wall_pieces_next_to_sprite_walls(self):
        def ent(model, x, z):
            return {"components": [{"type": "TransformDefinitionComponent", "position": {"x": x, "y": 0, "z": z}},
                                   {"type": "ModelDefinitionComponent", "filename": model}]}
        sprite = walls_sprite.model_path("m", (2, 1, 0))
        wall, far, prop = "data/hd/env/model/a/wall01.model", "data/hd/env/model/a/wall02.model", "data/hd/env/model/a/barrel.model"
        near = walls_hd.sprite_neighbours([ent(sprite, 50, 50), ent(wall, 61, 45), ent(wall, 41, 59), ent(far, 80, 50),
                                           ent(prop, 52, 52)])
        self.assertEqual(dict(near), {wall: 2})


if __name__ == "__main__":
    unittest.main()
