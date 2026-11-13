"""maps_flat: the wall / flat rule, the verdict file, the flat scene and the painted pieces (no game data)."""
import copy
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import projtemp  # noqa: E402,F401

import maps_flat as mfl  # noqa: E402

WALL, KERB, STAIR, PLAIN, VOID = (1, 24, 0), (1, 31, 0), (0, 31, 12), (0, 1, 8), (0, 4, 18)
VERDICT = {WALL: ("wall", "none"), KERB: ("flat", "art"), STAIR: ("flat", "art"), PLAIN: ("flat", "biome"), VOID: ("flat", "void")}


def ent(name, x, z, kinds=("ModelDefinitionComponent",), y=0.0, **extra):
    comps = [{"type": "TransformDefinitionComponent", "position": {"x": x, "y": y, "z": z}}]
    for k in kinds:
        c = {"type": k}
        if k == "ModelDefinitionComponent":
            c["filename"] = "data/hd/env/model/%s.model" % name
        if k == "PhysicsBodyDefinitionComponent":
            c["fixturedefs"] = [{"shapetype": {"filename": "data/hd/env/model/%s.physics" % name}}]
        c.update(extra)
        comps.append(c)
    return {"type": "Entity", "name": name, "id": 1, "components": comps}


class RuleTest(unittest.TestCase):
    def test_floors(self):
        self.assertEqual(mfl.rule(0, "act3/docktown", 4, 40, 25, void=True)[:2], ("flat", "void"))
        self.assertEqual(mfl.rule(0, "act3/kurast", 31, 40, 0)[:2], ("flat", "biome"))   # terrace paving: HD street paving
        self.assertEqual(mfl.rule(0, "act3/kurast", 31, 40, 15)[:2], ("flat", "art"))    # blocks sub-tiles: the picture shows it
        self.assertEqual(mfl.rule(0, "act2/tomb", 8, 40, 25)[:2], ("flat", "art"))
        self.assertEqual(mfl.rule(0, "act4/fort", 1, 40, 0)[:2], ("flat", "biome"))

    def test_cave_rock_floors_stand(self):
        self.assertEqual(mfl.rule(0, "act1/caves", 0, 40, 15)[:2], ("wall", "biome"))           # rock wall in the floor tile
        self.assertEqual(mfl.rule(0, "act1/caves", 0, 40, 25, void=True)[:2], ("wall", "void"))  # black rock: black, walls on it
        self.assertEqual(mfl.rule(0, "act1/caves", 5, 40, 0)[:2], ("flat", "biome"))            # open cave floor
        self.assertEqual(mfl.rule(0, "act2/tomb", 8, 40, 15)[:2], ("flat", "biome"))            # other sets unchanged

    def test_uprights_by_height(self):
        self.assertEqual(mfl.rule(1, "act3/kurast", 24, 161, 5)[0], "wall")
        self.assertEqual(mfl.rule(2, "act3/kurast", 31, 51, 5)[:2], ("flat", "art"))
        self.assertEqual(mfl.rule(1, "act2/tomb", 16, 77, 0)[0], "unsure")
        self.assertEqual(mfl.rule(7, "x", 0, mfl.RISE_WALL, 1)[0], "wall")
        self.assertEqual(mfl.rule(7, "x", 0, mfl.RISE_UNSURE - 1, 1)[0], "flat")

    def test_low_band_by_blocking(self):
        self.assertEqual(mfl.rule(2, "act3/docktown", 4, 115, 5)[:2], ("wall", "none"))    # ruined wall
        self.assertEqual(mfl.rule(2, "act1/graveyard", 10, 106, 2)[0], "wall")             # graveyard fence
        self.assertEqual(mfl.rule(1, "act2/tomb", 16, 83, 0)[:2], ("unsure", "art"))       # railing: blocks nothing
        self.assertEqual(mfl.rule(14, "act3/jungle", 0, 90, 13)[0], "wall")                # fern that blocks
        self.assertEqual(mfl.rule(12, "act3/docktown", 4, 90, 0)[:2], ("flat", "art"))     # prop that blocks nothing
        self.assertEqual(mfl.rule(14, "act3/jungle", 0, 172, 0)[0], "wall")                # tree crown
        self.assertEqual(mfl.rule(1, "x", 0, mfl.RISE_UNSURE - 1, 25)[0], "flat")

    def test_step_set_uprights_are_flat(self):
        self.assertEqual(mfl.rule(6, "act3/kurast", 30, 85, 5)[:2], ("flat", "art"))
        self.assertEqual(mfl.rule(7, "act3/kurast", 30, 91, 1)[:2], ("flat", "art"))
        self.assertEqual(mfl.rule(1, "act3/kurast", 29, 85, 5)[0], "wall")

    def test_wall_piece_without_a_tile_is_not_painted(self):
        self.assertEqual(mfl.rule(1, "", 30, 0, 0)[:2], ("flat", "none"))

    def test_other_orientations(self):
        self.assertEqual(mfl.rule(15, "act4/fort", 2, 0, 0, roof=240)[0], "wall")
        self.assertEqual(mfl.rule(16, "act2/arcane", 0, 2, 0)[:2], ("flat", "none"))
        self.assertEqual(mfl.rule(11, "act2/tomb", 0, 203, 5)[:2], ("flat", "art"))       # doorway: painted
        self.assertEqual(mfl.rule(10, "", 33, 0, 0)[:2], ("unsure", "none"))
        self.assertEqual(mfl.rule(13, "x", 0, 0, 0)[:2], ("flat", "none"))

    def test_rise(self):
        self.assertEqual(mfl.rise([(0, -201, 1), (100, -30, 1)], 1), 161)
        self.assertEqual(mfl.rise([(0, 0, 1), (80, 79, 1)], 0), 40)
        self.assertEqual(mfl.rise([], 1), 0)


class TableTest(unittest.TestCase):
    def test_round_trip_and_unsure_is_flat(self):
        rows = {}
        for key, (v, p) in (((1, 24, 0), ("wall", "none")), ((1, 16, 0), ("unsure", "art"))):
            rows[("m",) + key] = {"map": "m", "orientation": key[0], "main": key[1], "sub": key[2], "folder": "f", "cells": 3,
                                  "rise_px": 1, "blocked": 0, "verdict": v, "paint": p, "reason": "r"}
        with tempfile.TemporaryDirectory() as d:
            path = Path(d) / "t.tsv"
            mfl.save_table(rows, path)
            back = mfl.load_table(path)
            self.assertEqual(set(back), set(rows))
            self.assertEqual(mfl.verdicts(back, "m"), {(1, 24, 0): ("wall", "none"), (1, 16, 0): ("flat", "art")})
            self.assertEqual(mfl.verdicts(back, "other"), {})
            path.write_text(path.read_text(encoding="utf-8").replace("\twall\t", "\ttall\t"), encoding="utf-8")
            with self.assertRaises(ValueError):
                mfl.load_table(path)

    def test_shipped_table_is_well_formed(self):
        table = mfl.load_table()
        self.assertTrue(table)
        for k, r in table.items():
            self.assertIn(r["verdict"], mfl.VERDICTS, k)
            self.assertIn(r["paint"], mfl.PAINTS, k)
            if r["verdict"] == "wall":
                self.assertIn(r["paint"], ("biome", "void") if k[1] == 0 else ("none",), k)


class SceneTest(unittest.TestCase):
    # cells: (0, 0) wall, (1, 0) kerb on a stair floor, (2, 0) plain floor, (3..5, 0) and (3..5, 1) void
    PLACES = [(0, 0, "wall", 0, WALL), (0, 0, "floor", 0, PLAIN), (1, 0, "wall", 0, KERB), (1, 0, "floor", 0, STAIR),
              (2, 0, "floor", 0, PLAIN)] + [(x, y, "floor", 0, VOID) for x in (3, 4, 5) for y in (0, 1)]
    VOIDS = {(x, y) for x in (3, 4, 5) for y in (0, 1)}

    def scene(self):
        return {"entities": [
            ent("wallpiece", 5.0, 5.0, ("ModelDefinitionComponent", "PhysicsBodyDefinitionComponent")),
            ent("edgepiece", 10.0, 5.0),                                                   # pivot on the wall cell's edge
            ent("bench", 15.0, 5.0, ("ModelDefinitionComponent", "PhysicsBodyDefinitionComponent")),
            ent("stairslab", 25.0, 5.0),
            ent("voidcliff", 45.0, 5.0),
            ent("decal", 25.0, 5.0, ("TerrainDecalDefinitionComponent",)),
            ent("voiddecal", 45.0, 15.0, ("TerrainDecalDefinitionComponent",)),
            ent("fog", 25.0, 5.0, ("VfxDefinitionComponent",), filename="data/hd/vfx/FX_Fog_20x20.particles"),
            ent("wallfog", 5.0, 5.0, ("VfxDefinitionComponent",), filename="data/hd/vfx/FX_FlatFog_30x30.particles"),
            ent("leaves", 25.0, 5.0, ("VfxDefinitionComponent",), filename="data/hd/vfx/FX_Leaves_30x30.particles"),
            ent("candle", 25.0, 5.0, ("VfxDefinitionComponent",), filename="data/hd/vfx/vfx_candle_light.particles"),
            ent("prefab", 25.0, 5.0, ("PrefabPlacementDefinitionComponent",)),
        ], "dependencies": {"models": [{"path": "data/hd/env/model/%s.model" % n} for n in ("wallpiece", "bench", "stairslab")],
                            "physics": [{"path": "data/hd/env/model/%s.physics" % n} for n in ("wallpiece", "bench")]},
            "perTileBiomeOverrides": [{"tileX": 2, "tileY": 0, "biomeFilename": "data/hd/env/biome/act3_travincal_outdoors.json"},
                                      {"tileX": 4, "tileY": 1, "biomeFilename": "data/hd/env/biome/act4_fort.json"}]}

    def flat(self):
        return mfl.flatten(self.scene(), self.PLACES, VERDICT, self.VOIDS, "m", VOID)

    def test_only_walls_stand(self):
        out, stats, _m = self.flat()
        names = {e["name"] for e in out["entities"]}
        self.assertTrue({"wallpiece", "edgepiece", "decal", "leaves"} <= names)
        self.assertFalse({"bench", "stairslab", "voidcliff", "voiddecal", "candle", "prefab", "fog", "wallfog"} & names)
        self.assertEqual(stats["wall_cells"], 1)
        walls = {(0, 0)}
        for c in mfl.solid_cells(out["entities"]):
            self.assertTrue(mfl.cells_near(c[0] * 10 + 5, c[1] * 10 + 5, 10) & walls, c)

    def test_no_geometry_above_the_floor_except_walls(self):
        out, _, models = self.flat()
        for e in out["entities"]:
            if mfl.is_painted(e):
                self.assertEqual(mfl.position(e)[1], 0.0)
        self.assertTrue(all(mfl.is_painted(e) for e in out["entities"] if e["name"].startswith("mxp_")))
        rects = {k: (0, -91, 92, -34) if k[0] else (0, 0, 160, 79) for k in (KERB, STAIR)}
        uvs = {k: (0, 0, 1, 1) for k in rects}
        for spec in models.values():
            verts, _t = mfl.chunk_mesh(spec, rects, uvs)
            self.assertTrue(all(0.0 < v[0][1] <= mfl.PAINT_MAX for v in verts))

    def test_walls_hd_props_are_not_painted(self):
        prop = {"name": "mxp_58_55_0", "components": [{"type": "TransformDefinitionComponent", "position": {"x": 585, "y": 0.9, "z": 555}},
                                                     {"type": "ModelDefinitionComponent", "filename": "x.model"}]}
        self.assertFalse(mfl.is_painted(prop))
        self.assertEqual(mfl.solid_cells([prop]), {(58, 55)})

    def test_painted_floor_and_void(self):
        out, stats, models = self.flat()
        quads = [q for s in models.values() if s["kind"] == "art" for q in s["quads"]]
        self.assertEqual([(q[0], q[1], q[2]) for q in quads], [(STAIR, 1, 0), (KERB, 1, 0)])   # stair art, then the kerb
        self.assertEqual(stats["art_pictures"], 2)
        rects = [r for s in models.values() if s["kind"] == "void" for r in s["rects"]]
        covered = [(x + i, y + j) for x, y, w, h in rects for i in range(w) for j in range(h)]
        self.assertEqual(sorted(covered), sorted(self.VOIDS))          # exactly the void, nothing placed over walkable cells
        self.assertEqual([o["tileX"] for o in out["perTileBiomeOverrides"]], [2])

    def test_biome_swap(self):
        out, stats, _m = self.flat()
        self.assertEqual(out["perTileBiomeOverrides"][0]["biomeFilename"], "data/hd/env/biome/act3_kurast.json")
        self.assertEqual(stats["biome_swapped"], 1)
        self.assertIn({"path": "data/hd/env/biome/act3_kurast.json"}, out["dependencies"]["json"])

    def test_dependencies_and_inputs(self):
        scene = self.scene()
        before = copy.deepcopy(scene)
        out, _, models = mfl.flatten(scene, self.PLACES, VERDICT, self.VOIDS, "m", VOID)
        self.assertEqual(scene, before)                                # the converted scene is not changed
        deps = [d["path"] for d in out["dependencies"]["models"]]
        self.assertIn("data/hd/env/model/wallpiece.model", deps)
        self.assertNotIn("data/hd/env/model/bench.model", deps)
        self.assertTrue(set(models) <= set(deps))
        self.assertEqual(out["dependencies"]["physics"], [{"path": "data/hd/env/model/wallpiece.physics"}])
        used = {c.get("filename") for e in out["entities"] for c in e["components"]}
        self.assertEqual(set(models), {m for m in used if m and "/mxl/flat/" in m})   # one entity per painted model

    def test_physics_only_on_walls(self):
        out, _, _m = self.flat()
        bodies = [e for e in out["entities"] if "PhysicsBodyDefinitionComponent" in mfl.types_of(e)]
        self.assertEqual([e["name"] for e in bodies], ["wallpiece"])   # units stand on the ground plane off the walls


class WallSpriteTest(unittest.TestCase):
    def test_upright_sprite_of_a_flat_kind_is_dropped(self):
        kerb = ent("mxl/wallsprite/cypherpunk/wall_1_31_0", 0.5 * mfl.TILE, 0.5 * mfl.TILE)
        wall = ent("mxl/wallsprite/cypherpunk/wall_1_24_0", 0.5 * mfl.TILE, 0.5 * mfl.TILE)
        other = ent("act3/kurast/barrel", 0.5 * mfl.TILE, 0.5 * mfl.TILE)
        flat = frozenset({KERB})
        self.assertTrue(mfl.flat_sprite(kerb, flat))
        self.assertFalse(mfl.flat_sprite(wall, flat))
        self.assertFalse(mfl.flat_sprite(other, flat))
        walls = {(0, 0)}
        self.assertFalse(mfl.keep(kerb, walls, set(), flat))   # painted on the floor instead, even next to a wall
        self.assertTrue(mfl.keep(wall, walls, set(), flat))
        self.assertTrue(mfl.keep(kerb, walls, set()))           # no flat kinds given: kept as before

    def test_whole_structures(self):
        def piece(name, cx):
            e = ent("act1/monastry/gateway01", cx * mfl.TILE, 0.5 * mfl.TILE)
            e["name"] = name
            return e
        gate = piece("mxs_230", 2.4)          # pivot 1.4 cells off the wall cell (Duncraig's gateways and junctions)
        sprite = piece("mxs_2_0_1", 2.4)      # walls_sprite's per-cell name: not a structure piece
        far = piece("mxs_231", 3.5)
        walls = {(0, 0)}
        self.assertTrue(mfl.structure_piece(gate))
        self.assertFalse(mfl.structure_piece(sprite))
        self.assertFalse(mfl.keep(gate, walls, set()))                            # other maps: one-unit slack as before
        self.assertTrue(mfl.keep(gate, walls, set(), whole_structures=True))
        self.assertFalse(mfl.keep(sprite, walls, set(), whole_structures=True))
        self.assertFalse(mfl.keep(far, walls, set(), whole_structures=True))      # beyond STRUCTURE_REACH
        self.assertIn("epicwhiners", mfl.WHOLE_STRUCTURES)


class VoidAndChunkTest(unittest.TestCase):
    def test_void_cells(self):
        places = [(0, 0, "floor", 0, VOID), (0, 0, "wall", 0, KERB),          # void with a kerb on it: black, kerb painted over
                  (1, 0, "floor", 0, VOID), (1, 0, "wall", 0, WALL),          # a wall stands there: not covered
                  (2, 0, "floor", 0, VOID), (2, 0, "floor", 1, PLAIN),        # ground on another floor layer: not void
                  (3, 0, "floor", 0, VOID)]
        void = mfl.void_cells(places, VERDICT)
        self.assertEqual(void, {(0, 0), (3, 0)})
        self.assertEqual([(q[0], q[1]) for q in mfl.art_pieces(places, VERDICT, void)], [(KERB, 0)])

    def test_chunks_hold_at_most_the_donors_quads(self):
        items = [(x, y) for x in range(20) for y in range(20)]
        groups = mfl.chunked(items, lambda c: c, size=6, most=10)
        self.assertEqual(sorted(i for _b, its in groups for i in its), sorted(items))
        self.assertTrue(all(len(its) <= 10 for _b, its in groups))
        for (bx, by, _r), its in groups:
            self.assertTrue(all(x // 6 == bx and y // 6 == by for x, y in its))

    def test_chunk_art_lands_on_its_classic_pixels(self):
        rect = (0, -91, 92, -34)
        g = mfl.LIFT_WALL + mfl.LIFT_ROW * 30
        spec = {"kind": "art", "origin": (45.0, 45.0), "quads": [(KERB, 13, 17, g)]}
        verts, tris = mfl.chunk_mesh(spec, {KERB: rect}, {KERB: (0, 0, 1, 1)})
        self.assertEqual(len(tris), 2)
        for (x, y, z), _n, _t, (u, v) in verts:     # back to the floor along the camera's axis, then to classic's screen
            fx, fz = x + 45.0 - mfl.SQRT15 * y - 130.0, z + 45.0 - mfl.SQRT15 * y - 170.0
            self.assertAlmostEqual(y, g)
            self.assertAlmostEqual(80 + 8 * (fx - fz), rect[0] + u * (rect[2] - rect[0]), places=6)
            self.assertAlmostEqual(4 * (fx + fz) - mfl.WALL_Y, rect[1] + v * (rect[3] - rect[1]), places=6)

    def test_void_quads_cover_their_cells(self):
        spec = {"kind": "void", "origin": (0.0, 0.0), "rects": [(2, 3, 4, 1)]}
        verts, tris = mfl.chunk_mesh(spec, {}, {})
        xs = [v[0][0] - mfl.SQRT15 * mfl.LIFT_VOID for v in verts]
        zs = [v[0][2] - mfl.SQRT15 * mfl.LIFT_VOID for v in verts]
        e = mfl.VOID_OVERLAP
        self.assertAlmostEqual(min(xs), 20 - e)
        self.assertAlmostEqual(max(xs), 60 + e)
        self.assertAlmostEqual(min(zs), 30 - e)
        self.assertAlmostEqual(max(zs), 40 + e)
        self.assertEqual(len(tris), 2)

    def test_art_atlas_colour_and_scale(self):
        import numpy as np
        pal = np.zeros((256, 4), np.uint8)
        pal[1:, :3], pal[1:, 3] = 40, 255
        tiles = {KERB: [(x, y, 1) for x in range(8) for y in range(4)]}
        rgba, rects, uvs = mfl.art_atlas([KERB], tiles, pal, (np.array([80.0, 80.0, 80.0]), np.array([10.0, 10.0, 10.0])), 2)
        self.assertEqual(rgba.shape[1], 2 * 2048)
        x0, y0 = int(uvs[KERB][0] * rgba.shape[1]), int(uvs[KERB][1] * rgba.shape[0])
        px = rgba[y0 + 2, x0 + 4]
        self.assertEqual(px[3], 255)
        self.assertGreater(int(px[0]), 60)                    # moved most of the way from 40 toward the paving's 80


class GeometryTest(unittest.TestCase):
    def test_floor_point_corners(self):
        self.assertEqual(mfl.floor_point(80, 0), (0.0, 0.0))
        self.assertEqual(mfl.floor_point(160, 40), (10.0, 0.0))
        self.assertEqual(mfl.floor_point(0, 40), (0.0, 10.0))
        self.assertEqual(mfl.floor_point(80, 80), (10.0, 10.0))

    def test_painted_wall_lands_on_its_classic_pixels(self):
        rect = (0, -201, 101, -30)
        verts, tris = mfl.paint_mesh(rect, (0, 0, 1, 1), mfl.WALL_Y)
        self.assertEqual(len(tris), 2)
        for (x, _y, z), _n, _t, (u, v) in verts:     # floor -> screen: px = 80 + 8 (X - Z), py = 4 (X + Z)
            px, py = 80 + 8 * (x - z), 4 * (x + z) - mfl.WALL_Y
            self.assertAlmostEqual(px, rect[0] + u * (rect[2] - rect[0]), places=6)
            self.assertAlmostEqual(py, rect[1] + v * (rect[3] - rect[1]), places=6)

    def test_rectangles_cover_exactly(self):
        cells = {(x, y) for x in range(5) for y in range(3)} | {(7, 7), (8, 7), (7, 8)}
        rects = mfl.rectangles(cells, limit=4)
        got = [(x + i, y + j) for x, y, w, h in rects for i in range(w) for j in range(h)]
        self.assertEqual(len(got), len(set(got)))
        self.assertEqual(set(got), cells)
        self.assertTrue(all(w <= 4 and h <= 4 for _x, _y, w, h in rects))

    def test_lift_keeps_the_pixel(self):
        p = mfl.lifted(30.0, 40.0, 0.2)       # moved along the camera axis (s, 1, s)
        self.assertAlmostEqual((p["x"] - 30.0) / p["y"], mfl.SQRT15)
        self.assertAlmostEqual((p["z"] - 40.0) / p["y"], mfl.SQRT15)


if __name__ == "__main__":
    unittest.main()
