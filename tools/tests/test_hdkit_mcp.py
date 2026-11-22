"""hdkit.view asset listing, render-vs-shot compare, the content store, camera facts, the new CLI commands and the stdio MCP
server over them. No GPU needed; the MCP tests skip without the `mcp` package, the GPU render test runs only with
HDKIT_GPU_TESTS=1 (and wgpu and mcp)."""
import asyncio
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import numpy as np

TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))
import projtemp  # noqa: E402,F401  (temp files stay inside the project, tools/projtemp.py)
from hdkit import gpugate, store  # noqa: E402
from hdkit.view import assets, camera, cli, compare, vfs  # noqa: E402

try:
    import mcp  # noqa: F401
    HAVE_MCP = True
except ImportError:
    HAVE_MCP = False


def _touch(p: Path, data=b"x"):
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(data)
    return p


def _save(arr, p):
    from PIL import Image
    Image.fromarray(arr).save(p)
    return str(p)


def scene_pair(shift=(0, 0), seed=1):
    """A textured ground (twin), the same with a two-colour disk unit at feet (60, 80) (shot), and a render of the disk
    drawn `shift` px away (RGBA, feet at (60, 80) + shift)."""
    rng = np.random.default_rng(seed)
    twin = rng.integers(40, 90, (120, 120, 3)).astype(np.uint8)
    yy, xx = np.mgrid[:120, :120]
    disk = (xx - 60) ** 2 + (yy - 60) ** 2 <= 18 ** 2
    top = disk & (yy < 50)
    shot = twin.copy()
    shot[disk] = (20, 30, 160)
    shot[top] = (200, 230, 250)
    render = np.zeros((120, 120, 4), np.uint8)
    d2 = np.roll(np.roll(disk, shift[1], 0), shift[0], 1)
    t2 = np.roll(np.roll(top, shift[1], 0), shift[0], 1)
    render[d2] = (20, 30, 160, 255)
    render[t2] = (200, 230, 250, 255)
    return shot, twin, render, disk


class Walk(unittest.TestCase):
    def test_units_models_resolve(self):
        with tempfile.TemporaryDirectory() as d:
            a, b = Path(d) / "a", Path(d) / "b"
            _touch(a / "hd/character/enemy/Fungus.json", b"{}")
            _touch(a / "hd/character/enemy/fungus/fungus_state_machine.json", b"{}")
            _touch(b / "hd/character/enemy/mummy1.json", b"{}")
            _touch(b / "hd/character/enemy/fungus.json", b"{}")
            _touch(a / "hd/character/enemy/fungus/torso_lod0.model")
            _touch(b / "hd/character/enemy/fungus/torso_lod0.model")
            _touch(b / "hd/character/enemy/mummy1/mummy1_lod0.model")
            fs = vfs.Layered([("a", a), ("b", b)])
            u = assets.units(fs)
            self.assertEqual([x["logical"] for x in u], ["hd/character/enemy/fungus.json", "hd/character/enemy/mummy1.json"])
            self.assertEqual(u[0]["root"], "a")
            m = assets.models(fs)
            self.assertEqual(len(m), 2)
            self.assertEqual({x["root"] for x in m if "fungus" in x["logical"]}, {"a"})
            self.assertEqual(len(assets.models(fs, "mummy")), 1)
            self.assertEqual(len(assets.models(fs, "*/fungus/*.model")), 1)
            lst = assets.listing(fs, "units", limit=1)
            self.assertEqual((lst["total"], lst["shown"]), (2, 1))
            r = assets.resolve(fs, "Data/HD/character/enemy/fungus/torso_lod0.model")
            self.assertEqual((r["found"], r["root"], r["also_in"]), (True, "a", ["b"]))
            self.assertFalse(assets.resolve(fs, "hd/none.json")["found"])
            self.assertEqual(fs.provenance(), [{"logical": "hd/character/enemy/fungus/torso_lod0.model", "root": "a",
                                                "path": str(a / "hd/character/enemy/fungus/torso_lod0.model")}])
            with self.assertRaises(ValueError):
                assets.listing(fs, "clips")
            with self.assertRaises(ValueError):
                assets.listing(fs, "maps")


class Compare(unittest.TestCase):
    def test_twin_mask_and_measures(self):
        shot, twin, render, disk = scene_pair()
        res, extra = compare.compare(render, shot, (60, 80), (60, 80), twin=twin)
        self.assertEqual(res["mask"], "twin")
        self.assertGreater(res["iou_at_feet"], 0.97)
        self.assertEqual(res["shift"], [0, 0])
        self.assertAlmostEqual(res["luma_ratio"], 1.0, places=3)
        self.assertEqual(res["cap_game"], [200.0, 230.0, 250.0])
        self.assertEqual(res["cap_distance"], 0.0)
        self.assertEqual(compare.panel(render, extra, res).shape, (120, 244, 3))

    def test_shift_found(self):
        shot, twin, render, _ = scene_pair(shift=(4, -3))
        res, _e = compare.compare(render, shot, (60, 80), (60, 80), twin=twin, reach=6)
        self.assertLess(res["iou_at_feet"], 0.8)
        self.assertEqual(res["shift"], [-4, 3])
        self.assertGreater(res["iou_best"], 0.97)

    def test_cut_feet_and_given_mask_and_exclude(self):
        shot, twin, render, disk = scene_pair()
        big = np.zeros((300, 300, 3), np.uint8)
        big[100:220, 50:170] = shot
        bmask = np.zeros((300, 300), bool)
        bmask[100:220, 50:170] = disk
        res, _e = compare.compare(render, big, (110, 180), (60, 80), shot_mask=bmask, exclude=[(110, 100, 170, 220)])
        self.assertEqual(res["mask"], "given")
        self.assertLess(res["game_px"], disk.sum() * 0.6)
        with self.assertRaises(ValueError):
            compare.compare(render, big, (110, 180))

    def test_parts(self):
        a = np.zeros((20, 20), bool)
        a[5:10, 5:10] = True
        self.assertEqual(compare.best_shift(np.roll(a, 2, 1), a, reach=3)[1:], (-2, 0))
        self.assertIsNone(compare.cap_colour(np.zeros((4, 4, 3)), np.zeros((4, 4), bool)))
        self.assertIsNone(compare.luma_median(np.zeros((4, 4, 3)), np.zeros((4, 4), bool)))
        self.assertEqual(compare.cut(np.arange(16).reshape(4, 4), (1, 1), (0, 0), (2, 2)).tolist(), [[5, 6], [9, 10]])
        self.assertEqual(compare.cut(np.ones((4, 4)), (0, 0), (5, 5), (3, 3)).sum(), 0)


class Store(unittest.TestCase):
    def test_put_and_offload(self):
        with tempfile.TemporaryDirectory() as d:
            st, out = Path(d) / "store", Path(d) / "out"
            big, small = _touch(out / "big.png", b"B" * 5000), _touch(out / "small.png", b"s")
            again = _touch(out / "again.png", b"B" * 5000)
            moved = store.offload([big, small, again, out / "missing.png"], 1000, out / "art-manifest.json", {"t": 1}, st)
            self.assertEqual(set(moved), {str(big), str(again)})
            e = moved[str(big)]
            obj = st / "objects" / "sha256" / e["sha256"][:2] / e["sha256"]
            self.assertEqual(Path(e["object"]), obj)
            self.assertEqual(obj.read_bytes(), b"B" * 5000)
            self.assertFalse(big.exists())
            self.assertTrue(small.exists())
            self.assertEqual(list((st / "tmp").iterdir()), [])
            man = json.loads((out / "art-manifest.json").read_text("utf-8"))
            self.assertEqual(len(man["files"]), 2)
            self.assertTrue((st / "manifests" / "hdkit-view" / "out_art-manifest.json").exists())

    def test_root(self):
        with mock.patch.dict(os.environ, {"HDKIT_STORE": "X:/s"}):
            self.assertEqual(store.root(), Path("X:/s"))
        with mock.patch.dict(os.environ, {"HDKIT_STORE": "", "MXL_ART_STORE": "Y:/art"}):
            self.assertEqual(store.root(), Path("Y:/art"))

    def test_cli_finish(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "o"
            png = _touch(out / "u_k0.png", b"P" * 3000)
            a = cli.build_parser().parse_args(["render", "x.json", "--store-min-mb", "0.001", "--out", str(out)])
            rep = {"images": [{"png": str(png)}], "sheet": None}
            with mock.patch.dict(os.environ, {"HDKIT_STORE": str(Path(d) / "st")}):
                cli._finish(a, rep, out)
            self.assertIn("stored", rep["images"][0])
            self.assertTrue((out / "art-manifest.json").exists())
            self.assertEqual(json.loads((out / "metrics.json").read_text("utf-8"))["stored"][0]["size"], 3000)


class CameraAndCli(unittest.TestCase):
    def test_facts(self):
        f = camera.facts(1080)
        self.assertAlmostEqual(f["px_per_unit"], 1080 / 53.03, places=3)
        self.assertEqual(f["feet_px_16x9"], [960.0, 525.0])
        self.assertEqual(f["subtile_step_px"], [28.8, 14.4])
        self.assertEqual(camera.facts()["projection"], "orthographic")

    def test_info_and_compare_cmd(self):
        cam = cli.info_cmd(cli.build_parser().parse_args(["camera", "--height", "900"]))
        self.assertAlmostEqual(cam["px_per_unit"], 16.9715, places=3)
        with mock.patch.object(gpugate, "read_counters", lambda: (1.0, "3D", 5.0)), \
                mock.patch.dict(os.environ, {"HDKIT_LOCK_GLOBS": "Z:/no/such/lock*"}):
            self.assertTrue(cli.info_cmd(cli.build_parser().parse_args(["gate"]))["free"])
        shot, twin, render, _ = scene_pair()
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)
            a = cli.build_parser().parse_args(["compare", _save(render, p / "r.png"), _save(shot, p / "s.png"),
                                               "--twin", _save(twin, p / "t.png"), "--shot-feet", "60,80",
                                               "--render-feet", "60,80", "--panel", str(p / "panel.png"),
                                               "--out", str(p / "c.json")])
            res = cli.compare_cmd(a)
            self.assertGreater(res["iou_best"], 0.97)
            self.assertTrue((p / "panel.png").exists())
            self.assertEqual(json.loads((p / "c.json").read_text("utf-8"))["shift"], [0, 0])


def _call(srv, name, args):
    r = asyncio.run(srv.call_tool(name, args))
    blocks = r[0] if isinstance(r, tuple) else r
    text = next(b.text for b in blocks if b.type == "text")
    return json.loads(text), [b for b in blocks if b.type == "image"]


@unittest.skipUnless(HAVE_MCP, "needs the mcp package (official Python SDK) in this python")
class McpServer(unittest.TestCase):
    def setUp(self):
        from hdkit.view import mcp_server
        self.m = mcp_server
        self.srv = mcp_server.build()

    def test_tools_listed(self):
        names = [t.name for t in asyncio.run(self.srv.list_tools())]
        self.assertEqual(sorted(names), sorted(self.m.TOOL_NAMES))

    def test_argv(self):
        self.assertEqual(self.m.argv_of("render", ["u.json"], {"root": ["a=1", "b=2"], "no_glow": True, "glow_gain": None,
                                                                "hide": None, "ss": 4, "dir64": "3,5"}),
                         ["render", "u.json", "--root", "a=1", "--root", "b=2", "--no-glow", "--ss", "4", "--dir64", "3,5"])
        with self.assertRaises(ValueError):
            self.m.parse(["render"])

    def test_gpu_refused_politely(self):
        busy = gpugate.Reading(locks=["game.lock.2"], why="lock held: game.lock.2")
        with mock.patch.dict(self.m._STATE, {"renderer": None, "sessions": {}}), \
                mock.patch.object(self.m.gpugate, "check", lambda *a, **k: busy):
            for tool in ("view_render", "view_sheet", "view_turntable"):
                res, imgs = _call(self.srv, tool, {"asset": "hd/x.json", "roots": ["a=."]})
                self.assertTrue(res["refused"])
                self.assertIn("game.lock.2", res["why"])
                self.assertEqual(imgs, [])
            self.assertIsNone(self.m._STATE["renderer"])     # no GPU device was even opened

    def test_data_tools(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / "r"
            _touch(root / "hd/character/enemy/fungus.json", b"{}")
            res, _ = _call(self.srv, "view_assets", {"kind": "units", "roots": ["r=%s" % root]})
            self.assertEqual(res["items"][0]["logical"], "hd/character/enemy/fungus.json")
            res, _ = _call(self.srv, "view_resolve", {"path": "data/hd/character/enemy/fungus.json",
                                                      "roots": ["r=%s" % root]})
            self.assertEqual(res["root"], "r")
            res, _ = _call(self.srv, "view_camera", {"height": 1080})
            self.assertAlmostEqual(res["px_per_unit"], 20.366, places=2)
            res, _ = _call(self.srv, "view_rig_load", {"spec": "game"})
            self.assertEqual(res["tone"], "game")
            res, _ = _call(self.srv, "view_rig_save", {"path": str(Path(d) / "rig.json"), "spec": "game",
                                                       "changes": {"exposure": 0.25, "meta": {"by": "test"}}})
            self.assertEqual(res["rig"]["exposure"], 0.25)
            self.assertEqual(res["rig"]["meta"]["by"], "test")
            self.assertEqual(json.loads((Path(d) / "rig.json").read_text("utf-8"))["tone"], "game")

    def test_compare_tool(self):
        shot, twin, render, _ = scene_pair(shift=(2, 0))
        with tempfile.TemporaryDirectory() as d:
            p = Path(d)
            with mock.patch.dict(os.environ, {"HDKIT_VIEW_OUT": str(p / "out")}):
                res, imgs = _call(self.srv, "view_compare", {"render": _save(render, p / "r.png"),
                                                             "shot": _save(shot, p / "s.png"),
                                                             "twin": _save(twin, p / "t.png"),
                                                             "shot_feet": [60, 80], "render_feet": [60, 80]})
            self.assertEqual(res["shift"], [-2, 0])
            self.assertTrue(Path(res["panel"]).is_file())
            self.assertTrue(str(res["panel"]).startswith(str(p / "out")))
            self.assertEqual(len(imgs), 1)


@unittest.skipUnless(HAVE_MCP and os.environ.get("HDKIT_GPU_TESTS") == "1",
                     "GPU test: set HDKIT_GPU_TESTS=1 (and have wgpu and mcp)")
class McpGpu(unittest.TestCase):
    def test_card_render_through_the_server(self):
        from PIL import Image
        from hdkit.view import mcp_server, scene
        with tempfile.TemporaryDirectory() as d:
            fr = Path(d) / "frames"
            (fr / "nu").mkdir(parents=True)
            (fr / "frames.json").write_text(json.dumps({"nu": {"box": [-16, -48], "frames": 1}}), "utf-8")
            img = np.zeros((48, 32, 4), np.uint8)
            img[8:46, 6:26] = (200, 120, 40, 255)
            Image.fromarray(img).save(fr / "nu" / ("d%d_f00.png" % scene.CLOCKWISE_8[0]))
            srv = mcp_server.build()
            free = gpugate.Reading(free=True, why="free")
            with mock.patch.object(mcp_server.gpugate, "check", lambda *a, **k: free), \
                    mock.patch.dict(os.environ, {"HDKIT_VIEW_OUT": str(Path(d) / "out")}):
                res, imgs = _call(srv, "view_render", {"asset": "card:%s" % fr, "mode": "nu", "size": "96x96",
                                                       "ss": 1, "bg": "#000000"})
            self.assertNotIn("refused", res)
            png = Path(res["images"][0]["png"])
            self.assertTrue(png.is_file())
            self.assertGreater(res["images"][0]["measures"]["coverage"], 0)
            self.assertEqual(len(imgs), 1)
            self.assertTrue(Path(res["metrics"]).is_file())


if __name__ == "__main__":
    unittest.main()
