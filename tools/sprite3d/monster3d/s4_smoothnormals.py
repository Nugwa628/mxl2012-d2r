"""Stage 4 finish (round 13, Glowing Fungus): smooth the body's vertex normals in every LOD, the rigid part untouched.

  python s4_smoothnormals.py <stage dir> [--iters 6] [--keep 0.0] [--bone jaw] [--lods 0,1,2,3,4] [--report <json>]

Why: the generated body mesh is crumpled (many small facets at odd angles, from the reconstruction); its vertex normals
follow every facet, so under a key light the body breaks into bright and dark slivers and reads as crinkled foil even
with a matte ORM (round 13: metal 0, roughness 0.94, specular 0.04). Classic's body is drawn with broad, soft shading.

For each torso_lod<N>.model in the stage's overlay, per mesh: vertices at the same position (the UV seams split them)
are welded; the welded normals start from the area-weighted face normals and are smoothed --iters times over the mesh
edges (each vertex: mean of itself and its neighbours, renormalised); a vertex then gets
normalize(keep x its own normal + (1 - keep) x the smoothed one). Vertices fully on --bone (the cap) keep their normal
exactly. Tangents are re-orthogonalised to the new normal (handedness kept). Positions, UVs, skin and topology are not
touched. The file is rewritten in place (d2r_mesh.write_model re-reads it to check it).
"""
import json
import sys
from pathlib import Path

import numpy as np

import common

sys.path.insert(0, str(common.WT / "tools"))
import d2r_mesh  # noqa: E402
import d2r_model as dm  # noqa: E402
import hd_gltf  # noqa: E402


def opt(a, name, default):
    return a[a.index(name) + 1] if name in a else default


def smooth(pos, nrm, tris, fixed, iters, keep):
    key = np.round(pos * 1e4).astype(np.int64)
    _u, wid, inv = np.unique(key, axis=0, return_index=True, return_inverse=True)
    inv = inv.ravel()
    nw = len(wid)
    T = inv[tris]
    fn = np.cross(pos[tris[:, 1]] - pos[tris[:, 0]], pos[tris[:, 2]] - pos[tris[:, 0]])   # area weighted
    N = np.zeros((nw, 3))
    for c in range(3):
        np.add.at(N, T[:, c], fn)
    N /= np.maximum(np.linalg.norm(N, axis=1, keepdims=True), 1e-12)
    # orientation as the mesh's own normals (a face winding flip would invert the smoothed one)
    own = np.zeros((nw, 3))
    np.add.at(own, inv, nrm)
    N *= np.where((N * own).sum(1) < 0, -1.0, 1.0)[:, None]
    E = np.vstack([T[:, [0, 1]], T[:, [1, 2]], T[:, [2, 0]]])
    E = np.unique(np.sort(E, 1), axis=0)
    E = E[E[:, 0] != E[:, 1]]
    deg = np.bincount(E.ravel(), minlength=nw)[:, None] + 1.0
    for _ in range(iters):
        S = N.copy()
        np.add.at(S, E[:, 0], N[E[:, 1]])
        np.add.at(S, E[:, 1], N[E[:, 0]])
        N = S / deg
        N /= np.maximum(np.linalg.norm(N, axis=1, keepdims=True), 1e-12)
    out = keep * nrm + (1 - keep) * N[inv]
    out /= np.maximum(np.linalg.norm(out, axis=1, keepdims=True), 1e-12)
    out[fixed] = nrm[fixed]
    return out


def main():
    a = sys.argv[1:]
    stage = Path(a[0])
    iters, keep, bone = int(opt(a, "--iters", "6")), float(opt(a, "--keep", "0.0")), opt(a, "--bone", "jaw")
    lods = [int(x) for x in opt(a, "--lods", "0,1,2,3,4").split(",")]
    rep = {"iters": iters, "keep": keep, "lods": {}}
    for lod in lods:
        path = next(Path(stage, "overlay").rglob("torso_lod%d.model" % lod))
        g = dm.Gr2File.read(path.read_bytes())
        tree = dm.parse_tree(g)
        r = {}
        for m in tree["Meshes"]:
            d = hd_gltf.decode_mesh(m)
            if "joints" not in d or not len(d["tris"]):
                continue
            names = [b["BoneName"] for b in m["BoneBindings"]]
            bi = names.index(bone) if bone in names else -1
            fixed = (d["joints"][:, 0] == bi) & (d["weights"][:, 0] >= 254) if bi >= 0 else np.zeros(len(d["pos"]), bool)
            n0 = d["nrm"] / np.maximum(np.linalg.norm(d["nrm"], axis=1, keepdims=True), 1e-12)
            n1 = smooth(d["pos"], n0, d["tris"], fixed, iters, keep)
            t = d["tan"][:, :3]
            t = t - (t * n1).sum(1, keepdims=True) * n1
            t /= np.maximum(np.linalg.norm(t, axis=1, keepdims=True), 1e-12)
            n8 = np.clip(np.round(n1 * 127), -127, 127).astype(int)
            t8 = np.clip(np.round(t * 127), -127, 127).astype(int)
            vs = m["PrimaryVertexData"]["Vertices"].obj
            changed = 0
            for i, v in enumerate(vs):
                if fixed[i]:
                    continue
                nv = [int(n8[i, 0]), int(n8[i, 1]), int(n8[i, 2]), v["Normal"][3]]
                if list(v["Normal"]) != nv:
                    changed += 1
                v["Normal"] = nv
                if "Tangent" in v.f:
                    v["Tangent"] = [int(t8[i, 0]), int(t8[i, 1]), int(t8[i, 2]), v["Tangent"][3]]
            ang = np.degrees(np.arccos(np.clip((n0 * n1).sum(1), -1, 1)))[~fixed]
            r[m["Name"]] = {"vertices": len(vs), "fixed": int(fixed.sum()), "changed": changed,
                            "turn_deg_median": round(float(np.median(ang)), 1), "turn_deg_p95": round(float(np.percentile(ang, 95)), 1)}
        r["bytes"] = d2r_mesh.write_model(g, tree, path)
        rep["lods"][lod] = r
        print(lod, json.dumps(r), flush=True)
    (stage / "smoothnormals.json").write_text(json.dumps(rep, indent=1))
    if "--report" in a:
        Path(opt(a, "--report", "")).write_text(json.dumps(rep, indent=1))


if __name__ == "__main__":
    main()
