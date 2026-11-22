"""Stage 2: put two separately generated parts (the Fungus: body and cap) into one mesh.

  venv python s2_join.py [--token T] <body score name> <cap score name> <out.npz>

Both parts were scored by s2_score.py against the sprites of their own part (s2_parts.py) with the SAME fixed camera
(--elev, --ky), so each has, per direction, the scale and offset that lay it on its part of the sprite. From those 8 pairs:
the cap's size against the body (median of the scale ratios), its turn about the vertical (median azimuth difference) and
its place (least squares over the 16 screen equations). Writes the joined mesh (body frame, y up, facing +z): score it as
<name>=<out.npz>:4:none.
"""
import json
import sys

import numpy as np

import common

sys.path.insert(0, str(common.WT / "tools" / "sprite3d"))
import cam_fit  # noqa: E402

body, cap, out = sys.argv[1:4]
S = common.STAGES / "2-shape" / "score"
B, C = np.load(S / body / "body.npz"), np.load(S / cap / "body.npz")
cb, cc = (json.loads((S / n / "cams.json").read_text())["cams"] for n in (body, cap))
ring = [str(v) for v in common.CLOCKWISE_8]
assert all(cb[v]["el"] == cc[v]["el"] and cb[v]["ky"] == cc[v]["ky"] for v in ring), "score both parts with the same --elev and --ky"
k = float(np.median([cc[v]["s"] / cb[v]["s"] for v in ring]))
th = np.radians(float(np.median([((cb[v]["az"] - cc[v]["az"] + 180) % 360) - 180 for v in ring])))
A, rhs = [], []
for v in ring:
    b, c = cb[v], cc[v]
    r, u, _ = cam_fit.basis(b["az"], b["el"])
    A.append(b["s"] * r)
    rhs.append(c["tx"] - b["tx"])
    A.append(b["s"] * b["ky"] * u)
    rhs.append(b["ty"] - c["ty"] + b["ky"] * u[1] * (b["s"] * b["yoff"] - c["s"] * c["yoff"]))
o, res, *_ = np.linalg.lstsq(np.array(A), np.array(rhs), rcond=None)
p = C["pos"]
p = np.stack([p[:, 0] * np.cos(th) + p[:, 2] * np.sin(th), p[:, 1], -p[:, 0] * np.sin(th) + p[:, 2] * np.cos(th)], 1) * k + o
pos = np.vstack([B["pos"], p])
tris = np.vstack([B["tris"], C["tris"] + len(B["pos"])])
np.savez(out, pos=pos, tris=tris)
err = np.array(A) @ o - np.array(rhs)
print(out, "cap scale %.3f turn %.1f deg at %s; screen misfit rms %.1f px (4x sprite pixels)"
      % (k, np.degrees(th), o.round(3), float(np.sqrt((err ** 2).mean()))))
