"""hdkit.view calibration measures: the unit's own light in the vis rig (on for live modes, off for the corpse), the env
option, and compare's like-with-like blocks (`shared`, `own`) and twin_diff. No GPU needed."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

import numpy as np

TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))
import projtemp  # noqa: E402,F401  (temp files stay inside the project, tools/projtemp.py)
from hdkit.view import compare, rig  # noqa: E402

VIS = {"entities": [
    {"name": "vd", "components": [{"type": "VisualDataComponent", "exposureValue": 4, "characterBrightnessFactor": 0.4,
                                   "unitLightPower": 500, "unitLightAttenuation": 5.0, "unitLightDistanceScaler": 1.5,
                                   "unitLightDistanceOffsetRatio": 0.5}]},
    {"name": "monster_fill_light", "components": [
        {"type": "DirectionalLightDefinitionComponent", "power": 30, "color": {"x": 1, "y": 1, "z": 1},
         "lightMask": 74}]}]}


class UnitLight(unittest.TestCase):
    def resolve(self, opts):
        with tempfile.TemporaryDirectory() as d:
            p = Path(d) / "v.json"
            p.write_text(json.dumps(VIS), "utf-8")
            return rig.resolve("vis:" + str(p) + opts)

    def test_unit_light_point(self):
        r = self.resolve(";unit=2,128,128,255")
        pts = [p for p in r.light.points if p.get("unit_light")]
        self.assertEqual(len(pts), 1)
        p = pts[0]
        self.assertAlmostEqual(p["radius"], 2 * 2 * 1.5)
        self.assertAlmostEqual(p["pos"][1], 6.0 * 0.5)
        self.assertAlmostEqual(p["color"][2], 500 * 0.4)
        self.assertAlmostEqual(p["color"][0], 128 / 255 * 500 * 0.4)
        self.assertEqual(r.meta["unit_light"]["power"], 500)

    def test_for_mode_drops_it_for_the_corpse(self):
        r = self.resolve(";unit=2,128,128,255;ulgain=0.5")
        self.assertIs(r.for_mode("nu"), r)
        dd = r.for_mode("DD")
        self.assertFalse(any(p.get("unit_light") for p in dd.light.points))
        self.assertTrue(any(p.get("unit_light") for p in r.light.points))   # the rig itself is unchanged
        plain = self.resolve("")
        self.assertIs(plain.for_mode("dd"), plain)

    def test_env(self):
        r = self.resolve(";env=6.03")
        self.assertEqual(tuple(r.light.env_col), (6.03, 6.03, 6.03))
        self.assertTrue(any("env colour" in a for a in r.assumptions))


class Shared(unittest.TestCase):
    def scene(self):
        H, W = 80, 60
        rng = np.random.default_rng(1)
        twin = rng.integers(20, 60, (H, W, 3)).astype(np.uint8)       # textured ground
        shot = twin.copy()
        shot[20:60, 20:40] = (90, 150, 210)                           # the unit
        shot[20:30, 20:40] = (100, 170, 240)                          # its cap ring
        render = np.zeros((H, W, 4), np.uint8)
        render[20:60, 20:40, :3] = (60, 100, 140)
        render[20:60, 20:40, 3] = 255
        return render, shot, twin

    def test_twin_diff(self):
        _r, shot, twin = self.scene()
        dm, relit, ls, lt = compare.twin_diff(shot, twin)
        self.assertGreater(dm[40, 30], 28)
        self.assertEqual(dm[5, 5], 0)
        self.assertEqual(ls.shape, lt.shape)
        self.assertFalse(relit[40, 30])

    def test_compare_blocks(self):
        render, shot, twin = self.scene()
        res, _ex = compare.compare(render, shot, (30, 60), (30, 60), twin, None, (), 2)
        sh = res["shared"]
        self.assertGreater(sh["px"], 600)
        self.assertEqual(sh["weak"], 10.0)
        for k in ("all", "cap", "body", "cap_rgb", "own"):
            self.assertIn(k, sh)
        self.assertGreater(sh["all"]["game"], sh["all"]["render"])
        self.assertAlmostEqual(sh["all"]["err"], abs(np.log((sh["all"]["render"] + 1) / (sh["all"]["game"] + 1))),
                               places=2)
        self.assertGreater(sh["cap_rgb"]["blue_game"], 1.0)
        own = sh["own"]
        for k in ("p50", "p90", "ring"):
            self.assertIn(k, own)
        self.assertGreater(own["ring"]["dist"], 0)
        res0, _ = compare.compare(render, shot, (30, 60), (30, 60), twin, None, (), 2, weak=None)
        self.assertIsNone(res0["shared"]["weak"])
        self.assertLessEqual(res0["shared"]["px"], sh["px"])

    def test_hysteresis_off_by_default(self):
        _r, shot, twin = self.scene()
        a = compare.twin_mask(shot, twin, (30, 60))
        b = compare.twin_mask(shot, twin, (30, 60), weak=None)
        self.assertTrue(np.array_equal(a, b))


if __name__ == "__main__":
    unittest.main()
