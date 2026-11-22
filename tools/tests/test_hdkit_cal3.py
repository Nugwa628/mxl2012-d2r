"""hdkit.view tone path of the game's LUT build (tone.lut_chain, value_curve, bloom), the rig's `lut` tone and its options
(env tint, ambient tint, bloom, value curve), compare's fair mask block, and gpugate's call-time counters. No GPU needed."""
import json
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

import numpy as np

TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))
import projtemp  # noqa: E402,F401  (temp files stay inside the project, tools/projtemp.py)
from hdkit import gpugate  # noqa: E402
from hdkit.view import compare, rig, tone  # noqa: E402

VIS = {"entities": [
    {"name": "vd", "components": [{"type": "VisualDataComponent", "exposureValue": 4, "characterBrightnessFactor": 0.4,
                                   "bloomCutoff": 1.0, "bloomIntensity": 1.0,
                                   "depthFogColor": {"x": 0.2, "y": 0.3, "z": 0.6}}]},
    {"name": "global_key_light", "components": [
        {"type": "DirectionalLightDefinitionComponent", "power": 2, "color": {"x": 0.5, "y": 0.6, "z": 1.0},
         "lightMask": 9}]}]}


def _resolve(opts):
    with tempfile.TemporaryDirectory() as d:
        p = Path(d) / "v.json"
        p.write_text(json.dumps(VIS), "utf-8")
        return rig.resolve("vis:" + str(p) + opts)


class LutChain(unittest.TestCase):
    def test_greys_match_old_table(self):
        out = tone.lut_chain(np.array([[g, g, g] for g in (0.1, 0.2, 0.5, 1.0)]))
        for got, want in zip(out[:, 0], (0.349, 0.485, 0.734, 0.953)):
            self.assertAlmostEqual(float(got), want, delta=0.01)
        self.assertTrue(np.allclose(out[:, 0], out[:, 1], atol=1e-3))

    def test_bright_blue_keeps_saturation(self):
        o = np.clip(tone.lut_chain(np.array([0.05, 0.4, 1.5])), 0, 1) * 255
        self.assertLess(o[0], 30)      # the old per-channel table gave red 63
        self.assertGreater(o[2], 250)

    def test_monotonic_and_bounded(self):
        g = np.linspace(0, 50, 200)
        o = tone.lut_chain(np.stack([g, g, g], -1))[:, 0]
        self.assertTrue(np.all(np.diff(o) >= -1e-6))
        self.assertGreater(o[-1], 1.0)              # not clipped: the 8-bit target write clips, not the chain

    def test_value_curve_off_is_identity(self):
        v = np.array([[0.2, 0.3, 0.4], [1.5, 0.1, 0.0]])
        self.assertTrue(np.allclose(tone.value_curve(v), v))
        lifted = tone.value_curve(v, brightness=1.0)
        self.assertTrue(np.allclose(lifted, 2 * v))

    def test_bloom_cutoff(self):
        img = np.zeros((32, 32, 3))
        self.assertEqual(float(tone.bloom(img + 0.5).max()), 0.0)     # luma below the cutoff: no bloom
        img[16, 16] = 20.0
        b = tone.bloom(img)
        self.assertGreater(float(b[16, 16].max()), 0.0)
        self.assertGreater(float(b[16, 18].max()), 0.0)                # spreads to neighbours


class RigOptions(unittest.TestCase):
    def test_lut_tone_and_bloom(self):
        r = _resolve(";tone=lut;bloom=1")
        self.assertEqual(r.tone, "lut")
        self.assertEqual(r.post["bloom"]["cutoff"], 1.0)
        back = rig.Rig.from_dict(json.loads(json.dumps(r.as_dict())))
        self.assertEqual(back.post, r.post)
        lin = np.zeros((16, 16, 4))
        lin[6:10, 6:10] = (50.0, 50.0, 50.0, 1.0)
        disp, a = r.encode_image(lin)
        self.assertEqual(disp.shape, (16, 16, 3))
        self.assertTrue(np.allclose(a[6:10, 6:10], 1.0))
        self.assertGreater(float(a[5, 8, 0]), 0.0)                     # halo outside the unit

    def test_no_bloom_no_image_path(self):
        self.assertIsNone(_resolve(";tone=lut").encode_image(np.zeros((4, 4, 4))))

    def test_env_and_ambient_tint(self):
        r = _resolve(";env=6;envtint=key;amb=2,key")
        e = r.light.env_col
        self.assertAlmostEqual(0.2126 * e[0] + 0.7152 * e[1] + 0.0722 * e[2], 6.0, places=4)
        self.assertGreater(e[2], e[0])
        base = _resolve("").light.ambient
        a = r.light.ambient
        y = lambda c: 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2]  # noqa: E731
        self.assertAlmostEqual(y(a), 2 * y(base), places=4)

    def test_value_curve_live_only(self):
        r = _resolve(";tone=lut;vc=0.5,0,live")
        self.assertIn("value", r.post)
        self.assertNotIn("value", r.for_mode("dd").post)
        self.assertIn("value", r.for_mode("nu").post)


class FairMask(unittest.TestCase):
    def test_fair_block_on_identical_render(self):
        h, w = 120, 120
        ground = np.full((h, w, 3), 40, np.uint8)
        shot = ground.copy()
        shot[40:90, 45:75] = (110, 200, 240)
        rgba = np.zeros((h, w, 4), np.uint8)
        rgba[40:90, 45:75] = (110, 200, 240, 255)
        res, _ = compare.compare(rgba, shot, (60, 90), render_feet=(60, 90), twin=ground)
        f = res["shared"]["fair"]
        self.assertGreater(f["iou"], 0.95)
        self.assertAlmostEqual(f["p50"]["ratio"], 1.0, places=2)
        self.assertLess(f["ring"]["dist"], 1.0)


class GateCounters(unittest.TestCase):
    def test_patched_read_counters_is_used(self):
        with mock.patch.object(gpugate, "read_counters", lambda: (1.0, "3D", 5.0)):
            rd = gpugate.check(["Z:/no/such/lock*"])
        self.assertTrue(rd.free)
        self.assertEqual(rd.gpu, 1.0)
        with mock.patch.object(gpugate, "read_counters", lambda: (90.0, "3D", 5.0)):
            self.assertFalse(gpugate.check(["Z:/no/such/lock*"]).free)


if __name__ == "__main__":
    unittest.main()
