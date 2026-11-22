"""Stage 5c: a monster's own clip for any mode (walk, attack, get-hit, ...), fitted to its classic sprite frames.

  venv python s5_clipfit.py fit [--token T] --mode <wl|a1|a2|gh|...> <build stage dir> <classic frames dir> <out clip.json>
                                [--iters 400] [--starts 6] [--smooth 1] [--seed 1] [--sheet <png>] [--frames a-b]
                                [--hold <clip.json> --free p1,p2,... [--hold-lift | --hold-lift-from <clip.json>] [--ground 0.05]]
                                [--bounds p=lo:hi,...] [--rest W]
  venv python s5_clipfit.py write [--token T] <stage dir with overlay> <clip.json> [<clip.json> ...]
  venv python s5_clipfit.py measure [--token T] <build stage dir> <classic frames dir> <clip.json> [--sheet <png>]

Inputs (nothing here is about one monster; what differs per monster is in clipfit_config.json):
- the build stage (s5_build.py): skinned_lod0.npz (bind pose; a rigid part such as the Fungus cap on MONSTERS[token]
  ["cap_bone"]), the donor's skeleton (EV/d2r/data/hd/character/enemy/<donor>/torso_lod0.model);
- classic's frames of the mode (s1_frames.py classic: <mode>/d<D>_f<NN>.png, all 8 facings, and frames.json with each
  mode's box (origin = the unit's ground point), frame count and COF speed);
- the camera of classic's sprites: orthographic, elevation `el`, per-facing azimuths from the monster's caprim.json,
  and k px per unit from the live part's width in the NU frames (s5_corpsefit.Fit.calibrate).

fit: for each frame of the mode, one pose of the donor skeleton (the config's template: a few dozen joint angles plus a
body shift), so that the posed model's silhouette matches classic's frame in all 8 facings at once. Score per facing:
IoU of the whole silhouette + part_weight x IoU of the part (classic: the part_mask colour test, convex hull; ours: the
part's vertices). The sum over facings, minus a small pull toward the previous frame's pose (temporal prior, in steps),
is maximised by a random search with shrinking steps. Frame 0 takes the best of --starts restarts; each later frame
starts from the frame before. The body is put on the ground (lowest vertex at y = 0) in every pose. After the fit each
parameter track is smoothed (--smooth passes of [1 2 1]/4, around the loop for looping modes) and scored again.

Timing comes from classic's mode data: frame i of the mode is at i / fps with fps = 25 x speed / 256 (COF speed), the
clip lasts frames / fps, and an attack's hit frame (the COF key byte) falls at the same time as in classic.

A stage rigged by rig_embed.py (rig.json beside its overlay) is posed through rig_embed's retarget: the template poses the
donor skeleton as before, Rig turns that pose into the stage's own skeleton (embedded lengths, leg IK) and skins with the
stage's bind. write then writes the donor-convention clip into <stage>/clips_donor.animations and retargets the overlay.

write: the fitted clips replace the donor's clips of those modes in the stage's combined.animations (curve types
DaK32fC32f and D4/D3 constants from the file's own type table, 60 samples a second, poses between classic frames by
Catmull-Rom on the parameters). The part bone keeps its track (held at rest under the head); the corpse shell bone is
put under the floor in world space in every sample (so it stays hidden when the body turns over).

measure: per frame and facing, silhouette IoU, part IoU and the part's tilt (orientation of its outline's main axis and
its height/width) against classic; json and an optional sheet (classic | fit outlines, 3 facings, every frame).
"""
import json
import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage as nd
from skimage.morphology import convex_hull_image

import common
import s5_death as sd

sys.path.insert(0, str(common.WT / "tools"))
sys.path.insert(0, str(common.WT / "tools" / "sprite3d"))
import cam_fit  # noqa: E402
import d2r_mesh  # noqa: E402
import d2r_model as dm  # noqa: E402

CFG = json.loads((Path(__file__).with_name("clipfit_config.json")).read_text(encoding="utf-8"))
DIRS = range(8)
SAMPLE_FPS = 60


def mcfg():
    return CFG["monsters"][common.TOKEN]


def mode_timing(frames_dir, mode):
    """(frames, fps, hit frames) of a mode from classic's data: frames.json (s1_frames) and, for the key bytes, the COF."""
    meta = json.loads((Path(frames_dir) / "frames.json").read_text())[mode]
    keys = meta.get("keys")
    if keys is None:
        try:
            sys.path.insert(0, str(common.FCOPY))
            import monster_sheet
            keys = monster_sheet.load(common.TOKEN)[mode]["cof"]["keys"]
        except Exception:  # noqa: BLE001
            keys = []
    fps = 25.0 * meta["speed"] / 256.0
    return meta["frames"], fps, [i for i, k in enumerate(keys) if k]


def part_mask(rgba, rule):
    a = rgba.astype(float)
    R, G, B, A = a[..., 0], a[..., 1], a[..., 2], a[..., 3]
    m = (A > 0) & (B >= rule["b_min"]) & (B - np.maximum(R, G) > rule["b_over_rg"])
    lab, n = nd.label(m, structure=np.ones((3, 3)))
    if not n:
        return m
    size = nd.sum(m, lab, range(1, n + 1))
    sl = nd.find_objects(lab)
    big = sl[int(np.argmax(size))]
    y0, y1, x0, x1 = big[0].start - 4, big[0].stop + 4, big[1].start - 4, big[1].stop + 4
    keep = [i + 1 for i, s in enumerate(sl) if size[i] >= 3 and s[0].start >= y0 and s[0].stop <= y1
            and s[1].start >= x0 and s[1].stop <= x1]
    m = np.isin(lab, keep)
    return convex_hull_image(m) if m.sum() >= 3 else m


def splat(px, py, shape):
    m = np.zeros(shape, bool)
    xi, yi = np.round(px).astype(int), np.round(py).astype(int)
    ok = (xi >= 0) & (yi >= 0) & (xi < shape[1]) & (yi < shape[0])
    m[yi[ok], xi[ok]] = True
    return nd.binary_closing(nd.binary_dilation(m), iterations=1)


def iou(a, b):
    u = (a | b).sum()
    return float((a & b).sum() / u) if u else 0.0


def tilt(mask):
    """(main-axis angle in degrees, height/width of the outline) of a mask, from its second moments."""
    ys, xs = np.nonzero(mask)
    if len(xs) < 5:
        return np.nan, np.nan
    c = np.cov(np.vstack([xs, ys]))
    w, v = np.linalg.eigh(c)
    ang = np.degrees(np.arctan2(v[1, 1], v[0, 1]))
    ang = (ang + 90) % 180 - 90
    return float(ang), float((ys.max() - ys.min() + 1) / (xs.max() - xs.min() + 1))


class Rig:
    """The donor skeleton, the skinned mesh and the pose template."""

    def __init__(self, stage):
        cfg = __import__("s5_build").MONSTERS[common.TOKEN]
        self.sk = sd.Skeleton(common.EV / "d2r/data/hd/character/enemy" / cfg["donor"] / "torso_lod0.model")
        skin = np.load(Path(stage) / "skinned_lod0.npz")
        names = list(skin["bones"])
        self.vb = np.array([[self.sk.idx[names[j]] for j in row] for row in skin["bone_idx"]])
        self.w = skin["weights"]
        self.V = np.hstack([skin["pos"], np.ones((len(skin["pos"]), 1))])
        self.part_bone = cfg.get("cap_bone")
        self.partv = self.vb[:, 0] == self.sk.idx[self.part_bone] if self.part_bone else np.zeros(len(self.V), bool)
        self.bodysel = np.nonzero(~self.partv)[0][::4]
        self.partsel = np.nonzero(self.partv)[0][::3]
        self.tpl = CFG["templates"][mcfg()["template"]]
        self.P = self.tpl["params"]
        self.names = [p["name"] for p in self.P]
        self.lo = np.array([p["lo"] for p in self.P], float)
        self.hi = np.array([p["hi"] for p in self.P], float)
        self.step = np.array([p["step"] for p in self.P], float)
        self.cog = self.sk.idx["cog"]
        # a stage rigged by rig_embed.py (rig.json): the template still poses the donor skeleton (its parameters are about
        # the donor's bind joints), the pose is retargeted onto the stage's own skeleton and skinned with its bind
        self.rt, self.Binv = None, self.sk.Binv
        if (Path(stage) / "rig.json").is_file():
            import rig_embed
            rj = json.loads((Path(stage) / "rig.json").read_text())
            ip = rig_embed.InPlace(cfg, rig_embed.cfg_profile()[1], dict(rj["joints"], _edges=rj["edges"]), Path(rj["donor_model"]),
                                   rj.get("trunk", "delta"))
            if ip.sk.names != self.sk.names:
                raise SystemExit("rig.json: the donor model's bones are not the template skeleton's")
            self.rt = rig_embed.Retarget(ip)
            self.Binv = [np.linalg.inv(F) for F in ip.F]

    def own_worlds(self, loc):
        """World matrices of the skinned skeleton for donor-convention locals (the stage's own after a retarget)."""
        if self.rt is None:
            W = []
            for i, p in enumerate(self.sk.parent):
                W.append(W[p] @ loc[i] if p >= 0 else loc[i])
            return W
        L = self.rt.apply(np.stack(loc))
        return list(self.rt.worlds(self.rt.ip.sk, L))

    def motions(self, x):
        """{bone index: 4x4 world-axis motion about its bind joint} of parameter vector x (template base included)."""
        rot, shift = {}, np.zeros(3)
        for b, r in self.tpl.get("base", {}).items():
            rot[b] = np.array(r, float)
        for p, v in zip(self.P, x):
            if "translate" in p:
                shift += v * np.array(p["translate"], float)
            for b, wv in p.get("bones", {}).items():
                rot[b] = rot.get(b, np.zeros(3)) + v * np.array(wv, float)
        D = {}
        for b, r in rot.items():
            i = self.sk.idx[b]
            D[i] = sd.about(sd.euler(*r), self.sk.B[i][:3, 3])
        D[self.cog] = sd.trans(shift) @ D.get(self.cog, np.eye(4))
        return D

    def posed(self, x, sel=None, lift=None):
        """(world bone matrices with the body on the ground, posed points of sel, lift). lift given: that lift instead of
        the one that puts the lowest point on the ground (round 13: the held body keeps its height, see fit --hold-lift)."""
        D = self.motions(x)
        _l, W = self.sk.pose(D)
        if self.rt is not None:
            W = self.own_worlds(_l)
        sel = np.r_[self.bodysel, self.partsel] if sel is None else sel
        P = self.skin(W, sel)
        lift = -P[:, 1].min() if lift is None else float(lift)
        P[:, 1] += lift
        D[self.cog] = sd.trans(np.array([0.0, lift, 0.0])) @ D[self.cog]
        return D, P, lift

    def skin(self, W, sel):
        M = np.stack([W[j] @ self.Binv[j] for j in range(len(W))])
        P = np.zeros((len(sel), 3))
        for c in range(4):
            P += self.w[sel, c, None] * np.einsum("nij,nj->ni", M[self.vb[sel, c]], self.V[sel])[:, :3]
        return P


class Target:
    """Classic's frames of one mode: silhouettes and part masks per facing and frame, and the camera."""

    def __init__(self, rig, frames_dir, mode):
        import s5_corpsefit as cf
        self.rig = rig
        fd = Path(frames_dir)
        self.meta = json.loads((fd / "frames.json").read_text())
        self.mode = mode
        self.n, self.fps, self.hits = mode_timing(fd, mode)
        m = mcfg()
        cap = json.loads(common.art(m["caprim"]).read_text())
        self.az = {int(k): v["az"] for k, v in cap["views"].items()}
        self.rule = m["part_mask"]
        self.sil, self.part, self.img = {}, {}, {}
        for d in DIRS:
            for i in range(self.n):
                im = np.asarray(Image.open(fd / mode / ("d%d_f%02d.png" % (d, i))).convert("RGBA"))
                self.img[d, i] = im
                self.sil[d, i] = im[..., 3] > 0
                self.part[d, i] = part_mask(im, self.rule)
        # k (px per unit) from the live part's width in the NU frames, as the corpse fit (s5_corpsefit.Fit.calibrate)
        f = cf.Fit.__new__(cf.Fit)
        f.sk, f.vb, f.w, f.V, f.capv = rig.sk, rig.vb, rig.w, rig.V, rig.partv
        f.capb = rig.V[rig.partv, :3]
        f.frames, f.az = self.meta, self.az
        f.nucap = {d: part_mask(np.asarray(Image.open(fd / "nu" / ("d%d_f00.png" % d)).convert("RGBA")), self.rule)
                   for d in DIRS}
        f.dd_dy = 0.0
        self.cal = f.calibrate(float(m.get("el", 35.0)))
        self.k, self.el = f.k, f.el
        self.basis = {d: cam_fit.basis(self.az[d], self.el) for d in DIRS}
        # the part's colour can also be on the body (the Fungus' pale blue limbs pass the rim test): a classic part mask
        # larger than the part can ever show (its face-on area, the bind part seen along its own up axis) or very small
        # is left out of the score and of the tilt measures for that frame and facing
        from scipy.spatial import ConvexHull
        pb = rig.V[rig.partv, :3]
        disc = ConvexHull(pb[:, [0, 2]]).volume * self.k ** 2 if len(pb) > 3 else np.inf
        self.part_area_max = float(disc)
        # and a mask whose outline does not run on part-coloured pixels (the hull took in a limb): the share of the hull's
        # edge on the loose colour test (dilated 1 px) below edge_min
        lo = self.rule.get("loose", self.rule)
        self.rim = {}
        for key, im in self.img.items():
            a = im.astype(int)
            self.rim[key] = nd.binary_dilation((a[..., 3] > 0) & (a[..., 2] >= lo["b_min"])
                                               & (a[..., 2] - np.maximum(a[..., 0], a[..., 1]) > lo["b_over_rg"]))
        emin = float(self.rule.get("edge_min", 0.62))

        def clean(key, m):
            e = m & ~nd.binary_erosion(m)
            return 0.08 * disc <= m.sum() <= 1.2 * disc and e.any() and self.rim[key][e].mean() >= emin
        self.part_ok = {key: bool(clean(key, m)) for key, m in self.part.items()}

    def proj(self, P, d):
        r, u, _w = self.basis[d]
        x0, y0 = -self.meta[self.mode]["box"][0], -self.meta[self.mode]["box"][1]
        return x0 + self.k * (P @ r), y0 - self.k * (P @ u)

    def masks(self, P, d, shape):
        nb = len(self.rig.bodysel)
        bx, by = self.proj(P, d)
        part = splat(bx[nb:], by[nb:], shape)
        return splat(bx[:nb], by[:nb], shape) | part, part

    def score(self, x, i, detail=False):
        lift = getattr(self, "lift", {}).get(i)
        _D, P, _l = self.rig.posed(x, lift=lift)
        # with a held lift the feet are not snapped to the ground: penalise the lowest point's distance from it
        gpen = float(getattr(self, "ground_w", 0.0)) * (P[:, 1].min() / 0.1) ** 2 if lift is not None else 0.0
        wpart = float(mcfg().get("part_weight", 0.5))
        wedge = float(mcfg().get("edge_weight", 0.5))
        tot, rows = 0.0, {}
        for d in DIRS:
            sil, pm = self.sil[d, i], self.part[d, i]
            ours, ours_p = self.masks(P, d, sil.shape)
            ok = self.part_ok[d, i]
            a, b = iou(ours, sil), iou(ours_p, pm) if ok else np.nan
            # our part's outline on classic's part-coloured pixels (works where the classic mask is left out)
            e = ours_p & ~nd.binary_erosion(ours_p)
            edge = float(self.rim[d, i][e].mean()) if e.any() else 0.0
            tot += a + (wpart * b if ok else 0.0) + wedge * edge
            if detail:
                ta, tr = tilt(pm) if ok else (np.nan, np.nan)
                oa, orr = tilt(ours_p)
                da = (oa - ta + 90) % 180 - 90 if np.isfinite(ta) and np.isfinite(oa) else np.nan
                rows[d] = {"iou": round(a, 3), "part_iou": None if not ok else round(b, 3), "tilt_err_deg": None if np.isnan(da) else round(float(da), 1),
                           "hw_ratio": None if not (np.isfinite(orr) and np.isfinite(tr)) else round(orr / tr, 3),
                           "masks": (ours, ours_p)}
        if detail:
            rows["ground"] = round(float(P[:, 1].min()), 4)
        return (tot / 8 - gpen, rows) if detail else tot / 8 - gpen


def fit(a, opt):
    stage, frames_dir, out = a[:3]
    mode = opt("--mode", "a1")
    rig = Rig(stage)
    tg = Target(rig, frames_dir, mode)
    rng = np.random.default_rng(int(opt("--seed", "1")))
    iters, starts = int(opt("--iters", "400")), int(opt("--starts", "6"))
    prior = float(opt("--prior", "0.004"))
    drop = float(opt("--drop", "0.06"))
    fr = opt("--frames", None)
    idx = list(range(tg.n)) if fr is None else list(range(int(fr.split("-")[0]), int(fr.split("-")[1]) + 1))
    t0 = time.time()
    # round 13: --bounds name=lo:hi,... narrows a parameter's range; --hold <clip.json> keeps every parameter not named in
    # --free at that clip's (smoothed) value per frame, so a refit of the limbs leaves the body and the part as they were;
    # --rest W pulls the free parameters toward 0 (the template's hanging limbs) by W x (x / step)^2
    for b in (opt("--bounds", "") or "").split(","):
        if b:
            n, r = b.split("=")
            k = rig.names.index(n)
            rig.lo[k], rig.hi[k] = (float(v) for v in r.split(":"))
    hold = None
    free = np.ones(len(rig.names), bool)
    if opt("--hold", None):
        hc = json.loads(Path(opt("--hold", "")).read_text(encoding="utf-8"))
        hold = {i: np.array(p, float) for i, p in zip(hc["frames"], hc["params"])}
        names = (opt("--free", "") or "").split(",")
        free = np.array([n in names for n in rig.names])
    rest = float(opt("--rest", "0"))
    # --hold-lift: every frame keeps the held clip's lift (body height), so a part on the held bones (the cap) keeps its
    # exact world transform whatever the free limbs do; --ground W penalises the feet leaving the ground instead
    # --hold-lift-from <clip.json>: the lifts stored in that clip instead (a rig_embed stage: its feet differ from the rig
    # the held clip was made on, but its head, and so the cap, rides at the same place for the same lift)
    lifts = None
    if hold is not None and opt("--hold-lift-from", None):
        lc = json.loads(Path(opt("--hold-lift-from", "")).read_text(encoding="utf-8"))
        lifts = {i: float(v) for i, v in zip(lc["frames"], lc["lift"])}
        tg.lift = lifts
        tg.ground_w = float(opt("--ground", "0.05"))
    elif hold is not None and "--hold-lift" in sys.argv:
        lifts = {i: float(rig.posed(hold[i])[2]) for i in hold}
        tg.lift = lifts
        tg.ground_w = float(opt("--ground", "0.05"))

    def held(y, i):
        if hold is None:
            return y
        y = y.copy()
        y[~free] = hold[i][~free]
        return y

    def search(x, i, n_it, prev, scale0=0.6):
        def obj(y):
            s = tg.score(y, i)
            if prev is not None:
                s -= prior * float((((y - prev) / rig.step) ** 2).sum())
            if rest:
                s -= rest * float(((y[free] / rig.step[free]) ** 2).sum())
            return s
        x = held(np.clip(x, rig.lo, rig.hi), i)
        best = obj(x)
        for it in range(n_it):
            scale = scale0 * (1 - it / n_it) + 0.05
            y = x.copy()
            pick = (rng.random(len(x)) < 0.25) & free
            pick[rng.choice(np.nonzero(free)[0])] = True
            y[pick] += rng.normal(0, 1, pick.sum()) * rig.step[pick] * scale
            y = held(np.clip(y, rig.lo, rig.hi), i)
            s = obj(y)
            if s > best:
                best, x = s, y
        return x, best

    X = {}
    x = np.clip(np.zeros(len(rig.names)), rig.lo, rig.hi)
    if hold is not None:
        x = held(x, idx[0])
    for n, i in enumerate(idx):
        if n == 0:
            cands = []
            for s in range(starts):
                x0 = x.copy() if s == 0 else np.clip(rng.normal(0, 1, len(x)) * rig.step * 2.0, rig.lo, rig.hi)
                cands.append(search(x0, i, iters // 2, None, 1.0))
            x, _b = max(cands, key=lambda c: c[1])
            x, _b = search(x, i, iters, None)
        else:
            # from the frame before; a second start from a jump in the root's turn catches fast moves (a flip)
            xa, ba = search(X[idx[n - 1]].copy(), i, iters, X[idx[n - 1]])
            xb = X[idx[n - 1]].copy()
            xb[0] += rng.choice([-1, 1]) * 40
            xb, bb = search(np.clip(xb, rig.lo, rig.hi), i, iters // 2, X[idx[n - 1]], 0.8)
            x = xa if ba >= bb else xb
        # a fast move (a dive, a flip) can leave the search on the wrong side: when the frame scores clearly below the
        # one before, try a grid of root turns (seeds) with the rest of the pose from the frame before
        if n and tg.score(x, i) < tg.score(X[idx[n - 1]], idx[n - 1]) - drop:
            cands = [(x, tg.score(x, i) - prior * float((((x - X[idx[n - 1]]) / rig.step) ** 2).sum()))]
            for rx in (-30, 30, 60, 90, 120, 160):
                for rz in (-35, 0, 35):
                    y = X[idx[n - 1]].copy()
                    y[0], y[2] = rx, rz
                    cands.append(search(np.clip(y, rig.lo, rig.hi), i, iters // 4, X[idx[n - 1]], 0.8))
            x, _b = max(cands, key=lambda c: c[1])
            x, _b = search(x, i, iters, X[idx[n - 1]])
        X[i] = x
        print("frame %d score %.3f (%.0f s)" % (i, tg.score(x, i), time.time() - t0), flush=True)
    # refinement sweeps: each frame again, from itself and from its neighbours, pulled toward the neighbours' mean
    for sweep in range(int(opt("--sweeps", "2"))):
        order = idx if sweep % 2 else idx[::-1]
        for i in order:
            n = idx.index(i)
            nb = [X[idx[j]] for j in (n - 1, n + 1) if 0 <= j < len(idx)]
            ref = np.mean(nb, 0)
            cands = []
            for x0 in [X[i]] + nb:
                cands.append(search(x0.copy(), i, iters // 2, ref, 0.3))
            X[i] = max(cands, key=lambda c: c[1])[0]
        print("sweep %d: %s (%.0f s)" % (sweep, " ".join("%.2f" % tg.score(X[i], i) for i in idx), time.time() - t0), flush=True)
    raw = np.array([X[i] for i in idx])
    sm = raw.copy()
    loop = mode in mcfg().get("loop", []) and fr is None
    for _ in range(int(opt("--smooth", "1"))):
        if loop:
            sm = 0.25 * np.roll(sm, 1, 0) + 0.5 * sm + 0.25 * np.roll(sm, -1, 0)
        else:
            pad = np.vstack([sm[:1], sm, sm[-1:]])
            sm = 0.25 * pad[:-2] + 0.5 * pad[1:-1] + 0.25 * pad[2:]
    if hold is not None:
        sm[:, ~free] = np.array([hold[i] for i in idx])[:, ~free]
    res = {"mode": mode, "clip": CFG["clip_names"][mode], "token": common.TOKEN, "frames": idx, "fps": tg.fps,
           "length": tg.n / tg.fps, "hit_frames": tg.hits, "hit_times": [round(h / tg.fps, 4) for h in tg.hits],
           "loop": loop, "names": rig.names, "params_raw": raw.round(3).tolist(), "params": sm.round(3).tolist(),
           **({"lift": [round(lifts[i], 5) for i in idx]} if lifts else {}),
           "calibration": tg.cal, "fit_seconds": round(time.time() - t0, 1),
           "settings": {"iters": iters, "starts": starts, "prior": prior, "drop": drop, "sweeps": int(opt("--sweeps", "2")),
                        "smooth": int(opt("--smooth", "1")), "hold": opt("--hold", None),
                        "free": [n for n, f in zip(rig.names, free) if f] if hold is not None else None,
                        "bounds": opt("--bounds", None), "rest": rest, "hold_lift": lifts is not None,
                        "ground": float(opt("--ground", "0.05")) if lifts is not None else None}}
    res["measure"] = measure_clip(tg, rig, idx, sm)
    Path(out).write_text(json.dumps(res, indent=1), encoding="utf-8")
    print(json.dumps({k: v for k, v in res["measure"].items() if k != "per_frame"}))
    if "--sheet" in sys.argv:
        sheet(tg, rig, idx, sm, opt("--sheet", ""), res["measure"])


def measure_clip(tg, rig, idx, X):
    per = []
    for i, x in zip(idx, X):
        _s, rows = tg.score(np.asarray(x), i, detail=True)
        g = rows.pop("ground", None)
        per.append({"frame": i, **({"ground": g} if g is not None else {}),
                    **{d: {k: v for k, v in r.items() if k != "masks"} for d, r in rows.items()}})
    allr = [r for p in per for d, r in p.items() if d not in ("frame", "ground")]
    med = lambda k: round(float(np.nanmedian([np.nan if r[k] is None else r[k] for r in allr])), 3)  # noqa: E731
    return {"median_iou": med("iou"), "median_part_iou": med("part_iou"),
            "median_abs_tilt_err_deg": round(float(np.nanmedian([abs(r["tilt_err_deg"]) for r in allr if r["tilt_err_deg"] is not None])), 1),
            "median_hw_ratio": med("hw_ratio"),
            "iou_per_frame": [round(float(np.median([p[d]["iou"] for d in DIRS])), 3) for p in per],
            "part_iou_per_frame": [round(float(np.nanmedian([np.nan if p[d]["part_iou"] is None else p[d]["part_iou"]
                                                             for d in DIRS] + [np.nan])), 3) for p in per],
            "part_masks_used": int(sum(r["part_iou"] is not None for r in allr)), "part_masks_all": len(allr),
            **({"ground_max_abs": round(max(abs(p["ground"]) for p in per), 4)} if per and "ground" in per[0] else {}),
            "per_frame": per}


def sheet(tg, rig, idx, X, path, meas, dirs=(4, 5, 0)):
    tiles = []
    for d in dirs:
        row_c, row_f = [], []
        for i, x in zip(idx, X):
            _s, rows = tg.score(np.asarray(x), i, detail=True)
            ours, ours_p = rows[d]["masks"]
            im = tg.img[d, i]
            h, w = im.shape[:2]
            c = Image.new("RGB", (w, h), (40, 40, 48))
            c.paste(Image.fromarray(im), (0, 0), Image.fromarray(im))
            t = np.zeros((h, w, 3), np.uint8) + 40
            t[tg.sil[d, i]] = [100, 100, 112]
            t[tg.part[d, i]] = [60, 90, 200] if tg.part_ok[d, i] else [70, 70, 90]
            t[ours & ~nd.binary_erosion(ours)] = [255, 210, 60]
            t[ours_p & ~nd.binary_erosion(ours_p)] = [255, 80, 80]
            row_c.append(np.asarray(c))
            row_f.append(t)
        tiles += [np.hstack(row_c), np.hstack(row_f)]
    img = Image.fromarray(np.vstack(tiles)).resize((tiles[0].shape[1] * 2, sum(t.shape[0] for t in tiles) * 2), Image.NEAREST)
    dr = ImageDraw.Draw(img)
    hgt = tiles[0].shape[0] * 2
    for k, d in enumerate(dirs):
        dr.text((4, 2 + 2 * k * hgt), "classic %s d%d" % (tg.mode, d), fill=(230, 230, 230))
        dr.text((4, 2 + (2 * k + 1) * hgt), "fit d%d (yellow body, red part)" % d, fill=(230, 230, 230))
    wt = tiles[0].shape[1] * 2 // len(idx)
    for n, i in enumerate(idx):
        dr.text((n * wt + 4, img.height - 12), "%d %.2f" % (i, meas["iou_per_frame"][n]), fill=(255, 230, 120))
    img.save(path)
    print("sheet", path, img.size)


def catmull(P, t, loop):
    """P (n, k) keys at 0..n-1; values at fractional positions t (loop: around, else clamped)."""
    n = len(P)
    out = []
    for s in t:
        i = int(np.floor(s))
        u = s - i
        if loop:
            p0, p1, p2, p3 = P[(i - 1) % n], P[i % n], P[(i + 1) % n], P[(i + 2) % n]
        else:
            c = lambda j: P[min(max(j, 0), n - 1)]  # noqa: E731
            p0, p1, p2, p3 = c(i - 1), c(i), c(i + 1), c(i + 2)
        out.append(0.5 * (2 * p1 + (-p0 + p2) * u + (2 * p0 - 5 * p1 + 4 * p2 - p3) * u * u + (-p0 + 3 * p1 - 3 * p2 + p3) * u ** 3))
    return np.array(out)


def clip_locals(rig, clip, shell_bone, drop):
    """(sample times, per-sample local matrices) of a fitted clip."""
    X = np.array(clip["params"], float)
    n, fps, L = len(X), clip["fps"], clip["length"]
    times = np.round(np.arange(0, L + 1e-6, 1.0 / SAMPLE_FPS), 6)
    if times[-1] < L - 1e-6:
        times = np.append(times, L)
    # frame i at i/fps; a loop returns to frame 0 at L, a one-shot holds its last frame
    pos_ = times * fps if clip["loop"] else np.minimum(times * fps, n - 1)
    xs = catmull(X, pos_, clip["loop"])
    lifts = catmull(np.array(clip["lift"], float)[:, None], pos_, clip["loop"])[:, 0] if "lift" in clip else [None] * len(xs)
    sk = rig.sk
    S = sk.idx[shell_bone] if shell_bone else None
    hidden = sd.trans(np.array([0.0, -drop, 0.0])) @ sk.B[S] if S is not None else None
    locs = []
    for x, lf in zip(xs, lifts):
        D, _P, _l = rig.posed(x, lift=lf)
        loc, W = sk.pose(D)
        if S is not None:
            loc[S] = np.linalg.inv(W[sk.parent[S]]) @ hidden
        locs.append(loc)
    return times, locs


def write(a, opt):
    stage, clips = Path(a[0]), [json.loads(Path(p).read_text(encoding="utf-8")) for p in a[1:]]
    rig = Rig(stage)
    m = mcfg()
    folder = "hd/character/enemy/mxl/m3d/" + common.NAME
    path = stage / "overlay" / folder / "animation" / "combined.animations"
    if rig.rt is not None:          # rig_embed stage: the donor-convention clips are the source; the overlay is retargeted
        path = stage / "clips_donor.animations"
    g = dm.Gr2File.read(path.read_bytes())
    tree = dm.parse_tree(g)
    kinds = {}
    for an in tree["Animations"]:
        for tg in an["TrackGroups"]:
            for tr in tg["TransformTracks"]:
                for k in ("OrientationCurve", "PositionCurve"):
                    v = tr[k]["CurveData"]
                    kinds.setdefault(list(v.obj.f)[0], v)
    tmpl_k, tmpl_q, tmpl_p = (kinds["CurveDataHeader_DaK32fC32f"], kinds["CurveDataHeader_D4Constant32f"],
                              kinds["CurveDataHeader_D3Constant32f"])
    real = tmpl_k.obj["Knots"][0].td

    def header(tmpl, deg):
        hk = list(tmpl.obj.f)[0]
        h = tmpl.obj[hk]
        return hk, dm.Obj(h.td, {"Format": h["Format"], "Degree": deg})

    def curve_k(knots, controls):
        hk, h = header(tmpl_k, 1)
        return dm.Variant(tmpl_k.td, dm.Obj(tmpl_k.obj.td, {hk: h, "Padding": 0,
                                                             "Knots": [dm.Obj(real, {"Real32": float(x)}) for x in knots],
                                                             "Controls": [dm.Obj(real, {"Real32": float(x)}) for x in controls]}))

    def curve_c(tmpl, values):
        hk, h = header(tmpl, 0)
        return dm.Variant(tmpl.td, dm.Obj(tmpl.obj.td, {hk: h, "Padding": 0, "Controls": [float(x) for x in values]}))

    def set_track(tr, qs, ps, ts):
        qs = np.array(qs)
        for i in range(1, len(qs)):
            if qs[i] @ qs[i - 1] < 0:
                qs[i] = -qs[i]
        ps = np.array(ps)
        tr["OrientationCurve"]["CurveData"] = curve_c(tmpl_q, qs[0]) if np.abs(qs - qs[0]).max() < 1e-6 else curve_k(ts, qs.ravel())
        tr["PositionCurve"]["CurveData"] = curve_c(tmpl_p, ps[0]) if np.abs(ps - ps[0]).max() < 1e-6 else curve_k(ts, ps.ravel())

    report = {}
    by_name = {c["clip"]: c for c in clips}
    for an in tree["Animations"]:
        c = by_name.get(an["Name"])
        if c is None:
            continue
        times, locs = clip_locals(rig, c, m.get("shell_bone"), float(m.get("shell_drop", 12.0)))
        root = next(x for x in an["TrackGroups"] if x["Name"] == "root")
        kept = []
        for tr in root["TransformTracks"]:
            bn = tr["Name"]
            if bn == rig.part_bone:
                kept.append(bn)          # the part stays on its bone at rest under the head (s5_death.py)
                continue
            i = rig.sk.idx[bn]
            set_track(tr, [sd.mat_q(L[i][:3, :3]) for L in locs], [L[i][:3, 3] for L in locs], times)
        an["Duration"] = float(c["length"])
        report[an["Name"]] = {"mode": c["mode"], "length": round(c["length"], 4), "samples": len(times),
                              "fps": round(c["fps"], 3), "loop": c["loop"], "hit_times": c["hit_times"], "kept": kept}
    missing = set(by_name) - set(report)
    if missing:
        raise SystemExit("no clip named %s in %s" % (sorted(missing), path))
    report["bytes"] = d2r_mesh.write_model(g, tree, path)
    if rig.rt is not None:
        import rig_embed
        report["retarget"] = {k: v for k, v in rig_embed.retarget_file(stage).items() if k in by_name or k == "bytes"}
    (stage / "clips.json").write_text(json.dumps(report, indent=1), encoding="utf-8")
    print(json.dumps(report))


def measure(a, opt):
    stage, frames_dir, clip_path = a[:3]
    c = json.loads(Path(clip_path).read_text(encoding="utf-8"))
    rig = Rig(stage)
    tg = Target(rig, frames_dir, c["mode"])
    if "lift" in c:
        tg.lift = dict(zip(c["frames"], c["lift"]))
    m = measure_clip(tg, rig, c["frames"], np.array(c["params"]))
    print(json.dumps({k: v for k, v in m.items() if k != "per_frame"}))
    if "--sheet" in sys.argv:
        sheet(tg, rig, c["frames"], np.array(c["params"]), opt("--sheet", ""), m)


def main():
    a = sys.argv[1:]
    opt = lambda n, d: a[a.index(n) + 1] if n in a else d  # noqa: E731
    vals = ("--mode", "--iters", "--starts", "--smooth", "--seed", "--sheet", "--frames", "--prior", "--drop", "--sweeps",
            "--hold", "--free", "--bounds", "--rest", "--ground", "--hold-lift-from")
    pos = [x for i, x in enumerate(a[1:], 1) if not x.startswith("--") and a[i - 1] not in vals]
    {"fit": fit, "write": write, "measure": measure}[a[0]](pos, opt)


if __name__ == "__main__":
    main()
