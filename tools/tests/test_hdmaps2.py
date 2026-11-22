"""Lane hdmaps2: the map viewer's ground, lights and materials, the atlas upscaler's floor lattice, the parity audit's
measures. Synthetic data only, no game files, no GPU."""
import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import projtemp  # noqa: E402,F401
from hdkit.view import gpu  # noqa: E402
from hdkit.view.mapview import ground, units  # noqa: E402
from hdkit.view.mapview.frame import Frame  # noqa: E402


class FakeDs:
    def __init__(self, floor):
        self.floor = np.asarray(floor, np.int64)
        self.height, self.width = self.floor.shape

    def floors(self):
        return [self.floor]


class FakeFs:
    def __init__(self, files):
        self.files = files

    def read(self, p):
        if p not in self.files:
            raise FileNotFoundError(p)
        v = self.files[p]
        return v if isinstance(v, bytes) else __import__("json").dumps(v).encode()

    def exists(self, p):
        return p in self.files


def biome(name, n):
    return {"name": name, "terrainDataHigh": {"terrainLayers": [{"Albedo": "%s_%d_alb" % (name, i), "Normal": "n",
                                                                   "ORM": "o"} for i in range(n)]}}


class Ground(unittest.TestCase):
    def setUp(self):
        self.fs = FakeFs({"data/hd/env/biome/a.json": biome("a", 3), "data/hd/env/biome/b.json": biome("b", 2)})

    def test_floor_cells_and_hidden(self):
        f = np.zeros((2, 3), np.int64)
        f[0, 0] = 1
        f[1, 2] = 1 | (1 << 31)       # hidden: no floor
        f[1, 1] = 0x100               # prop1 0: nothing drawn
        self.assertEqual(ground.floor_cells(FakeDs(f)).tolist(), [[True, False, False], [False, False, False]])

    def test_base_layer_and_override(self):
        f = np.ones((2, 2), np.int64)
        pj = {"perTileBiomeOverrides": [{"tileX": 1, "tileY": 0, "biomeFilename": "data/hd/env/biome/b.json"}]}
        g = ground.Ground(self.fs, pj, FakeDs(f), "data/hd/env/biome/a.json", None)
        self.assertEqual(g.slots, [("data/hd/env/biome/a.json", 0), ("data/hd/env/biome/b.json", 0)])
        R = ground.RES
        cen = lambda x, y: g.W[y * R + R // 2, x * R + R // 2]   # noqa: E731
        self.assertAlmostEqual(float(cen(0, 0)[0]), 1.0, 3)
        self.assertAlmostEqual(float(cen(1, 0)[1]), 1.0, 3)
        self.assertTrue(g.mask.all())

    def test_no_floor_no_ground(self):
        f = np.zeros((3, 3), np.int64)
        f[1, 1] = 1
        g = ground.Ground(self.fs, {}, FakeDs(f), "a", None)
        self.assertFalse(g.mask[0, 0])
        self.assertTrue(g.mask[ground.RES + ground.RES // 2, ground.RES + ground.RES // 2])

    def test_biome_path(self):
        self.assertEqual(ground._biome_path("act1_cathedral"), "data/hd/env/biome/act1_cathedral.json")
        self.assertEqual(ground._biome_path("hd/env/biome/x.json"), "data/hd/env/biome/x.json")

    def test_box_blur_keeps_mass(self):
        a = np.zeros((20, 20, 2), np.float32)
        a[8:12, 8:12, 0] = 1
        b = ground._blur(a, 2)
        self.assertAlmostEqual(float(b[..., 0].sum()), 16.0, 3)


class Lights(unittest.TestCase):
    def test_pick_points_keeps_directional_and_nearest(self):
        pts = [{"pos": (1e4, 0, 0), "radius": 1e6, "color": [1, 1, 1], "directional": True}]
        pts += [{"pos": (float(i), 0.0, 0.0), "radius": 5.0, "color": [1, 1, 1]} for i in range(100)]
        got = gpu.pick_points(pts, np.array([0.0, 0, 0]), 1.0)
        self.assertTrue(got[0].get("directional"))
        self.assertEqual([p["pos"][0] for p in got[1:]], [float(i) for i in range(6)])   # within radius + 1 only

    def test_pack_points_size(self):
        self.assertEqual(len(gpu.pack_points([])), 4 + 8 * gpu.MAX_POINTS)
        self.assertEqual(gpu.FOG_AT, 44 + len(gpu.pack_points([])))

    def test_fire_kinds(self):
        self.assertEqual(units.fire_kind("data/hd/vfx/particles/env/common/generic/vfx_candle_light.particles"), "candle")
        self.assertEqual(units.fire_kind("vfx_tikitorch1_opened"), "torch")
        self.assertEqual(units.fire_kind("dust_motes"), None)


class Upscale(unittest.TestCase):
    def test_lattice_centre_copy_and_cover(self):
        import maps_upscale as mu
        px = np.zeros((80, 160, 4), np.uint8)
        yy, xx = np.mgrid[0:80, 0:160]
        dia = np.abs(xx - 79.5) / 80 + np.abs(yy - 39.5) / 40 <= 1.0
        px[dia] = (200, 100, 50, 255)
        can, (cx, cy) = mu.lattice(px)
        self.assertTrue((can[cy:cy + 80, cx:cx + 160][dia] == px[dia]).all())
        # the lattice fills the centre copy's whole rectangle (the neighbours cover the corners)
        self.assertGreater((can[cy:cy + 80, cx:cx + 160, 3] > 0).mean(), 0.97)
        self.assertTrue(mu.is_floor_tile(px))


class BackProject(unittest.TestCase):
    def test_averages_give_the_classic_pixels_back_and_detail_stays(self):
        import maps_upscale as mu
        rng = np.random.default_rng(3)
        small = np.zeros((16, 16, 4), np.uint8)
        small[..., :3] = rng.integers(40, 200, (16, 16, 3))
        small[..., 3] = 255
        small[:, :3, 3] = 0                                   # a transparent strip: left alone
        big = np.zeros((64, 64, 4), np.uint8)
        up = np.kron(small[..., :3].astype(int), np.ones((4, 4, 1), int))
        detail = rng.integers(-20, 20, (64, 64, 3))
        big[..., :3] = np.clip(up + 25 + detail, 0, 255)      # a colour drift of +25 and some fine detail
        big[..., 3] = np.kron(small[..., 3], np.ones((4, 4), np.uint8))
        out = mu.backproject(big, small, iters=4)
        down = out[..., :3].astype(float).reshape(16, 4, 16, 4, 3).mean((1, 3))
        err = np.abs(down - small[..., :3])[:, 4:].mean()       # away from the strip's edge
        self.assertLess(err, 1.5)
        self.assertGreater(np.abs(out[..., :3].astype(float) - np.kron(down, np.ones((4, 4, 1)))).mean(), 5)   # detail kept
        self.assertTrue((out[..., 3] == big[..., 3]).all())


class Store(unittest.TestCase):
    def test_store_then_fetch_gives_the_same_files(self):
        import tempfile
        import maps_upscale as mu
        with tempfile.TemporaryDirectory() as d:
            d = Path(d)
            (d / "src").mkdir()
            (d / "src" / "a_atlas.png").write_bytes(b"one")
            (d / "src" / "b_atlas.json").write_bytes(b"two")
            doc = mu.store(d / "src", d / "m.json", {"tool": "test"}, root=d / "store", log=lambda s: None)
            self.assertEqual([f["path"] for f in doc["files"]], ["a_atlas.png", "b_atlas.json"])
            self.assertTrue((d / "store" / "manifests" / "maps-classic-4x" / "m.json").is_file())
            self.assertEqual(mu.fetch(d / "out", d / "m.json", root=d / "store"), 2)
            self.assertEqual((d / "out" / "a_atlas.png").read_bytes(), b"one")


class MemWatch(unittest.TestCase):
    def test_stops_a_growing_command_and_passes_a_small_one(self):
        import memwatch
        grow = [sys.executable, "-c", "import time\na = []\nfor i in range(60):\n    a.append(bytearray(20 << 20))\n"
                                      "    time.sleep(0.05)\n"]
        self.assertEqual(memwatch.run(grow, 200 << 20, 0.1, log=lambda s: None), 137)
        self.assertEqual(memwatch.run([sys.executable, "-c", "pass"], 200 << 20, 0.1, log=lambda s: None), 0)


class Audit(unittest.TestCase):
    def test_identical_pictures_score_high(self):
        import maps_audit as ma
        fr = Frame(0, 0, 3, 3, 1.0, 40, 40)
        W, H = fr.size
        rng = np.random.default_rng(1)
        full = np.ones((H, W, 4), np.float32)
        full[..., :3] = rng.random((H, W, 3))
        st = np.zeros((H, W, 4), np.float32)
        st[10:30, 10:60] = 1
        cells = [(x, y) for x in range(4) for y in range(4)]
        ht = st.copy()
        ht[..., :3] = 0.5 * st[..., 3:4]          # standing: half of 20 units high
        m = ma.measures(st, full, full, ht, full, fr, cells)
        self.assertEqual(m["missing"], 0.0)
        self.assertEqual(m["extra"], 0.0)
        self.assertGreater(m["edges"], 0.99)
        self.assertGreater(m["floor_corr"], 0.99)
        self.assertGreater(m["score"], 99.0)

    def test_missing_walls_counted(self):
        import maps_audit as ma
        fr = Frame(0, 0, 3, 3, 1.0, 40, 40)
        W, H = fr.size
        full = np.ones((H, W, 4), np.float32) * 0.5
        st = np.zeros((H, W, 4), np.float32)
        st[10:30, 10:60] = 1
        m = ma.measures(st, full, full, np.zeros_like(st), full, fr, [])
        self.assertEqual(m["missing"], 1.0)


class LowerWalls(unittest.TestCase):
    def test_paint_shows_where_the_upright_curtain_would(self):
        import sprite_scene as ss
        import walls_sprite as ws
        from hdkit.view import camera
        cam = camera.OrthoCamera(camera.GAME_EL, camera.GAME_AZ, 8 * np.sqrt(2.0))   # 1 classic px per px
        rect, uv = (0, -100, 160, -20), (0.0, 0.0, 1.0, 1.0)    # above the floor line, where the curtain exists
        px = lambda ps: np.round(cam.to_pixels(np.array(ps, float), (0, 0)), 3).tolist()   # noqa: E731
        lv, lt = ss.lower_mesh(rect, uv)
        cv, _ct = ws.tile_mesh(rect, uv, "floor", ss.PX_HEIGHT)
        tops = px([p for p, _n, _t, q in cv if q[1] == 0.0 and q[0] in (0.0, 1.0)])
        self.assertEqual(len(tops), 2)
        got = px([p for p, *_r in lv])
        self.assertEqual(sorted(tops), sorted(got[:2]))            # the paint's top corners are the curtain's
        self.assertEqual(sorted(map(tuple, got)), [(-80.0, -20.0), (-80.0, 60.0), (80.0, -20.0), (80.0, 60.0)])
        for p, *_r in lv:                                          # over the black ground, under the floor art
            self.assertAlmostEqual(p[1], ss.LOWER_LIFT)
            self.assertLess(p[1], ws.FLOOR_LIFT)

    def test_skirt_draws_the_picture_under_the_floor_line_where_classic_does(self):
        import sprite_scene as ss
        import walls_sprite as ws
        from hdkit.view import camera
        cam = camera.OrthoCamera(camera.GAME_EL, camera.GAME_AZ, 8 * np.sqrt(2.0))
        rect, uv = (0, -60, 160, 40), (0.0, 0.0, 1.0, 1.0)     # frame rows 20..120: across the floor line
        x0, y0, x1, y1 = rect
        sv, st = ss.skirt_mesh(rect, uv)
        self.assertTrue(st)
        for p, _n, _t, (u, v) in sv:          # each vertex shows its own picture pixel where classic draws it
            want = (x0 + u * (x1 - x0) - ws.KINK, y0 + ws.WALL_Y + v * (y1 - y0))
            got = cam.to_pixels(np.array([p], float), (0, 0))[0]
            self.assertAlmostEqual(got[0], want[0], 3)
            self.assertAlmostEqual(got[1], want[1], 3)
            self.assertAlmostEqual(p[1], ss.SKIRT_LIFT)
            self.assertGreaterEqual(want[1] + 1e-6, ws.foot(want[0] + ws.KINK))   # only under the floor line
        # the skirt covers exactly the picture's pixels under the floor line (rows 20..120, line |x - 80| / 2)

        def area(vs, ts):
            P = cam.to_pixels(np.array([q[0] for q in vs], float), (0, 0))
            cr = lambda e, f: e[0] * f[1] - e[1] * f[0]   # noqa: E731
            return sum(abs(cr(P[b] - P[a], P[c] - P[a])) / 2 for a, b, c in ts)
        cols = np.arange(x0, x1) + 0.5
        under = np.clip((y1 + ws.WALL_Y) - np.maximum(ws.foot(cols), y0 + ws.WALL_Y), 0, None).sum()
        self.assertAlmostEqual(area(sv, st), float(under), 3)
        self.assertEqual(ss.skirt_mesh((0, -200, 160, -160), uv), ([], []))   # all above the line: no skirt

    def test_lower_walls_only_in_the_classic_build(self):
        import sprite_scene as ss
        self.assertEqual(ss.CLASS_OF[17], ss.LOWER)
        self.assertFalse(ss.LOWER_ORIENTATIONS & set(ss.MapHandle.walls.__defaults__[0]))


class Crop(unittest.TestCase):
    def test_floor_chunks_reaching_into_a_crop_are_kept(self):
        from types import SimpleNamespace as NS
        from hdkit.view.mapview import hd
        fr = Frame(40, 40, 45, 45, 1.0, 128, 128)

        def pl(model, cx, cy):
            m = np.eye(4)
            m[0, 3], m[2, 3] = cx * 10.0, cy * 10.0
            return NS(kind="model", wall=False, model=model, matrix=m)
        chunk = "data/hd/env/model/mxl/wallsprite/m/cypherpunk/rock_2_2.model"
        sc = NS(placements=[pl(chunk, 32, 32), pl("data/hd/env/model/x/prop.model", 32, 32), pl(chunk, 64, 64)])
        got = [p.model for p in hd.select(sc, fr, {"props"})]
        self.assertEqual(got, [chunk])             # the chunk from (32, 32) covers the crop; the prop there does not

    def test_cull_on_the_screen_not_in_a_box_of_cells(self):
        from types import SimpleNamespace as NS
        from hdkit.view.mapview import hd
        fr = Frame(12, 57, 18, 63, 3.6)                       # a 4K crop of Fauztinville

        def pl(cx, cy):
            m = np.eye(4)
            m[0, 3], m[2, 3] = cx * 10.0, cy * 10.0
            return NS(kind="model", wall=True, model="data/hd/env/model/x/wall.model", matrix=m)
        on_screen = pl(8.7, 57.5)          # 4 cells before the crop's x range, yet on its left side on the screen
        far = pl(60.0, 10.0)               # far off to the right and above
        got = hd.select(NS(placements=[on_screen, far]), fr, {"walls"})
        self.assertEqual(got, [on_screen])


class Rounds(unittest.TestCase):
    def test_list_and_serve_only_below_root(self):
        import os
        import tempfile
        import threading
        import urllib.error
        import urllib.request
        from hdkit.view.mapview import webmap
        with tempfile.TemporaryDirectory() as d:
            st = Path(d) / "r1" / "cypherpunk"
            st.mkdir(parents=True)
            for n in ("2_hd.png", "1_classic.png", "x.txt"):
                (st / n).write_bytes(b"\x89PNG")
            (st / "note.txt").write_text("hi")
            (Path(d) / "secret.png").write_bytes(b"no")
            got = webmap.list_rounds(Path(d))
            self.assertEqual(got[0]["sets"][0]["pics"], ["1_classic.png", "2_hd.png"])
            self.assertEqual(got[0]["sets"][0]["note"], "hi")
            os.environ["MXL_ROUNDS"] = str(Path(d) / "r1" / "..")
            ready = threading.Event()
            box = {}
            t = threading.Thread(target=webmap.serve, kwargs={"port": 0, "ready": lambda s, u: (box.update(s=s, u=u),
                                                                                              ready.set())}, daemon=True)
            t.start()
            ready.wait(5)
            try:
                ok = urllib.request.urlopen(box["u"] + "rounds/r1/cypherpunk/1_classic.png").read()
                self.assertEqual(ok, b"\x89PNG")
                for bad in ("rounds/r1/cypherpunk/x.txt", "rounds/r1/%2e%2e/%2e%2e/secret.png", "rounds/../secret.png"):
                    with self.assertRaises(urllib.error.HTTPError):
                        urllib.request.urlopen(box["u"] + bad)
                self.assertIn(b"Map rounds", urllib.request.urlopen(box["u"] + "rounds").read())
            finally:
                box["s"].shutdown()
                os.environ.pop("MXL_ROUNDS")


if __name__ == "__main__":
    unittest.main()
