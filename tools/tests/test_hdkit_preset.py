"""hdkit.view.preset (preset JSON + .ds1 objects as a scene) and the light terms the scene and the vis rig use (gpu.Light fog,
per-class point gain that leaves directional terms alone). No GPU and no game files needed."""
import json
import sys
import unittest
from pathlib import Path

import numpy as np

TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))
import projtemp  # noqa: E402,F401  (temp files stay inside the project, tools/projtemp.py)
from hdkit.view import gpu, preset  # noqa: E402


class FakeFs:
    def __init__(self, files):
        self.files = files

    def read(self, logical):
        if logical not in self.files:
            raise FileNotFoundError(logical)
        return self.files[logical]


class PresetTest(unittest.TestCase):
    def test_quat_matrix(self):
        self.assertTrue(np.allclose(preset.quat_matrix({}), np.eye(3)))
        s = 2 ** -0.5
        R = preset.quat_matrix({"x": 0, "y": s, "z": 0, "w": s})          # 90 degrees about +y: x -> -z
        self.assertTrue(np.allclose(R @ [1, 0, 0], [0, 0, -1]))
        self.assertTrue(np.allclose(R @ R.T, np.eye(3)))

    def test_trs(self):
        M = preset.trs({"position": {"x": 1, "y": 2, "z": 3}, "scale": {"x": 2, "y": 2, "z": 2}})
        self.assertTrue(np.allclose(M @ [1, 0, 0, 1], [3, 2, 3, 1]))
        self.assertTrue(np.allclose(preset.trs(None), np.eye(4)))

    def test_ds1_objects(self):
        objs, lights, unknown = preset.ds1_objects([(2, 1, 20, 29, 0), (1, 5, 3, 3, 0)])
        self.assertEqual(len(objs), 1)
        self.assertTrue(np.allclose(objs[0].matrix[:3, 3], (40, 0, 58)))
        self.assertEqual(unknown, [(1, 5, 3, 3)])
        L = lights[0]
        self.assertEqual(L["radius"], 38.0)                               # objects.txt Lit 19 sub-tiles x 2
        self.assertAlmostEqual(max(L["color"]), 1.0)
        self.assertEqual(L["pos"][1], 6.5)

    def test_placements_with_prefab(self):
        tr = {"type": "TransformDefinitionComponent", "position": {"x": 10, "y": 0, "z": 0}}
        pre = {"biomeFilename": "b.json", "entities": [
            {"name": "rock", "components": [tr, {"type": "ModelDefinitionComponent", "filename": "rock.model", "lightMask": 9}]},
            {"name": "pf", "components": [tr, {"type": "PrefabPlacementDefinitionComponent", "prefab": "p.json"}]},
            {"name": "snd", "components": [{"type": "AudioEmitterComponent"}]}]}
        sub = {"entities": [{"name": "bush", "components": [
            {"type": "TransformDefinitionComponent", "position": {"x": 1, "y": 0, "z": 2}},
            {"type": "ModelDefinitionComponent", "filename": "bush.model"}]}]}
        fs = FakeFs({"pre.json": json.dumps(pre).encode(), "p.json": json.dumps(sub).encode()})
        out, skipped, biome = preset.placements(fs, "pre.json")
        self.assertEqual([p.model for p in out], ["rock.model", "bush.model"])
        self.assertTrue(np.allclose(out[1].matrix[:3, 3], (11, 0, 2)))
        self.assertEqual(skipped, {"AudioEmitterComponent": 1})
        self.assertEqual(biome, "b.json")


class LightTermsTest(unittest.TestCase):
    def test_fog_in_dict_and_default_off(self):
        self.assertNotIn("fog", gpu.Light().as_dict())
        self.assertEqual(gpu.Light(fog=(0.3, 0.4, 0.5, 0.15)).as_dict()["fog"], [0.3, 0.4, 0.5, 0.15])

    def test_class_gain_skips_directional(self):
        pts = ({"pos": (0, 1, 0), "radius": 5, "color": [1, 1, 1]},
               {"pos": (1e4, 0, 0), "radius": 1e6, "atten": 0.0, "color": [2, 2, 2], "directional": True})
        lt = gpu.Light(points=pts, classes={"unit": {"point_gain": 0.5}}).for_class("unit")
        self.assertEqual(lt.points[0]["color"], [0.5, 0.5, 0.5])
        self.assertEqual(lt.points[1]["color"], [2, 2, 2])


if __name__ == "__main__":
    unittest.main()
