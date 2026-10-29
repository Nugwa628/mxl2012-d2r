"""Mesh .npz (pos, nrm, uv, tris) <-> Wavefront .obj, plain numpy.

    obj_npz.py to_obj <in.npz> <out.obj> [--suffix _1] [--uv]  # pos<suffix>, tris<suffix>; --uv adds uv and nrm
    obj_npz.py to_npz <out.npz> <lod0.obj> [<lod1.obj> ...]   # one vertex per (position, uv, normal) corner; LOD k gets the suffix _k

The npz of a UV-mapped mesh has vertices split along UV seams, which is what D2R's vertex buffer needs.
"""
import sys

import numpy as np


def read_obj(path):
    v, vt, vn, corners, tris = [], [], [], {}, []
    pos, uv, nrm = [], [], []
    for ln in open(path, encoding="utf-8"):
        p = ln.split()
        if not p:
            continue
        if p[0] == "v":
            v.append([float(x) for x in p[1:4]])
        elif p[0] == "vt":
            vt.append([float(x) for x in p[1:3]])
        elif p[0] == "vn":
            vn.append([float(x) for x in p[1:4]])
        elif p[0] == "f":
            ids = []
            for c in p[1:]:
                a = c.split("/")
                key = (int(a[0]), int(a[1]) if len(a) > 1 and a[1] else 0, int(a[2]) if len(a) > 2 and a[2] else 0)
                if key not in corners:
                    corners[key] = len(pos)
                    pos.append(v[key[0] - 1])
                    uv.append(vt[key[1] - 1] if key[1] else [0, 0])
                    nrm.append(vn[key[2] - 1] if key[2] else [0, 1, 0])
                ids.append(corners[key])
            for i in range(1, len(ids) - 1):
                tris.append([ids[0], ids[i], ids[i + 1]])
    uv = np.array(uv, float)
    uv[:, 1] = 1 - uv[:, 1]  # obj v runs up, D2R textures run down
    return np.array(pos, float), np.array(nrm, float), uv, np.array(tris, int)


def main():
    a = sys.argv[1:]
    if a[0] == "to_obj":
        d = np.load(a[1])
        sfx = a[a.index("--suffix") + 1] if "--suffix" in a else ""
        with open(a[2], "w") as f:
            for p in d["pos" + sfx]:
                f.write("v %.6f %.6f %.6f\n" % tuple(p))
            uv = "--uv" in a  # one vt / vn per vertex: the npz of a UV-mapped mesh has its vertices split along the seams
            if uv:
                for p in d["uv" + sfx]:
                    f.write("vt %.6f %.6f\n" % (p[0], 1 - p[1]))
                for p in d["nrm" + sfx]:
                    f.write("vn %.6f %.6f %.6f\n" % tuple(p))
            for t in d["tris" + sfx] + 1:
                f.write("f %d/%d/%d %d/%d/%d %d/%d/%d\n" % (t[0], t[0], t[0], t[1], t[1], t[1], t[2], t[2], t[2]) if uv
                        else "f %d %d %d\n" % tuple(t))
    elif a[0] == "to_npz":
        res = {}
        for k, p in enumerate(a[2:]):
            pos, nrm, uv, tris = read_obj(p)
            s = "" if k == 0 else "_%d" % k
            res["pos" + s], res["nrm" + s], res["uv" + s], res["tris" + s] = pos, nrm, uv, tris
            print("lod", k, len(pos), "verts", len(tris), "tris")
        np.savez(a[1], **res)
    else:
        print(__doc__)


if __name__ == "__main__":
    main()
