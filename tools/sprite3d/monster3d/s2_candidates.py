"""Stage 2: every side-view candidate reduced to its connected pieces. The largest piece is the body candidate
(stages/2-shape/cand/<name>.npz, 150k triangles); the other pieces above 0.5 % of the faces are listed (and kept in
<name>_pieces.npz) so a loose axe can be found again.

  venv python s2_candidates.py <raw.npz> [...]
"""
import sys
from pathlib import Path

import numpy as np
import pymeshlab
import trimesh

import common

OUT = common.STAGES / "2-shape" / "cand"
OUT.mkdir(parents=True, exist_ok=True)
for path in sys.argv[1:]:
    d = np.load(path)
    m = trimesh.Trimesh(d["pos"], d["tris"], process=False)
    parts = sorted(m.split(only_watertight=False), key=lambda p: -len(p.faces))
    stem = Path(path).stem
    total = len(m.faces)
    print(stem, "pieces:", [(len(p.faces), p.bounds.round(2).tolist()) for p in parts if len(p.faces) > total * 0.005], flush=True)
    body = parts[0]
    ms = pymeshlab.MeshSet()
    ms.add_mesh(pymeshlab.Mesh(np.asarray(body.vertices, np.float64), np.asarray(body.faces, np.int32)))
    ms.meshing_decimation_quadric_edge_collapse(targetfacenum=150000, preservenormal=True, qualitythr=0.4, autoclean=True)
    b = ms.current_mesh()
    np.savez(OUT / (stem + ".npz"), pos=b.vertex_matrix(), tris=b.face_matrix().astype(np.int64))
    rest = {}
    for i, p in enumerate(parts[1:6]):
        if len(p.faces) > total * 0.005:
            rest["pos_%d" % i], rest["tris_%d" % i] = np.asarray(p.vertices), np.asarray(p.faces)
    np.savez(OUT / (stem + "_pieces.npz"), **rest)
