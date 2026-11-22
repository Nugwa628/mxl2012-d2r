"""Stage 4: the UV-mapped mesh (body, and the Hardliner's axe when the folder holds one) and its five LODs (Blender Decimate,
UVs kept).

  venv python s4_lods.py [--token T] <final dir (mesh_uv.npz[, axe.npz])> <out dir> [--ratios 0.5,0.25,0.12,0.06]

Writes <out>/mesh_lods.npz (pos, nrm, uv, tris and the _1 .. _4 suffixes; upright body frame, height 1). An axe is told from
the body by its uv (the bottom quarter of the atlas), so it survives the decimation as a piece of its own.
"""
import subprocess
import sys
from pathlib import Path

import numpy as np

import common

sys.path.insert(0, str(common.WT / "tools" / "sprite3d"))
import render_soft  # noqa: E402

BLENDER = common.BLENDER
a = sys.argv[1:]
src, out = Path(a[0]), Path(a[1])
ratios = a[a.index("--ratios") + 1] if "--ratios" in a else "0.5,0.25,0.12,0.06"
out.mkdir(parents=True, exist_ok=True)
m = np.load(src / "mesh_uv.npz")
pos, tris, uv, nrm = m["pos"], m["tris"], m["uv"], m["nrm"]
has_axe = (src / "axe.npz").is_file()
if has_axe:
    ax = np.load(src / "axe.npz")
    tris = np.vstack([tris, ax["tris"] + len(pos)])
    pos, uv = np.vstack([pos, ax["pos"]]), np.vstack([uv, ax["uv"]])
    nrm = np.vstack([nrm, render_soft.vertex_normals(ax["pos"], ax["tris"])])
np.savez(out / "lod0.npz", pos=pos, nrm=nrm, uv=uv, tris=tris)
tool = common.WT / "tools" / "sprite3d"
py = [sys.executable, "-I"]
subprocess.run([*py, str(tool / "obj_npz.py"), "to_obj", str(out / "lod0.npz"), str(out / "in.obj"), "--uv"], check=True)
(common.HOME / "logs").mkdir(exist_ok=True)
log = open(common.HOME / "logs" / "blender-lods.log", "w")
subprocess.run([str(BLENDER), "-b", "--factory-startup", "-P", str(tool / "unwrap.py"), "--", str(out / "in.obj"), str(out / "set"),
                "--keep-uv", "--ratios", ratios], check=True, stdout=log, stderr=subprocess.STDOUT)
subprocess.run([*py, str(tool / "obj_npz.py"), "to_npz", str(out / "mesh_lods.npz")]
               + [str(out / ("set_lod%d.obj" % k)) for k in range(5)], check=True)
d = np.load(out / "mesh_lods.npz")
for k in range(5):
    s = "" if k == 0 else "_%d" % k
    axe = (d["uv" + s][:, 1] > 0.75) & has_axe
    print("lod %d: %d vertices, %d triangles (axe: %d vertices, %d triangles)"
          % (k, len(d["pos" + s]), len(d["tris" + s]), int(axe.sum()), int(axe[d["tris" + s]].all(1).sum())))
