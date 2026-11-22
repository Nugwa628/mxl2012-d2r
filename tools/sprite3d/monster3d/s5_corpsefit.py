"""Stage 5b helper: fit the corpse pose of s5_death.py --pose to classic's corpse (DD) frames, one 3D pose for 8 facings.

  venv python s5_corpsefit.py [--token T] <skinned_lod0.npz> <classic frames dir> <caprim.json> <out pose.json>
                              [--init <pose.json>] [--iters 1500] [--sheet <png>] [--seed 1] [--el 35]
                              [--bound "name=lo,hi;..."]

Inputs: s5_build.py's skinned_lod0.npz (bind pose, cap bound to the cap bone), the classic frames (dd/d<N>_f00.png,
nu/d<N>_f00.png and frames.json with each mode's box, whose origin is the unit's ground point) and the per-facing camera
azimuths of s3_caprim.py's caprim.json (views -> az).
Camera (cam_fit.basis): orthographic, azimuth per facing, one elevation, k px per model unit, the unit's origin at the frame's
origin. k is found first from the live cap's width (NU frames: classic's cap hull against the bind-pose cap, which is rigid
on the head) at the given elevation, then kept for the corpse.
Corpse score per facing: IoU of the whole silhouette + IoU of the cap (classic: the hull of its saturated blue rim; ours: the
splatted cap vertices) - a penalty on the distance of the cap centroids (in px); the sum over the 8 facings is maximised by
a random search with shrinking steps over the pose parameters (cog turn and shift, a curl, the arms, the cap's rotation and
place, and dd_dy: classic draws its DD frames about 12-15 px below the unit's ground point, so the corpse's screen origin
shifts by dd_dy px; fixed at 0 unless --bound opens it, e.g. --bound "dd_dy=0,24"). cap_sink is bounded to 0.3 units so the
fit cannot hide the cap under the floor (y = 0) instead of laying it out. Writes the pose json (s5_death.py --pose) with the per-facing scores; --sheet draws classic | fit outlines.

  venv python s5_corpsefit.py bake [--token T] <build stage dir> <classic frames dir> <caprim.json> <pose.json> <out.png>
                              [--el 35] [--size 512] [--smooth 3] [--gain 1.0] [--sat 1.0] [--gamma 1.0] [--report <json>]
                              [--cap-from <albedo_final.png>,GAIN,SAT]

bake: the corpse albedo (s5_build.py --corpse-albedo) from classic's own DD frames. The body of the stage's skinned_lod0.npz is
put in the fitted pose (the shell's pose), each vertex is projected into the 8 DD frames with the fitted camera, and its
colour is the weighted mean of what the frames show there: weight (n . view)^2 where the vertex is in front (a depth buffer of
body and cap) and the frame is opaque and not the cap's saturated blue. Unseen vertices take their mesh neighbours' colour;
--smooth N rounds of neighbour averaging take out single-frame speckle. Colours: chroma x --sat, then 255 (c/255)^--gamma, then x --gain; rasterised
in the model's own (unsquashed) UV layout at --size. --cap-from: the cap texels (for s5_death.py --shell-cap) are the
live albedo's own cap, scaled down, times GAIN with chroma times SAT.
"""
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage as nd
from skimage.morphology import convex_hull_image

import common
import s5_death as sd

sys.path.insert(0, str(common.WT / "tools" / "sprite3d"))
import cam_fit  # noqa: E402

DIRS = range(8)
# Glowing Fungus DD frames (152 x 111): x0, x1, y0, y1 of the fallen cap per facing
DD_CAP_BOX = {0: (80, 127, 47, 96), 1: (16, 55, 36, 88), 2: (27, 71, 1, 38), 3: (90, 132, 6, 48),
              4: (110, 138, 23, 76), 5: (38, 94, 53, 111), 6: (9, 40, 13, 63), 7: (55, 107, 0, 26)}


def rim_mask(rgba):
    a = rgba.astype(float)
    R, G, B, A = a[..., 0], a[..., 1], a[..., 2], a[..., 3]
    rim = (A > 0) & (B >= 120) & (B - np.maximum(R, G) > 50)
    lab, n = nd.label(rim, structure=np.ones((3, 3)))
    if not n:
        return rim
    # the biggest piece and the pieces of 3+ px inside its box grown by 4 px (the rim is broken by specks; the body's pale
    # blue highlights lie outside it)
    size = nd.sum(rim, lab, range(1, n + 1))
    sl = nd.find_objects(lab)
    big = sl[int(np.argmax(size))]
    y0, y1, x0, x1 = big[0].start - 4, big[0].stop + 4, big[1].start - 4, big[1].stop + 4
    keep = [i + 1 for i, s in enumerate(sl) if size[i] >= 3 and s[0].start >= y0 and s[0].stop <= y1
            and s[1].start >= x0 and s[1].stop <= x1]
    rim = np.isin(lab, keep)
    return convex_hull_image(rim) if rim.sum() >= 3 else rim


def splat(px, py, shape):
    m = np.zeros(shape, bool)
    xi, yi = np.round(px).astype(int), np.round(py).astype(int)
    ok = (xi >= 0) & (yi >= 0) & (xi < shape[1]) & (yi < shape[0])
    m[yi[ok], xi[ok]] = True
    return nd.binary_closing(nd.binary_dilation(m), iterations=1)


def iou(a, b):
    u = (a | b).sum()
    return float((a & b).sum() / u) if u else 0.0


class Fit:
    def __init__(self, skin_path, frames_dir, caprim):
        self.sk = sd.Skeleton(common.EV / "d2r/data/hd/character/enemy" / __import__("s5_build").MONSTERS[common.TOKEN]["donor"]
                              / "torso_lod0.model")
        skin = np.load(skin_path)
        names = list(skin["bones"])
        self.vb = np.array([[self.sk.idx[names[j]] for j in row] for row in skin["bone_idx"]])
        self.w = skin["weights"]
        self.V = np.hstack([skin["pos"], np.ones((len(skin["pos"]), 1))])
        cap_bone = __import__("s5_build").MONSTERS[common.TOKEN]["cap_bone"]
        self.capv = self.vb[:, 0] == self.sk.idx[cap_bone]
        # every 3rd body vertex is plenty for a silhouette at 1x
        self.bodysel = np.nonzero(~self.capv)[0][::3]
        self.capb = skin["pos"][self.capv]
        self.cb = self.capb.mean(0)
        self.frames = json.loads((Path(frames_dir) / "frames.json").read_text())
        self.az = {int(k): v["az"] for k, v in json.loads(Path(caprim).read_text())["views"].items()}
        self.dd, self.ddcap, self.nucap = {}, {}, {}
        for d in DIRS:
            im = np.asarray(Image.open(Path(frames_dir) / "dd" / ("d%d_f00.png" % d)).convert("RGBA"))
            self.dd[d] = (im[..., 3] > 0, im)
            if DD_CAP_BOX:
                # classic's fallen cap: its opaque pixels inside a box read off the DD frame (the saturated-blue rim test
                # also takes the body's pale blue highlights, and an edge-on or upturned cap shows little rim)
                x0, x1, y0, y1 = DD_CAP_BOX[d]
                m = np.zeros(im.shape[:2], bool)
                m[y0:y1, x0:x1] = im[y0:y1, x0:x1, 3] > 0
                self.ddcap[d] = m
            else:
                self.ddcap[d] = rim_mask(im)
            nu = np.asarray(Image.open(Path(frames_dir) / "nu" / ("d%d_f00.png" % d)).convert("RGBA"))
            self.nucap[d] = rim_mask(nu)

    dd_dy = 0.0     # the DD frames' origin shift (px, down), fitted with the pose (pose params 'dd_dy')

    def proj(self, P, d, k, el, mode):
        r, u, _w = cam_fit.basis(self.az[d], el)
        x0, y0 = -self.frames[mode]["box"][0], -self.frames[mode]["box"][1]
        if mode == "dd":
            y0 += self.dd_dy
        return x0 + k * (P @ r), y0 - k * (P @ u)

    def calibrate(self, el=35.0):
        """k from the live cap's WIDTH (classic's rim hull in the NU frames against the bind-pose cap), median over the
        facings. The cap's height on screen is not used: classic's live cap shows rounder than ours (its tilt, see the
        report), and fitting it pulls the elevation to the end of any range."""
        ks = []
        for d in DIRS:
            px, _py = self.proj(self.capb, d, 1.0, el, "nu")
            xs = np.nonzero(self.nucap[d])[1]
            ks.append((xs.max() - xs.min() + 1) / (px.max() - px.min() + 1e-9))
        self.k, self.el = float(np.median(ks)), el
        return {"k": round(self.k, 3), "k_per_facing": [round(float(x), 2) for x in ks], "el": el}

    def corpse(self, pose):
        """(body points, cap points) of the corpse of `pose`, world coordinates."""
        sd.set_pose(pose)
        sk = self.sk
        D = sd.body_motion(sk, sd.LENGTH)
        _l, W = sk.pose(D)
        M = np.stack([W[j] @ sk.Binv[j] for j in range(len(W))])
        sel = self.bodysel
        P = np.zeros((len(sel), 3))
        for c in range(4):
            P += self.w[sel, c, None] * np.einsum("nij,nj->ni", M[self.vb[sel, c]], self.V[sel])[:, :3]
        P[:, 1] -= P[:, 1].min()
        C, _centre, _R = sd.cap_rest(self.capb, self.cb, pose)
        Q = (C @ np.hstack([self.capb, np.ones((len(self.capb), 1))]).T).T[:, :3]
        return P, Q

    def score(self, pose, detail=False):
        self.dd_dy = float(pose.get("params", {}).get("dd_dy", 0.0))
        P, Q = self.corpse(pose)
        tot, rows = 0.0, {}
        for d in DIRS:
            sil, _im = self.dd[d]
            bx, by = self.proj(P, d, self.k, self.el, "dd")
            # the game floor hides what lies under it (--hide-body relies on that): the sunk part of the cap is not seen
            above = Q[:, 1] >= 0
            cx, cy = self.proj(Q[above], d, self.k, self.el, "dd")
            ours_cap = splat(cx, cy, sil.shape)
            ours = splat(bx, by, sil.shape) | ours_cap
            i_all, i_cap = iou(ours, sil), iou(ours_cap, self.ddcap[d])
            if self.ddcap[d].any() and ours_cap.any():
                ya, xa = np.nonzero(self.ddcap[d])
                yb, xb = np.nonzero(ours_cap)
                dist = float(np.hypot(xa.mean() - xb.mean(), ya.mean() - yb.mean()))
            else:
                dist = 99.0
            s = i_all + i_cap - 0.01 * dist
            tot += s
            if detail:
                rows[d] = {"iou": round(i_all, 3), "cap_iou": round(i_cap, 3), "cap_dist_px": round(dist, 1),
                           "masks": (ours, ours_cap)}
        return (tot / 8, rows) if detail else tot / 8


def posed_body(f, pose):
    """All vertices of the Fit's mesh in `pose` (world; the body's lowest point on the ground). The cap is not moved."""
    sd.set_pose(pose)
    sk = f.sk
    _l, W = sk.pose(sd.body_motion(sk, sd.LENGTH))
    M = np.stack([W[j] @ sk.Binv[j] for j in range(len(W))])
    P = np.zeros((len(f.V), 3))
    for c in range(4):
        P += f.w[:, c, None] * np.einsum("nij,nj->ni", M[f.vb[:, c]], f.V)[:, :3]
    P[:, 1] -= P[~f.capv, 1].min()
    return P


def raster_uv(uv, tris, colr, size, cov_out=None):
    """Per-vertex colours rasterised in UV space (barycentric), charts grown by 8 px, the rest the mean colour. cov_out (a
    list) gets the coverage before the growing."""
    img = np.zeros((size, size, 3), np.float32)
    cov = np.zeros((size, size), bool)
    for t in tris:
        q = uv[t] * size
        x0, y0 = np.floor(q.min(0)).astype(int)
        x1, y1 = np.ceil(q.max(0)).astype(int)
        x0, y0, x1, y1 = max(x0, 0), max(y0, 0), min(x1, size - 1), min(y1, size - 1)
        if x1 < x0 or y1 < y0:
            continue
        yy, xx = np.mgrid[y0:y1 + 1, x0:x1 + 1] + 0.5
        (ax, ay), (bx, by), (cx, cy) = q
        den = (by - cy) * (ax - cx) + (cx - bx) * (ay - cy)
        if abs(den) < 1e-12:
            continue
        l1 = ((by - cy) * (xx - cx) + (cx - bx) * (yy - cy)) / den
        l2 = ((cy - ay) * (xx - cx) + (ax - cx) * (yy - cy)) / den
        l3 = 1 - l1 - l2
        m = (l1 >= -0.02) & (l2 >= -0.02) & (l3 >= -0.02)
        if not m.any():
            continue
        c = l1[..., None] * colr[t[0]] + l2[..., None] * colr[t[1]] + l3[..., None] * colr[t[2]]
        img[y0:y1 + 1, x0:x1 + 1][m] = c[m]
        cov[y0:y1 + 1, x0:x1 + 1] |= m
    if cov_out is not None:
        cov_out.append(cov.copy())
    for _ in range(8):
        grown = nd.grey_dilation(img * cov[..., None], size=(3, 3, 1))
        nc = nd.binary_dilation(cov)
        img[nc & ~cov] = grown[nc & ~cov]
        cov = nc
    img[~cov] = colr.mean(0)
    return img


def bake(a, opt):
    import scipy.sparse as sp
    import render_soft
    stage, frames, caprim, pose_path, out = a[:5]
    f = Fit(Path(stage) / "skinned_lod0.npz", frames, caprim)
    cal = f.calibrate(float(opt("--el", "35")))
    pose = json.loads(Path(pose_path).read_text(encoding="utf-8"))
    f.dd_dy = float(pose.get("params", {}).get("dd_dy", 0.0))
    skin = np.load(Path(stage) / "skinned_lod0.npz")
    T = skin["tris"]
    P = posed_body(f, pose)
    C, _c, _R = sd.cap_rest(f.capb, f.cb, pose)
    P[f.capv] = (C @ np.hstack([f.capb, np.ones((len(f.capb), 1))]).T).T[:, :3]
    N = render_soft.vertex_normals(P, T)
    body = ~f.capv
    acc, wsum = np.zeros((len(P), 3)), np.zeros(len(P))
    for d in DIRS:
        sil, im = f.dd[d]
        _r, _u, w = cam_fit.basis(f.az[d], f.el)
        px, py = f.proj(P, d, f.k, f.el, "dd")
        z = P @ w
        H, Wd = sil.shape
        zb = np.full((H, Wd), -np.inf)
        xi, yi = np.round(px).astype(int), np.round(py).astype(int)
        ok = (xi >= 0) & (yi >= 0) & (xi < Wd) & (yi < H)
        np.maximum.at(zb, (yi[ok], xi[ok]), z[ok])
        zb = nd.maximum_filter(zb, 3)
        xc, yc = np.clip(xi, 0, Wd - 1), np.clip(yi, 0, H - 1)
        vis = ok & body & (z >= zb[yc, xc] - 0.35)
        col = im.astype(float)[yc, xc]
        blue = col[:, 2] - np.maximum(col[:, 0], col[:, 1])
        good = vis & (col[:, 3] > 0) & ~((col[:, 2] >= 120) & (blue > 50))
        wt = np.clip(N @ w, 0, 1) ** 2 * good
        acc += wt[:, None] * col[:, :3]
        wsum += wt
    seen = wsum > 1e-3
    colr = np.zeros((len(P), 3))
    colr[seen] = acc[seen] / wsum[seen, None]
    n = len(P)
    ij = np.vstack([T[:, [0, 1]], T[:, [1, 2]], T[:, [2, 0]]])
    A = sp.coo_matrix((np.ones(2 * len(ij)), (np.r_[ij[:, 0], ij[:, 1]], np.r_[ij[:, 1], ij[:, 0]])), shape=(n, n)).tocsr()
    A.data[:] = 1.0
    known = seen & body
    for _ in range(300):            # unseen body vertices take their neighbours' colour
        if known.sum() == body.sum():
            break
        s_ = A @ (colr * known[:, None])
        c_ = A @ known.astype(float)
        new = ~known & body & (c_ > 0)
        colr[new] = s_[new] / c_[new, None]
        known = known | new
    colr[body & ~known] = colr[known].mean(0)     # pieces with no seen vertex at all
    deg = np.asarray(A.sum(1)).ravel()
    for _ in range(int(opt("--smooth", "3"))):
        colr[body] = (0.5 * colr + 0.5 * (A @ colr) / np.maximum(deg, 1)[:, None])[body]
    lum = np.array([0.2126, 0.7152, 0.0722])
    L0 = colr @ lum
    colr = L0[:, None] + (colr - L0[:, None]) * float(opt("--sat", "1.0"))
    colr = 255 * np.power(np.clip(colr, 0, 255) / 255, float(opt("--gamma", "1.0")))   # classic's corpse: dark mid, bright top
    colr = np.clip(colr * float(opt("--gain", "1.0")), 0, 255)
    size = int(opt("--size", "512"))
    strip = json.loads((Path(stage) / "build.json").read_text(encoding="utf-8")).get("strip") or 0.0
    uv = skin["uv"].copy()
    uv[:, 0] = uv[:, 0] / (1 - strip)
    bcov = []
    img = raster_uv(uv, T[body[T].all(1)], colr, size, bcov)
    cap_rep = None
    if opt("--cap-from", None) is not None:
        # the corpse cap (s5_death.py --shell-cap): the live albedo's cap texels, scaled to the miniature, times GAIN with
        # their chroma times SAT: the rim pattern and dark centre stay, the rim gets as bright as classic's corpse rim
        src, cg, cs = opt("--cap-from", "").split(",")
        alb = Image.open(src).convert("RGB")
        Wa = alb.width
        alb = np.asarray(alb.crop((0, 0, int(round(Wa * (1 - strip))), alb.height)).resize((size, size), Image.BOX), np.float32)
        cov = []
        raster_uv(uv, T[(~body)[T].all(1)], np.zeros((len(P), 3)), size, cov)
        capm = cov[0] | (nd.binary_dilation(cov[0], iterations=2) & ~bcov[0])
        La = alb @ lum
        ca = La[..., None] + (alb - La[..., None]) * float(cs)
        ca = np.clip(ca * float(cg), 0, 255)
        img[capm] = ca[capm]
        cap_rep = {"from": src, "gain": float(cg), "sat": float(cs), "texels": int(capm.sum()),
                   "L_p10_50_90": [round(float(x), 1) for x in np.percentile(ca[capm] @ lum, [10, 50, 90])]}
    Image.fromarray(np.clip(img, 0, 255).astype(np.uint8)).save(out)
    rep = {"calibration": cal, "seen_share": round(float((seen & body).sum() / body.sum()), 3),
           "vertex_L_before_p10_50_90": [round(float(x), 1) for x in np.percentile(L0[body], [10, 50, 90])],
           "vertex_L_p10_50_90": [round(float(x), 1) for x in np.percentile(colr[body] @ lum, [10, 50, 90])],
           "rgb_mean": [round(float(x), 1) for x in colr[body].mean(0)], "gain": float(opt("--gain", "1.0")),
           "sat": float(opt("--sat", "1.0")), "gamma": float(opt("--gamma", "1.0")), "smooth": int(opt("--smooth", "3")), "cap": cap_rep}
    if opt("--report", None) is not None:
        Path(opt("--report", "")).write_text(json.dumps(rep, indent=1), encoding="utf-8")
    print(json.dumps(rep))


# parameter vector <-> pose
NAMES = ["cog_rx", "cog_ry", "cog_rz", "sh_x", "sh_z", "curl", "legs", "arm_fwd", "arm_down",
         "cap_rx", "cap_ry", "cap_rz", "cap_x", "cap_z", "cap_sink", "cap_scale", "dd_dy"]
STEP = np.array([20, 30, 20, 1.0, 1.0, 15, 20, 30, 20, 25, 30, 25, 1.0, 1.0, 0.3, 0.15, 4.0])
# cap_sink stays within 0.3 of the floor: the game floor hides a sunk cap (round 6). dd_dy (fixed at 0 unless --bound
# opens it) shifts the DD frames' origin down: classic may draw a corpse lower than the unit's ground point, and without
# the shift the fit sinks or flattens the cap to reach it (round 8)
LO = np.array([-60, -180, -130, -5, -5, 0, 0, -90, 0, -180, -180, -180, -7, -7, -0.3, 1.0, 0.0])
HI = np.array([60, 180, 130, 5, 5, 45, 90, 90, 90, 180, 180, 180, 7, 7, 0.3, 1.0, 0.0])


def to_pose(x):
    v = dict(zip(NAMES, x))
    c, g = v["curl"], v["legs"]
    bones = {"spine_01": [c, 0, 0], "chest": [0.7 * c, 0, 0], "neck": [0.5 * c, 0, 0], "head": [0.5 * c, 0, 0],
             "L_Thigh": [-g, 0, 0], "R_Thigh": [-g, 0, 0], "L_Calf": [1.3 * g, 0, 0], "R_Calf": [1.3 * g, 0, 0],
             "L_UpperArm": [-v["arm_fwd"], 0, -v["arm_down"]], "R_UpperArm": [-v["arm_fwd"], 0, v["arm_down"]],
             "L_ForeArm": [-0.5 * v["arm_fwd"], 0, 0], "R_ForeArm": [-0.5 * v["arm_fwd"], 0, 0]}
    return {"cog": [v["cog_rx"], v["cog_ry"], v["cog_rz"]], "pivot": [0.0, 0.0, 0.0], "shift": [v["sh_x"], 0.0, v["sh_z"]],
            "bones": bones, "cap": {"rot": [v["cap_rx"], v["cap_ry"], v["cap_rz"]], "centre": [v["cap_x"], v["cap_z"]],
                                    "sink": v["cap_sink"], "scale": v["cap_scale"]},
            "params": {k: round(float(val), 3) for k, val in v.items()}}


def main():
    a = sys.argv[1:]
    opt = lambda n, d: a[a.index(n) + 1] if n in a else d  # noqa: E731
    if a and a[0] == "bake":
        flags = ("--el", "--size", "--smooth", "--gain", "--sat", "--gamma", "--report", "--token", "--cap-from")
        return bake([x for i, x in enumerate(a) if i > 0 and not x.startswith("--") and a[i - 1] not in flags], opt)
    pos =[x for i, x in enumerate(a) if not x.startswith("--") and (i == 0 or a[i - 1] not in
                                                                         ("--init", "--iters", "--sheet", "--seed", "--token", "--el", "--bound"))]
    skin, frames, caprim, out = pos[:4]
    f = Fit(skin, frames, caprim)
    cal = f.calibrate(float(opt("--el", "35")))
    print("calibration", cal)
    rng = np.random.default_rng(int(opt("--seed", "1")))
    for b in opt("--bound", "").split(";") if "--bound" in a else []:
        # --bound "name=lo,hi;...": a narrower range for a parameter (e.g. cap_rz=-130,-90: top turned a little down)
        n_, r_ = b.split("=")
        LO[NAMES.index(n_)], HI[NAMES.index(n_)] = map(float, r_.split(","))
    if "--init" in a:
        ip = json.loads(Path(opt("--init", "")).read_text())["params"]
        x = np.clip(np.array([ip.get(n, 0.0 if n == "dd_dy" else 1.0) for n in NAMES], float), LO, HI)
    else:
        # side fall onto the left side (+x), head to +x, cap on its rim beyond the head, top facing +x (classic DD)
        x = np.array([0, 0, -90, 0, 0, 20, 40, 30, 60, 0, 0, -90, 5.0, 0, 0.1, 1.0, 0.0])
    best = f.score(to_pose(x))
    iters = int(opt("--iters", "1500"))
    for it in range(iters):
        scale = 0.6 * (1 - it / iters) + 0.05
        y = x.copy()
        pick = rng.random(len(x)) < 0.3
        pick[rng.integers(len(x))] = True
        y[pick] += rng.normal(0, 1, pick.sum()) * STEP[pick] * scale
        y = np.clip(y, LO, HI)
        s = f.score(to_pose(y))
        if s > best:
            best, x = s, y
        if it % 250 == 0:
            print(it, round(best, 4))
    total, rows = f.score(to_pose(x), detail=True)
    pose = to_pose(x)
    pose["fit"] = {"score": round(total, 4), "calibration": cal,
                   "per_facing": {d: {k: v for k, v in r.items() if k != "masks"} for d, r in rows.items()},
                   "median_iou": round(float(np.median([r["iou"] for r in rows.values()])), 3),
                   "median_cap_iou": round(float(np.median([r["cap_iou"] for r in rows.values()])), 3),
                   "median_cap_dist_px": round(float(np.median([r["cap_dist_px"] for r in rows.values()])), 1)}
    Path(out).write_text(json.dumps(pose, indent=1), encoding="utf-8")
    print(json.dumps(pose["fit"]))
    if "--sheet" in a:
        tiles = []
        for d in DIRS:
            sil, im = f.dd[d]
            ours, ours_cap = rows[d]["masks"]
            t = np.zeros(sil.shape + (3,), np.uint8) + 40
            t[sil] = [110, 110, 120]
            t[f.ddcap[d]] = [60, 90, 200]
            edge = ours & ~nd.binary_erosion(ours)
            t[edge] = [255, 210, 60]
            ce = ours_cap & ~nd.binary_erosion(ours_cap)
            t[ce] = [255, 80, 80]
            big = Image.fromarray(t).resize((sil.shape[1] * 3, sil.shape[0] * 3), Image.NEAREST)
            orig = Image.fromarray(im).resize(big.size, Image.NEAREST)
            pair = Image.new("RGB", (big.width * 2, big.height), (40, 40, 48))
            pair.paste(orig, (0, 0), orig)
            pair.paste(big, (big.width, 0))
            ImageDraw.Draw(pair).text((4, 4), "d%d iou %.2f cap %.2f dist %.1f" % (d, rows[d]["iou"], rows[d]["cap_iou"],
                                                                               rows[d]["cap_dist_px"]), fill=(240, 240, 240))
            tiles.append(np.asarray(pair))
        grid = np.vstack([np.hstack(tiles[i:i + 2]) for i in range(0, 8, 2)])
        Image.fromarray(grid).save(opt("--sheet", ""))


if __name__ == "__main__":
    main()
