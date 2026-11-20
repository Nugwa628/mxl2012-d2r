"""Tests of tools/sprite_scene.py (sprite walls for any map) and of the index records tools/model_lod_desc.py gives its models."""
import json
import struct
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import projtemp  # noqa: E402,F401  (temp files stay inside the project, tools/projtemp.py)

import model_lod_desc as mld  # noqa: E402
import sprite_scene as ss  # noqa: E402
import walls_hd  # noqa: E402
import walls_sprite as ws  # noqa: E402


# ---- model_lod_desc ------------------------------------------------------------------------------------------------------------
def lod_table(models):
    """A model_lod_desc.bin of [(path, [mesh count per LOD])]: every mesh record its own, bounds = its running number."""
    models = sorted(models, key=lambda m: mld.fnv(m[0]))
    n1, n2, n3 = len(models), sum(len(m[1]) for m in models), sum(sum(m[1]) for m in models)
    a1 = 24
    a2 = a1 + n1 * 44
    a3 = a2 + n2 * 12
    e, r2, r3 = b"", b"", b""
    for i, (path, lods) in enumerate(models):
        at2 = a2 + len(r2)
        e += struct.pack("<I6f", mld.fnv(path), 0, 0, 0, 1, 1, 1) + bytes([(2 << len(lods)) - 2, 0, 0, 0])
        e += struct.pack("<3I", len(lods), at2 - (a1 + i * 44 + 36), 32)
        for meshes in lods:
            here = a2 + len(r2)
            r2 += bytes([0, 7, 7, 7]) + struct.pack("<2I", meshes, a3 + len(r3) - (here + 8))
            for _ in range(meshes):
                k = float(len(r3) // 32)
                r3 += struct.pack("<6fIHH", k, k, k, k + 1, k + 1, k + 1, 1, 1, 32)
    return struct.pack("<6i", n1, a1 - 4, n2, a2 - 12, n3, a3 - 20) + e + r2 + r3


class OwnRecordsTest(unittest.TestCase):
    DONOR, OTHER = "data/hd/a/donor.model", "data/hd/a/other.model"

    def setUp(self):
        self.table = lod_table([(self.DONOR, [1, 1, 1]), (self.OTHER, [2, 1])])

    def test_the_helper_table_reads_back(self):
        self.assertEqual([len(lod) for lod in mld.lods_of(self.table, self.OTHER)], [2, 1])
        self.assertEqual([len(lod) for lod in mld.lods_of(self.table, self.DONOR)], [1, 1, 1])
        self.assertIsNone(mld.lods_of(self.table, "data/hd/a/none.model"))

    def test_without_own_the_new_path_shares_the_donors_records_and_nothing_grows(self):
        out = mld.add(self.table, {"data/hd/a/new.model": self.DONOR}, {"data/hd/a/new.model": ((1, 2, 3), (4, 5, 6))})
        self.assertEqual(len(out), len(self.table) + 44)
        self.assertEqual(mld.lods_of(out, "data/hd/a/new.model"), mld.lods_of(self.table, self.DONOR))
        self.assertEqual(mld.lods_of(out, self.OTHER), mld.lods_of(self.table, self.OTHER))

    def test_own_records_carry_the_models_lods_and_bounds(self):
        new, two = "data/hd/a/new.model", "data/hd/a/two.model"
        box, box2 = ((0.0, 0.0, 0.0), (10.0, 20.0, 10.0)), ((-1.0, 0.0, -1.0), (1.0, 2.0, 1.0))
        out = mld.add(self.table, {new: self.DONOR, two: self.DONOR}, {new: box, two: box2}, {new: [[box]], two: [[box2, box], [box2]]})
        entries = mld.parse(out)[0]
        e = mld.find(entries, new)
        self.assertEqual((e[28], struct.unpack_from("<I", e, 32)[0]), (0x02, 1))       # one LOD: the mask's bit 1
        self.assertEqual(struct.unpack_from("<6f", e, 4), box[0] + box[1])
        self.assertEqual(mld.lods_of(out, new), [[(box[0], box[1], (1, 1, 32))]])
        e2 = mld.find(entries, two)
        self.assertEqual((e2[28], struct.unpack_from("<I", e2, 32)[0]), (0x06, 2))
        self.assertEqual([[m[:2] for m in lod] for lod in mld.lods_of(out, two)], [[box2, box], [box2]])
        for old in (self.DONOR, self.OTHER):                                          # the old entries read as before
            self.assertEqual(mld.lods_of(out, old), mld.lods_of(self.table, old))
        self.assertEqual(len(out), len(self.table) + 2 * 44 + 3 * 12 + 4 * 32)

    def test_adding_the_same_models_again_changes_nothing(self):
        new = "data/hd/a/new.model"
        box = ((0.0, 0.0, 0.0), (1.0, 1.0, 1.0))
        once = mld.add(self.table, {new: self.DONOR}, {new: box}, {new: [[box]]})
        self.assertEqual(mld.add(once, {new: self.DONOR}, {new: box}, {new: [[box]]}), once)
        wider = mld.add(once, {new: self.DONOR}, {new: box}, {new: [[box], [box]]})    # a rebuilt model's old records go
        self.assertEqual(len(wider), len(once) + 12 + 32)
        self.assertEqual(len(mld.lods_of(wider, new)), 2)

    def test_compact_leaves_a_table_without_orphans_alone(self):
        self.assertEqual(mld.compact(self.table), self.table)

    def test_a_donor_may_be_a_path_the_same_call_adds_and_a_missing_one_is_an_error(self):
        first, second = "data/hd/a/first.model", "data/hd/a/second.model"
        out = mld.add(self.table, {first: self.OTHER, second: first})
        self.assertEqual(mld.lods_of(out, second), mld.lods_of(self.table, self.OTHER))
        with self.assertRaises(KeyError):
            mld.add(self.table, {first: "data/hd/a/none.model"})
        with self.assertRaises(KeyError):
            mld.add(self.table, {first: "data/hd/a/none.model"}, own={first: [[((0, 0, 0), (1, 1, 1))]]})

    def test_many_models_at_once(self):
        new = {"data/hd/a/n%d.model" % i: self.DONOR for i in range(400)}
        box = ((0.0, 0.0, 0.0), (1.0, 1.0, 1.0))
        out = mld.add(self.table, new, own={p: [[box]] for p in new})
        self.assertEqual(len(out), len(self.table) + 400 * (44 + 12 + 32))
        keys = [struct.unpack_from("<I", e)[0] for e in mld.parse(out)[0]]
        self.assertEqual(keys, sorted(keys))                                         # the game searches the table by key
        self.assertEqual(mld.lods_of(out, "data/hd/a/n399.model"), [[(box[0], box[1], (1, 1, 32))]])


# ---- tiles ---------------------------------------------------------------------------------------------------------------------
def dt1(tiles):
    """A .dt1 of [(orientation, style, sequence, rarity, roof height, blocked sub-tiles, (x, y, w, h, colour) or None)]: each
    tile one run-length block."""
    head = bytearray(0x114)
    struct.pack_into("<ii", head, 0, 7, 6)
    struct.pack_into("<ii", head, 0x10C, len(tiles), 0x114)
    headers, blocks = bytearray(96 * len(tiles)), bytearray()
    at = 0x114 + len(headers)
    for i, (o, s, q, rarity, roof, blocked, box) in enumerate(tiles):
        struct.pack_into("<h", headers, i * 96 + 4, roof)
        struct.pack_into("<4i", headers, i * 96 + 20, o, s, q, rarity)
        headers[i * 96 + 40:i * 96 + 40 + blocked] = b"\x01" * blocked
        if box is None:
            continue
        x, y, w, h, c = box
        rows = b"".join(bytes([0, w]) + bytes([c]) * w + b"\0\0" for _ in range(h))
        block = struct.pack("<hhhBBhihi", x, y, 0, 0, 0, 0, len(rows), 0, 20) + rows
        struct.pack_into("<iii", headers, i * 96 + 72, at + len(blocks), len(block), 1)
        blocks += block
    return bytes(head + headers + blocks)


class FakeDs:
    def __init__(self, width, height, walls, floors=()):
        self.width, self.height, self.act = width, height, 0
        self._walls, self._floors = walls, floors

    def _layer(self, cells):
        out = [0] * (self.width * self.height)
        for (x, y), c in cells.items():
            out[y * self.width + x] = c
        return out

    def wall_layers(self):
        return [(self._layer({xy: c for xy, (c, _o) in cells.items()}), self._layer({xy: o for xy, (_c, o) in cells.items()}))
                for cells in self._walls]

    def floor_layers(self):
        return [self._layer(cells) for cells in self._floors]


def dword(style, seq):
    return style << 20 | seq << 8 | 1


PALETTE = np.zeros((256, 4), np.uint8)
PALETTE[1:, :3] = 200
PALETTE[1:, 3] = 255
PALETTE[9, :3] = 2          # near black

WALLS = dt1([(1, 0, 3, 1, 0, 5, (60, -200, 40, 200, 5)),      # a wall, three variants: the middle one never rolled
             (1, 0, 3, 0, 0, 5, (60, -200, 40, 200, 6)),
             (1, 0, 3, 3, 0, 5, (60, -200, 40, 200, 7)),
             (15, 2, 1, 1, 240, 0, (0, 0, 160, 60, 5)),      # a roof 240 px up
             (12, 0, 1, 1, 0, 1, (70, -30, 20, 30, 5)),
             (13, 0, 0, 1, 0, 0, (0, -20, 10, 10, 5)),        # a shadow: never drawn
             (2, 0, 9, 1, 0, 0, None)])                       # no picture
FLOORS = dt1([(0, 0, 1, 1, 0, 0, (0, 0, 160, 79, 5)), (0, 0, 2, 1, 0, 25, (0, 0, 160, 79, 9)), (1, 0, 3, 1, 0, 0, (0, -9, 9, 9, 5))])


def handle():
    ds = FakeDs(8, 8, [{(1, 1): (dword(0, 3), 1), (2, 1): (dword(2, 1), 15), (3, 3): (dword(0, 1), 12), (4, 4): (dword(0, 0), 13),
                        (5, 5): (dword(0, 9), 2)}, {(1, 1): (dword(0, 1), 12)}],
                [{(0, 0): dword(0, 1), (1, 1): dword(0, 2), (6, 6): dword(0, 2)}])
    return ss.MapHandle("Adhoc\\Test.ds1", ds, [("x/walls.dt1", WALLS), ("x/floors.dt1", FLOORS)], 1, PALETTE)


class TilesTest(unittest.TestCase):
    def test_file_tiles_keeps_rarity_variants_roof_heights_and_blocked_sub_tiles(self):
        t = ss.file_tiles(WALLS)
        self.assertEqual([(v.n, v.rarity) for v in t[(1, 0, 3)]], [(0, 1), (1, 0), (2, 3)])
        self.assertEqual((t[(15, 2, 1)][0].roof, t[(1, 0, 3)][0].blocked, t[(12, 0, 1)][0].blocked), (240, 5, 1))
        self.assertNotIn((2, 0, 9), t)
        self.assertEqual(ws.rect_of(t[(1, 0, 3)][0].pixels), (60, -200, 100, 0))

    def test_pick_is_fixed_per_cell_and_follows_the_rarity(self):
        vs = ss.file_tiles(WALLS)[(1, 0, 3)]
        got = [ss.pick(vs, x, y, 0).n for x in range(40) for y in range(40)]
        self.assertEqual(got, [ss.pick(vs, x, y, 0).n for x in range(40) for y in range(40)])
        self.assertNotIn(1, got)                                # rarity 0 beside tiles with a rarity
        self.assertTrue(0.15 < got.count(0) / len(got) < 0.35)  # 1 : 3
        self.assertEqual(ss.pick(vs[1:2], 3, 4, 0).n, 1)        # alone: drawn
        dead = [ss.Variant((1, 0, 0), n, 0, []) for n in range(3)]
        self.assertEqual(ss.pick(dead, 3, 4, 0).n, 0)           # no rarity at all: the first

    def test_names_round_trip_and_fit_the_builds_readers(self):
        for key, n, tier in (((1, 0, 3), 0, 2), ((1, 0, 3), 2, 2), ((15, 2, 1), 0, 1), ((12, 0, 1), 1, 0), ((14, 5, 6), 0, 0)):
            name = ss.tile_name(key, n)
            self.assertEqual(ss.parse_name(name), (key, n))
            path = ss.MODEL % (("g", name.split("_")[0]) + key)
            self.assertTrue(ws.is_sprite(path))
            self.assertEqual(ws.key_of(path), key)              # maps_flat.flat_sprite reads the key the same way
            self.assertEqual(walls_hd.tier(path), tier)
        for bad in ("rock_0_1", "wall_1_2", "paint_a_1_2", "roof_1_0_3", "wallx_1_0_3"):
            self.assertIsNone(ss.parse_name(bad))

    def test_group_names_the_tile_file_and_the_palette(self):
        self.assertEqual(ss.group_of("Act3\\Kurast\\Walls.dt1", 3), "act3-kurast-walls-a3")
        self.assertNotEqual(ss.group_of("a/b.dt1", 1), ss.group_of("a/b.dt1", 2))

    def test_a_map_with_an_own_group_draws_into_atlases_of_its_own(self):
        pal = np.zeros((256, 4), np.uint8)
        own = ss.MapHandle("act3/temple/temple5.ds1", None, [], 3, pal)
        twin = ss.MapHandle("act3/temple/temple6.ds1", None, [], 3, pal)
        other = ss.MapHandle("expansion/glados/glados.ds1", None, [], 3, pal)
        tiles = "act3/kurast/interior.dt1"
        self.assertEqual(other.group(tiles), ss.group_of(tiles, 3))          # a map not in OWN_GROUP: the shared atlas
        self.assertEqual(own.group(tiles), ss.group_of(tiles, 3) + "-" + ss.OWN_GROUP["temple5"])
        self.assertEqual(own.group(tiles), twin.group(tiles))                # the two identical Reliquary maps share theirs
        for m in ss.OWN_GROUP:                                               # never a map that ships on the shared atlases
            self.assertNotIn(m, {Path(x).stem for x in ss.listed_maps(ss.CLASSIC_LIST)} - set(ss.OWN_GROUP))

    def test_a_map_on_own_atlas_does_not_share_a_tile_files_atlas(self):
        ds = FakeDs(8, 8, [{(1, 1): (dword(0, 3), 1)}], [{}])
        own = ss.MapHandle("Expansion\\IceCave\\RockIsDead.ds1", ds, [("x/walls.dt1", WALLS)], 5, PALETTE)
        other = ss.MapHandle("Expansion\\Voodoo\\Macumba.ds1", ds, [("x/walls.dt1", WALLS)], 5, PALETTE)
        self.assertIn("rockisdead", ss.OWN_GROUP)
        self.assertEqual(other.group("x/walls.dt1"), ss.group_of("x/walls.dt1", 5))
        self.assertEqual(own.group("x/walls.dt1"), ss.group_of("x/walls.dt1", 5) + "-rockisdead")

    def test_cut_black_drops_large_black_patches_only(self):
        px = [(x, y, 9) for x in range(12) for y in range(12)] + [(x, 20, 9) for x in range(5)] + [(x, 30, 5) for x in range(200)]
        out = ss.cut_black(px, PALETTE)
        self.assertEqual(len(out), 5 + 200)
        self.assertFalse(any(y < 12 for _x, y, _c in out))


class HandleTest(unittest.TestCase):
    def test_the_first_file_with_a_key_wins(self):
        h = handle()
        self.assertEqual((h.name, h.key, h.stem), ("adhoc/test.ds1", "adhoc/test", "test"))
        self.assertEqual(h.source[(1, 0, 3)], "x/walls.dt1")
        self.assertEqual(len(h.variants[(1, 0, 3)]), 3)
        self.assertEqual(len(h.by_file["x/floors.dt1"][(1, 0, 3)]), 1)

    def test_walls_are_the_upright_orientations_that_have_a_tile(self):
        got = {(x, y, n): v.key for x, y, n, v in handle().walls()}
        self.assertEqual(got, {(1, 1, 0): (1, 0, 3), (2, 1, 0): (15, 2, 1), (3, 3, 0): (12, 0, 1), (1, 1, 1): (12, 0, 1)})
        self.assertEqual({v.key for *_r, v in handle().walls({15})}, {(15, 2, 1)})

    def test_floors_drawn_are_those_that_block(self):
        h = handle()
        self.assertEqual([(x, y, v.key) for x, y, _n, v in h.floors("blocked")], [(1, 1, (0, 0, 2)), (6, 6, (0, 0, 2))])
        self.assertEqual(len(h.floors("all")), 3)
        self.assertEqual(h.floors("none"), [])

    def test_floors_share_a_key_by_rarity_unless_animated(self):
        h = handle()
        key = next(k for k in h.variants if k[0] == 0)
        rare = [ss.Variant(key, n, 1, [(0, 0, 1)]) for n in range(4)]
        h.variants[key] = rare
        self.assertGreater(len({v.n for *_c, v in h.floors("all") if v.key == key} | {ss.pick(rare, x, x, 0).n for x in range(40)}), 1)
        h.variants[key] = [ss.Variant(key, n, 1, [(0, 0, 1)], animated=True) for n in range(4)]
        self.assertEqual({v.n for *_c, v in h.floors("all") if v.key == key}, {0})

    def test_flat_keys_follow_the_table_then_the_tiles_own_data(self):
        h = handle()
        keys = {(1, 0, 3), (12, 0, 1), (15, 2, 1)}
        self.assertEqual(h.flat_keys(keys, {}), {(12, 0, 1)})                       # a 30 px prop: a low edge, painted
        self.assertEqual(h.flat_keys(keys, {(1, 0, 3): ("flat", "art"), (12, 0, 1): ("wall", "none")}), {(1, 0, 3)})


# ---- geometry ------------------------------------------------------------------------------------------------------------------
def screen(p):
    """The classic pixel (diamond frame) the measured camera shows a point of the cell at."""
    x, h, z = p
    return ws.KINK + (x - z) * ws.PX_PER_UNIT, (x + z) * ws.PX_PER_UNIT / 2 - h * ss.PX_HEIGHT


class GeometryTest(unittest.TestCase):
    def test_height_scale_is_the_measured_cameras(self):
        self.assertAlmostEqual(ss.PX_HEIGHT, 9.798, 3)
        # a point lifted along the camera's axis (S, 1, S) stays on its pixel
        a, b = screen((3.0, 0.0, 4.0)), screen((3.0 + 2 * ss.S, 2.0, 4.0 + 2 * ss.S))
        self.assertAlmostEqual(a[0], b[0])
        self.assertAlmostEqual(a[1], b[1])

    def test_a_curtains_uv_is_the_pixel_under_its_vertex(self):
        rect = (0, -156, 160, -36)
        v = ss.Variant((1, 0, 3), 0, 1, [])
        verts, tris = ss.mesh_of(v, rect, (0.0, 0.0, 1.0, 1.0))
        self.assertTrue(tris)
        for pos, _n, _t, (u, w) in verts:
            sx, sy = screen(pos)
            self.assertAlmostEqual(u, (sx - rect[0]) / 160, 5)
            self.assertAlmostEqual(w, (sy - (rect[1] + ws.WALL_Y)) / 120, 5)

    def test_camera_light_changes_a_curtains_normals_only(self):
        rect, v = (0, -156, 160, -36), ss.Variant((1, 0, 3), 0, 1, [])
        up, cam = ss.mesh_of(v, rect, (0.0, 0.0, 1.0, 1.0)), ss.mesh_of(v, rect, (0.0, 0.0, 1.0, 1.0), "camera")
        self.assertEqual(up[1], cam[1])
        self.assertEqual([(p, t, uv) for p, _n, t, uv in up[0]], [(p, t, uv) for p, _n, t, uv in cam[0]])
        self.assertEqual({n for _p, n, _t, _uv in up[0]}, {(0.0, 1.0, 0.0)})
        self.assertEqual({n for _p, n, _t, _uv in cam[0]}, {ss.CAMERA_NORMAL})
        n, t = ss.CAMERA_NORMAL, cam[0][0][2]
        self.assertAlmostEqual(sum(c * c for c in n), 1.0, 3)
        self.assertAlmostEqual(sum(a * b for a, b in zip(n, t[:3])), 0.0, 5)
        self.assertGreater(n[0] * ss.S + n[1] + n[2] * ss.S, 0)      # toward the camera, which looks along (-S, -1, -S)
        floor = ss.Variant((0, 0, 0), 0, 1, [])
        self.assertEqual(ss.mesh_of(floor, (0, 0, 160, 80), (0.0, 0.0, 1.0, 1.0), "camera"), ss.mesh_of(floor, (0, 0, 160, 80), (0.0, 0.0, 1.0, 1.0)))

    def test_a_roof_is_a_level_plane_its_height_up_showing_the_picture_in_place(self):
        rect = (0, 0, 160, 60)
        v = ss.Variant((15, 2, 1), 0, 1, [], roof=240)
        verts, tris = ss.mesh_of(v, rect, (0.0, 0.0, 1.0, 1.0))
        self.assertEqual({round(p[1], 4) for p, *_ in verts}, {round(240 / ss.PX_HEIGHT, 4)})
        for pos, _n, _t, (u, w) in verts:
            sx, sy = screen(pos)
            self.assertAlmostEqual(u * 160, sx, 4)
            self.assertAlmostEqual(w * 60 - 240, sy, 4)          # classic draws the roof its height up
        for a, b, c in tris:
            pa, pb, pc = (np.array(verts[i][0]) for i in (a, b, c))
            self.assertGreater(np.cross(pb - pa, pc - pa)[1], 0)

    def test_sprite_entities(self):
        e = ss.sprite_entity("m.model", 3, 4, 1, 77, gap=2)
        p = e["components"][0]["position"]
        self.assertEqual((e["name"], e["id"], len(e["components"])), ("mxt_3_4_1", 77, 3))
        self.assertAlmostEqual(p["y"], 2 * ws.LAYER_GAP)
        self.assertAlmostEqual((p["x"] - 30.0) / p["y"], ss.S, 2)
        self.assertAlmostEqual((p["z"] - 40.0) / p["y"], ss.S, 2)
        self.assertEqual([c["name"] for c in e["components"]], ["mxt_3_4_1_t", "mxt_3_4_1_m", "mxt_3_4_1_w"])
        c = ss.chunk_entity("m.model", 1, 2, 5)
        self.assertEqual((c["name"], c["components"][0]["position"]), ("mxc_1_2", {"x": 160.0, "y": 0.0, "z": 320.0}))
        self.assertEqual([x["type"] for x in c["components"]], ["TransformDefinitionComponent", "ModelDefinitionComponent"])

    def test_chunk_mesh_lays_each_quad_on_its_cell(self):
        rects, uvs = {(0, 0, 2): (0, 0, 160, 80)}, {(0, 0, 2): (0.0, 0.0, 1.0, 1.0)}
        verts, tris = ss.chunk_mesh([(0, 0, 0, (0, 0, 2)), (3, 2, 1, (0, 0, 2))], rects, uvs)
        self.assertEqual((len(verts), len(tris)), (8, 4))
        xs, zs = [p[0] for p, *_ in verts[4:]], [p[2] for p, *_ in verts[4:]]
        self.assertEqual((min(xs), max(xs), min(zs), max(zs)), (30.0, 40.0, 20.0, 30.0))
        self.assertGreater(verts[4][0][1], verts[0][0][1])        # the upper layer over the lower


class AtlasTest(unittest.TestCase):
    def test_atlas_holds_every_picture_apart_in_a_power_of_two(self):
        px = {k: [(x, y, 5) for x in range(10 + 9 * k) for y in range(-(20 + 7 * k), 0)] for k in range(30)}
        rgba, places, rects = ss.make_atlas(px, PALETTE)
        h, w = rgba.shape[:2]
        self.assertTrue(w in ss.WIDTHS and h >= ss.MIN_SIDE and h & (h - 1) == 0)
        boxes = [(places[k][0], places[k][1], rects[k][2] - rects[k][0], rects[k][3] - rects[k][1]) for k in px]
        for i, (x, y, bw, bh) in enumerate(boxes):
            self.assertTrue(x + bw <= w and y + bh <= h)
            self.assertTrue((rgba[y:y + bh, x:x + bw, 3] == 255).all())
            for x2, y2, w2, h2 in boxes[i + 1:]:
                self.assertFalse(x < x2 + w2 and x2 < x + bw and y < y2 + h2 and y2 < y + bh)

    def test_albedo_takes_a_whole_multiple_of_the_exported_atlas(self):
        from PIL import Image
        rgba = ss.make_atlas({"wall_1_0_3": [(x, y, 5) for x in range(40) for y in range(100)]}, PALETTE)[0]
        with tempfile.TemporaryDirectory() as d:
            opts = SimpleNamespace(export=d, albedo=None, scale=1, method="lanczos")
            px, scale = ss.texture_pixels(rgba, "g", opts)
            self.assertEqual((scale, px.shape), (1, rgba.shape))
            exported = Image.open(Path(d) / "g_atlas.png")
            self.assertEqual(exported.size, (rgba.shape[1], rgba.shape[0]))
            art = Path(d) / "art"
            art.mkdir()
            exported.resize((exported.width * 2, exported.height * 2), Image.NEAREST).save(art / "g_atlas.png")
            opts = SimpleNamespace(export=None, albedo=str(art), scale=1, method="lanczos")
            px, scale = ss.texture_pixels(rgba, "g", opts)
            self.assertEqual((scale, px.shape[0], px.shape[1]), (2, rgba.shape[0] * 2, rgba.shape[1] * 2))
            self.assertTrue((px[::2, ::2] == rgba).all())                       # the picture itself, alpha kept
            self.assertEqual(ss.texture_pixels(rgba, "other", opts)[1], 1)      # no file for this atlas: the atlas
            self.assertEqual(ss.texture_pixels(rgba, "g", SimpleNamespace(export=None, albedo=str(art / "g_atlas.png"), scale=1, method="lanczos"))[1], 2)
            exported.resize((exported.width * 2, exported.height * 3), Image.NEAREST).save(art / "g_atlas.png")
            with self.assertRaises(SystemExit):
                ss.texture_pixels(rgba, "g", opts)


# ---- scene ---------------------------------------------------------------------------------------------------------------------
class FloorEdgeTest(unittest.TestCase):
    def test_pinholes_of_one_or_two_texels_close_and_an_outline_stays(self):
        rgba = np.zeros((10, 10, 4), np.uint8)
        rgba[2:8, 2:8, 3] = 255
        rgba[3, 3, 3] = 0                                    # one texel
        rgba[5, 4:6, 3] = 0                                  # two texels
        out = ss.fill_pinholes(rgba)
        self.assertTrue((out[2:8, 2:8, 3] == 255).all())
        out[2:8, 2:8, 3] = 0
        self.assertEqual(int(out[..., 3].max()), 0)          # nothing grew outside the picture
        self.assertEqual(int(rgba[3, 3, 3]), 0)

    def test_a_floor_pictures_alpha_grows_two_texels_into_its_padding_and_no_colour_changes(self):
        rgba = np.zeros((12, 12, 4), np.uint8)
        rgba[..., :3] = 90                                   # bled colour everywhere
        rgba[5:7, 5:7, 3] = 255
        out = ss.solid_edges(rgba, 2)
        self.assertTrue((out[..., :3] == rgba[..., :3]).all())
        self.assertEqual(int(out[5, 3, 3]), 255)             # two texels left of the picture
        self.assertEqual(int(out[5, 2, 3]), 0)
        self.assertEqual(int(out[4, 4, 3]), 255)             # the diagonal neighbour: two steps
        self.assertEqual(int(out[3, 3, 3]), 0)
        self.assertEqual(int(rgba[5, 4, 3]), 0)              # the input is left alone


def ent(name, x, z, model=None, ident=1, kind="ModelDefinitionComponent"):
    comps = [{"type": "TransformDefinitionComponent", "name": name + "_t", "position": {"x": float(x), "y": 0.0, "z": float(z)}}]
    if model:
        comps.append({"type": kind, "name": name + "_m", "filename": model})
    return {"type": "Entity", "name": name, "id": ident, "components": comps}


WALL_M, PROP_M, FLAT_M = "data/hd/env/model/a/wall01.model", "data/hd/env/model/a/barrel.model", "data/hd/env/model/mxl/flat/m/paint_a_0.model"
SPRITE_M = "data/hd/env/model/mxl/wallsprite/m/wall_1_0_3.model"


def scene():
    ents = [ent("mxw_1_1_0", 10, 10, WALL_M, 1), ent("mxw_5_5_0", 50, 50, PROP_M, 2), ent("mxs_1_1_0", 10, 10, SPRITE_M, 3),
            ent("mxs_7", 25, 12, WALL_M, 4), ent("mxs_8", 60, 60, WALL_M, 5), ent("mxj_0_1", 12, 28, WALL_M, 6),
            ent("mxp_2_2_0", 20, 20, "data/hd/env/model/a/house.model", 7), ent("mxp_a_3", 0, 0, FLAT_M, 8),
            ent("mxf_1_1_0", 10, 10, "data/hd/env/model/mxl/wallsprite/m/step_0_0_1.model", 9), ent("mxk_0", 0, 0, WALL_M, 10),
            ent("terrain", 0, 0, "data/hd/env/preset/x/terrain.model", 11), ent("light1", 10, 10, None, 12),
            ent("d2r_wall", 14, 9, "data/hd/env/model/b/wall_stone02.model", 13), ent("d2r_far", 70, 70, "data/hd/env/model/b/wall_stone02.model", 14),
            ent("d2r_weed", 10, 10, "data/hd/env/model/b/weed03.model", 15), ent("mxt_1_1_0", 10, 10, "old/wall_1_0_3.model", 16),
            ent("mxc_0_0", 0, 0, "old/rock_0_0.model", 17),
            {"type": "TileBiomeOverride", "name": "mxb_1_1", "tileX": 1, "tileY": 1}]
    models = sorted({m for e in ents for m in walls_hd.models_of(e)} | {"data/hd/env/model/listed/only.model"})
    return {"type": "Preset", "biomeFilename": "data/hd/env/biome/x.json", "entities": ents,
            "dependencies": {"models": [{"path": m} for m in models], "json": [{"path": "data/hd/env/biome/x.json"}]}}


class MergeTest(unittest.TestCase):
    def merged(self):
        new = [ss.sprite_entity("new/wall_1_0_3.model", 1, 1, 0, ss.ID_BASE)]
        return ss.merge_scene(scene(), new, {(1, 1)})

    def test_the_rule(self):
        out, why = self.merged()
        names = [e["name"] for e in out["entities"]]
        self.assertEqual(names, ["mxw_5_5_0", "mxs_8", "mxp_a_3", "mxf_1_1_0", "mxk_0", "terrain", "light1", "d2r_far", "d2r_weed",
                                 "mxb_1_1", "mxt_1_1_0"])
        self.assertEqual(why, {"cell piece": 2, "structure": 2, "set piece": 1, "d2r wall": 1, "own": 2})
        self.assertEqual(out["biomeFilename"], "data/hd/env/biome/x.json")
        self.assertEqual(out["dependencies"]["json"], [{"path": "data/hd/env/biome/x.json"}])

    def test_dependencies_follow_the_entities(self):
        deps = [d["path"] for d in self.merged()[0]["dependencies"]["models"]]
        self.assertIn("new/wall_1_0_3.model", deps)
        self.assertIn("data/hd/env/model/listed/only.model", deps)      # listed without an entity: left alone
        self.assertIn(WALL_M, deps)                                     # still drawn by mxs_8 and the walkway
        for gone in (SPRITE_M, "data/hd/env/model/a/house.model", "old/wall_1_0_3.model", "old/rock_0_0.model"):
            self.assertNotIn(gone, deps)
        self.assertEqual(deps, sorted(deps))

    def test_merging_again_changes_nothing(self):
        new = [ss.sprite_entity("new/wall_1_0_3.model", 1, 1, 0, ss.ID_BASE)]
        once = ss.merge_scene(scene(), new, {(1, 1)})[0]
        self.assertEqual(ss.merge_scene(once, new, {(1, 1)})[0], once)

    def test_no_sprite_cell_no_change_but_the_tools_own(self):
        out, why = ss.merge_scene(scene(), [], set())
        self.assertEqual(why, {"own": 2})
        self.assertEqual(len(out["entities"]), len(scene()["entities"]) - 2)

    def test_the_all_classic_scene_keeps_no_model_of_the_base(self):
        new = [ss.sprite_entity("new/wall_1_0_3.model", 1, 1, 0, ss.ID_BASE)]
        out, why = ss.merge_scene(scene(), new, {(1, 1)}, True)
        self.assertEqual([e["name"] for e in out["entities"]], ["light1", "mxb_1_1", "mxt_1_1_0"])
        self.assertEqual(why, {"base piece": 14, "own": 2})
        self.assertEqual([d["path"] for d in out["dependencies"]["models"]], ["data/hd/env/model/listed/only.model", "new/wall_1_0_3.model"])
        self.assertEqual(ss.merge_scene(out, new, {(1, 1)}, True)[0], out)

    def test_a_sprite_without_fade_has_no_wall_transparency(self):
        kinds = lambda e: [c["type"] for c in e["components"]]
        self.assertIn("WallTransparencyComponent", kinds(ss.sprite_entity("a.model", 1, 1, 0, 5)))
        solid = ss.sprite_entity("a.model", 1, 1, 0, 5, 0, False)
        self.assertEqual(kinds(solid), ["TransformDefinitionComponent", "ModelDefinitionComponent"])
        self.assertEqual([c["name"] for c in solid["components"]], ["mxt_1_1_0_t", "mxt_1_1_0_m"])

    def test_ids_skip_what_the_scene_uses(self):
        s = scene()
        s["entities"][0]["id"] = ss.ID_BASE + 1
        s["entities"][15]["id"] = ss.ID_BASE + 2          # this tool's own, replaced: its id is free
        ids = ss.count_ids(s)
        self.assertEqual([next(ids) for _ in range(3)], [ss.ID_BASE, ss.ID_BASE + 2, ss.ID_BASE + 3])

    def test_flat_scene_is_known_by_its_painted_models(self):
        self.assertTrue(ss.is_flat(scene()))
        self.assertFalse(ss.is_flat({"entities": [ent("mxw_1_1_0", 10, 10, WALL_M)]}))


class PlanTest(unittest.TestCase):
    def opts(self, **kw):
        return SimpleNamespace(**dict(dict(orientations=sorted(ss.DRAWN), rule="auto", floors="blocked"), **kw))

    def test_on_a_flat_scene_painted_kinds_stay_painted_and_no_floor_art_is_added(self):
        h = handle()
        plan = ss.build_map(h, scene(), "built", self.opts())
        self.assertTrue(plan["flat"])
        self.assertEqual(plan["floors"], [])
        self.assertEqual(sorted({v.key for *_r, v in plan["walls"]}), [(1, 0, 3), (15, 2, 1)])
        self.assertEqual(plan["skipped"], 2)
        self.assertEqual(len(ss.build_map(h, scene(), "built", self.opts(rule="all"))["walls"]), 4)

    def test_asked_for_every_floor_a_flat_scene_gets_them_too(self):
        h = handle()
        every = ss.build_map(h, scene(), "built", self.opts(floors="all"))["floors"]
        self.assertEqual(len(every), len(h.floors("all")))
        self.assertGreater(len(every), len(h.floors("blocked")))
        self.assertEqual(ss.build_map(h, scene(), "built", self.opts(floors="none"))["floors"], [])

    def test_elsewhere_every_upright_tile_and_the_blocking_floors(self):
        plan = ss.build_map(handle(), {"entities": []}, "empty", self.opts())
        self.assertEqual((len(plan["walls"]), len(plan["floors"]), plan["skipped"]), (4, 2, 0))

    def test_special_tiles_are_drawn_on_the_door_maps_only(self):
        tiles = dt1([(11, 0, 0, 1, 0, 5, (70, -220, 90, 180, 5)), (1, 0, 3, 1, 0, 5, (60, -200, 40, 200, 5))])
        ds = FakeDs(8, 8, [{(2, 2): (dword(0, 0), 11), (3, 3): (dword(0, 3), 1)}], [{}])
        keys = lambda stem: sorted(v.key for *_r, v in ss.build_map(
            ss.MapHandle("x/%s.ds1" % stem, ds, [("x/w.dt1", tiles)], 5, PALETTE), {"entities": []}, "empty", self.opts())["walls"])
        self.assertIn("rockisdead", ss.DOOR_MAPS)
        self.assertEqual(keys("rockisdead"), [(1, 0, 3), (11, 0, 0)])
        self.assertEqual(keys("macumba"), [(1, 0, 3)])
        self.assertNotIn(11, ss.DRAWN)
        self.assertEqual(ss.tile_name((11, 0, 0)), "wall_11_0_0")
        self.assertEqual(ss.parse_name("wall_11_0_0"), ((11, 0, 0), 0))


class GroundTest(unittest.TestCase):
    def biome(self):
        lay = {"name": "grass01", "Albedo": "a_alb.texture", "GrassDensity": 0.7, "GrassShootsDensity": 0.2, "Clutter": [{"m": 1}]}
        return {"type": "Biome", "name": "act3_kurast", "terrainDataUltra": {"terrainLayers": [dict(lay), dict(lay, GrassDensity=0.0)]},
                "terrainDataLow": {"terrainLayers": [dict(lay)]}}

    def test_a_bare_biome_grows_nothing_and_keeps_its_ground(self):
        src = self.biome()
        out = ss.bare_biome(src, "mxl2012_bare_x")
        self.assertEqual(out["name"], "mxl2012_bare_x")
        for tier in ("terrainDataUltra", "terrainDataLow"):
            for lay in out[tier]["terrainLayers"]:
                self.assertEqual((lay["GrassDensity"], lay["Clutter"], lay["Albedo"]), (0.0, [], "a_alb.texture"))
        self.assertEqual(src["terrainDataUltra"]["terrainLayers"][0]["GrassDensity"], 0.7)      # the source is not touched

    def test_bare_ground_takes_the_art_cells_overrides_and_the_biomes_nothing_names(self):
        b = "data/hd/env/biome/%s.json"
        s = {"biomeFilename": b % "x", "entities": [],
             "perTileBiomeOverrides": [{"tileX": 1, "tileY": 1, "biomeFilename": b % "act3_kurast"},
                                       {"tileX": 2, "tileY": 1, "biomeFilename": b % "act3_kurast"},
                                       {"tileX": 9, "tileY": 9, "biomeFilename": b % "act4_fort"}],
             "dependencies": {"json": [{"path": b % "x"}, {"path": b % "act3_kurast"}, {"path": b % "act4_fort"}, {"path": "data/other.json"}]}}
        out, gone = ss.bare_ground(s, {(1, 1), (2, 1)}, "mxl2012_bare_x")
        self.assertEqual(gone, 2)
        self.assertEqual(out["biomeFilename"], b % "mxl2012_bare_x")
        self.assertEqual([(o["tileX"], o["tileY"]) for o in out["perTileBiomeOverrides"]], [(9, 9)])
        self.assertEqual([d["path"] for d in out["dependencies"]["json"]], [b % "act4_fort", "data/other.json", b % "mxl2012_bare_x"])
        self.assertEqual(len(s["perTileBiomeOverrides"]), 3)

    def test_the_bare_copy_is_written_from_the_base_folders_biome(self):
        with tempfile.TemporaryDirectory() as tmp:
            base, out = Path(tmp) / "base", Path(tmp) / "out"
            f = base / "hd" / "env" / "biome" / "mxl2012_tint_x.json"
            f.parent.mkdir(parents=True)
            f.write_text(json.dumps(self.biome()), encoding="utf-8")
            s = {"biomeFilename": "data/hd/env/biome/mxl2012_tint_x.json"}
            name = ss.write_bare_biome(out, base, s, lambda rel: self.fail("D2R's file asked for: %s" % rel))
            self.assertEqual(name, "mxl2012_bare_tint_x")
            got = json.loads((out / "hd" / "env" / "biome" / (name + ".json")).read_text("utf-8"))
            self.assertEqual(got["terrainDataUltra"]["terrainLayers"][0]["GrassDensity"], 0.0)
            self.assertEqual(ss.write_bare_biome(out, base, {"biomeFilename": "data/hd/env/biome/%s.json" % name}, None), name)

    def vis(self, power):
        return {"name": "v", "entities": [
            {"name": "vis", "components": [{"type": "VisualDataComponent", "iblIntensity": 2.0, "playerUnitLightPower": 2125.0,
                                            "playerUnitLightDistanceScaler": 1.333}]},
            {"name": "global_key_light", "components": [{"type": "DirectionalLightDefinitionComponent", "color": {"x": 1.0, "y": 1.0, "z": 1.0}, "power": power}]},
            {"name": "player_key_light", "components": [{"type": "DirectionalLightDefinitionComponent", "color": {"x": 1.0, "y": 0.9, "z": 0.8}, "power": 30.0}]}]}

    def test_black_ground_blacks_every_layer_of_every_tier_and_names_its_textures(self):
        src = self.biome()
        out = ss.black_ground(src)
        for tier in ("terrainDataUltra", "terrainDataLow"):
            for lay in out[tier]["terrainLayers"]:
                self.assertEqual((lay["Albedo"], lay["Normal"], lay["ORM"]), tuple(ss.BLACK_GROUND % k for k in ("alb", "nrm", "orm")))
        self.assertEqual([d["path"] for d in out["dependencies"]["textures"]], [ss.BLACK_GROUND % k for k in ("alb", "nrm", "orm")])
        self.assertEqual(src["terrainDataUltra"]["terrainLayers"][0]["Albedo"], "a_alb.texture")
        self.assertEqual(len(ss.black_ground(out)["dependencies"]["textures"]), 3)              # named once

    def test_the_black_ground_textures_are_black_and_as_large_as_d2rs_terrain_textures(self):
        import d2r_texture
        with tempfile.TemporaryDirectory() as tmp:
            alb, nrm, orm = ss.write_black_ground(Path(tmp))
            fmt, w, h, mips = d2r_texture.parse_texture(alb.read_bytes())
            self.assertEqual((fmt, w, h, len(mips)), (d2r_texture.FMT_BC3, 1024, 1024, 11))
            self.assertEqual(d2r_texture.parse_texture(orm.read_bytes())[0], d2r_texture.FMT_BC3_LIN)
            self.assertEqual(int(d2r_texture.small_mip(alb.read_bytes(), 64)[..., :3].max()), 0)
            px = d2r_texture.small_mip(orm.read_bytes(), 64)
            self.assertEqual((int(px[..., 0].max()), int(px[..., 1].min())), (0, 255))           # no ambient light, fully rough

    def test_classic_vis_sets_the_key_light_and_only_the_values_given(self):
        out = ss.classic_vis(self.vis(0.0), "n", {"key": (0.5, 1.0, 0.7), "power": 12.0, "player": 5000.0})
        key = out["entities"][1]["components"][0]
        self.assertEqual((key["color"], key["power"]), ({"x": 0.5, "y": 1.0, "z": 0.7}, 12.0))
        self.assertEqual(out["entities"][2]["components"][0]["power"], 30.0)                     # the player's lights stay
        v = out["entities"][0]["components"][0]
        self.assertEqual((v["iblIntensity"], v["playerUnitLightPower"], v["playerUnitLightDistanceScaler"]), (2.0, 5000.0, 1.333))
        self.assertEqual((out["name"], ss.key_power(out), ss.key_power(self.vis(0.0))), ("n", 12.0, 0.0))
        self.assertNotIn("specularContribution", key)                                          # not given: left as it is

    def test_a_maps_spec_sets_only_the_key_lights_specular_share(self):
        from unittest import mock
        with mock.patch.dict(ss.CLASSIC_LIGHT, {"caveroom4": {"gain": 0.5, "spec": 0.0}}, clear=True):
            _n, light, _b, vis, *_r = self.classic_biome("caveroom4", 0.0, (255, 255, 0, 0))
        self.assertEqual(light["spec"], 0.0)
        specs = {e["name"]: c.get("specularContribution") for e in vis["entities"] for c in e["components"]}
        self.assertEqual(specs, {"vis": None, ss.KEY_LIGHT: 0.0, "player_key_light": None})

    def classic_biome(self, key, power, ambient=None):
        with tempfile.TemporaryDirectory() as tmp:
            base, out = Path(tmp) / "base", Path(tmp) / "out"
            biome = dict(self.biome(), visualDataFilenames=[{"visualDataFilename": "data/hd/env/vis/x_day.json"}],
                         dependencies={"json": [{"path": "data/hd/env/vis/x_day.json"}]})
            for rel, body in (("hd/env/biome/x.json", biome), ("hd/env/vis/x_day.json", self.vis(power))):
                (base / rel).parent.mkdir(parents=True, exist_ok=True)
                (base / rel).write_text(json.dumps(body), encoding="utf-8")
            s = {"biomeFilename": "data/hd/env/biome/x.json"}
            name, light = ss.write_classic_biome(out, base, s, lambda rel: self.fail("D2R's file asked for: %s" % rel), key, ambient)
            got = json.loads((out / "hd" / "env" / "biome" / (name + ".json")).read_text("utf-8"))
            vis = out / "hd" / "env" / "vis" / (name + ".json")
            again = ss.write_classic_biome(out, base, {"biomeFilename": "data/hd/env/biome/%s.json" % name}, None, key)
            return name, light, got, json.loads(vis.read_text("utf-8")) if vis.is_file() else None, again, \
                all((out / (ss.BLACK_GROUND % k)[len("data/"):]).is_file() for k in ("alb", "nrm", "orm"))

    def test_a_classic_biome_is_bare_and_black_and_has_the_maps_light(self):
        from unittest import mock
        with mock.patch.dict(ss.CLASSIC_LIGHT, {}, clear=True):           # the rule alone
            name, light, biome, vis, again, textures = self.classic_biome("dungrm6a", 0.0, (212, 255, 81, 128))
        self.assertEqual((name, light, again, textures), ("mxl2012_classic_dungrm6a", ss.classic_light((212, 255, 81, 128)), (name, None), True))
        lay = biome["terrainDataUltra"]["terrainLayers"][0]
        self.assertEqual((lay["GrassDensity"], lay["Clutter"], lay["Albedo"]), (0.0, [], ss.BLACK_GROUND % "alb"))
        self.assertEqual(biome["visualDataFilenames"][0]["visualDataFilename"], "data/hd/env/vis/%s.json" % name)
        self.assertEqual([d["path"] for d in biome["dependencies"]["json"]], ["data/hd/env/vis/%s.json" % name])
        self.assertEqual(ss.key_power(vis), light["power"])

    def test_a_maps_gains_scale_the_rules_key_and_player_light(self):
        from unittest import mock
        with mock.patch.dict(ss.CLASSIC_LIGHT, {"inarius": {"gain": 0.5, "pgain": 2.0, "reach": 3.0}}, clear=True):
            _n, light, *_r = self.classic_biome("inarius", 0.0, (192, 255, 255, 0))
        rule = ss.classic_light((192, 255, 255, 0))
        self.assertEqual((light["power"], light["player"], light["reach"]), (round(rule["power"] * 0.5, 4), rule["player"] * 2.0, 3.0))
        self.assertNotIn("gain", light)

    def test_classic_light_is_the_levels_ambient_in_linear_light(self):
        lt = ss.classic_light((48, 0, 0, 255))                       # Fauztinville: dim, pure blue
        self.assertEqual(lt["key"], (0.0, 0.0, 1.0))
        self.assertAlmostEqual(lt["power"], ss.LIGHT_RULE["key"] * (48 / 255) ** ss.AMBIENT_GAMMA, 3)
        self.assertEqual((lt["ibl"], lt["fog"], lt["lut"]), (ss.LIGHT_RULE["ibl"], 0.0, ss.LIGHT_RULE["lut"]))
        bright = ss.classic_light((255, 255, 0, 0))                  # Hole Level 2: full red
        self.assertEqual((bright["key"], bright["power"]), ((1.0, 0.0, 0.0), ss.LIGHT_RULE["key"]))
        self.assertEqual(ss.classic_light(None), ss.DEFAULT_LIGHT)
        self.assertGreater(ss.classic_light((64, 255, 255, 0))["power"], ss.classic_light((32, 255, 255, 0))["power"])

    def test_classic_vis_sets_lut_fall_off_and_fog(self):
        lt = dict(ss.classic_light((48, 0, 0, 255)))
        v0 = self.vis(0.0)
        v0["entities"][0]["components"][0].update(depthFogDensity=1.5, fogDensity=0.2, gradingLutFile="data/hd/env/lut/x.dds")
        v0["dependencies"] = {"other": [{"path": "data/hd/env/lut/x.dds"}]}
        out = ss.classic_vis(v0, "n", lt)
        v = out["entities"][0]["components"][0]
        self.assertEqual((v["depthFogDensity"], v["fogDensity"], v["gradingLutFile"]), (0.0, 0.0, ss.LIGHT_RULE["lut"]))
        self.assertEqual((v["iblIntensity"], v["playerUnitLightAttenuation"]), (ss.LIGHT_RULE["ibl"], ss.LIGHT_RULE["attenuation"]))
        self.assertEqual(out["dependencies"]["other"], [{"path": ss.LIGHT_RULE["lut"]}])

    def test_lamps_are_the_still_unkillable_light_monsters_and_become_point_lights(self):
        with tempfile.TemporaryDirectory() as tmp:
            ex = Path(tmp)
            tsv = lambda rows: chr(10).join(chr(9).join(r) for r in rows) + chr(10)
            (ex / "monstats.txt").write_text(tsv([("Id", "hcIdx", "MonStatsEx", "Velocity", "Run", "killable"), ("lamp", "7", "lamp", "0", "0", ""),
                                                  ("turret", "8", "turret", "0", "0", "1"), ("imp", "9", "imp", "6", "9", "")]), "utf-8")
            (ex / "monstats2.txt").write_text(tsv([("Id", "Light", "light-r", "light-g", "light-b"), ("lamp", "7", "255", "128", "128"),
                                                   ("turret", "5", "255", "0", "0"), ("imp", "3", "1", "2", "3")]), "utf-8")
            lamps = ss.scenery_lights(ex)
        self.assertEqual(lamps, {7: (7, (255, 128, 128))})
        ds = type("D", (), {"objects": [[1, 7, 52, 33, 0], [1, 8, 1, 1, 0], [2, 7, 9, 9, 0]]})()
        self.assertEqual(ss.light_monsters(ds, lamps), [(52, 33, 7, (255, 128, 128))])
        e = ss.point_entity(52, 33, 0, 99, 7, (255, 128, 128))
        t, lc = e["components"]
        self.assertEqual((e["name"], e["id"], t["position"]["x"], t["position"]["z"]), ("mxc_10_6_0", 99, 105.0, 67.0))
        self.assertEqual((lc["color"]["x"], lc["radius"]), (1.0, 7 * ss.LIGHT_RULE["point_reach"]))
        self.assertLess(lc["color"]["y"], 0.5)                       # linear: (128 / 255) ** 2.2
        self.assertEqual(ss.dropped(e, set(), True), "own")          # a later run replaces it

    def test_lit_objects_are_the_objects_alight_at_start_found_through_d2rs_preset_and_class(self):
        with tempfile.TemporaryDirectory() as tmp:
            mod, d2r = Path(tmp) / "mod", Path(tmp) / "d2r"
            mod.mkdir(), d2r.mkdir()
            tsv = lambda rows: chr(10).join(chr(9).join(r) for r in rows) + chr(10)
            (mod / "objects.txt").write_text(tsv([("Id", "Lit0", "Lit1", "Lit2", "InitFn", "Red", "Green", "Blue"),
                                                  ("1", "0", "19", "19", "8", "255", "178", "0"),       # torch: lit by its init
                                                  ("2", "0", "17", "0", "1", "255", "255", "255"),      # shrine: lit when used
                                                  ("3", "10", "0", "0", "0", "255", "100", "100")]), "utf-8")
            (d2r / "objects.txt").write_text(tsv([("Class", "*ID"), ("Torch", "1"), ("Shrine", "2"), ("Light", "3")]), "utf-8")
            (d2r / "objpreset.txt").write_text(tsv([("Index", "Act", "ObjectClass"), ("5", "1", "Torch"), ("6", "1", "Shrine"),
                                                    ("5", "2", "Light")]), "utf-8")
            lit = ss.object_lights(mod, d2r)
        self.assertEqual(lit, {("1", "5"): (19, (255, 178, 0)), ("2", "5"): (10, (255, 100, 100))})
        ds = type("D", (), {"act": 0, "objects": [[2, 5, 10, 11, 0], [2, 6, 1, 1, 0], [1, 5, 9, 9, 0]]})()
        self.assertEqual(ss.lit_objects(ds, lit), [(10, 11, 19, (255, 178, 0))])

    def test_level_ambient_skips_day_cycle_levels(self):
        rows = [{"Id": "1", "Intensity": "0", "Red": "1", "Green": "2", "Blue": "3"}, {"Id": "2", "Intensity": "48", "Red": "0", "Green": "0", "Blue": "255"}]
        self.assertEqual((ss.level_ambient(rows, [1, 2]), ss.level_ambient(rows, [1])), ((48, 0, 0, 255), None))

    def test_a_map_without_a_light_of_its_own_gets_one_only_where_the_biomes_key_light_is_off(self):
        name, light, biome, vis, _again, _t = self.classic_biome("nomap", 0.0)
        self.assertEqual((light, ss.key_power(vis)), (ss.DEFAULT_LIGHT, ss.DEFAULT_LIGHT["power"]))
        name, light, biome, vis, _again, _t = self.classic_biome("nomap", 20.0)
        self.assertEqual((light, vis), (None, None))
        self.assertEqual(biome["visualDataFilenames"][0]["visualDataFilename"], "data/hd/env/vis/x_day.json")   # the biome's light as it is

    def test_bare_ground_without_cells_takes_every_override(self):
        b = "data/hd/env/biome/%s.json"
        s = {"biomeFilename": b % "x", "entities": [], "perTileBiomeOverrides": [{"tileX": 1, "tileY": 1, "biomeFilename": b % "act3_kurast"}],
             "dependencies": {"json": [{"path": b % "act3_kurast"}]}}
        out, gone = ss.bare_ground(s, None, "mxl2012_classic_x")
        self.assertEqual((gone, out["perTileBiomeOverrides"], [d["path"] for d in out["dependencies"]["json"]]), (1, [], [b % "mxl2012_classic_x"]))


# ---- the switch ----------------------------------------------------------------------------------------------------------------
class SwitchTest(unittest.TestCase):
    def test_the_committed_list_names_no_map(self):
        self.assertEqual(ss.listed_maps(ss.LIST), [])
        self.assertEqual(ss.listed_maps(ss.LIST.with_name("no_such_list.json")), [])

    def test_with_no_map_listed_nothing_is_read_or_written(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "data"
            self.assertEqual(ss.main(["build", "--list", str(ss.LIST), str(out)]), 0)
            self.assertFalse(out.exists())
            self.assertEqual(ws.main(["build", "--list", str(ss.LIST), str(out)]), 0)      # walls_sprite.py build is the same tool
            self.assertFalse(out.exists())

    def test_the_build_runs_the_step_after_the_flat_maps_on_the_list(self):
        import build
        steps = [s[0] for s in build.ART_STEPS]
        at = steps.index("sprite_scene.py")
        self.assertEqual(steps[at - 1], "maps_flat.py")
        step = build.ART_STEPS[at]
        self.assertEqual(step[1:4], ["build", "--list", str(ss.LIST)])
        self.assertEqual(step[-1], str(build.MOD / "data"))
        self.assertNotIn("--classic", step)
        classic = build.ART_STEPS[at + 1]                     # the classic maps right after, by default (no environment switch)
        self.assertEqual(classic[:5], ["sprite_scene.py", "build", "--list", str(ss.CLASSIC_LIST), "--classic"])
        self.assertEqual(classic[5], str(build.MOD / "data"))
        self.assertLess(at + 1, steps.index("ds1_paths.py"))

    def test_the_classic_list_names_own_maps_once_and_none_on_the_merge_list(self):
        import walls_hd
        classic = ss.listed_maps(ss.CLASSIC_LIST)
        self.assertTrue(classic, "the shipped classic list is empty")
        self.assertEqual(len(classic), len(set(classic)))
        self.assertLessEqual(set(classic), set(walls_hd.MAPS))
        self.assertFalse(set(classic) & set(ss.listed_maps(ss.LIST)), "a map on both lists")
        for m in classic:                                     # each has a light entry tuned against classic
            self.assertIn(Path(m).stem, ss.CLASSIC_LIGHT, m)

    def test_a_scene_the_build_moved_is_found_where_it_went(self):
        with tempfile.TemporaryDirectory() as d:
            preset = Path(d) / "hd" / "env" / "preset"
            self.assertEqual(ss.scene_file(d, "act1/caves/caveroom4"), preset / "act1" / "caves" / "caveroom4.json")
            moved = preset / "mxl2012" / "act1" / "caves" / "caveroom4.json"       # tools/ds1_paths.py: an edited D2R map
            moved.parent.mkdir(parents=True)
            moved.write_text("{}", encoding="utf-8")
            self.assertEqual(ss.scene_file(d, "act1/caves/caveroom4"), moved)
            self.assertEqual(ss.scene_file(d, "expansion/ghetto/cypherpunk"), preset / "expansion" / "ghetto" / "cypherpunk.json")

    def test_a_list_reads_its_maps(self):
        with tempfile.TemporaryDirectory() as d:
            f = Path(d) / "l.json"
            f.write_text(json.dumps({"maps": ["expansion/ghetto/cypherpunk.ds1"]}), encoding="utf-8")
            self.assertEqual(ss.listed_maps(f), ["expansion/ghetto/cypherpunk.ds1"])


# ---- models (need D2R's donor file: skipped where it is not at hand) -----------------------------------------------------------
def donor():
    try:
        return walls_hd.d2r_bytes(ws.DONOR[:-len(".model")] + "_lod0.model")
    except (SystemExit, OSError):
        return None


class ModelTest(unittest.TestCase):
    def test_a_model_with_its_own_counts_and_its_index_records(self):
        if not donor():
            self.skipTest("D2R's donor model is not at hand")
        import d2r_model as dm
        verts, tris = ws.tile_mesh((0, -156, 80, -36), (0.0, 0.0, 1.0, 1.0), "floor", ss.PX_HEIGHT)
        tex = {"alb": "data/hd/env/texture/a_alb.texture", "nrm": ws.FLAT_NRM, "orm": ws.FLAT_ORM}
        own, _lo, _hi = ws.sprite_model(donor(), verts, tris, tex, pad=False)
        padded, lo, hi = ws.sprite_model(donor(), verts, tris, tex)
        mesh = dm.parse_tree(dm.Gr2File.read(own))["Meshes"][0]
        self.assertEqual(len(mesh["PrimaryVertexData"]["Vertices"].obj), len(verts))
        self.assertEqual(len(mesh["PrimaryTopology"]["Indices16"]), len(tris) * 3)
        self.assertEqual(mesh["PrimaryTopology"]["Groups"][0]["TriCount"], len(tris))
        self.assertLess(len(own), len(padded))
        old = dm.parse_tree(dm.Gr2File.read(padded))["Meshes"][0]
        self.assertEqual(len(old["PrimaryVertexData"]["Vertices"].obj), ws.DONOR_LOD0_VERTS)     # the default: as before
        with tempfile.TemporaryDirectory() as d:
            m = ss.Models(Path(d), lambda rel: donor(), lods=1)
            m.write("data/hd/env/model/mxl/wallsprite/t/g/wall_1_0_3.model", verts, tris, tex)
            files = sorted(f.name for f in Path(d).rglob("*.model"))
            self.assertEqual(files, ["wall_1_0_3_lod0.model"])
            table = m.write_index(lod_table([(ws.DONOR, [1, 1, 1, 1, 1])]))
            got = mld.lods_of(table, "data/hd/env/model/mxl/wallsprite/t/g/wall_1_0_3.model")
            self.assertEqual(len(got), 1)
            self.assertEqual([round(v, 3) for v in got[0][0][1]], [round(v, 3) for v in hi])
            self.assertEqual((Path(d) / "hd" / "model_lod_desc.bin").read_bytes(), table)


if __name__ == "__main__":
    unittest.main()
