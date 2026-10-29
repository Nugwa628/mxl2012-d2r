#!/usr/bin/env python
"""Mesh builder on d2r_model's Writer: put a triangle mesh into a copy of a vanilla D2R `.model`.

A vanilla skinned part (`<unit>/<part>_lodN.model`, docs/hd-models.md) is a Gr2File whose tree holds several Meshes (body,
fur, jaw, armour ...) behind one Model. `replace_with_mesh` keeps one of them as the template, overwrites its vertices,
triangles, bone bindings and bounds with the new geometry, drops the others (also from the Model's MeshBindings) and
leaves materials, textures and everything else as the donor had them. Vertex format (28 B, skinned): Position
int16[4] (xyz = round(p / VertexScale * 32767), w = round(log2(VertexScale) / 13 * 32767)), BoneWeights uint8[4] (sum 255),
BoneIndices uint8[4] (into the mesh's BoneBindings), Normal and Tangent int8[4] (tangent w = handedness * 127), UV as raw
half-floats.

  py -3 tools/d2r_mesh.py swap <donor.model> <mesh.npz> <out.model> [--bone NAME] [--keep NAME] [--lod K] [--albedo GAME_PATH]
  (mesh.npz: pos (N,3), nrm (N,3), uv (N,2), tris (M,3), optional bone_idx (N,4) and weights (N,4) with `bones` names)

Run with a python that has numpy; the repo's tools run with `py -3 -I`-less defaults (numpy is in requirements).
"""
import math
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import d2r_model as dm  # noqa: E402


def tangents(pos, nrm, uv, tris):
    """Per-vertex tangent (xyz) and handedness from the UV layout; (N,3) and (N,)."""
    n = len(pos)
    t = np.zeros((n, 3))
    b = np.zeros((n, 3))
    p0, p1, p2 = pos[tris[:, 0]], pos[tris[:, 1]], pos[tris[:, 2]]
    u0, u1, u2 = uv[tris[:, 0]], uv[tris[:, 1]], uv[tris[:, 2]]
    e1, e2 = p1 - p0, p2 - p0
    d1, d2 = u1 - u0, u2 - u0
    det = d1[:, 0] * d2[:, 1] - d2[:, 0] * d1[:, 1]
    det = np.where(np.abs(det) < 1e-12, 1e-12, det)
    tt = (e1 * d2[:, 1:2] - e2 * d1[:, 1:2]) / det[:, None]
    bb = (e2 * d1[:, 0:1] - e1 * d2[:, 0:1]) / det[:, None]
    for k in range(3):
        np.add.at(t, tris[:, k], tt)
        np.add.at(b, tris[:, k], bb)
    t = t - nrm * np.sum(t * nrm, 1, keepdims=True)
    ln = np.linalg.norm(t, axis=1, keepdims=True)
    fallback = np.cross(nrm, np.array([0.0, 1.0, 0.0]))
    fallback[np.linalg.norm(fallback, axis=1) < 1e-6] = [1.0, 0.0, 0.0]
    t = np.where(ln > 1e-9, t / np.maximum(ln, 1e-12), fallback / np.maximum(np.linalg.norm(fallback, axis=1, keepdims=True), 1e-12))
    hand = np.where(np.sum(np.cross(nrm, t) * b, 1) < 0, -1.0, 1.0)
    return t, hand


def i8(x):
    return np.clip(np.round(x * 127), -127, 127).astype(int)


def vertex_scale(pos):
    return float(np.abs(pos).max()) * 1.0001


def encode_vertices(vtd, pos, nrm, uv, tris, bone_idx, weights, scale):
    """Vertex Objs of struct type `vtd` for float geometry. Returns the list."""
    pos, nrm, uv = np.asarray(pos, float), np.asarray(nrm, float), np.asarray(uv, float)
    q = np.clip(np.round(pos / scale * 32767), -32767, 32767).astype(int)
    w = int(round(math.log2(scale) / 13 * 32767))
    nrm = nrm / np.maximum(np.linalg.norm(nrm, axis=1, keepdims=True), 1e-12)
    tan, hand = tangents(pos, nrm, uv, tris)
    n8, t8 = i8(nrm), i8(tan)
    h = np.round(np.asarray(uv, np.float32).astype(np.float16).view(np.uint16)).astype(int)
    wt = np.asarray(weights, float)
    wt = wt / np.maximum(wt.sum(1, keepdims=True), 1e-12)
    w8 = np.round(wt * 255).astype(int)
    w8[np.arange(len(w8)), w8.argmax(1)] += 255 - w8.sum(1)  # the four add up to exactly 255
    out = []
    for i in range(len(pos)):
        out.append(dm.Obj(vtd, {
            "Position": [int(q[i, 0]), int(q[i, 1]), int(q[i, 2]), w],
            "BoneWeights": [int(x) for x in w8[i]],
            "BoneIndices": [int(x) for x in bone_idx[i]],
            "Normal": [int(n8[i, 0]), int(n8[i, 1]), int(n8[i, 2]), 0],
            "Tangent": [int(t8[i, 0]), int(t8[i, 1]), int(t8[i, 2]), int(hand[i] * 127)],
            "TextureCoordinates0": [int(h[i, 0]), int(h[i, 1])],
        }))
    return out


def replace_with_mesh(tree, keep, pos, nrm, uv, tris, bone=None, bone_idx=None, weights=None, bones=None, drop_others=True):
    """Overwrite mesh `keep` (name) of `tree` with the geometry and drop all other meshes.

    Without bone_idx / weights the mesh is rigid to the bone `bone` (name in the donor skeleton). With them, `bones` are
    the binding names and bone_idx (N,4) indexes that list."""
    meshes = tree["Meshes"]
    me = next(m for m in meshes if m["Name"] == keep)
    pos, tris = np.asarray(pos, float), np.asarray(tris, int)
    n = len(pos)
    if bone_idx is None:
        bones = [bone]
        bone_idx = np.zeros((n, 4), int)
        weights = np.zeros((n, 4))
        weights[:, 0] = 1.0
    if n > 65535:
        raise ValueError("%d vertices do not fit 16-bit indices" % n)
    scale = vertex_scale(pos)
    old = me["PrimaryVertexData"]["Vertices"]
    vtd = old.obj[0].td
    old.obj = encode_vertices(vtd, pos, nrm, uv, tris, bone_idx, weights, scale)
    topo = me["PrimaryTopology"]
    idx_td = topo["Indices16"][0].td
    topo["Indices16"] = [dm.Obj(idx_td, {"Int16": int(i)}) for i in tris.reshape(-1)]
    for g in topo["Groups"][1:]:
        pass
    grp = topo["Groups"][0]
    grp["MaterialIndex"], grp["TriFirst"], grp["TriCount"] = grp["MaterialIndex"], 0, len(tris)
    topo["Groups"] = [grp]
    # bone bindings: one per name, box around the vertices that use the bone
    tmpl = me["BoneBindings"][0]
    bind = []
    inv = {b["Name"]: np.array(b["InverseWorldTransform"], float).reshape(4, 4) for b in tree["Skeletons"][0]["Bones"]}
    for bi, name in enumerate(bones):
        use = (bone_idx == bi) & (weights > 0)
        sel = use.any(1)
        pts = pos[sel] if sel.any() else pos
        pts = pts @ inv[name][:3, :3] + inv[name][3, :3]  # the box is in the bone's own space (row vectors)
        b = dm.Obj(tmpl.td, dict(tmpl.f))
        b["BoneName"] = name
        b["OBBMin"] = [float(x) for x in pts.min(0)]
        b["OBBMax"] = [float(x) for x in pts.max(0)]
        b["TriangleIndices"] = []
        bind.append(b)
    me["BoneBindings"] = bind
    ed = me["ExtendedData"].obj
    ed["bbMin"] = [float(x) for x in pos.min(0)]
    ed["bbMax"] = [float(x) for x in pos.max(0)]
    ed["VertexScale"] = float(scale)
    if drop_others:
        tree["Meshes"] = [me]
        tree["TriTopologies"] = [topo]
        keep = next(mb for mo in tree["Models"] for mb in mo["MeshBindings"] if mb["Mesh"] is me)
        for mo in tree["Models"]:
            # vanilla files carry the whole mesh set in both Models (lodLevel N and N+1); a Model left without a binding makes the
            # engine assert (model_asset.cpp:305 MeshBindingCount >= 1) when the file is loaded by its plain name (a new path)
            mo["MeshBindings"] = [mb for mb in mo["MeshBindings"] if mb["Mesh"] is me] or [keep]
    return tree


def set_albedo(tree, mesh_name, path):
    """Point the AlbedoTexture map of the mesh's first material at `path` (a game path, `data/hd/...texture`)."""
    me = next(m for m in tree["Meshes"] if m["Name"] == mesh_name)
    for mp in me["MaterialBindings"][0]["Material"]["Maps"]:
        if mp["Usage"] == "AlbedoTexture":
            mp["Map"]["Texture"]["FromFileName"] = path
            return
    raise KeyError("no AlbedoTexture map")


def set_maps(tree, mesh_name, paths):
    """Point maps of the mesh's first material at game paths: `paths` maps a usage (AlbedoTexture, ORMTexture, NormalTexture,
    MaskTexture, ThicknessTexture) to `data/hd/...texture`; usages the material does not have are skipped."""
    me = next(m for m in tree["Meshes"] if m["Name"] == mesh_name)
    for mp in me["MaterialBindings"][0]["Material"]["Maps"]:
        if mp["Usage"] in paths:
            mp["Map"]["Texture"]["FromFileName"] = paths[mp["Usage"]]


def load_model(path):
    g = dm.Gr2File.read(Path(path).read_bytes())
    return g, dm.parse_tree(g)


def write_model(gr2, tree, path):
    out = dm.Writer(gr2).build(tree).write()
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    Path(path).write_bytes(out)
    # re-read to be sure the file is well formed
    dm.parse_tree(dm.Gr2File.read(out))
    return len(out)


def main():
    a = sys.argv[1:]
    if len(a) < 4 or a[0] != "swap":
        print(__doc__)
        return 1
    donor, npz, out = a[1:4]
    bone = a[a.index("--bone") + 1] if "--bone" in a else "pelvis_bind_jnt"
    keep = a[a.index("--keep") + 1] if "--keep" in a else "Goatman_lowShape"
    d = np.load(npz, allow_pickle=True)
    lod = int(a[a.index("--lod") + 1]) if "--lod" in a else 0
    sfx = "" if lod == 0 else "_%d" % lod
    g, tree = load_model(donor)
    kw = {}
    if "bone_idx" in d:
        kw = dict(bone_idx=d["bone_idx"], weights=d["weights"], bones=[str(x) for x in d["bones"]])
    replace_with_mesh(tree, keep, d["pos" + sfx], d["nrm" + sfx], d["uv" + sfx], d["tris" + sfx], bone=bone, **kw)
    if "--albedo" in a:
        set_albedo(tree, keep, a[a.index("--albedo") + 1])
    print(out, write_model(g, tree, out), "bytes")
    return 0


if __name__ == "__main__":
    sys.exit(main())
