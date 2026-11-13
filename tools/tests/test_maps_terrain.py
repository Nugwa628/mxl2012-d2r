"""maps_terrain: lifted ground, steps, the floor body file, the terrain entity and the pieces raised onto it; the model
writer against one of D2R's terrain models when the game data is there."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import projtemp  # noqa: E402,F401

import maps_terrain as mt  # noqa: E402


def screen(p):
    """Where the camera shows a world point: its ground point in tile space."""
    return (round(p[0] - mt.SLIDE * p[1], 6), round(p[2] - mt.SLIDE * p[1], 6))


class LiftTest(unittest.TestCase):
    def test_lifted_ground_stays_over_its_tile(self):
        pos, tris = mt.lift_quads([mt.rect(10, 20, 20, 30, 5.0), mt.rect(20, 20, 30, 30, 5.0, 0.0, 0.0, 5.0)])
        self.assertEqual(len(pos), 6)                                   # the shared edge's corners once
        self.assertEqual(len(tris), 4)
        self.assertEqual(sorted({screen(p) for p in pos}), [(10, 20), (10, 30), (20, 20), (20, 30), (30, 20), (30, 30)])
        self.assertIn((10 + 5 * mt.SLIDE, 5.0, 20 + 5 * mt.SLIDE), pos)
        self.assertAlmostEqual(mt.STEP, 4.899, places=3)                # D2R's terrace step slides its tiles by 6
        for t in tris:
            self.assertGreater(mt.normal(*(pos[i] for i in t))[1], 0)   # every face turned up

    def test_stair_covers_its_run_with_treads_and_risers(self):
        q = mt.stair(0, 0, 10, 40, 8.0, 0.0, 4)
        self.assertEqual(len(q), 8)
        edges = [(a[0][1], a[2][1]) for a in q]                         # each quad's z range in tile space
        self.assertAlmostEqual(edges[0][1], 10 - 2 * mt.SLIDE)          # tread: run 10 less what the riser of 2 takes
        self.assertEqual((edges[0][0], edges[1][1]), (0, 10.0))
        self.assertEqual([e[0] for e in edges[1:]], [e[1] for e in edges[:-1]])   # no gap on the screen
        self.assertEqual(edges[-1][1], 40)
        pos, tris, normals = mt.split_faces(*mt.lift_quads(q), crease=0.9)
        kinds = {(round(n[0], 3), round(n[1], 3), round(n[2], 3)) for n in normals}
        self.assertEqual(kinds, {(0.0, 1.0, 0.0), (0.0, 0.0, 1.0)})     # flat treads, risers facing the camera's side
        self.assertEqual(mt.stair_height(1, 0, 40, 8.0, 0.0, 4), 8.0)
        self.assertEqual(mt.stair_height(39, 0, 40, 8.0, 0.0, 4), 2.0)

    def test_stair_along_x_and_too_steep(self):
        q = mt.stair(0, 0, 20, 10, 4.0, 0.0, 2, axis="x")
        pos, tris, normals = mt.split_faces(*mt.lift_quads(q), crease=0.9)
        self.assertIn((1.0, 0.0, 0.0), {tuple(round(v, 3) for v in n) for n in normals})
        with self.assertRaises(ValueError):
            mt.stair(0, 0, 10, 10, 9.0, 0.0, 2)

    def test_donor_is_the_smallest_that_fits(self):
        self.assertTrue(mt.donor(4, 2).endswith("mephswarpu/terrain.model"))
        self.assertTrue(mt.donor(5, 2).endswith("travn/terrain.model"))
        self.assertTrue(mt.donor(100, 124).endswith("travs/terrain.model"))
        with self.assertRaises(ValueError):
            mt.donor(30000, 10)
        self.assertEqual(mt.lod0("a/b/terrain.model"), "a/b/terrain_lod0.model")


class PhysicsTest(unittest.TestCase):
    def test_round_trip(self):
        quads = [mt.rect(x * 10, z * 10, x * 10 + 10, z * 10 + 10, 3.0) for x in range(6) for z in range(5)]
        pos, tris = mt.lift_quads(quads)
        got = mt.read_physics(mt.physics(pos, tris))
        self.assertEqual(len(got["pos"]), len(pos))
        self.assertEqual(len(got["tris"]), len(tris))
        for a, b in zip(got["pos"], pos):
            for u, v in zip(a, b):
                self.assertAlmostEqual(u, v, places=3)
        self.assertAlmostEqual(got["area"], 3000.0, delta=1.0)


class SceneTest(unittest.TestCase):
    def piece(self, name, x, z, y=0.0):
        return {"type": "Entity", "name": name, "components": [
            {"type": "TransformDefinitionComponent", "position": {"x": x, "y": y, "z": z}},
            {"type": "ModelDefinitionComponent", "filename": "data/hd/env/model/%s.model" % name}]}

    def test_entity_and_dependencies(self):
        e = mt.entity("mxl_t", 1, mt.MODEL_PATH % "t", mt.PHYSICS_PATH % "t", shadows=False)
        kinds = [c["type"] for c in e["components"]]
        self.assertIn("ModelDefinitionComponent", kinds)
        self.assertNotIn("TerrainDefinitionComponent", kinds)
        model = next(c for c in e["components"] if c["type"] == "ModelDefinitionComponent")
        self.assertEqual(model["shadowMask"], 0)
        scene = {"entities": [self.piece("wall", 1, 2)], "dependencies": {"models": [], "physics": []}}
        got = mt.add_entities(scene, [e])
        self.assertEqual(len(got["entities"]), 2)
        self.assertEqual(len(scene["entities"]), 1)                     # the scene given is left as it was
        self.assertIn({"path": mt.MODEL_PATH % "t"}, got["dependencies"]["models"])
        self.assertIn({"path": mt.PHYSICS_PATH % "t"}, got["dependencies"]["physics"])

    def test_raise_entities(self):
        ents = [self.piece("wall", 100, 50, 2.0), self.piece("low", 300, 50), self.piece("stairs_a01", 100, 60),
                {"type": "Entity", "name": "bare", "components": []}]
        got, moved = mt.raise_entities(ents, lambda x, z: 7.0 if x < 200 else 0.0,
                                       drop=lambda e: e["name"].startswith("stairs_"))
        self.assertEqual((len(got), moved), (3, 1))
        self.assertEqual(got[0]["components"][0]["position"],
                         {"x": round(100 + 7 * mt.SLIDE, 4), "y": 9.0, "z": round(50 + 7 * mt.SLIDE, 4)})
        self.assertEqual(ents[0]["components"][0]["position"], {"x": 100, "y": 2.0, "z": 50})
        self.assertIs(got[1], ents[1])


class ModelTest(unittest.TestCase):
    def test_model_from_a_d2r_template(self):
        import walls_hd
        path = mt.donor(60, 60)
        try:
            template = walls_hd.d2r_bytes(mt.lod0(path))
        except Exception as e:                                          # no game data on this machine
            self.skipTest("no D2R data: %s" % e)
        pos, tris, normals = mt.split_faces(*mt.lift_quads(mt.stair(100, 200, 120, 240, 8.0, 0.0, 4)), crease=0.9)
        data, lo, hi = mt.model(template, pos, tris, normals)
        self.assertEqual(mt.counts(data), mt.counts(template))          # the index entry copied from the donor holds
        got, got_tris = mt.read_model(data)
        self.assertEqual(len(got_tris), len(tris))
        for k in range(3):
            self.assertAlmostEqual(lo[k], min(p[k] for p in pos), delta=0.5)
            self.assertAlmostEqual(hi[k], max(p[k] for p in pos), delta=0.5)
        used = {i for t in got_tris for i in t}
        for i in used:
            self.assertLess(min(sum((a - b) ** 2 for a, b in zip(got[i], p)) for p in pos), 0.01)


if __name__ == "__main__":
    unittest.main()
