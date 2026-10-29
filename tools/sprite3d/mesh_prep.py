"""Generated GLB -> decimated mesh.npz in D2R model space (for tools/d2r_mesh.py), runs in the 3D venv (trimesh, pymeshlab).

  mesh_prep.py <in.glb> <out.npz> [--tris N] [--height H] [--lods 1.0,0.5,0.25,0.12,0.06]

Model space: y up, feet on y = 0, centred on x and z, facing +z (goatman1's bind pose: height 6.6, jaw at +z). Glb input is
y-up with the front towards +z (Hunyuan3D). Planar front UVs (x, y of the bounding box) unless the mesh has its own;
the unwrap and bake of the real texture come in the texture step. With --lods the output holds pos/nrm/uv/tris for each
LOD as pos_1, tris_1 ... (LOD 0 has no suffix).
"""
import sys

import numpy as np
import pymeshlab
import trimesh


def decimate(v, f, n):
    ms = pymeshlab.MeshSet()
    ms.add_mesh(pymeshlab.Mesh(v, f))
    ms.meshing_decimation_quadric_edge_collapse(targetfacenum=int(n), preservenormal=True, preserveboundary=True,
                                                 qualitythr=0.5, autoclean=True)
    m = ms.current_mesh()
    return m.vertex_matrix(), m.face_matrix()


def main():
    a = sys.argv[1:]
    src, out = a[0], a[1]
    tris = int(a[a.index("--tris") + 1]) if "--tris" in a else 25000
    height = float(a[a.index("--height") + 1]) if "--height" in a else 6.6
    fr = [float(x) for x in a[a.index("--lods") + 1].split(",")] if "--lods" in a else [1.0]
    m = trimesh.load(src, force="mesh")
    v = np.asarray(m.vertices, float)
    v[:, 1] -= v[:, 1].min()
    v[:, 0] -= (v[:, 0].min() + v[:, 0].max()) / 2
    v[:, 2] -= (v[:, 2].min() + v[:, 2].max()) / 2
    v *= height / v[:, 1].max()
    f = np.asarray(m.faces, int)
    res = {}
    for k, fac in enumerate(fr):
        vv, ff = decimate(v, f, tris * fac)
        mm = trimesh.Trimesh(vv, ff, process=True)
        nrm = np.asarray(mm.vertex_normals, float)
        vv = np.asarray(mm.vertices, float)
        lo, hi = vv.min(0), vv.max(0)
        uv = np.stack([(vv[:, 0] - lo[0]) / (hi[0] - lo[0]), 1 - (vv[:, 1] - lo[1]) / (hi[1] - lo[1])], 1)
        suf = "" if k == 0 else "_%d" % k
        res["pos" + suf], res["nrm" + suf], res["uv" + suf], res["tris" + suf] = vv, nrm, uv, np.asarray(mm.faces, int)
        print("lod", k, len(vv), "verts", len(mm.faces), "tris")
    np.savez(out, **res)


if __name__ == "__main__":
    main()
