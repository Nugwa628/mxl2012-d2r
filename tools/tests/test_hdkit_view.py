"""hdkit.view (the CASC-free model viewer) and hdkit.gpugate: file layer, camera, tiling, PNG streaming, colour and image
measures, the GPU gate's parser and decisions. No GPU needed; the one GPU test runs only with HDKIT_GPU_TESTS=1 and wgpu."""
import io
import math
import os
import sys
import tempfile
import unittest
import zlib
from pathlib import Path

import numpy as np

TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))
import projtemp  # noqa: E402,F401  (temp files stay inside the project, tools/projtemp.py)
from hdkit import gpugate  # noqa: E402
from hdkit.view import camera, gpu, metrics, scene, tiling, vfs  # noqa: E402


class FileLayer(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        base = Path(self.tmp.name)
        self.mod, self.game = base / "mod", base / "game"
        for root, text in ((self.mod, b"mod"), (self.game, b"game")):
            (root / "hd" / "Character").mkdir(parents=True)
            (root / "hd" / "Character" / "Unit.json").write_bytes(text)
        (self.game / "hd" / "Character" / "only_game.txt").write_bytes(b"g")

    def tearDown(self):
        self.tmp.cleanup()

    def test_normalise(self):
        self.assertEqual(vfs.normalise("Data\\HD\\Character\\X.Json"), "hd/character/x.json")
        self.assertEqual(vfs.normalise("./data/hd/a.txt"), "hd/a.txt")
        self.assertEqual(vfs.normalise("/hd/a.txt"), "hd/a.txt")

    def test_first_root_wins_and_is_recorded(self):
        fs = vfs.Layered([("mod", self.mod), ("game", self.game)])
        self.assertEqual(fs.read("data/hd/character/unit.json"), b"mod")
        self.assertEqual(fs.read("HD/CHARACTER/ONLY_GAME.TXT"), b"g")
        prov = {p["logical"]: p["root"] for p in fs.provenance()}
        self.assertEqual(prov, {"hd/character/unit.json": "mod", "hd/character/only_game.txt": "game"})

    def test_order_matters(self):
        fs = vfs.Layered([("game", self.game), ("mod", self.mod)])
        self.assertEqual(fs.read("hd/character/unit.json"), b"game")

    def test_missing(self):
        fs = vfs.Layered([("mod", self.mod)])
        self.assertFalse(fs.exists("hd/character/only_game.txt"))
        with self.assertRaises(FileNotFoundError):
            fs.read("hd/nothing.json")

    def test_parse_roots(self):
        self.assertEqual(vfs.parse_roots(["a=x/y", "z"]), [("a", Path("x/y")), ("root2", Path("z"))])


class Camera(unittest.TestCase):
    def test_basis_orthonormal(self):
        for el in (30.0, 34.3):
            r, u, w = camera.basis(45.0, el)
            M = np.stack([r, u, w])
            self.assertTrue(np.allclose(M @ M.T, np.eye(3)))
            self.assertTrue(np.allclose(np.cross(r, u), w))

    def test_ground_grid_scale(self):
        cam = camera.OrthoCamera(30.0)
        o = np.array([800.0, 428.0])
        # one world unit along x: 12 px right and 6 px down (a sub-tile of 2 units: 24 x 12), the 2:1 ground of el 30
        self.assertTrue(np.allclose(cam.to_pixels([1, 0, 0], o) - o, [12.0, 6.0]))
        self.assertTrue(np.allclose(cam.to_pixels([0, 0, 1], o) - o, [-12.0, 6.0]))
        # one unit up: k cos(el) = 14.70 px
        self.assertAlmostEqual(float(o[1] - cam.to_pixels([0, 1, 0], o)[1]), 12 * math.sqrt(2) * math.cos(math.radians(30)))

    def test_tile_matrix_matches_pixels(self):
        cam = camera.OrthoCamera(34.3, k=50.0)
        rng = np.random.default_rng(1)
        P = rng.uniform(-3, 3, (20, 3))
        origin = (517.0, 801.0)
        for rect in ((0, 0, 1024, 1024), (512, 256, 256, 512), (1000, 900, 64, 32)):
            M = cam.matrix(origin, rect, -10.0, 10.0)
            clip = np.hstack([P, np.ones((20, 1))]) @ M.T
            self.assertTrue(np.allclose(clip[:, 3], 1.0))
            px = camera.ndc_to_pixels(clip[:, :2], rect)
            self.assertTrue(np.allclose(px, cam.to_pixels(P, origin)))
            d = clip[:, 2]
            self.assertTrue(((d >= 0) & (d <= 1)).all())
            # nearer the camera = smaller depth
            self.assertTrue(np.allclose(np.argsort(d), np.argsort(-cam.depth(P))))

    def test_unit_pixel(self):
        self.assertEqual(camera.unit_pixel(0, 0), (800.0, 437.5))
        x, y = camera.unit_pixel(10, 0)
        self.assertEqual((x - 800.0, y - 437.5), (240.0, 120.0))
        x, y = camera.unit_pixel(10, 0, 1080)          # 288 x 144 at 1080p
        self.assertAlmostEqual(x - 960.0, 288.0)
        self.assertAlmostEqual(y - 525.0, 144.0)
        # one sub-tile step is k sqrt(2) across and k / sqrt(2) down at the ground-grid scale
        self.assertAlmostEqual(camera.K_1600x900 * math.sqrt(2.0), 24.0)

    def test_facings(self):
        self.assertEqual([camera.key_dir64(k) for k in range(8)], [0, 8, 16, 24, 32, 40, 48, 56])
        self.assertEqual(camera.facing_yaw(0), 45.0)
        self.assertEqual(camera.facing_yaw(16), 45.0 - 90.0)
        self.assertEqual(camera.facing_yaw(16, 0.0, 1.0), 90.0)
        self.assertTrue(np.allclose(camera.rot_y(90) @ [0, 0, 1], [1, 0, 0]))


class Tiling(unittest.TestCase):
    def test_plan_covers_once(self):
        for W, H, t in ((100, 70, 32), (64, 64, 64), (1, 1, 8), (16384, 300, 4096)):
            cover = np.zeros((H, W), int)
            for x0, y0, w, h in tiling.plan(W, H, t):
                self.assertTrue(0 < w <= t and 0 < h <= t)
                cover[y0:y0 + h, x0:x0 + w] += 1
            self.assertTrue((cover == 1).all())
        with self.assertRaises(ValueError):
            tiling.plan(0, 5, 4)

    def test_rows(self):
        rows = tiling.rows(tiling.plan(100, 70, 32))
        self.assertEqual(len(rows), 3)
        self.assertEqual([len(r) for r in rows], [4, 4, 4])
        self.assertTrue(all(len({t[1] for t in r}) == 1 for r in rows))

    def test_seam_windows(self):
        W, H, t = 100, 70, 32
        wins = tiling.seam_windows(W, H, t, half=4)
        # 3 inner vertical edges x 3 tile rows + 2 inner horizontal edges x 4 tile columns
        self.assertEqual(len(wins), 3 * 3 + 2 * 4)
        for x0, y0, w, h in wins:
            self.assertTrue(0 <= x0 and 0 <= y0 and x0 + w <= W and y0 + h <= H)
        dense = tiling.seam_windows(W, H, t, half=4, every=8)
        self.assertGreater(len(dense), len(wins))
        for x0, y0, w, h in dense:
            on_v = any(x0 < e < x0 + w for e in range(t, W, t))
            on_h = any(y0 < e < y0 + h for e in range(t, H, t))
            self.assertTrue(on_v or on_h)

    def test_stitch(self):
        img = np.arange(70 * 100 * 4, dtype=np.uint32).reshape(70, 100, 4) % 251
        parts = [(r, img[r[1]:r[1] + r[3], r[0]:r[0] + r[2]]) for r in tiling.plan(100, 70, 32)]
        self.assertTrue((tiling.stitch(parts, 100, 70, 4, np.uint32) == img).all())

    def test_png_stream_roundtrip(self):
        from PIL import Image
        rng = np.random.default_rng(2)
        img = rng.integers(0, 256, (37, 23, 4), dtype=np.uint8)
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "x.png"
            png = tiling.PngStream(p, 23, 37, 4)
            png.write(img[:10])
            png.write(img[10:11])
            png.write(img[11:])
            png.close()
            with Image.open(p) as im:
                back = np.array(im)
            self.assertTrue((back == img).all())
            png = tiling.PngStream(Path(d) / "y.png", 4, 2, 3)
            with self.assertRaises(ValueError):
                png.write(np.zeros((3, 4, 3), np.uint8))
            with self.assertRaises(ValueError):
                png.close()
            png.f.close()


class Colour(unittest.TestCase):
    def test_srgb_roundtrip(self):
        x = np.linspace(0, 1, 101)
        self.assertTrue(np.allclose(gpu.srgb_decode(gpu.srgb_encode(x)), x, atol=1e-6))
        self.assertAlmostEqual(float(gpu.srgb_encode(np.array(0.5))), 0.7354, places=3)

    def test_box_down(self):
        a = np.arange(16, dtype=float).reshape(4, 4, 1)
        self.assertTrue(np.allclose(gpu.box_down(a, 2)[..., 0], [[2.5, 4.5], [10.5, 12.5]]))
        self.assertIs(gpu.box_down(a, 1), a)

    def test_to_uint8_straight_alpha(self):
        lin = np.zeros((1, 3, 4))
        lin[0, 0] = (0.25, 0.25, 0.25, 0.5)      # premultiplied grey 0.5 at half cover
        lin[0, 1] = (1, 1, 1, 1)
        out = gpu.to_uint8(lin, "lit")
        self.assertEqual(out[0, 0].tolist(), [188, 188, 188, 128])
        self.assertEqual(out[0, 1].tolist(), [255, 255, 255, 255])
        self.assertEqual(out[0, 2].tolist(), [0, 0, 0, 0])
        over = gpu.to_uint8(lin, "lit", bg=(0.0, 0.0, 0.0))
        self.assertEqual(over[0, 0, 3], 255)
        self.assertEqual(int(over[0, 0, 0]), int(round(255 * float(gpu.srgb_encode(np.array(0.25))))))
        self.assertEqual(gpu.to_uint8(lin, "normals")[0, 0, 0], 128)    # data passes are not sRGB-encoded

    def test_card_mips_keep_colour(self):
        img = np.zeros((4, 4, 4), np.uint8)
        img[:2, :2] = (200, 50, 10, 255)            # one opaque quarter, the rest transparent black
        mips = gpu._mip_chain(img)
        self.assertEqual([m.shape[:2] for m in mips], [(4, 4), (2, 2), (1, 1)])
        self.assertEqual(mips[1][0, 0].tolist(), [200, 50, 10, 255])
        self.assertEqual(mips[2][0, 0, :3].tolist(), [200, 50, 10])      # no dark fringe from the transparent texels
        self.assertEqual(int(mips[2][0, 0, 3]), 64)


class Measures(unittest.TestCase):
    def test_image(self):
        img = np.zeros((10, 8, 4), np.uint8)
        img[2:7, 3:5] = (100, 100, 100, 255)
        m = metrics.image(img)
        self.assertEqual((m["height_px"], m["width_px"], m["covered_px"]), (5, 2, 10))
        self.assertEqual(m["bbox"], [3, 2, 5, 7])
        self.assertAlmostEqual(m["luma_mean"], 100.0, places=3)
        self.assertEqual(sum(m["hist16"]), 1.0)
        self.assertEqual(metrics.image(np.zeros((4, 4, 4), np.uint8))["height_px"], 0)

    def test_iou(self):
        a = np.zeros((4, 4), bool)
        b = a.copy()
        a[:2], b[1:3] = True, True
        self.assertAlmostEqual(metrics.iou(a, b), 4 / 12)
        self.assertEqual(metrics.iou(np.zeros((2, 2)), np.zeros((2, 2))), 0.0)

    def test_texels_per_pixel(self):
        scr = np.array([[[0, 0], [10, 0], [0, 10]]] * 3, float)
        tex = scr * 2.0                             # every pixel covers 2 x 2 texels
        self.assertEqual(metrics.texels_per_pixel(scr, tex)["median"], 2.0)
        self.assertEqual(metrics.texels_per_pixel(scr[:, :, :] * 0, tex)["triangles"], 0)


class Card(unittest.TestCase):
    def test_corners(self):
        b = 20
        q = scene.card_corners(-10, -30, 12, b, b)
        # the frame's lowest row sits on the ground (y 0), one row up is 1/9.798 unit higher
        self.assertTrue(np.allclose(q[2:, 1], 0.0))
        self.assertAlmostEqual(q[0, 1], (b + 30) / (8 * math.sqrt(1.5)))
        # the anchor column stands at (b/8, b/8): the card faces the az-45 camera (its width runs along x - z)
        self.assertTrue(np.allclose(scene.card_corners(0, 0, 0, b, b)[3], [b / 8, 0, b / 8]))
        r, _u, w = camera.basis(45.0, 30.0)
        self.assertAlmostEqual(float(np.dot(q[1] - q[0], w)), 0.0)


class Gate(unittest.TestCase):
    SAMPLE = ('"(PDH-CSV 4.0)","\\\\PC\\GPU Engine(pid_1_luid_0x0_0xA_phys_0_eng_0_engtype_3D)\\Utilization Percentage",'
              '"\\\\PC\\GPU Engine(pid_2_luid_0x0_0xA_phys_0_eng_0_engtype_3D)\\Utilization Percentage",'
              '"\\\\PC\\GPU Engine(pid_2_luid_0x0_0xA_phys_0_eng_5_engtype_Compute_0)\\Utilization Percentage",'
              '"\\\\PC\\Processor(_Total)\\% Processor Time"\n'
              '"11/19/2026 10:00:00.000","12.5","20.0","7.0","33.3"\n')

    def test_parse(self):
        gpu_pct, eng, cpu = gpugate.parse_typeperf(self.SAMPLE)
        self.assertAlmostEqual(gpu_pct, 32.5)       # two processes on one engine add up
        self.assertEqual(eng, "3D")
        self.assertAlmostEqual(cpu, 33.3)
        self.assertEqual(gpugate.parse_typeperf("nothing"), (None, "", None))

    def test_decisions(self):
        with tempfile.TemporaryDirectory() as d:
            glob = [os.path.join(d, "game.lock*")]
            self.assertTrue(gpugate.check(glob, counters=lambda: (3.0, "3D", 10.0)).free)
            self.assertFalse(gpugate.check(glob, counters=lambda: (55.0, "3D", 10.0)).free)
            self.assertFalse(gpugate.check(glob, counters=lambda: (3.0, "3D", 95.0)).free)
            self.assertFalse(gpugate.check(glob, counters=lambda: (None, "", None)).free)
            self.assertTrue(gpugate.check(glob, counters=lambda: (None, "", 10.0)).free)
            Path(d, "game.lock.2").write_text("x")
            rd = gpugate.check(glob, counters=lambda: (0.0, "3D", 0.0))
            self.assertFalse(rd.free)
            self.assertIn("game.lock.2", rd.why)


@unittest.skipUnless(os.environ.get("HDKIT_GPU_TESTS") == "1", "GPU test: set HDKIT_GPU_TESTS=1 (and have wgpu)")
class GpuProbe(unittest.TestCase):
    def test_probe(self):
        try:
            import wgpu  # noqa: F401
        except ImportError:
            self.skipTest("wgpu not installed")
        p = gpu.probe()
        self.assertTrue(p["msaa_rgba16float"][1]["ok"])
        self.assertEqual(p["msaa_rgba16float"][1]["rgb_centre"], [1.0, 0.5, 0.25])


if __name__ == "__main__":
    unittest.main()
