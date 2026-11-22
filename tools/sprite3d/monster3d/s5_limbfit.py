"""Stage 5c (round 14, Glowing Fungus): refit the limbs of a stage's existing clip to classic, the body and cap held.

  venv python s5_limbfit.py fit <stage dir> <classic frames dir> <mode> <out clip.json> [--clip <name>]
        [--iters 300] [--prior 0.01] [--rest 0.002] [--ground 0.4] [--smooth 2] [--sweeps 1] [--seed 1]
        [--bounds p=lo:hi,...] [--free p,p,...] [--from-old] [--chamfer W] [--starts K] [--sheet <png>]
  venv python s5_limbfit.py write <stage dir> <clip.json> [<clip.json> ...]
  venv python s5_limbfit.py measure <stage dir> <classic frames dir> <mode> [--clip <name>] [--json <out>]

Why: s5_clipfit.py fits a whole pose (body, head, limbs) from the bind pose. The cap's motion in every clip is approved
and must not change, and the round 11 fit inputs of WL, A1, A2 and GH are gone. This tool takes the clip already in the
stage (same name as the mode's clip) and keeps every bone's track as it is except the limb chains:

- held: every bone outside the limbs (root, cog, pelvis, spine, chest, clavicles, neck, head, jaw, the shell bone),
  world matrices sampled from the stage's own clip with hdkit.view's pose code;
- fitted, per classic frame: the template's 12 limb parameters (s5_clipfit's biped_d2r: Larm_fwd .. Rknee, with its
  base pose of hanging arms) turn the upper arms, forearms, thighs and calves about their bind joints, relative to the
  held parent (W = W_parent B_parent^-1 D B);
- derived: the wrists continue the forearms (bind-relative), the feet are put flat on the ground plane facing the
  pelvis' heading (yaw only), toes bind-relative to the feet.

Score per frame: the mean over the 8 facings of the silhouette IoU against classic (s5_clipfit.Target: camera,
masks, calibration), minus a ground penalty (the lowest body point off y = 0, the body's lift is held), a pull to the
previous frame and a weak pull to the hanging pose. Random search with shrinking steps, sweeps, then [1 2 1]/4
smoothing (around the loop for looping modes).
write: the fitted limb tracks (60 samples a second, parameters between frames by Catmull-Rom, the held parents sampled
from the clip at the same time) replace those bones' tracks in the stage's combined.animations; every other track is
left byte for byte (the cap's included).
"""
import json
import sys
import time
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage as nd

import common
import s5_clipfit as cf
import s5_death as sd

sys.path.insert(0, str(common.WT / "tools"))
import d2r_mesh  # noqa: E402
import d2r_model as dm  # noqa: E402
from hdkit.view import gr2  # noqa: E402

FOLDER = "hd/character/enemy/mxl/m3d/fungus"
LIMB = ["Larm_fwd", "Larm_out", "Lelbow", "Rarm_fwd", "Rarm_out", "Relbow",
        "Lleg_fwd", "Lleg_out", "Lknee", "Rleg_fwd", "Rleg_out", "Rknee"]
# round 16 (--trunk): deltas on top of the held clip for the trunk, cog and head; the cap (on the head) then moves with
# them and is scored against classic's cap (owner/coordinator ruling: fit the cap's motion to classic per mode)
TRUNK = [("cog_rx", {"cog": [1, 0, 0]}, -40, 40, 8), ("cog_ry", {"cog": [0, 1, 0]}, -45, 45, 8),
         ("cog_rz", {"cog": [0, 0, 1]}, -40, 40, 8), ("tx", "x", -1.5, 1.5, 0.25), ("ty", "y", -1.5, 1.0, 0.2),
         ("tz", "z", -1.5, 1.5, 0.25), ("bend", {"spine_01": [1, 0, 0], "chest": [0.7, 0, 0]}, -35, 35, 8),
         ("side", {"spine_01": [0, 0, 1], "chest": [0, 0, 0.7]}, -30, 30, 6),
         ("twist", {"spine_01": [0, 1, 0], "chest": [0, 0.7, 0]}, -35, 35, 8),
         ("head_rx", {"neck": [0.5, 0, 0], "head": [1, 0, 0]}, -35, 35, 8),
         ("head_ry", {"head": [0, 1, 0]}, -35, 35, 8), ("head_rz", {"neck": [0, 0, 0.5], "head": [0, 0, 1]}, -35, 35, 8)]
FITTED = ["L_UpperArm", "R_UpperArm", "L_ForeArm", "R_ForeArm", "L_Thigh", "R_Thigh", "L_Calf", "R_Calf"]
DERIVED = ["L_Wrist", "R_Wrist", "L_Foot", "R_Foot", "L_Ball", "R_Ball"]


def opt(a, n, d):
    return a[a.index(n) + 1] if n in a else d


class LimbRig:
    def __init__(self, stage, clip_name):
        stage = Path(stage)
        model = stage / "overlay" / FOLDER / "torso_lod0.model"
        self.sk = sd.Skeleton(model)
        _m, self.gsk = gr2.load_meshes(model.read_bytes())
        self.clips = gr2.load_clips((stage / "overlay" / FOLDER / "animation" / "combined.animations").read_bytes(), self.gsk)
        self.clip = self.clips[clip_name]
        z = np.load(stage / "skinned_lod0.npz")
        names = [str(x) for x in z["bones"]]
        self.vb = np.array([[self.sk.idx[names[j]] for j in row] for row in z["bone_idx"]])
        self.w = z["weights"]
        self.V = np.hstack([z["pos"], np.ones((len(z["pos"]), 1))])
        self.part_bone = "jaw"
        self.partv = self.vb[:, 0] == self.sk.idx["jaw"]
        self.bodysel = np.nonzero(~self.partv)[0][::3]
        self.partsel = np.nonzero(self.partv)[0][::3]
        tpl = cf.CFG["templates"][cf.mcfg()["template"]]
        self.base = {b: np.array(r, float) for b, r in tpl.get("base", {}).items()}
        P = {p["name"]: p for p in tpl["params"]}
        self.P = [P[n] for n in LIMB]
        self.names = list(LIMB)
        self.lo = np.array([p["lo"] for p in self.P], float)
        self.hi = np.array([p["hi"] for p in self.P], float)
        self.step = np.array([p["step"] for p in self.P], float)
        self.B, self.Binv = self.sk.B, self.sk.Binv
        self.idx = self.sk.idx
        # which bones are recomputed: the fitted and derived ones and everything under them
        rec = set(self.idx[n] for n in FITTED + DERIVED)
        for i, p in enumerate(self.sk.parent):
            if p in rec:
                rec.add(i)
        self.rec = rec
        self._held = {}
        self.trunk = False
        self.arm_fix = False

    def use_trunk(self):
        self.trunk = True
        self.names = list(LIMB) + [n for n, *_ in TRUNK]
        self.lo = np.r_[self.lo[:len(LIMB)], [lo for _n, _b, lo, _h, _s in TRUNK]]
        self.hi = np.r_[self.hi[:len(LIMB)], [hi for _n, _b, _l, hi, _s in TRUNK]]
        self.step = np.r_[self.step[:len(LIMB)], [st for *_x, st in TRUNK]]

    def held(self, t):
        key = round(float(t), 6)
        if key not in self._held:
            H = gr2.pose_at(self.gsk, self.clip, float(t)).worlds
            Lh = [H[i] if p < 0 else np.linalg.inv(H[p]) @ H[i] for i, p in enumerate(self.sk.parent)]
            self._held[key] = (H, Lh)
        return self._held[key][0]

    def held_locals(self, t):
        self.held(t)
        return self._held[round(float(t), 6)][1]

    def worlds(self, x, t):
        H = self.held(t)
        if x is None:
            # derive only: the limb bones keep the clip's own rotations, wrists/feet/toes are derived as below
            x = np.zeros(len(self.P))
            keep_fitted = True
        else:
            keep_fitted = False
        rot = {b: r.copy() for b, r in self.base.items()}
        for p, v in zip(self.P, x):
            for b, wv in p.get("bones", {}).items():
                rot[b] = rot.get(b, np.zeros(3)) + v * np.array(wv, float)
        drot, shift = {}, np.zeros(3)
        if self.trunk and len(x) > len(LIMB):
            for (nm, bw, *_r), v in zip(TRUNK, x[len(LIMB):]):
                if isinstance(bw, str):
                    shift["xyz".index(bw)] += v
                else:
                    for b, wv in bw.items():
                        drot[b] = drot.get(b, np.zeros(3)) + v * np.array(wv, float)
        moved = bool(drot) and any(np.abs(r).max() > 0 for r in drot.values()) or np.abs(shift).max() > 0
        Lh = self.held_locals(t) if moved else None
        W = [None] * len(H)
        heading = None
        for i, p in enumerate(self.sk.parent):
            n = self.sk.names[i]
            if i not in self.rec:
                if not moved:
                    W[i] = H[i]
                    continue
                W[i] = Lh[i] if p < 0 else W[p] @ Lh[i]
                if n in drot:
                    W[i] = sd.about(sd.euler(*drot[n]), W[i][:3, 3]) @ W[i]
                if n == "cog":
                    W[i] = sd.trans(shift) @ W[i]
                continue
            if keep_fitted and n in FITTED:
                W[i] = W[p] @ np.linalg.inv(H[p]) @ H[i]
            elif n in rot or n in FITTED:
                r = rot.get(n, np.zeros(3))
                if self.arm_fix and n in ("L_UpperArm", "R_UpperArm"):
                    # round 16 fix: the donor binds its arms horizontal along x, so the template's x turn (arm_fwd),
                    # applied before the z hang-down, only twisted the arm. Swing forward after hanging it.
                    R = sd.euler(r[0], 0, 0) @ sd.euler(0, r[1], r[2])
                elif self.arm_fix and n in ("L_ForeArm", "R_ForeArm"):
                    # the elbow likewise: its x turn twisted the forearm about itself; bend it about the bind's
                    # vertical instead (forward, +z, for positive elbow on both sides)
                    e = -r[0]
                    R = sd.euler(0, e if n[0] == "R" else -e, 0) @ sd.euler(0, r[1], r[2])
                else:
                    R = sd.euler(*r)
                D = sd.about(R, self.B[i][:3, 3])
                W[i] = W[p] @ self.Binv[p] @ D @ self.B[i]
            elif n in ("L_Wrist", "R_Wrist", "L_Ball", "R_Ball"):
                W[i] = W[p] @ self.Binv[p] @ self.B[i]
            elif n in ("L_Foot", "R_Foot"):
                if heading is None:
                    pel = self.idx["pelvis"]
                    R = (W[pel] @ self.Binv[pel])[:3, :3]
                    f = R @ np.array([0.0, 0.0, 1.0])
                    yaw = np.degrees(np.arctan2(f[0], f[2]))
                    heading = sd.euler(0, yaw, 0)
                ank = (W[p] @ self.Binv[p] @ self.B[i])[:3, 3]
                M = np.eye(4)
                M[:3, :3] = heading @ self.B[i][:3, :3]
                M[:3, 3] = ank
                W[i] = M
            else:
                # under a recomputed bone: the clip's own local
                W[i] = W[p] @ np.linalg.inv(H[p]) @ H[i]
        return W

    def skin(self, W, sel):
        M = np.stack([W[j] @ self.Binv[j] for j in range(len(W))])
        P = np.zeros((len(sel), 3))
        for c in range(4):
            P += self.w[sel, c, None] * np.einsum("nij,nj->ni", M[self.vb[sel, c]], self.V[sel])[:, :3]
        return P

    def posed(self, x, t):
        W = self.worlds(x, t)
        return W, self.skin(W, np.r_[self.bodysel, self.partsel])


class Score:
    def __init__(self, rig, frames_dir, mode, ground_w, chamfer=0.0):
        self.rig = rig
        self.chamfer = chamfer
        self._edt = {}
        # s5_clipfit.Target wants a Rig-like object (sk, vb, w, V, partv, bodysel)
        self.tg = cf.Target(rig, frames_dir, mode)
        self.ground_w = ground_w
        self.part_w = 0.0
        self.tilt_w = 0.0
        self.arm_w = 0.0
        self.arm_idx = None
        self._tilt = {}

    def t(self, i):
        return i / self.tg.fps

    def __call__(self, x, i, detail=False):
        _W, P = self.rig.posed(x, self.t(i))
        g = float(P[:len(self.rig.bodysel), 1].min())
        tot, rows = 0.0, {}
        for d in cf.DIRS:
            sil = self.tg.sil[d, i]
            ours, ours_p = self.tg.masks(P, d, sil.shape)
            a = cf.iou(ours, sil)
            tot += a
            pi_ = None
            if self.part_w and self.tg.part_ok[d, i]:
                pi_ = cf.iou(ours_p, self.tg.part[d, i])
                tot += self.part_w * pi_
                if self.tilt_w:
                    # --tilt W: the cap's lean against classic's (deg / 10, capped at 3), round 16
                    if (d, i) not in self._tilt:
                        self._tilt[d, i] = cf.tilt(self.tg.part[d, i])[0]
                    ta, oa = self._tilt[d, i], cf.tilt(ours_p)[0]
                    if np.isfinite(ta) and np.isfinite(oa):
                        tot -= self.tilt_w * min(abs((oa - ta + 90) % 180 - 90) / 10.0, 3.0)
            if self.arm_w and self.arm_idx is not None:
                # --arms W: our arm pixels against classic's silhouette left over once our torso, legs and cap
                # (dilated 2 px) are taken out, so a fling classic shows and we miss costs directly (round 16)
                nb = len(self.rig.bodysel)
                bx, by = self.tg.proj(P, d)
                isarm = np.zeros(len(bx), bool)
                isarm[self.arm_idx] = True
                rest = cf.splat(bx[~isarm], by[~isarm], sil.shape)
                resid = sil & ~nd.binary_dilation(rest, iterations=2)
                am = cf.splat(bx[:nb][isarm[:nb]], by[:nb][isarm[:nb]], sil.shape)
                am = nd.binary_dilation(am, iterations=1)
                if resid.sum() > 4 or am.sum():
                    tot += self.arm_w * cf.iou(am & ~nd.binary_dilation(rest, iterations=2), resid)
            if self.chamfer:
                # --chamfer W: outline distance both ways (px, capped at 8), so a thin limb that misses classic's raised
                # arm costs as much as its distance, not just its few pixels (round 15)
                if (d, i) not in self._edt:
                    self._edt[d, i] = np.minimum(nd.distance_transform_edt(~sil), 8.0)
                eo = np.minimum(nd.distance_transform_edt(~ours), 8.0)
                c = 0.5 * (float(eo[sil].mean()) + float(self._edt[d, i][ours].mean())) / 8.0
                tot -= self.chamfer * c
            if detail:
                rows[d] = {"iou": round(a, 3), "mask": ours, "part_iou": None if pi_ is None else round(pi_, 3)}
        s = tot / 8 - self.ground_w * (g / 0.1) ** 2
        return (s, rows, g) if detail else s


def fit(a):
    stage, frames, mode, out = a[:4]
    clip = opt(a, "--clip", cf.CFG["clip_names"].get(mode, mode))
    rig = LimbRig(stage, clip)
    rig.arm_fix = "--old-arms" not in a
    sc = Score(rig, frames, mode, float(opt(a, "--ground", "0.4")), float(opt(a, "--chamfer", "0")))
    if "--trunk" in a:
        rig.use_trunk()
        sc.part_w = float(opt(a, "--part", "1.0"))
        sc.tilt_w = float(opt(a, "--tilt", "0"))
    if "--arms" in a:
        sc.arm_w = float(opt(a, "--arms", "1.0"))
        kind = np.load(Path(stage) / "skinned_lod0.npz")["kind"]
        sc.arm_idx = np.nonzero(kind[rig.bodysel] == "arm")[0]
    for b in (opt(a, "--bounds", "") or "").split(","):
        if b:
            n, r = b.split("=")
            k = rig.names.index(n)
            rig.lo[k], rig.hi[k] = (float(v) for v in r.split(":"))
    free = np.ones(len(rig.names), bool)
    if "--free" in a:
        fr = opt(a, "--free", "").split(",")
        free = np.array([n in fr for n in rig.names])
    rng = np.random.default_rng(int(opt(a, "--seed", "1")))
    iters, prior, rest = int(opt(a, "--iters", "300")), float(opt(a, "--prior", "0.01")), float(opt(a, "--rest", "0.002"))
    n = sc.tg.n
    t0 = time.time()
    x0 = np.clip(np.zeros(len(rig.names)), rig.lo, rig.hi)
    if "--init" in a:
        # a previous fit (limb-only ones are padded with zero trunk deltas): every frame starts from it
        ic = json.loads(Path(opt(a, "--init", "")).read_text())
        X = {i: np.clip(np.r_[p, np.zeros(len(rig.names) - len(p))], rig.lo, rig.hi) for i, p in zip(ic["frames"], ic["params"])}
        if rig.arm_fix and not ic.get("arm_fix"):
            # the old arm_fwd / elbow values did nothing (twists); start them at zero under the fixed arms
            for k in [rig.names.index(n_) for n_ in ("Larm_fwd", "Rarm_fwd", "Lelbow", "Relbow")]:
                for x_ in X.values():
                    x_[k] = np.clip(0.0, rig.lo[k], rig.hi[k])
    else:
        X = {}

    def obj(y, i, prev):
        s = sc(y, i)
        if prev is not None:
            s -= prior * float((((y - prev) / rig.step) ** 2).sum())
        return s - rest * float(((y / rig.step) ** 2).sum())

    def search(x, i, n_it, prev, scale0=0.6):
        x = np.clip(x, rig.lo, rig.hi)
        best = obj(x, i, prev)
        for it in range(n_it):
            scale = scale0 * (1 - it / n_it) + 0.05
            y = x.copy()
            pick = (rng.random(len(x)) < 0.25) & free
            pick[rng.choice(np.nonzero(free)[0])] = True
            y[pick] += rng.normal(0, 1, pick.sum()) * rig.step[pick] * scale
            y = np.clip(y, rig.lo, rig.hi)
            s = obj(y, i, prev)
            if s > best:
                best, x = s, y
        return x, best

    # --from-old: per frame, also start from the parameters that best reproduce the stage clip's own limb bone
    # directions (a least-squares fit), and keep whichever start scores better
    old = {}
    if "--from-old" in a and not rig.trunk:
        from scipy.optimize import least_squares
        pairs = [("L_UpperArm", "L_ForeArm"), ("L_ForeArm", "L_Wrist"), ("R_UpperArm", "R_ForeArm"), ("R_ForeArm", "R_Wrist"),
                 ("L_Thigh", "L_Calf"), ("L_Calf", "L_Foot"), ("R_Thigh", "R_Calf"), ("R_Calf", "R_Foot")]
        pi = [(rig.idx[p_], rig.idx[c_]) for p_, c_ in pairs]

        def dirs(W):
            v = np.array([W[c_][:3, 3] - W[p_][:3, 3] for p_, c_ in pi])
            return v / np.linalg.norm(v, axis=1, keepdims=True)
        prev_o = x0
        for i in range(n):
            H = rig.held(sc.t(i))
            target = dirs(H)
            r = least_squares(lambda y: (dirs(rig.worlds(y, sc.t(i))) - target).ravel(), prev_o, bounds=(rig.lo, rig.hi),
                              diff_step=1e-3)
            old[i] = prev_o = r.x
    for i in range(n):
        start = X.get(i, X[i - 1] if i else x0)
        x, b = search(start.copy(), i, iters if i else iters * 2, X.get(i - 1), 0.8 if i else 1.0)
        if i in old:
            x2, b2 = search(old[i].copy(), i, iters, X.get(i - 1), 0.5)
            if b2 > b:
                x, b = x2, b2
        # --starts K: K random starts more per frame (uniform in the bounds), for swings the previous frame cannot reach
        for _k in range(int(opt(a, "--starts", "0"))):
            y0 = x.copy()
            y0[free] = rng.uniform(rig.lo[free], rig.hi[free])
            x3, b3 = search(y0, i, iters // 2, X.get(i - 1), 0.6)
            if b3 > b:
                x, b = x3, b3
        X[i] = x
        print("frame %d score %.3f (%.0f s)" % (i, sc(x, i), time.time() - t0), flush=True)
    for sweep in range(int(opt(a, "--sweeps", "1"))):
        for i in (range(n) if sweep % 2 else range(n - 1, -1, -1)):
            nb = [X[j] for j in (i - 1, i + 1) if 0 <= j < n]
            ref = np.mean(nb, 0)
            X[i] = max((search(x0_.copy(), i, iters // 2, ref, 0.3) for x0_ in [X[i]] + nb), key=lambda c: c[1])[0]
        print("sweep %d (%.0f s)" % (sweep, time.time() - t0), flush=True)
    raw = np.array([X[i] for i in range(n)])
    sm = raw.copy()
    loop = mode in cf.mcfg().get("loop", [])
    for _ in range(int(opt(a, "--smooth", "2"))):
        if loop:
            sm = 0.25 * np.roll(sm, 1, 0) + 0.5 * sm + 0.25 * np.roll(sm, -1, 0)
        else:
            pad = np.vstack([sm[:1], sm, sm[-1:]])
            sm = 0.25 * pad[:-2] + 0.5 * pad[1:-1] + 0.25 * pad[2:]
    # --refine R: after smoothing, R rounds of deterministic coordinate search on the free trunk parameters per frame
    # (steps 0.4/0.2/0.1 of each parameter's step), against the mean of the neighbouring frames as prior; with
    # --dense-cap every cap vertex is splatted. Round 16: the random search left the cap ~1 px off classic's (cap IoU
    # 0.86 where a 1 px shift gives 0.89).
    nref = int(opt(a, "--refine", "0"))
    if nref and rig.trunk:
        if "--dense-cap" in a:
            rig.partsel = np.nonzero(rig.partv)[0]
        tk = [k for k, n_ in enumerate(rig.names) if n_ not in LIMB and free[k]]
        for _r in range(nref):
            for i in range(n):
                nb = [sm[j % n] for j in (i - 1, i + 1) if loop or 0 <= j < n]
                ref = np.mean(nb, 0) if nb else None
                x = sm[i].copy()
                best = obj(x, i, ref)
                for f in (0.4, 0.2, 0.1):
                    for k in tk:
                        for sgn in (1, -1):
                            y = x.copy()
                            y[k] = np.clip(y[k] + sgn * f * rig.step[k], rig.lo[k], rig.hi[k])
                            s_ = obj(y, i, ref)
                            if s_ > best:
                                best, x = s_, y
                sm[i] = x
            print("refine %d (%.0f s)" % (_r, time.time() - t0), flush=True)
    per = []
    for i in range(n):
        s, rows, g = sc(sm[i], i, detail=True)
        per.append({"frame": i, "ground": round(g, 4), "iou": [rows[d]["iou"] for d in cf.DIRS]})
    res = {"mode": mode, "clip": clip, "frames": list(range(n)), "fps": sc.tg.fps, "length": n / sc.tg.fps, "loop": loop,
           "names": rig.names, "trunk": rig.trunk, "arm_fix": rig.arm_fix, "params_raw": raw.round(3).tolist(), "params": sm.round(3).tolist(),
           "settings": {"iters": iters, "prior": prior, "rest": rest, "ground": sc.ground_w, "chamfer": sc.chamfer, "bounds": opt(a, "--bounds", None),
                        "smooth": int(opt(a, "--smooth", "2")), "sweeps": int(opt(a, "--sweeps", "1")),
                        "free": [n_ for n_, f in zip(LIMB, free) if f]},
           "median_iou": round(float(np.median([v for p in per for v in p["iou"]])), 3),
           "ground_max_abs": round(max(abs(p["ground"]) for p in per), 4), "per_frame": per,
           "fit_seconds": round(time.time() - t0, 1)}
    Path(out).write_text(json.dumps(res, indent=1))
    print(json.dumps({k: res[k] for k in ("mode", "median_iou", "ground_max_abs", "fit_seconds")}))
    if "--sheet" in a:
        sheet(sc, sm, opt(a, "--sheet", ""))


def sheet(sc, X, path, dirs=(4, 5, 0, 2)):
    tiles = []
    for d in dirs:
        row = []
        for i, x in enumerate(X):
            _s, rows, _g = sc(x, i, detail=True)
            ours = rows[d]["mask"]
            im = sc.tg.img[d, i]
            t = np.zeros(im.shape[:2] + (3,), np.uint8) + 40
            t[sc.tg.sil[d, i]] = [110, 110, 125]
            t[ours & ~nd.binary_erosion(ours)] = [255, 210, 60]
            row.append(t)
        tiles.append(np.hstack(row))
    img = Image.fromarray(np.vstack(tiles))
    img = img.resize((img.width * 2, img.height * 2), Image.NEAREST)
    ImageDraw.Draw(img).text((4, 2), "classic silhouette (grey) vs fit outline (yellow), facings %s" % (dirs,), fill=(230, 230, 230))
    img.save(path)


def write(a):
    stage = Path(a[0])
    clips = [json.loads(Path(p).read_text()) for p in a[1:]]
    path = stage / "overlay" / FOLDER / "animation" / "combined.animations"
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
    for c in clips:
        rig = LimbRig(stage, c["clip"])
        if c.get("derive_only"):
            # {"clip": name, "derive_only": true}: rewrite only the wrists, feet and toes (round 14: the donor's skill1
            # twists the hands against the forearms; the long arms stretched there)
            L = rig.clip.duration
            times = np.round(np.arange(0, L + 1e-6, 1.0 / 60), 6)
            bones = DERIVED
            bi = [rig.idx[b] for b in bones]
            qs = {b: [] for b in bones}
            ps = {b: [] for b in bones}
            for t in times:
                W = rig.worlds(None, min(t, L))
                for b, i in zip(bones, bi):
                    Lc = np.linalg.inv(W[rig.sk.parent[i]]) @ W[i]
                    qs[b].append(sd.mat_q(Lc[:3, :3]))
                    ps[b].append(Lc[:3, 3])
            an = next(x for x in tree["Animations"] if x["Name"] == c["clip"])
            grp = max(an["TrackGroups"], key=lambda tg: len(tg["TransformTracks"]))
            done = [tr["Name"] for tr in grp["TransformTracks"] if tr["Name"] in qs]
            for tr in grp["TransformTracks"]:
                if tr["Name"] in qs:
                    set_track(tr, qs[tr["Name"]], ps[tr["Name"]], times)
            report[c["clip"]] = {"derive_only": True, "samples": len(times), "tracks": done}
            continue
        if c.get("trunk"):
            rig.use_trunk()
        rig.arm_fix = bool(c.get("arm_fix", False))
        X = np.array(c["params"], float)
        n, fps, L = len(X), c["fps"], c["length"]
        times = np.round(np.arange(0, L + 1e-6, 1.0 / 60), 6)
        if times[-1] < L - 1e-6:
            times = np.append(times, L)
        pos_ = times * fps if c["loop"] else np.minimum(times * fps, n - 1)
        xs = cf.catmull(X, pos_, c["loop"])
        bones = FITTED + DERIVED
        if rig.trunk:
            # the bones the trunk deltas turn or move; the corpse shell bone keeps its held world (under the floor)
            bones = bones + ["cog", "spine_01", "chest", "neck", "head", "loin_cloth"]
        bi = [rig.idx[b] for b in bones]
        qs = {b: [] for b in bones}
        ps = {b: [] for b in bones}
        for t, x in zip(times, xs):
            tt = min(t, rig.clip.duration)
            W = rig.worlds(x, tt)
            H = rig.held(tt)
            for b, i in zip(bones, bi):
                Wi = H[i] if b == "loin_cloth" else W[i]
                Lc = np.linalg.inv(W[rig.sk.parent[i]]) @ Wi
                qs[b].append(sd.mat_q(Lc[:3, :3]))
                ps[b].append(Lc[:3, 3])
        an = next(x for x in tree["Animations"] if x["Name"] == c["clip"])
        grp = max(an["TrackGroups"], key=lambda tg: len(tg["TransformTracks"]))
        done = []
        for tr in grp["TransformTracks"]:
            if tr["Name"] in qs:
                set_track(tr, qs[tr["Name"]], ps[tr["Name"]], times)
                done.append(tr["Name"])
        report[c["clip"]] = {"mode": c["mode"], "samples": len(times), "tracks": done}
    report["bytes"] = d2r_mesh.write_model(g, tree, path)
    (stage / "limbfit.json").write_text(json.dumps(report, indent=1))
    print(json.dumps(report))


def measure(a):
    """Silhouette IoU of a stage's own clip against classic, per facing, whole and in bands: the upper body (cap bottom
    to 55 % of the way to the ground: torso and arms) and the legs (below). Arms: classic's pale limb pixels in the upper
    band (luminance > 60, blue over red by 10, not the cap's blue) against our arm vertices there (stages built by
    s4_procbody.py, which labels the parts; older stages give no arm figure)."""
    stage, frames, mode = a[:3]
    clip = opt(a, "--clip", cf.CFG["clip_names"].get(mode, mode))
    rig = LimbRig(stage, clip)
    tg = cf.Target(rig, frames, mode)
    z = np.load(Path(stage) / "skinned_lod0.npz")
    kind = z["kind"] if "kind" in z.files else None
    allv = np.arange(len(rig.V))
    rows = []
    for i in range(tg.n):
        W = gr2.pose_at(rig.gsk, rig.clip, i / tg.fps).worlds
        Pall = rig.skin(W, allv)
        for d in cf.DIRS:
            sil, part = tg.sil[d, i], tg.part[d, i]
            bx, by = tg.proj(Pall, d)
            body = cf.splat(bx[~rig.partv], by[~rig.partv], sil.shape)
            capm = cf.splat(bx[rig.partv], by[rig.partv], sil.shape)
            ours = body | capm
            gy = -tg.meta[mode]["box"][1]
            ys = np.nonzero(part.any(1))[0]
            cb = ys.max() if len(ys) else gy * 0.4
            split = int(round(cb + 0.55 * (gy - cb)))
            up = np.zeros(sil.shape, bool)
            up[cb + 1:split] = True
            lo_ = np.zeros(sil.shape, bool)
            lo_[split:] = True
            csil = sil & ~part
            r = {"frame": i, "dir": d, "iou": cf.iou(ours, sil), "upper": cf.iou(body & up, csil & up),
                 "legs": cf.iou(body & lo_, csil & lo_),
                 "upper_area": float((body & up).sum() / max((csil & up).sum(), 1)),
                 "legs_area": float((body & lo_).sum() / max((csil & lo_).sum(), 1)),
                 "cap": cf.iou(capm, part) if tg.part_ok[d, i] else np.nan}
            if tg.part_ok[d, i]:
                ta, _tr = cf.tilt(part)
                oa, _or = cf.tilt(capm)
                r["cap_tilt_err"] = abs((oa - ta + 90) % 180 - 90) if np.isfinite(ta) and np.isfinite(oa) else np.nan
            else:
                r["cap_tilt_err"] = np.nan
            if kind is not None:
                arm = kind[~rig.partv] == "arm"
                am = cf.splat(bx[~rig.partv][arm], by[~rig.partv][arm], sil.shape) & up
                im = tg.img[d, i].astype(int)
                L = 0.2126 * im[..., 0] + 0.7152 * im[..., 1] + 0.0722 * im[..., 2]
                pale = csil & up & (L > 60) & (im[..., 2] - im[..., 0] > 10)
                r["arms"] = cf.iou(am, pale)
                r["arm_px_ratio"] = float(am.sum() / max(pale.sum(), 1))
            rows.append(r)
    keys = [k for k in rows[0] if k not in ("frame", "dir")]
    res = {"stage": str(stage), "mode": mode, "clip": clip,
           "median": {k: round(float(np.nanmedian([r[k] for r in rows])), 3) for k in keys},
           "per_dir": {d: {k: round(float(np.nanmedian([r[k] for r in rows if r["dir"] == d] + [np.nan])), 3) for k in keys}
                       for d in cf.DIRS}}
    print(json.dumps({"mode": mode, "median": res["median"]}))
    if "--json" in a:
        Path(opt(a, "--json", "")).write_text(json.dumps(res, indent=1))


if __name__ == "__main__":
    {"fit": fit, "write": write, "measure": measure}[sys.argv[1]](sys.argv[2:])
