"""Stage 3: the axe as its own piece, and the final atlas (body bake on top, axe strip below).

  venv python s3_axe.py <cand stem, e.g. nu_d5_s1> <body dir (body.npz, bake/)> <bake name> <out dir> [--tris 3000]
                        [--albedo albedo_clean.png]

The axe is the loose second piece TripoSG made. In the frame of the model (the input picture read as a level view) body + axe
match the direction-5 sprite best, so one camera is fitted there (elevation 0) and the axe takes its colours straight from that
sprite: blade faces from the axe pixels only (grey, filled outwards), shaft faces from the whole sprite.
Writes  axe.npz      pos (upright body frame, where the sprite holds it), local (shaft along +y, head up, blades in the yz
                     plane, grip at the origin, length 1), tris, uv (final atlas), rel_length (axe length / body height)
        albedo.png   the final atlas (2048 x 2048: body bake squeezed into the top 3/4, axe strip in the bottom 1/4)
        mesh_uv.npz  the body mesh with its uv moved to match
"""
import sys
from pathlib import Path

import numpy as np
import pymeshlab
from PIL import Image
from scipy import ndimage as ndi

import common

sys.path.insert(0, str(common.WT / "tools" / "sprite3d"))
import cam_fit  # noqa: E402

a = sys.argv[1:]
stem, bdir, bake, out = a[0], Path(a[1]), a[2], Path(a[3])
ntris = int(a[a.index("--tris") + 1]) if "--tris" in a else 3000
out.mkdir(parents=True, exist_ok=True)
cand = common.STAGES / "2-shape" / "cand"
body = np.load(cand / (stem + ".npz"))
pieces = np.load(cand / (stem + "_pieces.npz"))
ms = pymeshlab.MeshSet()
ms.add_mesh(pymeshlab.Mesh(pieces["pos_0"].astype(np.float64), pieces["tris_0"].astype(np.int32)))
ms.meshing_decimation_quadric_edge_collapse(targetfacenum=ntris, preservenormal=True, qualitythr=0.4, autoclean=True)
apos, atris = ms.current_mesh().vertex_matrix(), ms.current_mesh().face_matrix().astype(np.int64)

# one camera for body + axe in the model frame, against the whole direction-5 sprite
sprite = np.asarray(Image.open(common.STAGES / "1-frames" / "x4" / "nu00" / "nu_d5.png").convert("RGBA"))
axe_px = np.asarray(Image.open(common.STAGES / "3-texture" / "views_body" / "axe_d5.png").convert("RGBA"))
H, W = sprite.shape[:2]
DS = cam_fit.DS
mask = np.array(Image.fromarray(sprite[..., 3]).resize((W // DS, H // DS), Image.BILINEAR)) > 100
rng = np.random.default_rng(0)
allpos = np.vstack([body["pos"], pieces["pos_0"]])
alltris = np.vstack([body["tris"], pieces["tris_0"] + len(body["pos"])])
p0, p1, p2 = (allpos[alltris[:, k]] for k in range(3))
area = np.linalg.norm(np.cross(p1 - p0, p2 - p0), axis=1)
k = rng.choice(len(alltris), 100000, p=area / area.sum())
b = rng.random((100000, 2))
flip = b.sum(1) > 1
b[flip] = 1 - b[flip]
pts = p0[k] + b[:, :1] * (p1[k] - p0[k]) + b[:, 1:] * (p2[k] - p0[k])
yoff = float(pts[:, 1].mean())
sc, az, s, tx, ty = cam_fit.fit_view(pts - [0, yoff, 0], mask, 0.0, 0.0, 1.0, span=8, step=1.0)
print("camera of the generating view: az %.1f, IoU %.3f" % (az, sc))
xy = cam_fit.project(apos - [0, yoff, 0], az, 0.0, 1.0)
px, py = tx * DS + DS / 2 + s * DS * xy[:, 0], ty * DS + DS / 2 - s * DS * xy[:, 1]

# local frame of the axe: shaft = longest axis, head = the end with more spread
c = apos.mean(0)
_, _, vt = np.linalg.svd(apos - c, full_matrices=False)
if np.linalg.det(vt) < 0:
    vt[2] *= -1
q = (apos - c) @ vt.T                                    # shaft, blade width, thickness
if np.abs(q[q[:, 0] > 0, 1]).mean() < np.abs(q[q[:, 0] < 0, 1]).mean():
    q[:, 0] *= -1
    q[:, 2] *= -1
lo, hi = q[:, 0].min(), q[:, 0].max()
length = hi - lo
shaft_r = np.percentile(np.abs(q[q[:, 0] < lo + 0.3 * length, 1]), 90) * 1.6
grip = lo + 0.3 * length
local = np.stack([q[:, 2], q[:, 0] - grip, q[:, 1]], 1) / length          # x thin, y shaft (head up), z blades
blade_v = np.abs(q[:, 1]) > shaft_r
blade_f = blade_v[atris].sum(1) >= 2
print("axe: %d vertices, %d triangles, %d blade faces, length %.3f of body height %.3f"
      % (len(apos), len(atris), int(blade_f.sum()), length, np.ptp(body["pos"][:, 1])))


def filled(rgba, m):
    """rgb with every pixel outside m taken from the nearest pixel inside."""
    idx = ndi.distance_transform_edt(~m, return_distances=False, return_indices=True)
    return rgba[..., :3][idx[0], idx[1]]


grey = filled(axe_px, axe_px[..., 3] > 100)
whole = filled(sprite, sprite[..., 3] > 100)
SIZE, STRIP = 2048, 512
tile = STRIP - 8
strip = np.zeros((STRIP, SIZE, 3), np.uint8)
for i, img in enumerate((grey, whole)):
    strip[4:4 + tile, 4 + i * (tile + 8):4 + i * (tile + 8) + tile] = np.asarray(
        Image.fromarray(img).resize((tile, tile), Image.BICUBIC))
# faces get their own vertices (blade faces look into the grey tile, shaft faces into the whole sprite)
vid = atris.reshape(-1)
col = np.repeat(np.where(blade_f, 0, 1), 3)
u = (4 + col * (tile + 8) + px[vid] / W * tile) / SIZE
v = (SIZE - STRIP + 4 + py[vid] / H * tile) / SIZE
key = vid * 2 + col
uniq, first, inv = np.unique(key, return_index=True, return_inverse=True)
vsel = vid[first]
uv = np.stack([u[first], v[first]], 1).astype(np.float32)
tris = inv.reshape(-1, 3)

# the upright body frame of s3_prep.py
prep = np.load(bdir / "body.npz")
p = apos[vsel]
up = (np.stack([p[:, 2], p[:, 1] / np.cos(np.radians(30)), -p[:, 0]], 1) - prep["off"]) * float(prep["k"])
np.savez(out / "axe.npz", pos=up, local=local[vsel], tris=tris, uv=uv,
         rel_length=length / np.ptp(body["pos"][:, 1]) * np.cos(np.radians(30)))

alb = Image.open(bdir / bake / (a[a.index("--albedo") + 1] if "--albedo" in a else "albedo.png")).convert("RGB")
atlas = np.zeros((SIZE, SIZE, 3), np.uint8)
atlas[:SIZE - STRIP] = np.asarray(alb.resize((SIZE, SIZE - STRIP), Image.LANCZOS))
atlas[SIZE - STRIP:] = strip
Image.fromarray(atlas).save(out / "albedo.png")
m = np.load(bdir / bake / "mesh_uv.npz")
buv = m["uv"].copy()
buv[:, 1] *= (SIZE - STRIP) / SIZE
np.savez(out / "mesh_uv.npz", pos=m["pos"], nrm=m["nrm"], uv=buv, tris=m["tris"])
print("atlas", atlas.shape, "body", len(m["pos"]), "vertices", len(m["tris"]), "triangles; axe", len(up), "vertices", len(tris),
      "triangles")
