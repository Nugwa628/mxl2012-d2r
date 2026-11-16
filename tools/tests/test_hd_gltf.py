"""Unit tests of tools/hd_gltf.py (D2R HD .model meshes to glTF 2.0 binary and back) on a synthetic model tree built
here (no game files).
Run: py -3 -I -m unittest discover -s tools/tests -p "test_hd_gltf.py" """
import struct
import sys
import unittest
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import projtemp  # noqa: E402,F401  (temp files stay inside the project, tools/projtemp.py)
import d2r_model as dm  # noqa: E402
import hd_gltf as hg  # noqa: E402

ALB = "data/hd/env/texture/test/rock_alb.texture"
NRM = "data/hd/env/texture/test/rock_nrm.texture"


def td(*names, types=None):
    types = types or {}
    return dm.TypeDef([dm.Member(types.get(n, dm.M_INT32), n, array_size=4 if types.get(n) in (
        dm.M_BINORMAL16, dm.M_BINORMAL8, dm.M_NORMAL8, dm.M_UINT8) else 2 if types.get(n) == dm.M_REAL16 else 0)
        for n in names])


SKINNED = td("Position", "BoneWeights", "BoneIndices", "Normal", "Tangent", "TextureCoordinates0",
             types={"Position": dm.M_BINORMAL16, "BoneWeights": dm.M_NORMAL8, "BoneIndices": dm.M_UINT8,
                    "Normal": dm.M_BINORMAL8, "Tangent": dm.M_BINORMAL8, "TextureCoordinates0": dm.M_REAL16})
STATIC = td("Position", "Normal", "Tangent", "DiffuseColor0", "TextureCoordinates0",
            types={"Position": dm.M_BINORMAL16, "Normal": dm.M_BINORMAL8, "Tangent": dm.M_BINORMAL8,
                   "DiffuseColor0": dm.M_NORMAL8, "TextureCoordinates0": dm.M_REAL16})
IDX16 = td("Int16", types={"Int16": dm.M_INT16})
GROUP = td("MaterialIndex", "TriFirst", "TriCount")


def half(x):
    return int(np.float16(x).view(np.uint16))


def vertex(vtd, p, n=(0, 127, 0), uv=(0.5, 0.25), bones=(0, 1, 0, 0), w=(200, 55, 0, 0), col=(255, 128, 0, 255)):
    f = {"Position": [*p, 0], "Normal": [*n, 0], "Tangent": [127, 0, 0, 127], "TextureCoordinates0": [half(uv[0]), half(uv[1])]}
    if vtd is SKINNED:
        f.update(BoneWeights=list(w), BoneIndices=list(bones))
    else:
        f["DiffuseColor0"] = list(col)
    return dm.Obj(vtd, {m.name: f[m.name] for m in vtd.members})


def material(name, alb=ALB):
    tex = lambda p: dm.Obj(td("Texture"), {"Texture": dm.Obj(td("FromFileName"), {"FromFileName": p})})  # noqa: E731
    maps = [dm.Obj(td("Usage", "Map"), {"Usage": "AlbedoTexture", "Map": tex(alb)}),
            dm.Obj(td("Usage", "Map"), {"Usage": "NormalTexture", "Map": tex(NRM)})]
    return dm.Obj(td("Name", "Maps"), {"Name": name, "Maps": maps})


def mesh(name, vtd, verts, tris, groups, mats, bones=("root", "arm"), scale=2.0):
    topo = dm.Obj(td("Groups", "Indices", "Indices16", "VertexToVertexMap"), {
        "Groups": [dm.Obj(GROUP, {"MaterialIndex": m, "TriFirst": f, "TriCount": c}) for m, f, c in groups],
        "Indices": [], "Indices16": [dm.Obj(IDX16, {"Int16": i - 65536 if i > 32767 else i}) for i in tris],
        "VertexToVertexMap": []})
    ed = dm.Obj(td("bbMin", "bbMax", "VertexScale"), {"bbMin": [0, 0, 0], "bbMax": [0, 0, 0], "VertexScale": scale})
    return dm.Obj(td("Name", "PrimaryVertexData", "PrimaryTopology", "MaterialBindings", "BoneBindings", "ExtendedData"), {
        "Name": name,
        "PrimaryVertexData": dm.Obj(td("Vertices"), {"Vertices": dm.Variant(vtd, verts)}),
        "PrimaryTopology": topo,
        "MaterialBindings": [dm.Obj(td("Material"), {"Material": m}) for m in mats],
        "BoneBindings": [dm.Obj(td("BoneName", "OBBMin", "OBBMax", "TriangleIndices"),
                                {"BoneName": b, "OBBMin": [0, 0, 0], "OBBMax": [0, 0, 0], "TriangleIndices": []}) for b in bones],
        "ExtendedData": dm.Variant(ed.td, ed)})


def tree():
    """A skinned body (two materials, 4 vertices, 2 triangles) and a static vertex-coloured rock."""
    body = mesh("body", SKINNED, [vertex(SKINNED, p) for p in ((0, 0, 0), (16383, 0, 0), (0, 16383, 0), (16383, 16383, -8000))],
                [0, 1, 2, 1, 3, 2], [(0, 0, 1), (1, 1, 1)], [material("skin"), material("cloth", NRM)])
    rock = mesh("rock", STATIC, [vertex(STATIC, p, col=(10 * k, 20, 30, 255)) for k, p in enumerate(
        ((0, 0, 0), (32767, 0, 0), (0, 32767, 0)))], [0, 1, 2], [(0, 0, 1)], [material("stone")], bones=("root",), scale=1.0)
    eye = np.eye(4).reshape(-1).tolist()
    sk = dm.Obj(td("Bones"), {"Bones": [dm.Obj(td("Name", "InverseWorldTransform"), {"Name": n, "InverseWorldTransform": eye})
                                         for n in ("root", "arm")]})
    return dm.Obj(td("Skeletons", "Meshes"), {"Skeletons": [sk], "Meshes": [body, rock]})


def verts(t, name):
    m = next(m for m in t["Meshes"] if m["Name"] == name)
    return [v.f for v in m["PrimaryVertexData"]["Vertices"].obj]


class Glb(unittest.TestCase):
    def test_container_round_trip(self):
        g = {"asset": {"version": "2.0"}, "meshes": []}
        b = hg.write_glb(g, b"\1\2\3")
        self.assertEqual(len(b) % 4, 0)
        g2, bin2 = hg.read_glb(b)
        self.assertEqual((g2["asset"], bin2[:3], g2["buffers"][0]["byteLength"]), ({"version": "2.0"}, b"\1\2\3", 3))
        with self.assertRaises(ValueError):
            hg.read_glb(b"glTF" + struct.pack("<II", 1, 12))

    def test_export_writes_meshes_materials_and_skin(self):
        gltf, binary = hg.read_glb(hg.export_glb(tree()))
        self.assertEqual([m["name"] for m in gltf["meshes"]], ["body", "rock"])
        body = gltf["meshes"][0]
        self.assertEqual(len(body["primitives"]), 2)  # one per triangle group
        self.assertIn("_JOINTS", body["primitives"][0]["attributes"])
        self.assertEqual(body["extras"]["d2r"]["bones"], ["root", "arm"])
        self.assertIn("COLOR_0", gltf["meshes"][1]["primitives"][0]["attributes"])
        pos = hg.accessor(gltf, binary, body["primitives"][0]["attributes"]["POSITION"])
        self.assertAlmostEqual(float(pos[1, 0]), 16383 / 32767 * 2.0, places=5)
        self.assertEqual({i["uri"] for i in gltf["images"]}, {ALB, NRM})
        mat = gltf["materials"][body["primitives"][1]["material"]]
        self.assertEqual(mat["extras"]["d2r"]["maps"]["AlbedoTexture"], NRM)

    def test_unchanged_round_trip_is_exact(self):
        t = tree()
        before = {n: verts(t, n) for n in ("body", "rock")}
        hg.import_glb(t, hg.export_glb(tree()))
        for n in before:
            self.assertEqual(verts(t, n), before[n])
        self.assertIsNone(dm.tree_equal(t, tree()))

    def test_scale_edit_grows_the_quantisation_range_and_bounds(self):
        t = tree()
        hg.import_glb(t, hg.edit_glb(hg.export_glb(t), scale=3.0, offset=(0, 1, 0)))
        rock = t["Meshes"][1]
        ed = rock["ExtendedData"].obj
        self.assertAlmostEqual(ed["bbMax"][0], 3.0, places=3)
        self.assertAlmostEqual(ed["bbMin"][1], 1.0, places=3)
        self.assertGreater(ed["VertexScale"], 3.0)
        d = hg.decode_mesh(rock)
        np.testing.assert_allclose(d["pos"][1], [3.0, 1.0, 0.0], atol=1e-3)
        self.assertNotEqual(rock["PrimaryVertexData"]["Vertices"].obj[0]["Position"][3], 0)  # w follows the new scale
        self.assertEqual(rock["BoneBindings"][0]["OBBMax"][0], ed["bbMax"][0])
        self.assertEqual([v["DiffuseColor0"] for v in rock["PrimaryVertexData"]["Vertices"].obj],
                         [[0, 20, 30, 255], [10, 20, 30, 255], [20, 20, 30, 255]])

    def test_texture_swap_through_the_material(self):
        t = tree()
        new = "data/hd/env/texture/test/ice_alb.texture"
        hg.import_glb(t, hg.edit_glb(hg.export_glb(t), maps={"AlbedoTexture": new}))
        for m in t["Meshes"]:
            for b in m["MaterialBindings"]:
                alb = next(x for x in b["Material"]["Maps"] if x["Usage"] == "AlbedoTexture")
                self.assertEqual(alb["Map"]["Texture"]["FromFileName"], new)

    def test_new_vertices_take_the_nearest_skin(self):
        t = tree()
        g = {"pos": np.array([[0, 0, 0], [1, 0, 0], [0, 1, 0], [1, 1, -0.5], [1.01, 1, -0.5]], float),
             "nrm": None, "tan": None, "uv": np.zeros((5, 2), np.float32), "col": None, "joints": None, "weights": None,
             "tris": np.array([[0, 1, 2], [1, 3, 2], [1, 4, 3]]), "groups": [(0, 0, 3)], "maps": [{}]}
        body = t["Meshes"][0]
        hg.put_mesh(t, body, g, hg.decode_mesh(body))
        d = hg.decode_mesh(body)
        self.assertEqual(len(d["pos"]), 5)
        np.testing.assert_array_equal(d["joints"][4], d["joints"][3])
        self.assertEqual(body["PrimaryTopology"]["Groups"][0]["TriCount"], 3)
        np.testing.assert_allclose(np.linalg.norm(d["nrm"], axis=1), 1.0, atol=0.02)

    def test_high_16bit_indices_survive(self):
        t = tree()
        topo = t["Meshes"][1]["PrimaryTopology"]
        topo["Indices16"] = [dm.Obj(IDX16, {"Int16": v}) for v in (0, 1, -2)]  # index 65534 as the file stores it
        self.assertEqual(int(hg.decode_mesh(t["Meshes"][1])["tris"][0, 2]), 65534)

    def test_float_weights_are_normalised_to_255(self):
        w8 = hg.norm_weights([[0.5, 0.5, 0, 0], [1, 1, 1, 0]])
        self.assertEqual(w8.sum(1).tolist(), [255, 255])

    def test_unknown_mesh_is_refused(self):
        t = tree()
        t["Meshes"][1]["Name"] = "other"
        with self.assertRaises(ValueError):
            hg.import_glb(t, hg.export_glb(tree()))


if __name__ == "__main__":
    unittest.main()
