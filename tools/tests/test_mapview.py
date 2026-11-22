"""hdkit.view.mapview: .ds1 read/write (byte-identical round trip, edits), .dt1 block decoding, the classic draw order and
tile placement, the frame shared with the HD camera, tile-file resolution and working-copy edits. Synthetic data only: no
game files, no GPU, no CASC."""
import json
import struct
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))
import projtemp  # noqa: E402,F401  (temp files stay inside the project, tools/projtemp.py)
from hdkit.view import camera  # noqa: E402
from hdkit.view.mapview import classic, ds1 as D, dt1 as T, edit, world  # noqa: E402
from hdkit.view.mapview.frame import Frame, parse_cells  # noqa: E402


def iso_block(index: int) -> bytes:
    return bytes([index]) * 256


def floor_tile(main, sub, index, rarity=0, flags=b"\0" * 25):
    """A full 160x80 floor diamond made of 4x? iso blocks of one colour."""
    blocks = []
    for gy in range(5):
        for gx in range(5):
            # D2 floor blocks: x = 64 + (gx - gy) * 16 .. the usual staggered grid; any layout works for the decoder
            blocks.append((gx * 32, gy * 16, 1, iso_block(index)))
    return {"orientation": 0, "main": main, "sub": sub, "rarity": rarity, "flags": flags, "blocks": blocks}


def wall_tile(orientation, main, sub, index, height=96, roof_height=0):
    """A wall tile: one column of 32x32 RLE blocks of colour `index`, from y = -height up to 0 (x 64..96)."""
    rows = [[(0, [index] * 32)] for _ in range(32)]
    data = T.rle_block(rows)
    blocks = [(64, -height + 32 * k, 0, data) for k in range(height // 32)]
    if orientation == T.ROOF:
        blocks = [(64, 32 * k, 0, data) for k in range(height // 32)]
    return {"orientation": orientation, "main": main, "sub": sub, "blocks": blocks, "roof_height": roof_height}


class Ds1Test(unittest.TestCase):
    def test_round_trip_versions(self):
        for v in (3, 5, 9, 13, 16, 18):
            b = D.synthetic(4, 3, version=v, walls=2 if v >= 4 else 1, floors=2 if v >= 16 else 1,
                            objects=[(1, 5, 3, 4, 7), (2, 9, 10, 11, 0)], tail=b"\x01\x02\x03tail")
            ds = D.Ds1(b)
            self.assertEqual((ds.width, ds.height), (4, 3))
            self.assertEqual(ds.pack(), b, "version %d" % v)
            self.assertEqual(len(ds.objects), 2)
            self.assertEqual(ds.objects[1].as_list()[:4], [2, 9, 10, 11])

    def test_layer_stream_order(self):
        b = bytearray(D.synthetic(2, 2, version=18, walls=1, floors=1))
        ds = D.Ds1(bytes(b))
        n = 4
        # stream: wall0, orient0, floor0, shadow: put a marker in the floor layer's first dword
        struct.pack_into("<I", b, ds.layers_at + 2 * n * 4, 0x00500301)
        ds = D.Ds1(bytes(b))
        f = D.cell_fields(ds.floors()[0][0, 0])
        self.assertEqual((f["prop1"], f["sequence"], f["style"]), (1, 3, 5))
        self.assertEqual(int(ds.walls()[0][0, 0]), 0)

    def test_v3_layout(self):
        b = bytearray(D.synthetic(2, 2, version=3))
        ds = D.Ds1(bytes(b))
        self.assertEqual(ds.stream[:3], [("wall", 0), ("orient", 0), ("floor", 0)])
        self.assertIn(("tag", 0), ds.layers)

    def test_old_orientation_codes(self):
        b = bytearray(D.synthetic(1, 1, version=6))
        ds = D.Ds1(bytes(b))
        ds.layers[("orient", 0)][0, 0] = 3      # an old code
        self.assertEqual(int(ds.orientation(0)[0, 0]), 1)

    def test_edit_changes_only_that_dword(self):
        b = D.synthetic(3, 3, objects=[(2, 1, 2, 2, 0)], tail=b"paths")
        ds = D.Ds1(b)
        ds.layers[("floor", 0)][1, 2] = D.make_cell(7, 4)
        out = ds.pack()
        diff = [i for i in range(len(b)) if b[i] != out[i]]
        self.assertTrue(diff and all(ds.layers_at <= i < ds.objects_at for i in diff))
        self.assertTrue(out.endswith(b"paths"))
        ds2 = D.Ds1(out)
        self.assertEqual(D.cell_fields(ds2.floors()[0][1, 2])["style"], 7)

    def test_make_cell_keeps_other_bits(self):
        c = D.make_cell(3, 2, 1, False, keep=0x000FC000)
        f = D.cell_fields(c)
        self.assertEqual((f["style"], f["sequence"], f["prop1"], f["unknown"], f["hidden"]), (3, 2, 1, 0x3F, False))
        self.assertTrue(D.cell_fields(D.make_cell(1, 1, hidden=True))["hidden"])

    def test_bad_files(self):
        with self.assertRaises(ValueError):
            D.Ds1(b"\x12\0\0\0" + b"\0" * 6)
        with self.assertRaises(ValueError):
            D.Ds1(D.synthetic(4, 4)[:60])


class Dt1Test(unittest.TestCase):
    def test_iso_block(self):
        data = T.synthetic([{"orientation": 0, "main": 1, "sub": 2, "blocks": [(0, 0, 1, bytes(i % 255 + 1 for i in range(256)))]}])
        tl = T.parse(data)[0]
        img, x0, y0 = tl.image()
        self.assertEqual((x0, y0), (0, 0))
        self.assertEqual(int((img != 0).sum()), 256)
        self.assertEqual(int(img[0, 14]), 1)          # first row starts at x 14
        self.assertEqual(int(img[7, 0]), int(sum(T.ISO_N[:7])) % 255 + 1)   # row 7 is 32 wide from x 0

    def test_rle_block(self):
        rows = [[(2, [5, 6])], [], [(0, [7])]]
        data = T.synthetic([{"orientation": 1, "main": 0, "sub": 0, "blocks": [(0, -32, 0, T.rle_block(rows))]}])
        img, x0, y0 = T.parse(data)[0].image()
        self.assertEqual(y0, -32)
        self.assertEqual(img[0, 2:4].tolist(), [5, 6])
        self.assertEqual(int(img[2, 0]), 7)
        self.assertEqual(int(img[1].sum()), 0)

    def test_header_fields_and_flags(self):
        fl = bytearray(25)
        fl[T.subtile_index(1, 0)] = 1                  # sub-tile x 1, y 0 blocks walking
        data = T.synthetic([dict(floor_tile(3, 4, 9, rarity=5, flags=bytes(fl)))])
        tl = T.parse(data)[0]
        self.assertEqual((tl.orientation, tl.main, tl.sub, tl.rarity), (0, 3, 4, 5))
        g = tl.flag_grid()
        self.assertEqual(int(g[0, 1]), 1)
        self.assertEqual(int(g.sum()), 1)
        self.assertEqual(T.subtile_index(0, 4), 0)    # OpenDiablo2's lookup: bottom row first

    def test_bad(self):
        with self.assertRaises(ValueError):
            T.parse(b"\0" * 100)


class FakeSrc:
    """What classic.render needs: ds, lib, palette, key, source, act, notes, object_name."""

    def __init__(self, ds, tiles):
        self.ds = ds
        self.lib = world.TileLib([("test/t.dt1", T.synthetic(tiles))])
        pal = np.zeros((256, 3), np.uint8)
        pal[:, 0] = np.arange(256)
        pal[:, 1] = 100
        self.palette = pal
        self.key, self.source, self.act, self.notes = "test/map", "mod", 1, []

    def object_name(self, t, i):
        return "obj%d" % i


def small_map():
    ds = D.Ds1(D.synthetic(3, 3, objects=[(2, 7, 7, 7, 0)]))
    for y in range(3):
        for x in range(3):
            ds.layers[("floor", 0)][y, x] = D.make_cell(1, 0)
    ds.layers[("wall", 0)][1, 1] = D.make_cell(2, 0)
    ds.layers[("orient", 0)][1, 1] = T.LEFT
    ds.layers[("shadow", 0)][2, 2] = D.make_cell(4, 0)
    tiles = [floor_tile(1, 0, 10), wall_tile(T.LEFT, 2, 0, 20), wall_tile(T.SHADOW, 4, 0, 30, 32)]
    return ds, tiles


class DrawOrderTest(unittest.TestCase):
    def test_passes(self):
        ds, tiles = small_map()
        ds.layers[("wall", 0)][0, 2] = D.make_cell(5, 0)
        ds.layers[("orient", 0)][0, 2] = T.ROOF
        ds.layers[("wall", 0)][2, 0] = D.make_cell(6, 0)
        ds.layers[("orient", 0)][2, 0] = 16                     # lower left wall
        tiles += [wall_tile(T.ROOF, 5, 0, 40, 32, roof_height=50), wall_tile(16, 6, 0, 50, 32)]
        src = FakeSrc(ds, tiles)
        items, missing = classic.draw_list(src, classic.Options(layers=classic.parse_layers("all")))
        self.assertEqual(missing, {})
        kinds = [it[0].orientation for it in items]
        # pass 1 cell by cell: floors, shadow and the lower wall interleaved; then the upper wall; the roof last
        self.assertEqual(kinds[-1], T.ROOF)
        self.assertEqual(kinds[-2], T.LEFT)
        self.assertEqual(sorted(kinds[:-2]), sorted([0] * 9 + [T.SHADOW, 16]))
        # the lower wall at (0, 2) comes before that cell's floor
        cells = [(it[4], it[5], it[0].orientation) for it in items]
        self.assertLess(cells.index((0, 2, 16)), cells.index((0, 2, 0)))
        # placement: floor at the cell's top corner - 80; a wall 80 px lower than its block y; a roof lifted
        fl = next(it for it in items if it[0].orientation == 0 and it[4:] == (1, 1))
        self.assertEqual((fl[1], fl[2]), ((1 - 1) * 80 - 80, (1 + 1) * 40))
        wl = next(it for it in items if it[0].orientation == T.LEFT)
        self.assertEqual((wl[1], wl[2]), (0 * 80 - 80 + 64, 2 * 40 - 96 + 80))
        rf = next(it for it in items if it[0].orientation == T.ROOF)
        self.assertEqual(rf[2], (2 + 0) * 40 + 0 - 50)

    def test_north_corner_draws_both_parts(self):
        ds, tiles = small_map()
        ds.layers[("orient", 0)][1, 1] = T.NC_RIGHT
        tiles += [wall_tile(T.NC_RIGHT, 2, 0, 21), wall_tile(T.NC_LEFT, 2, 0, 22)]
        items, _m = classic.draw_list(FakeSrc(ds, tiles), classic.Options())
        o = [it[0].orientation for it in items if it[0].orientation in (3, 4)]
        self.assertEqual(o, [3, 4])

    def test_hidden_and_prop1(self):
        ds, tiles = small_map()
        ds.layers[("floor", 0)][0, 0] = D.make_cell(1, 0, hidden=True)
        ds.layers[("floor", 0)][0, 1] = D.make_cell(1, 0, prop1=0)
        items, _ = classic.draw_list(FakeSrc(ds, tiles), classic.Options(layers={"floor"}))
        self.assertEqual(len(items), 7)

    def test_missing_keys_reported(self):
        ds, tiles = small_map()
        ds.layers[("floor", 0)][0, 0] = D.make_cell(9, 9)
        _items, missing = classic.draw_list(FakeSrc(ds, tiles), classic.Options())
        self.assertEqual(missing, {(0, 9, 9): 1})

    def test_render_pixels(self):
        ds, tiles = small_map()
        src = FakeSrc(ds, tiles)
        fr = classic.frame_of(src, None, 1.0, rise=200)
        img, info = classic.render(src, fr, classic.Options(layers={"floor", "wall", "shadow"}))
        a = np.asarray(img)
        self.assertEqual(img.size, fr.size)
        # the wall (colour 20) covers the floor (10) where they overlap: wall column x 64..96 of cell (1, 1)
        wx, wy = fr.native_px(1, 1)
        px = a[int(wy) + 10, int(wx - 80 + 70)]
        self.assertEqual(tuple(px[:2]), (20, 100))
        # floor colour at the centre of cell (0, 0)
        cx, cy = fr.native_px(0.5, 0.5)
        self.assertEqual(int(a[int(cy), int(cx), 0]), 10)
        # the shadow halves the floor under it: (10, 100) -> (5, 50)
        no, _ = classic.render(src, fr, classic.Options(layers={"floor", "wall"}))
        b = np.asarray(no)
        d = np.nonzero((a[..., :3] != b[..., :3]).any(-1))
        self.assertTrue(len(d[0]) > 100)
        self.assertTrue(np.array_equal(a[d][:, :3], b[d][:, :3] // 2))
        self.assertIn((5, 50), {tuple(v) for v in a[d][:, :2].tolist()})
        self.assertEqual(info["tiles_drawn"], 11)

    def test_scaled_strips_match(self):
        ds, tiles = small_map()
        src = FakeSrc(ds, tiles)
        old = classic.STRIP_ROWS
        try:
            fr = classic.frame_of(src, None, 0.5, rise=200)
            whole, _ = classic.render(src, fr, classic.Options(layers={"floor", "wall"}))
            classic.STRIP_ROWS = 8
            strips, _ = classic.render(src, fr, classic.Options(layers={"floor", "wall"}))
        finally:
            classic.STRIP_ROWS = old
        self.assertTrue(np.array_equal(np.asarray(whole), np.asarray(strips)))

    def test_isolate_region(self):
        ds, tiles = small_map()
        src = FakeSrc(ds, tiles)
        fr = classic.frame_of(src, "1,1,1,1", 1.0, rise=200)
        img, info = classic.render(src, fr, classic.Options(layers={"floor"}, isolate=True))
        self.assertEqual(info["tiles_drawn"], 1)
        self.assertEqual(img.size, (160, 80 + 200 + 40))

    def test_layers_spec(self):
        self.assertEqual(classic.parse_layers("floor,wall"), {"floor", "wall"})
        s = classic.parse_layers("-roof,+grid")
        self.assertIn("grid", s)
        self.assertNotIn("roof", s)
        with self.assertRaises(ValueError):
            classic.parse_layers("nope")


class FrameTest(unittest.TestCase):
    def test_inverse(self):
        fr = Frame(2, 3, 10, 12, 0.5)
        px = fr.px(4.25, 7.5)
        self.assertTrue(np.allclose(fr.cell_at(*px), (4.25, 7.5)))
        w, h = fr.native_size
        self.assertEqual(w, ((10 + 1 - 3) + (12 + 1 - 2)) * 80)

    def test_hd_camera_lines_up(self):
        fr = Frame(0, 0, 20, 20, 0.75, rise=300)
        cam = camera.OrthoCamera(camera.GAME_EL, camera.GAME_AZ, camera.K_1600x900 * fr.hd_scale())
        for cx, cy in ((0, 0), (5, 2), (13.5, 19)):
            hp = cam.to_pixels(np.array([[cx * 10.0, 0.0, cy * 10.0]]), fr.hd_origin())[0]
            self.assertTrue(np.allclose(hp, fr.px(cx, cy), atol=1e-6), (cx, cy, hp, fr.px(cx, cy)))

    def test_parse_cells(self):
        self.assertEqual(parse_cells(None, 10, 8), (0, 0, 9, 7))
        self.assertEqual(parse_cells("5,6,2,1", 10, 8), (2, 1, 5, 6))
        self.assertEqual(parse_cells("-3,-3,-1,-1", 10, 8), (7, 5, 9, 7))
        self.assertEqual(parse_cells("4,4", 10, 8), (4, 4, 4, 4))


class WorldTest(unittest.TestCase):
    def test_first_file_wins_and_rarity(self):
        a = T.synthetic([floor_tile(1, 0, 10)])
        b = T.synthetic([floor_tile(1, 0, 11), floor_tile(2, 0, 12, rarity=1), floor_tile(2, 0, 13, rarity=3)])
        lib = world.TileLib([("a.dt1", a), ("b.dt1", b)])
        self.assertEqual(lib.file_of[(0, 1, 0)], "a.dt1")
        self.assertEqual(len(lib.variants(0, 1, 0)), 1)
        self.assertEqual(len(lib.variants(0, 2, 0)), 2)
        picks = {lib.pick(0, 2, 0, x, y).rarity for x in range(20) for y in range(20)}
        self.assertEqual(picks, {1, 3})
        self.assertIs(lib.pick(0, 2, 0, 3, 4), lib.pick(0, 2, 0, 3, 4))

    def test_map_source_and_tables(self):
        with tempfile.TemporaryDirectory() as tmp:
            mod, d2r = Path(tmp) / "mod", Path(tmp) / "d2r"
            (mod / "tiles" / "act1" / "test").mkdir(parents=True)
            (d2r / "tiles" / "act1" / "base").mkdir(parents=True)
            (mod / "excel").mkdir(parents=True)
            (d2r / "palette" / "act1").mkdir(parents=True)
            (d2r / "palette" / "act1" / "pal.dat").write_bytes(bytes([3, 2, 1]) * 256)
            ds, tiles = small_map()
            (mod / "tiles" / "act1" / "test" / "room.ds1").write_bytes(ds.pack())
            (d2r / "tiles" / "act1" / "base" / "floor.dt1").write_bytes(T.synthetic(tiles))
            (mod / "excel" / "levels.txt").write_text("Name\tId\tAct\tLevelType\nTest\t7\t0\t2\n")
            (mod / "excel" / "lvlprest.txt").write_text("Name\tLevelId\tFile1\tDt1Mask\nRoom\t7\tact1\\test\\room.ds1\t2\n")
            files = "\t".join("File %d" % i for i in range(1, 33))
            row = ["0"] * 32
            row[0], row[1] = "act1\\none\\x.dt1", "act1\\base\\floor.dt1"
            (mod / "excel" / "lvltypes.txt").write_text("Name\tId\t%s\nT\t2\t%s\n" % (files, "\t".join(row)))
            (mod / "excel" / "objects.txt").write_text("Class\tName\nTorch\tTiki torch\n")
            (mod / "excel" / "objpreset.txt").write_text("Index\tAct\tObjectClass\n7\t1\tTorch\n")
            roots = world.Roots(mod, d2r, casc=False)
            src = world.MapSource("act1/test/room", "auto", roots)
            self.assertEqual(src.source, "mod")
            self.assertEqual([f for f, _p in src.files], ["act1/base/floor.dt1"])    # mask bit 1 only
            self.assertEqual(src.levels[0]["level"], 7)
            self.assertEqual(src.palette[0].tolist(), [1, 2, 3])                    # BGR -> RGB
            self.assertEqual(src.object_name(2, 7), "Torch (Tiki torch)")
            self.assertEqual(roots.maps("mod"), ["act1/test/room"])
            # working copy: edits go to the copy, the extract stays as it was
            wc = edit.WorkCopy.init("act1/test/room", str(Path(tmp) / "wc"), "mod", hd=False, roots=roots)
            before = (mod / "tiles" / "act1" / "test" / "room.ds1").read_bytes()
            self.assertEqual(wc.ds1().pack(), before)
            self.assertTrue(wc.show()["ds1_identical"])
            wc.set_tile(2, 0, "floor", 0, style=1, seq=0, prop1=1, clear=True)
            wc.set_tile(0, 2, "wall", 0, style=2, seq=0, orientation=T.RIGHT)
            wc.obj_add(1, 3, 4, 4)
            wc.obj_move(0, 1, 1)
            wc.obj_remove(1)
            sh = wc.show()
            self.assertEqual(sh["cells_changed_total"], 3)   # floor, wall, its orientation
            self.assertFalse(sh["ds1_identical"])
            self.assertEqual(len(sh["edits"]), 5)
            self.assertEqual((mod / "tiles" / "act1" / "test" / "room.ds1").read_bytes(), before)
            ds2 = wc.ds1()
            self.assertEqual(int(ds2.floors()[0][0, 2]), 0)
            self.assertEqual(int(ds2.orientation(0)[2, 0]), T.RIGHT)
            self.assertEqual([o.as_list()[:4] for o in ds2.objects], [[2, 7, 1, 1]])
            # render from the copy: one floor fewer
            src2 = world.MapSource(wc.map, wc.source, roots, ds1_path=wc.ds1_path)
            items, _ = classic.draw_list(src2, classic.Options(layers={"floor"}))
            self.assertEqual(len(items), 8)
            with self.assertRaises(PermissionError):
                edit._guard(Path(tmp) / "elsewhere.ds1", wc.root)

    def test_preset_edits(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / "wc"
            (root / "data" / "hd" / "env" / "preset" / "x").mkdir(parents=True)
            p = root / "data" / "hd" / "env" / "preset" / "x" / "m.json"
            p.write_text(json.dumps({"entities": [{"type": "Entity", "name": "a", "id": 1, "components": [
                {"type": "TransformDefinitionComponent", "position": {"x": 1, "y": 0, "z": 2}}]}]}))
            (root / "edits.jsonl").touch()
            wc = edit.WorkCopy(root, {"map": "x/m", "source": "d2r", "preset_logical": "hd/env/preset/x/m.json"})
            wc.ent_add("hd/env/model/thing.model", (15, 0, 25), yaw=90)
            wc.ent_move(0, (5, 1, 6))
            d = wc.preset()
            self.assertEqual(len(d["entities"]), 2)
            self.assertEqual(d["entities"][0]["components"][0]["position"], {"x": 5.0, "y": 1.0, "z": 6.0})
            q = d["entities"][1]["components"][0]["orientation"]
            self.assertAlmostEqual(q["y"], 2 ** -0.5)
            wc.ent_remove(0)
            self.assertEqual([e["name"] for e in wc.preset()["entities"]], [d["entities"][1]["name"]])


if __name__ == "__main__":
    unittest.main()
