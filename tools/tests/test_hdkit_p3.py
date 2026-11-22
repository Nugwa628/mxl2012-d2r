"""hdkit.view light rigs, the game tone chain, layer toggles, contact sheets, turntable files and the watch loop.
No GPU needed (Prepared.select works on stand-in draws)."""
import json
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

import numpy as np

TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))
import projtemp  # noqa: E402,F401  (temp files stay inside the project, tools/projtemp.py)
from hdkit.view import cli, gpu, rig, sheets, tone  # noqa: E402


class Rigs(unittest.TestCase):
    def test_game_exposure(self):
        self.assertAlmostEqual(rig.exposure_for_ev(4.0), 0.0731, places=4)
        g = rig.game()
        self.assertEqual(g.tone, "game")
        self.assertIsNone(g.lut)
        self.assertAlmostEqual(g.light.key_col[0], 30 * 0.4, places=6)
        self.assertTrue(any("LUT" in u for u in g.unknown))

    def test_round_trip(self):
        with tempfile.TemporaryDirectory() as d:
            g = rig.game()
            p = g.save(Path(d) / "r.json")
            back = rig.resolve(str(p))
            self.assertEqual(back.as_dict(), g.as_dict())
            d2 = json.loads(p.read_text("utf-8"))
            d2["extra"] = 1
            p.write_text(json.dumps(d2), "utf-8")
            self.assertEqual(rig.load(p).meta["extra"], 1)

    def test_from_vis(self):
        vis = {"entities": [
            {"name": "vd", "components": [{"type": "VisualDataComponent", "exposureValue": 3,
                                           "characterBrightnessFactor": 0.5, "depthFogDensity": 0.15,
                                           "depthFogColor": {"x": 0.3, "y": 0.4, "z": 0.5}}]},
            {"name": "player_key_light", "components": [
                {"type": "DirectionalLightDefinitionComponent", "power": 20, "color": {"x": 1, "y": 0.5, "z": 0.25},
                 "lightMask": 68}]},
            {"name": "global_key", "components": [
                {"type": "DirectionalLightDefinitionComponent", "power": 4.5, "color": {"x": 0.4, "y": 0.45, "z": 1},
                 "lightMask": 9}]},
            {"name": "monster_fill_light", "components": [
                {"type": "TransformDefinitionComponent",
                 "orientation": {"x": -0.316228, "y": 0.632456, "z": -0.316228, "w": -0.632456}},
                {"type": "DirectionalLightDefinitionComponent", "power": 30, "color": {"x": 1, "y": 1, "z": 1},
                 "lightMask": 74}]}]}
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "v.json"
            p.write_text(json.dumps(vis), "utf-8")
            r = rig.resolve("vis:" + str(p))
            old = rig.from_vis(p, light_mask=None)
        self.assertAlmostEqual(r.exposure, rig.exposure_for_ev(3))
        self.assertEqual(len(r.lights), 3)
        # monster lightMask 19: monster_fill (74 & 19) is the key with its vis direction, global_key (9 & 19) a
        # directional term; player_key (68 & 19 = 0) is not used
        self.assertAlmostEqual(r.light.key_col[1], 30 * 0.5)
        self.assertTrue(np.allclose(r.light.key_dir, (0.6, 0.8, 0.0), atol=0.01))
        self.assertEqual([q["name"] for q in r.light.points], ["global_key"])
        self.assertAlmostEqual(r.light.points[0]["color"][2], 4.5 * 0.5)
        self.assertTrue(r.light.points[0]["directional"])
        self.assertEqual(r.light.fog, (0.3, 0.4, 0.5, 0.15))
        # light_mask None: the earlier rig, player key
        self.assertAlmostEqual(old.light.key_col[1], 0.5 * 20 * 0.5)
        self.assertEqual(old.light.points, ())

    def test_presets_and_default(self):
        self.assertEqual(rig.resolve(None).tone, "srgb")
        self.assertEqual(set(rig.PRESETS), {"default", "game"})
        d = rig.default()
        x = np.array([[0.0, 0.2, 1.0]])
        np.testing.assert_allclose(d.encode(x), gpu.srgb_encode(x))


class Tone(unittest.TestCase):
    def test_table(self):                      # values of viewer/re/excerpts/tonecurve.py
        for v, want in ((0.1, 0.3492), (0.5, 0.734), (1.0, 0.953)):
            self.assertAlmostEqual(float(tone.grey(v)), want, places=3)

    def test_apply_grey_and_hue(self):
        g = tone.apply(np.array([0.5, 0.5, 0.5]))
        self.assertAlmostEqual(float(g[0]), float(np.clip(tone.grey(0.5), 0, 1)), places=2)
        c = tone.apply(np.array([0.2, 0.1, 0.05]))
        self.assertTrue(c[0] > c[1] > c[2])
        self.assertTrue(np.all(tone.apply(np.array([1e3, 1e3, 1e3])) <= 1.0))
        np.testing.assert_allclose(tone.apply(np.zeros((2, 2, 3))), 0.0)

    def test_to_uint8_with_rig(self):
        lin = np.zeros((1, 2, 4))
        lin[0, 0] = (0.25, 0.25, 0.25, 0.5)     # premultiplied: straight 0.5
        out = gpu.to_uint8(lin, "lit", None, rig.game().encode)
        self.assertEqual(out[0, 0, 3], 128)
        self.assertEqual(out[0, 1, 3], 0)
        nrm = gpu.to_uint8(lin, "normals", None, rig.game().encode)   # data passes ignore the rig
        np.testing.assert_array_equal(nrm, gpu.to_uint8(lin, "normals"))


def _draw(name, part, mat, layers):
    return gpu.Draw(None, 3, None, None, [(None, None, None)] * len(layers), 0.0, np.zeros((1, 3, 3)),
                    np.zeros((1, 3, 2)), name, part, mat, list(layers))


class Select(unittest.TestCase):
    def setUp(self):
        self.p = gpu.Prepared([_draw("cap", "body", "hd/x/fungus_alb.texture", ["vfx_glow_cap", "vfx_glow_body"]),
                               _draw("stem", "body", "hd/x/stem_alb.texture", [])])

    def test_none(self):
        self.assertIs(self.p.select([]), self.p)

    def test_mesh_part_material(self):
        self.assertEqual([d.name for d in self.p.select(["mesh:CAP"]).draws], ["stem"])
        self.assertEqual(self.p.select(["part:body"]).draws, [])
        self.assertEqual([d.name for d in self.p.select(["material:stem_"]).draws], ["cap"])

    def test_layers_and_body(self):
        s = self.p.select(["layer:vfx_glow_cap"])
        self.assertEqual(s.draws[0].layer_names, ["vfx_glow_body"])
        self.assertEqual(len(s.draws[0].layers), 1)
        self.assertEqual(self.p.select(["layer:*"]).draws[0].layers, [])
        b = self.p.select(["body"])
        self.assertTrue(all(d.hidden_body for d in b.draws))
        self.assertEqual(len(b.draws[0].layers), 2)


class Sheets(unittest.TestCase):
    def cells(self, n, h=10, w=12):
        return [np.full((h, w, 4), 200, np.uint8) for _ in range(n)]

    def test_grid_size(self):
        g = sheets.grid(self.cells(6), 3, ["x"] * 6, title="t")
        self.assertEqual(g.size, (4 + 3 * 16, 24 + 2 * (10 + 4 + 16) + 4))
        g2 = sheets.grid(self.cells(5) + [None], 2, row_labels=["a", "b", "c"])
        self.assertEqual(g2.size[0], 90 + 4 + 2 * 16)

    def test_anim(self):
        from PIL import Image
        fr = self.cells(4)
        for i, f in enumerate(fr):
            f[..., 0] = 50 * i
        with tempfile.TemporaryDirectory() as d:
            gif = sheets.write_anim(fr, Path(d) / "a.gif", 10)
            apng = sheets.write_anim(fr, Path(d) / "a.png", 10)
            with Image.open(gif) as im:
                self.assertEqual(im.n_frames, 4)
            with Image.open(apng) as im:
                self.assertEqual(im.n_frames, 4)
                self.assertEqual(im.mode, "RGBA")
            with self.assertRaises(ValueError):
                sheets.write_anim(fr, Path(d) / "a.avi")
            try:
                sheets.ffmpeg_exe()
            except RuntimeError:
                return                                  # no imageio-ffmpeg in this Python: MP4 not testable here
            mp4 = sheets.write_anim([f[:5, :7] for f in fr], Path(d) / "a.mp4", 10)   # odd size: padded to even
            self.assertGreater(mp4.stat().st_size, 100)
            self.assertEqual(mp4.read_bytes()[4:8], b"ftyp")

    def test_turntable_yaws(self):
        y = sheets.turntable_yaws(4, 10.0)
        self.assertEqual(y, [10.0, -80.0, -170.0, -260.0])


class Watch(unittest.TestCase):
    def test_watcher(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "in.txt"
            p.write_text("a")
            w = sheets.Watcher([p, Path(d) / "missing"])
            self.assertEqual(w.changed(), [])
            p.write_text("abc")
            os.utime(p, ns=(time.time_ns(), time.time_ns() + 10 ** 9))
            self.assertEqual(w.changed(), [str(p)])
            self.assertEqual(w.changed(), [])

    def test_watch_reruns_on_change(self):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "in.txt"
            p.write_text("a")
            runs, ticks = [], [0]

            def sleep(_s):                     # the fake clock edits the file on the 2nd tick
                ticks[0] += 1
                if ticks[0] == 2:
                    p.write_text("changed")
                    os.utime(p, ns=(time.time_ns(), time.time_ns() + 10 ** 9))

            n = sheets.watch(lambda: runs.append(1), lambda: [p], 0, max_runs=2, log=lambda *_: None, sleep=sleep)
            self.assertEqual(n, 2)
            self.assertEqual(ticks[0], 2)

    def test_watch_survives_failure_and_idles_out(self):
        def bad():
            raise RuntimeError("x")
        logs = []
        n = sheets.watch(bad, lambda: [], 0, idle_exit=0.0, log=logs.append, sleep=lambda _s: time.sleep(0.01))
        self.assertEqual(n, 1)
        self.assertTrue(any("render failed" in m for m in logs))


class Cli(unittest.TestCase):
    def test_parser(self):
        ap = cli.build_parser()
        a = ap.parse_args(["render", "u.json", "--passes", "lit,orm_ao", "--hide", "layer:*", "--hide", "body",
                           "--rig", "game", "--layer-scale", "1.11"])
        self.assertEqual(a.hide, ["layer:*", "body"])
        self.assertEqual(a.layer_scale, 1.11)
        t = ap.parse_args(["turntable", "u.json", "--frames", "8", "--anim", "gif"])
        self.assertEqual(t.frames, 8)
        w = ap.parse_args(["watch", "--max-runs", "1", "render", "u.json", "--pass", "albedo"])
        self.assertEqual(w.inner[:2], ["render", "u.json"])
        self.assertEqual(ap.parse_args(w.inner).pass_name, "albedo")

    def test_rig_command(self):
        with tempfile.TemporaryDirectory() as d:
            out = Path(d) / "g.json"
            cli.main(["rig", "game", str(out)])
            self.assertEqual(rig.load(out).name, "game")

    def test_passes_in_shader(self):
        src = (TOOLS / "hdkit" / "view" / "shaders.wgsl").read_text("utf-8")
        self.assertEqual(set(cli.PASS_NAMES), set(gpu.PASSES))
        self.assertIn("pass_id >= 7 && pass_id <= 10", src)
        self.assertIn("pass_id == 11", src)                          # height
        self.assertEqual(max(gpu.PASSES.values()), 11)


if __name__ == "__main__":
    unittest.main()
