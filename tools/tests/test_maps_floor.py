"""maps_floor: legacy floor colours, the biome D2R paints a tile with, the per-tile paint and the void biome (no game data)."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import projtemp  # noqa: E402,F401

import maps_floor as mf  # noqa: E402

STONE, PAVE, DIRT, BLACK = ("s", 0, 1, 0), ("s", 0, 2, 0), ("s", 0, 3, 0), ("s", 0, 9, 0)
WALL = ("s", 1, 1, 0)


class LearnTest(unittest.TestCase):
    def test_most_common_biome_with_overrides(self):
        stock = {"a/one": {(0, 0): ((), (STONE,)), (1, 0): ((), (STONE,)), (2, 0): ((), (PAVE,))},
                 "a/two": {(0, 0): ((), (STONE,)), (1, 0): ((), (DIRT,))},
                 "a/none": {(0, 0): ((), (STONE,))}}
        scenes = {"a/one": ("town", {(2, 0): "plaza"}), "a/two": ("cave", {}), "a/none": None}
        got = mf.learn(stock, {STONE, PAVE}, scenes.get)
        self.assertEqual(got, {STONE: "town", PAVE: "plaza"})          # DIRT was not asked for

    def test_scene_biomes(self):
        scene = {"biomeFilename": "data/hd/env/biome/Act3_Kurast.json",
                 "perTileBiomeOverrides": [{"tileX": 3, "tileY": 4, "biomeFilename": "data/hd/env/biome/act4_fort.json"}]}
        self.assertEqual(mf.scene_biomes(scene), ("act3_kurast", {(3, 4): "act4_fort"}))


class PaintTest(unittest.TestCase):
    def setUp(self):
        self.cells = {(x, 0): ((), (STONE,)) for x in range(4)}
        self.cells.update({(x, 1): ((), (PAVE,)) for x in range(3)})
        self.cells.update({(0, 2): ((), (DIRT,)), (1, 2): ((), (BLACK,)), (2, 2): ((WALL,), (BLACK,)),
                           (4, 0): ((WALL,), ()), (9, 9): ((WALL,), ())})
        self.colours = {xy: (30, 30, 30) for xy in self.cells if xy[1] == 0}
        self.colours.update({xy: (120, 110, 100) for xy in self.cells if xy[1] == 1})
        self.colours.update({(0, 2): (100, 90, 80), (1, 2): (8, 4, 4), (2, 2): (8, 4, 4)})
        self.learnt = {STONE: "road", PAVE: "walk", DIRT: "mud"}

    def test_black_floor_is_void_and_two_biomes_are_kept(self):
        out, stats = mf.paint(self.cells, self.colours, self.learnt, limit=2)
        self.assertNotIn((1, 2), out)
        self.assertNotIn((2, 2), out)                                  # black under a wall stays void too
        self.assertEqual(out[(0, 0)], "road")
        self.assertEqual(out[(0, 1)], "walk")
        self.assertEqual(out[(0, 2)], "walk")                          # 'mud' is not kept: the light cell joins the light biome
        self.assertEqual(out[(4, 0)], "road")                          # a wall cell without floor takes its neighbour's
        self.assertNotIn((9, 9), out)
        self.assertEqual((stats["void"], stats["other_biome"], stats["under_walls"]), (2, 1, 1))
        self.assertEqual(stats["biomes"], {"road": 5, "walk": 4})

    def test_void_cells_have_no_wall(self):
        self.assertEqual(mf.void_cells(self.cells, self.colours), {(1, 2)})

    def test_overrides_in_the_scene(self):
        scene = {"dependencies": {"json": [{"path": mf.BIOME % "road"}]}, "entities": []}
        got = mf.set_overrides(scene, {(1, 0): "road", (0, 1): "walk", (0, 0): "road"})
        self.assertEqual([(o["tileX"], o["tileY"]) for o in got["perTileBiomeOverrides"]], [(0, 0), (1, 0), (0, 1)])
        self.assertEqual(got["perTileBiomeOverrides"][2]["biomeFilename"], "data/hd/env/biome/walk.json")
        self.assertEqual([d["path"] for d in got["dependencies"]["json"]], [mf.BIOME % "road", mf.BIOME % "walk"])
        self.assertEqual(len(scene["dependencies"]["json"]), 1)          # the source is not touched


class VoidBiomeTest(unittest.TestCase):
    def test_base_layer_of_every_tier(self):
        layer = {"name": "base", "Albedo": "a_alb.texture", "Normal": "a_nrm.texture", "ORM": "a_orm.texture", "NoiseScale": 0.5}
        biome = {"dependencies": {"textures": [{"path": "a_alb.texture"}]}}
        for tier in mf.TIERS:
            biome[tier] = {"terrainLayers": [dict(layer), {"name": "second", "Albedo": "b_alb.texture"}]}
        got = mf.void_biome(biome, "t/dark")
        for tier in mf.TIERS:
            base, second = got[tier]["terrainLayers"]
            self.assertEqual((base["Albedo"], base["Normal"], base["ORM"]), ("t/dark_alb.texture", "t/dark_nrm.texture", "t/dark_orm.texture"))
            self.assertEqual((base["name"], base["NoiseScale"], second["Albedo"]), ("base", 0.5, "b_alb.texture"))
        self.assertEqual(len(got["dependencies"]["textures"]), 4)
        self.assertEqual(biome[mf.TIERS[0]]["terrainLayers"][0]["Albedo"], "a_alb.texture")
        self.assertRaises(ValueError, mf.void_biome, {"terrainDataUltra": {"terrainLayers": []}})


class ColourTest(unittest.TestCase):
    class Ds:
        width, height = 2, 1

        def floor_layers(self):
            return [[1, 2], [0, 3]]

    def setUp(self):
        import dt1_pixels
        self.saved = (mf.walls_hd.floor_index, mf.ds1_remap.cell_key, dt1_pixels.tiles)
        self.dt1 = dt1_pixels
        mf.walls_hd.floor_index = lambda paths, tiles_of: {(0, 1, 0): "a.dt1", (0, 2, 0): "a.dt1", (0, 3, 0): "b.dt1"}
        mf.ds1_remap.cell_key = lambda c: (c, 0)
        dt1_pixels.tiles = lambda data: {(0, 1, 0): [(0, 0, 1), (1, 0, 2), (2, 0, 0)], (0, 2, 0): [(0, 0, 1), (1, 0, 1)],
                                         (0, 3, 0): [(0, 0, 2)]} if data == b"a" else {(0, 3, 0): [(0, 0, 2), (1, 0, 2), (2, 0, 2)]}

    def tearDown(self):
        mf.walls_hd.floor_index, mf.ds1_remap.cell_key, self.dt1.tiles = self.saved

    def test_mean_of_opaque_pixels_and_the_fuller_layer(self):
        palette = [(0, 0, 0), (10, 20, 30), (30, 40, 50)] + [(0, 0, 0)] * 253
        got = mf.tile_colours(self.Ds(), ["a.dt1", "b.dt1"], None, lambda p: p[:1].encode(), palette)
        self.assertEqual(got[(0, 0)], (20.0, 30.0, 40.0))               # index 0 is transparent
        self.assertEqual(got[(1, 0)], (30.0, 40.0, 50.0))               # the upper layer's tile has more pixels
        self.assertAlmostEqual(mf.luma((10, 20, 30)), 18.15)


if __name__ == "__main__":
    unittest.main()
