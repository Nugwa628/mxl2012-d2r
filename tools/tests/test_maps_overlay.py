"""Tests of tools/maps_overlay.py (lane hdmaps2): a synthetic build folder, no game files.

  python -m unittest tests.test_maps_overlay
"""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import projtemp  # noqa: E402,F401
import maps_overlay  # noqa: E402


def put(root, rel, body):
    p = root / rel
    p.parent.mkdir(parents=True, exist_ok=True)
    p.write_bytes(body)


class Overlay(unittest.TestCase):
    def test_follows_references_and_lods(self):
        with tempfile.TemporaryDirectory() as d:
            root = Path(d) / "build"
            m = b"data/hd/env/model/mxl/wallsprite/t/set/w_1.model"
            put(root, "data/hd/env/preset/act9/x/map.json",
                b'{"models":[{"path":"' + m + b'"}],"biome":"data/hd/env/biome/stock.json"}')
            put(root, "data/hd/env/preset/act9/x/other.json", b'{"models":[]}')
            put(root, m.decode(), b"\0data/hd/env/texture/mxl/wallsprite/t/set_alb.texture\0")
            put(root, "data/hd/env/model/mxl/wallsprite/t/set/w_1_lod0.model", b"lod")
            put(root, "data/hd/env/model/mxl/wallsprite/t/set/w_2.model", b"unused")
            put(root, "data/hd/env/texture/mxl/wallsprite/t/set_alb.texture", b"tex")
            put(root, "data/hd/model_lod_desc.bin", b"lods")
            out = Path(d) / "out"
            rep = maps_overlay.build_overlay(root / "data", out, ["act9/x/map"])
            got = sorted(f["path"] for f in rep["files"])
            self.assertEqual(got, ["data/hd/env/model/mxl/wallsprite/t/set/w_1.model",
                                   "data/hd/env/model/mxl/wallsprite/t/set/w_1_lod0.model",
                                   "data/hd/env/preset/act9/x/map.json",
                                   "data/hd/env/texture/mxl/wallsprite/t/set_alb.texture",
                                   "data/hd/model_lod_desc.bin"])
            self.assertEqual(rep["base_mod_refs"], ["data/hd/env/biome/stock.json"])
            for rel in got:
                self.assertEqual((out / rel).read_bytes(), (root / rel).read_bytes())
            self.assertEqual(json.loads((out / "overlay.json").read_text())["maps"], ["act9/x/map"])

    def test_missing_preset(self):
        with tempfile.TemporaryDirectory() as d:
            (Path(d) / "data" / "hd").mkdir(parents=True)
            with self.assertRaises(FileNotFoundError):
                maps_overlay.build_overlay(Path(d) / "data", Path(d) / "out", ["act9/x/none"])


if __name__ == "__main__":
    unittest.main()
