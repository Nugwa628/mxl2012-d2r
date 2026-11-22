"""Stage 2: raw TripoSG surface -> cleaned high mesh (largest piece, 250k triangles) + a grey 8-view sheet.

  venv python s2_clean.py <raw.npz> [...]        writes stages/2-shape/hi/<stem>.npz and <stem>_views.png
"""
import sys
from pathlib import Path

import numpy as np
import pymeshlab
from PIL import Image

import common

sys.path.insert(0, str(common.WT / "tools" / "sprite3d"))
import render_soft  # noqa: E402

OUT = common.STAGES / "2-shape" / "hi"
OUT.mkdir(parents=True, exist_ok=True)
for path in sys.argv[1:]:
    d = np.load(path)
    ms = pymeshlab.MeshSet()
    ms.add_mesh(pymeshlab.Mesh(d["pos"].astype(np.float64), d["tris"].astype(np.int32)))
    ms.meshing_remove_connected_component_by_face_number(mincomponentsize=int(len(d["tris"]) * 0.02))
    parts = ms.current_mesh().face_number()
    ms.meshing_decimation_quadric_edge_collapse(targetfacenum=250000, preservenormal=True, qualitythr=0.4, autoclean=True)
    m = ms.current_mesh()
    pos, tris = m.vertex_matrix(), m.face_matrix().astype(np.int64)
    stem = Path(path).stem
    np.savez(OUT / (stem + ".npz"), pos=pos, tris=tris)
    size = 360
    scale, centre = render_soft.framing(pos, size, 0)
    rows = []
    for el in (0, 30):
        rows.append(np.hstack([render_soft.render(pos, tris, az, el, size, scale, centre, bg=(40, 40, 48))
                               for az in (0, 45, 90, 135, 180, 225, 270, 315)]))
    Image.fromarray(np.vstack(rows)[..., :3]).save(OUT / (stem + "_views.png"))
    print(stem, "raw", len(d["tris"]), "kept", parts, "->", len(tris), "box", pos.min(0).round(2), pos.max(0).round(2), flush=True)
