"""tools/m3d_ship.py: approved 3D monsters from the art store into the mod build."""
import json
import os
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

TOOLS = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(TOOLS))
import projtemp  # noqa: E402,F401
import m3d_ship  # noqa: E402
import model_lod_desc  # noqa: E402

BUILT_LOD = TOOLS.parent / "work" / "mod" / "data" / "hd" / "model_lod_desc.bin"
DONOR = "data/hd/character/enemy/mummy1/torso.model"
NEW = "data/hd/character/enemy/mxl/m3d/test/torso.model"


def stage(root: Path, files: dict, u=0.5) -> Path:
    s = root / "stage"
    for rel, data in files.items():
        (s / "overlay" / rel).parent.mkdir(parents=True, exist_ok=True)
        (s / "overlay" / rel).write_bytes(data)
    (s / "build.json").write_text(json.dumps({"unit": "mxl_m3d_test", "model": NEW, "donor_model": DONOR, "u": u,
                                              "bounds": [[-2, 0, -2], [2, 8, 2]]}), encoding="utf-8")
    return s


class StoreAndBuild(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.store = self.tmp / "store"
        self.store.mkdir()
        (self.store / "README.md").write_text("store\n", encoding="utf-8")
        self.manifest = self.tmp / "m3d_ship.json"
        self.files = {"hd/character/enemy/mxl_m3d_test.json": b"{}", "hd/character/enemy/mxl/m3d/test/torso_lod0.model": b"m0"}
        m3d_ship.store(stage(self.tmp, self.files), ["test1", "test2"], self.manifest, self.store, log=lambda *_: None)
        self.data = self.tmp / "mod" / "data"
        (self.data / "hd" / "character").mkdir(parents=True)
        (self.data / m3d_ship.MONSTERS).write_text(json.dumps({"test1": "old_unit", "test2": "old_unit", "other": "x"}), encoding="utf-8")
        (self.data / m3d_ship.LOD_DESC).write_bytes(b"table")

    def test_store_writes_objects_and_entry(self):
        doc = json.loads(self.manifest.read_text(encoding="utf-8"))
        (m,) = doc["monsters"]
        self.assertEqual((m["ids"], m["unit"], m["model"], m["donor_model"]), (["test1", "test2"], "mxl_m3d_test", NEW, DONOR))
        self.assertEqual(m["bounds"], [[-1, 0, -1], [1, 4, 1]])     # times u, as g6_gamerun lays them
        self.assertEqual(sorted(f["path"] for f in m["files"]), sorted(self.files))
        for f in m["files"]:
            self.assertEqual(m3d_ship._object(self.store, f["sha256"]).read_bytes(), self.files[f["path"]])
        self.assertTrue((self.store / "manifests" / "m3d" / self.manifest.name).is_file())

    def test_build_lays_files_and_edits_both_indexes(self):
        calls = []
        with mock.patch.object(model_lod_desc, "add", lambda d, n2d, b: calls.append((d, n2d, b)) or d + b"+"):
            n = m3d_ship.build(self.data, self.manifest, self.store, log=lambda *_: None)
        self.assertEqual(n, 2)
        for rel, data in self.files.items():
            self.assertEqual((self.data / rel).read_bytes(), data)
        self.assertEqual(json.loads((self.data / m3d_ship.MONSTERS).read_text(encoding="utf-8")),
                         {"test1": "mxl_m3d_test", "test2": "mxl_m3d_test", "other": "x"})
        self.assertEqual(calls, [(b"table", {NEW: DONOR}, {NEW: ((-1, 0, -1), (1, 4, 1))})])
        self.assertEqual((self.data / m3d_ship.LOD_DESC).read_bytes(), b"table+")

    def test_build_stops_on_a_changed_object(self):
        doc = json.loads(self.manifest.read_text(encoding="utf-8"))
        m3d_ship._object(self.store, doc["monsters"][0]["files"][0]["sha256"]).write_bytes(b"changed")
        with self.assertRaises(SystemExit):
            m3d_ship.build(self.data, self.manifest, self.store, log=lambda *_: None)

    def test_build_stops_on_an_unknown_monster(self):
        (self.data / m3d_ship.MONSTERS).write_text(json.dumps({"test1": "old_unit", "other": "x"}), encoding="utf-8")
        with self.assertRaises(SystemExit):
            m3d_ship.build(self.data, self.manifest, self.store, log=lambda *_: None)

    def test_store_refuses_index_files_in_the_overlay(self):
        with self.assertRaises(SystemExit):
            m3d_ship.store(stage(self.tmp / "b", {m3d_ship.MONSTERS: b"{}"}), ["x"], self.manifest, self.store,
                           log=lambda *_: None)

    def test_off_switch(self):
        with mock.patch.dict(os.environ, {"MXL2012_M3D": "0"}), mock.patch.object(m3d_ship, "build") as b:
            self.assertEqual(m3d_ship.main(["build", str(self.data)]), 0)
        b.assert_not_called()


class Shipped(unittest.TestCase):
    def test_manifest_lists_the_fungus(self):
        doc = json.loads(m3d_ship.MANIFEST.read_text(encoding="utf-8"))
        (m,) = doc["monsters"]
        self.assertEqual((m["ids"], m["unit"]), (["fungus1", "fungus2", "glowingfs", "sumelite_1272"], "mxl_m3d_fungus"))
        paths = {f["path"] for f in m["files"]}
        self.assertIn("hd/character/enemy/mxl_m3d_fungus.json", paths)
        self.assertEqual(sum(p.endswith(".model") for p in paths), 5)   # LODs 0-4
        self.assertFalse(paths & {m3d_ship.MONSTERS, m3d_ship.LOD_DESC})

    @unittest.skipUnless(BUILT_LOD.is_file(), "needs a built mod")
    def test_real_table_takes_the_entry(self):
        doc = json.loads(m3d_ship.MANIFEST.read_text(encoding="utf-8"))
        m = doc["monsters"][0]
        data = BUILT_LOD.read_bytes()
        entries = model_lod_desc.parse(data)[0]
        self.assertIsNotNone(model_lod_desc.find(entries, m["donor_model"]))
        out = model_lod_desc.add(data, {m["model"]: m["donor_model"]}, {m["model"]: m["bounds"]})
        self.assertIsNotNone(model_lod_desc.find(model_lod_desc.parse(out)[0], m["model"]))


if __name__ == "__main__":
    unittest.main()
