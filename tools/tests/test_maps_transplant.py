"""maps_transplant: copied regions, entity moves, composition and the walkable-area check (no game data needed)."""
import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import projtemp  # noqa: E402,F401

import maps_transplant as mt  # noqa: E402


def wall(n):
    return ((("set", 1, n, 0),), (("set", 0, 0, 0),))


def floor(n=0):
    return ((), (("set", 0, n, 0),))


def entity(i, x, z, y=0.0, model="data/hd/env/model/a.model", extra=()):
    return {"type": "Entity", "name": "e%d" % i, "id": i, "components": [
        {"type": "TransformDefinitionComponent", "position": {"x": x, "y": y, "z": z},
         "orientation": {"x": 0.0, "y": 0.0, "z": 0.0, "w": 1.0}, "scale": {"x": 1.0, "y": 1.0, "z": 1.0}},
        {"type": "ModelDefinitionComponent", "filename": model}] + list(extra)}


def position(e):
    p = e["components"][0]["position"]
    return p["x"], p["y"], p["z"]


class RegionTest(unittest.TestCase):
    def setUp(self):
        # a D2R map of 6 x 4 with a wall ring of distinct tiles, and a second map that shares nothing
        self.stock = {"a/ring": {(x, y): (wall(x * 10 + y) if x in (0, 5) or y in (0, 3) else floor()) for x in range(6) for y in range(4)},
                      "a/other": {(x, y): wall(900 + x) for x in range(4) for y in range(2)}}

    def test_copy_at_an_offset_is_one_region(self):
        cells = {(x + 7, y + 2): s for (x, y), s in self.stock["a/ring"].items()}
        cells[(0, 0)] = wall(555)                                    # a cell D2R does not have
        regions = mt.find_regions(cells, self.stock)
        self.assertEqual(len(regions), 1)
        r = regions[0]
        self.assertEqual((r.stock, r.dx, r.dy, len(r.cells), r.walls), ("a/ring", -7, -2, 24, 16))
        self.assertIsNone(mt.whole_source(cells, regions))           # an offset, and a wall cell outside

    def test_whole_map_at_offset_zero(self):
        cells = dict(self.stock["a/ring"])
        regions = mt.find_regions(cells, self.stock)
        self.assertEqual(mt.whole_source(cells, regions), "a/ring")
        cov = mt.coverage(cells, regions)
        self.assertEqual((cov["walls_in"], cov["wall_cells"], cov["whole"]), (16, 16, "a/ring"))

    def test_changed_cells_split_and_stay_out(self):
        cells = dict(self.stock["a/ring"])
        for y in range(4):
            cells[(3, y)] = wall(700 + y)                            # a column the mapper redrew
        regions = mt.find_regions(cells, self.stock, small=(2, 2))
        covered = set().union(*(r.cells for r in regions))
        self.assertFalse(covered & {(3, y) for y in range(4)})
        self.assertEqual(len(covered), 20)
        self.assertIsNone(mt.whole_source(cells, regions))

    def test_layout_matches_walls_over_other_floors(self):
        cells = {xy: (sig[0], (("mine", 0, 7, 0),)) for xy, sig in self.stock["a/ring"].items()}    # the mapper's own floors
        self.assertEqual(mt.find_regions(cells, self.stock), [])
        regions = mt.find_regions(mt.layout(cells), {k: mt.layout(v) for k, v in self.stock.items()})
        self.assertEqual([(r.stock, r.dx, r.dy, len(r.cells), r.walls) for r in regions], [("a/ring", 0, 0, 24, 16)])

    def test_hand_built_map_has_no_region(self):
        cells = {(x, y): wall(5000 + x + 100 * y) for x in range(8) for y in range(8)}
        self.assertEqual(mt.find_regions(cells, self.stock), [])


class MoveTest(unittest.TestCase):
    def test_position_ids_targets_and_wall_coords(self):
        e = entity(11, 34.0, 12.0, 2.0, extra=[
            {"type": "FadeTargetComponent", "targetId": "12"},
            {"type": "WallTransparencyComponent", "wallTileLocalCoord": {"x": 3, "y": 1}},
            {"type": "VisualDataBoxDefinitionComponent", "targetId": "777"}])
        out = mt.move(e, "r0", 2, -1, drop=2.0, ids={"11", "12"})
        self.assertEqual(position(out), (12.0, 0.0, 20.0))
        self.assertEqual(out["id"], mt.new_id("r0", 11))
        self.assertEqual(out["components"][2]["targetId"], str(mt.new_id("r0", "12")))
        self.assertEqual(out["components"][3]["wallTileLocalCoord"], {"x": 1, "y": 2})
        self.assertEqual(out["components"][4]["targetId"], "777")     # not an entity of the scene: left alone
        self.assertEqual(position(e), (34.0, 2.0, 12.0))              # the source is not touched

    def test_no_wall_tile_stays_none(self):
        e = entity(1, 0.0, 0.0, extra=[{"type": "WallTransparencyComponent", "wallTileLocalCoord": {"x": -1, "y": -1}}])
        self.assertEqual(mt.move(e, "r", 5, 5)["components"][2]["wallTileLocalCoord"], {"x": -1, "y": -1})


class ComposeTest(unittest.TestCase):
    def setUp(self):
        self.region = mt.Region("a/src", 10, 0, {(x, y) for x in range(3) for y in range(3)}, 9)
        self.cells = {xy: wall(1) for xy in self.region.cells}
        self.cells.update({(5, 5): wall(2), (6, 5): wall(3)})
        self.src = {"dependencies": {"models": [{"path": "data/hd/env/model/a.model"}, {"path": "data/hd/env/model/b.model"}]},
                    "entities": [entity(1, 105.0, 5.0), entity(2, 125.0, 25.0, model="data/hd/env/model/b.model"),
                                 entity(3, 135.0, 5.0),               # one cell past the region, no tiles there: taken
                                 entity(4, 165.0, 5.0),               # far outside
                                 {"type": "Entity", "name": "terrain", "id": 9, "components": [{"type": "TerrainDefinitionComponent"}]}]}
        self.fallback = {"dependencies": {"models": [{"path": "data/hd/env/model/a.model"}, {"path": "data/hd/env/model/c.model"}]},
                         "biomeFilename": "data/hd/env/biome/x.json", "terrain": {},
                         "entities": [entity(1, 15.0, 15.0, model="data/hd/env/model/c.model"),     # inside the region: dropped
                                      entity(2, 55.0, 55.0, model="data/hd/env/model/c.model")]}

    def test_transplant_takes_the_region_and_its_border(self):
        got = mt.transplant(self.region, self.src, "r0", here=self.cells, there={})
        self.assertEqual(sorted(position(e)[0] for e in got), [5.0, 25.0, 35.0])

    def test_border_entity_on_another_cell_of_the_map_stays_out(self):
        cells = dict(self.cells)
        cells[(3, 0)] = wall(8)
        got = mt.transplant(self.region, self.src, "r0", here=cells, there={})
        self.assertEqual(sorted(position(e)[0] for e in got), [5.0, 25.0])

    def test_compose(self):
        scene, stats = mt.compose(self.cells, [self.region], self.fallback, lambda key: self.src)
        self.assertEqual(stats["fallback_entities"], 1)
        self.assertEqual(len(scene["entities"]), 4)
        self.assertEqual(len({e["id"] for e in scene["entities"]}), 4)
        self.assertEqual([m["path"][-7:] for m in scene["dependencies"]["models"]], ["a.model", "c.model", "b.model"])
        self.assertEqual(scene["biomeFilename"], "data/hd/env/biome/x.json")
        self.assertEqual(len(self.fallback["entities"]), 2)

    def test_region_that_is_most_of_its_map_takes_the_terrain_along(self):
        src = dict(self.src)
        src["terrain"] = {"type": "Entity", "name": "terrain", "id": 9, "components": [
            {"type": "TransformDefinitionComponent", "position": {"x": 0.0, "y": 0.0, "z": 0.0}},
            {"type": "TerrainDefinitionComponent"},
            {"type": "ModelDefinitionComponent", "filename": "data/hd/env/preset/a/src/terrain.model"},
            {"type": "PhysicsBodyDefinitionComponent", "filter": "floor"}]}
        there = {(x + 10, y): 1 for x in range(3) for y in range(4)}          # the region is 9 of the D2R map's 12 cells
        scene, stats = mt.compose(self.cells, [self.region], self.fallback, lambda key: src, stock_cells={"a/src": there})
        piece = [e for e in scene["entities"] if e["name"].startswith("ground_")]
        self.assertEqual(len(piece), 1)
        self.assertEqual([c["type"][:7] for c in piece[0]["components"]], ["Transfo", "ModelDe", "Physics"])
        self.assertEqual(position(piece[0]), (-100.0, round(mt.PIECE_LIFT + 0.01, 4), 0.0))
        self.assertTrue(stats["regions"][0]["terrain"])
        self.assertTrue(mt.is_terrain(piece[0]))
        self.assertEqual(src["terrain"]["name"], "terrain")
        class Pit:
            def height(self, x, z):
                return -5.0 if z > 30 else 0.0

        cells = dict(self.cells)
        cells[(1, 3)] = wall(77)                                              # the mapper redrew a cell of D2R's pit
        scene, stats = mt.compose(cells, [self.region], self.fallback, lambda key: src, lambda key, sc: Pit(), {"a/src": there})
        self.assertFalse(stats["regions"][0]["terrain"])
        far = {(x + 10, y): 1 for x in range(3) for y in range(9)}            # 9 of 27 cells: no terrain piece
        scene, stats = mt.compose(self.cells, [self.region], self.fallback, lambda key: src, stock_cells={"a/src": far})
        self.assertFalse(any(e["name"].startswith("ground_") for e in scene["entities"]))

    def test_flat_takes_the_terrain_height_out(self):
        class Hill:
            def height(self, x, z):
                return 4.0

        src = {"entities": [entity(1, 109.0, 9.0, 4.0)]}             # on ground 4 high over cell (10, 0)
        got = mt.transplant(self.region, src, "r0", Hill(), self.cells, {})
        self.assertEqual(position(got[0]), (5.0, 0.0, 5.0))
        kept = mt.transplant(self.region, src, "r0", Hill(), self.cells, {}, flat=False)
        self.assertEqual(position(kept[0]), (9.0, 4.0, 9.0))


class WalkTest(unittest.TestCase):
    class Tile:
        def __init__(self, key, blocked):
            self.key = key
            self.meta = bytes(40) + bytes(1 if n in blocked else 0 for n in range(25)) + bytes(1)

    class Ds:
        width, height = 2, 1

        def floor_layers(self):
            return [[1, 1]]

        def wall_layers(self):
            return [([0, 2], [0, 3])]

    def setUp(self):
        self.box = lambda model: ((-1.0, 0.0, -5.0), (1.0, 8.0, 5.0))    # a wall 2 thick, 10 long, 8 high
        self.table = {(0, 0, 0): self.Tile((0, 0, 0), ()), (3, 0, 0): self.Tile((3, 0, 0), {n for n in range(25) if n % 5 == 2})}
        self._key = mt.ds1_remap.cell_key
        mt.ds1_remap.cell_key = lambda c: (0, 0)

    def tearDown(self):
        mt.ds1_remap.cell_key = self._key

    def test_wall_on_its_blocked_column(self):
        res = mt.walk_check(self.Ds(), self.table, [entity(1, 15.0, 5.0)], flip=0, box_of=self.box)
        self.assertEqual((res["walkable"], res["blocked_on_walls"]), (45, 5))
        self.assertEqual((res["walk_through"], res["unseen"]), (0, 0))

    def test_wall_on_the_walkable_tile(self):
        res = mt.walk_check(self.Ds(), self.table, [entity(1, 5.0, 5.0)], flip=0, box_of=self.box)
        self.assertEqual(res["walk_through"], 5)

    def test_no_model_for_a_blocked_tile(self):
        res = mt.walk_check(self.Ds(), self.table, [], flip=0, box_of=self.box)
        self.assertEqual((res["unseen"], res["unseen_share"]), (5, 1.0))

    def test_low_and_overhead_pieces_do_not_block(self):
        low = lambda model: ((-1.0, 0.0, -5.0), (1.0, 2.0, 5.0))
        res = mt.walk_check(self.Ds(), self.table, [entity(1, 5.0, 5.0)], flip=0, box_of=low)
        self.assertEqual(res["walk_through"], 0)
        res = mt.walk_check(self.Ds(), self.table, [entity(1, 5.0, 5.0, y=6.0)], flip=0, box_of=self.box)
        self.assertEqual(res["walk_through"], 0)


if __name__ == "__main__":
    unittest.main()
