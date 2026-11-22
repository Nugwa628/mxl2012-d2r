"""Stage 3: a generated mesh -> the upright mesh the cameras are fitted to and the texture is projected on.

  venv python s3_prep.py <cand.npz> <out.npz> [--tris 36000] [--view 5] [--tilt stretch|pitch|none] [--keep 0.5] [--asis]

A mesh made from ONE sprite view is in the frame of that picture: the sprite camera looks down on the monster by 30 degrees
and the model reads the picture as a level view. --tilt undoes that: `stretch` scales y by 1/cos(30) (the height the camera
foreshortened; best for the Hardliner), `pitch` turns the mesh back by 30 degrees about the screen's x axis (what the camera
really did; a flat cap that the model made leaning towards the viewer needs it), `none` leaves it. --view is the file
direction the picture shows (ring 4,0,5,1,6,2,7,3, 45 degrees a step): the mesh is turned by that angle so the monster faces
+z. Then: pieces under --keep of the faces dropped, feet on y = 0, centred on x and z, height 1, decimated to --tris.
--asis: a mesh that already stands upright and faces +z (Hunyuan3D-2mv from the front / left / back / right sprites): the
same as --view 4 --tilt none --keep 0.02.
"""
import sys

import numpy as np
import pymeshlab

import common

a = sys.argv[1:]
opt = lambda n, d: a[a.index(n) + 1] if n in a else d  # noqa: E731
n = int(opt("--tris", 36000))
asis = "--asis" in a
view = 4 if asis else int(opt("--view", 5))
tilt = "none" if asis else opt("--tilt", "stretch")
keep = float(opt("--keep", 0.02 if asis else 0.5))
d = np.load(a[0])
p = d["pos"].astype(np.float64)
e = np.radians(30)
if tilt == "stretch":
    p = p * [1, 1 / np.cos(e), 1]
elif tilt == "pitch":      # camera coordinates (right, screen up, towards the camera) -> the world of a camera 30 degrees up
    p = np.stack([p[:, 0], p[:, 1] * np.cos(e) + p[:, 2] * np.sin(e), -p[:, 1] * np.sin(e) + p[:, 2] * np.cos(e)], 1)
t = np.radians(45 * common.CLOCKWISE_8.index(view))
pos = np.stack([p[:, 0] * np.cos(t) + p[:, 2] * np.sin(t), p[:, 1], -p[:, 0] * np.sin(t) + p[:, 2] * np.cos(t)], 1)
ms = pymeshlab.MeshSet()
ms.add_mesh(pymeshlab.Mesh(pos, d["tris"].astype(np.int32)))
ms.meshing_remove_connected_component_by_face_number(mincomponentsize=int(len(d["tris"]) * keep))
if n and ms.current_mesh().face_number() > n:
    ms.meshing_decimation_quadric_edge_collapse(targetfacenum=n, preservenormal=True, qualitythr=0.4, autoclean=True)
m = ms.current_mesh()
pos, tris = m.vertex_matrix(), m.face_matrix().astype(np.int64)
lo, hi = pos.min(0), pos.max(0)
k = 1.0 / (hi[1] - lo[1])
off = np.array([(lo[0] + hi[0]) / 2, lo[1], (lo[2] + hi[2]) / 2])
pos = (pos - off) * k
# the same transform for other pieces of this candidate (the Hardliner's axe): pos' = (R pos - off) * k
np.savez(a[1], pos=pos, tris=tris, off=off, k=k)
print(a[1], len(pos), "vertices", len(tris), "triangles", "box", pos.min(0).round(3), pos.max(0).round(3))
