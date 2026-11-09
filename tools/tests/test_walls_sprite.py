"""Tests of tools/walls_sprite.py: the curtain's geometry against the classic sprite, atlas packing and colour bleed."""
import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import projtemp  # noqa: E402,F401  (temp files stay inside the project, tools/projtemp.py)

import walls_sprite as ws


def screen(p):
    """The classic sprite pixel (diamond frame) a world point of the cell shows: x, y = the tile's own frame + WALL_Y."""
    x, h, z = p
    return ws.KINK + (x - z) * ws.PX_PER_UNIT, (x + z) * ws.PX_PER_UNIT / 2 - h * ws.PX_PER_HEIGHT


class GeometryTest(unittest.TestCase):
    def test_edges(self):
        self.assertEqual(ws.foot(0), 40)
        self.assertEqual(ws.foot(80), 0)
        self.assertEqual(ws.foot(160), 40)
        self.assertEqual(ws.edge_point(0), (0.0, 10.0))
        self.assertEqual(ws.edge_point(80), (0.0, 0.0))
        self.assertEqual(ws.edge_point(160), (10.0, 0.0))

    def test_uv_is_the_sprite_pixel_under_the_vertex(self):
        rect = (0, -156, 160, -36)
        verts, tris = ws.tile_mesh(rect, (0.0, 0.0, 1.0, 1.0))
        self.assertTrue(tris)
        x0, y0, x1, y1 = rect
        for pos, _n, _t, (u, v) in verts:
            sx, sy = screen(pos)
            self.assertAlmostEqual(u, (sx - x0) / (x1 - x0), 5)
            self.assertAlmostEqual(v, (sy - (y0 + ws.WALL_Y)) / (y1 - y0), 5)

    def test_a_kink_only_when_the_sprite_crosses_it(self):
        self.assertEqual(len(ws.tile_mesh((0, -100, 80, -40), (0, 0, 1, 1))[0]), 4)
        self.assertEqual(len(ws.tile_mesh((80, -100, 160, -40), (0, 0, 1, 1))[0]), 4)
        self.assertGreaterEqual(len(ws.tile_mesh((40, -100, 120, -40), (0, 0, 1, 1))[0]), 8)

    def test_floor_light_points_up_and_wall_light_along_the_wall(self):
        self.assertEqual(ws.tile_mesh((0, -100, 80, -40), (0, 0, 1, 1), "floor")[0][0][1], (0.0, 1.0, 0.0))
        self.assertEqual(ws.tile_mesh((0, -100, 80, -40), (0, 0, 1, 1), "wall")[0][0][1], (1.0, 0.0, 0.0))

    def test_winding_along_the_wall(self):
        verts, tris = ws.tile_mesh((0, -100, 80, -40), (0, 0, 1, 1))
        for a, b, c in tris:
            pa, pb, pc = (np.array(verts[i][0]) for i in (a, b, c))
            self.assertGreater(np.dot(np.cross(pb - pa, pc - pa), (1.0, 0.0, 0.0)), 0)

    def test_relief_keeps_the_picture(self):
        rect = (0, -156, 80, -36)
        verts, tris = ws.relief_mesh(rect, (0.0, 0.0, 1.0, 1.0), lambda _x, _y: 1.0, 1.5)
        self.assertTrue(tris)
        x0, y0, x1, y1 = rect
        for pos, _n, _t, (u, v) in verts:
            self.assertGreater(pos[0], 1.4)      # pushed out of the X = 0 wall
            lifted = (pos[0] - 1.5, pos[1] - 1.5, pos[2] - 1.5)
            sx, sy = screen(lifted)
            self.assertAlmostEqual(u, (sx - x0) / (x1 - x0), 4)
            self.assertAlmostEqual(v, (sy - (y0 + ws.WALL_Y)) / (y1 - y0), 4)


class EntityTest(unittest.TestCase):
    def test_layer_moves_along_the_view_line(self):
        t = ws.entity("m.model", 3, 4, 2, 7)["components"][0]["position"]
        self.assertAlmostEqual(t["x"] - 30.0, 2 * ws.LAYER_GAP)
        self.assertAlmostEqual(t["y"], 2 * ws.LAYER_GAP)
        self.assertAlmostEqual(t["z"] - 40.0, 2 * ws.LAYER_GAP)

    def test_no_shadow_by_default(self):
        self.assertEqual(ws.entity("m.model", 0, 0, 0, 0)["components"][1]["shadowMask"], 0)


class AtlasTest(unittest.TestCase):
    def test_pack_keeps_tiles_apart(self):
        sizes = {k: (100 + k * 7, 50 + k * 13) for k in range(40)}
        places, height = ws.pack(sizes, width=600)
        boxes = [(places[k][0], places[k][1], sizes[k][0], sizes[k][1]) for k in sizes]
        for i, (x, y, w, h) in enumerate(boxes):
            self.assertLessEqual(x + w, 600)
            self.assertLessEqual(y + h, height)
            for (x2, y2, w2, h2) in boxes[i + 1:]:
                self.assertFalse(x < x2 + w2 and x2 < x + w and y < y2 + h2 and y2 < y + h)

    def test_bleed_colours_only_transparent_pixels(self):
        a = np.zeros((5, 5, 4), np.uint8)
        a[2, 2] = (200, 100, 50, 255)
        out = ws.bleed(a, 1)
        self.assertEqual(tuple(out[2, 3]), (200, 100, 50, 0))
        self.assertEqual(tuple(out[2, 2]), (200, 100, 50, 255))
        self.assertEqual(tuple(out[0, 0]), (0, 0, 0, 0))


def floor_tile():
    """A classic floor diamond (160 x 79 rows) as palette pixels."""
    return [(x, y, 7) for y in range(79) for x in range(160) if abs(x - 80) / 2 <= min(y, 78 - y) + 1]


def wall_tile(top=-100):
    """A wall sprite from `top` (tile frame) down to the diamond's top corner."""
    return [(x, y, 5) for x in range(60, 100) for y in range(top, 0)]


class FakeDs:
    """wall_layers / floor_layers as walls_sprite reads them; cells {(x, y): dword} per layer."""

    def __init__(self, width, height, walls, floors=()):
        self.width, self.height = width, height
        self.walls, self.floors = walls, floors

    def _layer(self, cells):
        out = [0] * (self.width * self.height)
        for (x, y), c in cells.items():
            out[y * self.width + x] = c
        return out

    def wall_layers(self):
        return [(self._layer({xy: c for xy, (c, _o) in cells.items()}), self._layer({xy: o for xy, (_c, o) in cells.items()}))
                for cells in self.walls]

    def floor_layers(self):
        return [self._layer(cells) for cells in self.floors]


def dword(style, seq):
    return style << 20 | seq << 8


class MapSpritesTest(unittest.TestCase):
    def sprites(self, steps=(), arches=()):
        tiles = {(1, 0, 17): wall_tile(), (1, 0, 3): wall_tile(), (0, 0, 5): floor_tile(), (0, 0, 6): floor_tile()}
        ds = FakeDs(4, 4, [{(1, 1): (dword(0, 17), 1), (2, 1): (dword(0, 3), 1)}],
                    [{(0, 0): dword(0, 5), (1, 0): dword(0, 6), (2, 2): dword(0, 5)}])
        return ws.MapSprites("m", ds, tiles, np.zeros((256, 4), np.uint8), steps, arches)

    def test_model_paths_round_trip_and_name_the_cap_tier(self):
        import walls_hd
        for key, tier in (((1, 0, 17), 2), ((0, 0, 5), 3)):
            path = ws.model_path("m", key)
            self.assertTrue(ws.is_sprite(path))
            self.assertEqual(ws.key_of(path), key)
            self.assertEqual(walls_hd.tier(path), tier)

    def test_arches_force_only_their_cells(self):
        s = self.sprites(arches={(1, 0, 17), (9, 9, 9)})
        self.assertEqual(s.arches, {(1, 0, 17)})          # keys the map has no tile for are dropped
        self.assertTrue(s.forced((1, 1)))
        self.assertFalse(s.forced((2, 1)))
        self.assertFalse(self.sprites().forced((1, 1)))

    def test_floor_sprites_on_every_step_cell(self):
        self.assertEqual(self.sprites().floor_entities(), [])
        s = self.sprites(steps={(0, 0, 5)})
        ents = s.floor_entities()
        self.assertEqual([e["name"] for e in ents], ["mxf_0_0_0", "mxf_2_2_0"])
        self.assertEqual(len({e["id"] for e in ents}), 2)
        self.assertTrue(all(e["id"] >= ws.FLOOR_ID_BASE for e in ents))
        self.assertEqual([c["type"] for c in ents[0]["components"]], ["TransformDefinitionComponent", "ModelDefinitionComponent"])
        self.assertEqual(ents[1]["components"][0]["position"], {"x": 20.0, "y": 0.0, "z": 20.0})
        self.assertEqual(ents[0]["components"][1]["filename"], ws.model_path("m", (0, 0, 5)))

    def test_floor_mesh_covers_the_cell_flat_and_maps_the_diamond(self):
        verts, tris = ws.floor_mesh((0, 0, 160, 80), (0.0, 0.0, 1.0, 1.0))
        self.assertEqual(sorted((round(p[0], 6), round(p[2], 6)) for p, *_ in verts), [(0, 0), (0, 10), (10, 0), (10, 10)])
        self.assertTrue(all(p[1] == ws.FLOOR_LIFT for p, *_ in verts))
        for p, _n, _t, uv in verts:        # the UV is the classic pixel of the floor point: px = 80 + 8 (X - Z), py = 4 (X + Z)
            self.assertAlmostEqual(uv[0] * 160, 80 + 8 * (p[0] - p[2]))
            self.assertAlmostEqual(uv[1] * 80, 4 * (p[0] + p[2]))
        for a, b, c in tris:               # facing up
            pa, pb, pc = (np.array(verts[i][0]) for i in (a, b, c))
            self.assertGreater(np.cross(pb - pa, pc - pa)[1], 0)

    def test_box_of_a_floor_key_is_flat(self):
        lo, hi = self.sprites(steps={(0, 0, 5)}).box((0, 0, 5))
        self.assertEqual((lo[1], hi[1]), (ws.FLOOR_LIFT, ws.FLOOR_LIFT))
        lo, hi = self.sprites().box((1, 0, 17))
        self.assertGreater(hi[1], 1)


if __name__ == "__main__":
    unittest.main()
