"""Round 18: the corpse pose of the HD body, fitted to classic's DD frames (all 8 facings), for s4_hdcap.py corpse --target.

  venv python s4_hdcorpse.py fit <stage> <classic frames dir> <caprim.json> <out pose.json> [--side L|R|both]
                                 [--iters 2500] [--seed 1] [--el 35] [--sheet <png>] [--init <pose.json>]
                                 [--cap-flat | --cap-attached] [--outside 0.6] [--ground 0.08]

Owner, round 18: "he is supposed to be laying on his side, with his arms and legs folded over to the side too, check
legacy". Classic's DD frames show a low, long, compact heap: the body on its side along the ground, arms and legs folded
to the same side, and the cap lying flat on the ground beside the head.

The pose model is s5_death.py's (set_pose: world-axis turns about the bind joints, x side, y up, z forward; the cog
turns about the bind origin, then shifts) on THIS stage's skeleton and mesh (skinned_lod3.npz), scored with
s5_corpsefit.Fit (classic's camera per facing, k from the live cap's width, IoU of the whole silhouette and of the cap
region, the cap centroid distance).
- on its side: the cog's roll about the forward axis is bounded to 60..120 degrees (--side L) or -120..-60 (R); both
  are fitted and the better kept unless --side picks one;
- folded limbs: thighs, calves, upper arms and forearms swing forward or back and in or out freely (body frame), the
  trunk can curl and bend sideways, the head turn;
- the cap: its own up axis (the bind cap's least-variance axis) turned to world up, then a turn about up and tilts of up
  to 100 degrees (classic's DD frames show it on its rim beside the head: thin and upright at facings 4 and 6, its
  gills to the camera at 0 and 5); --cap-flat keeps the tilts within 8 degrees (lying flat). Sunk 0.05 under the floor;
  a soft pull keeps its centre within its radius + 0.6 units of the head;
- --ground W (0.08): minus W times (the trunk's lowest point above 0.15 units + a quarter of the heap's mean height), so
  it lies on the floor rather than propped on a leg;
- --cap-attached (owner, round 18: "it is standing, attached just slightly bent where it touches the ground"): the cap
  is not thrown; it stays on the head (the jaw, rigid as in every other clip) with a flex of up to 12 degrees at the
  jaw, so the head and neck put it on its rim; the heap with the cap is set on the floor and the cap's lowest point
  is pulled onto it;
- --height H (2.0) --height-w W (0.3): minus W times the heap's 97th-percentile height above H units;
- --outside W (0.6): minus W times the mean share of our silhouette outside classic's (a limb thrown out of the heap).
"""
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage as nd

import common
import s5_corpsefit as cf
import s5_death as sd
import s4_procbody as pb

NAMES = ["cog_rx", "cog_ry", "cog_rz", "sh_x", "sh_z", "curl", "bend", "head_rx", "head_rz",
         "Lua_x", "Lua_z", "Rua_x", "Rua_z", "Lfa_x", "Rfa_x", "Lth_x", "Lth_z", "Rth_x", "Rth_z", "Lca_x", "Rca_x",
         "cap_ry", "cap_tx", "cap_tz", "cap_x", "cap_z", "dd_dy", "jaw_x", "jaw_z"]
LO = np.array([-40, -180, 60, -3, -3, -30, -30, -60, -60, -110, -90, -110, -90, -110, -110, -110, -60, -110, -60,
               -10, -10, -180, -100, -100, -6, -6, 0, -12, -12], float)
HI = np.array([40, 180, 120, 3, 3, 60, 30, 60, 60, 110, 90, 110, 90, 10, 10, 60, 60, 60, 60, 130, 130,
               180, 100, 100, 6, 6, 24, 12, 12], float)
STEP = np.array([10, 30, 10, 0.6, 0.6, 10, 8, 10, 8, 25, 20, 25, 20, 25, 25, 20, 15, 20, 15, 25, 25,
                 40, 20, 20, 1.0, 1.0, 5, 4, 4], float)


def opt(a, n, d):
    return a[a.index(n) + 1] if n in a else d


def mat_euler(R):
    """(rx, ry, rz) degrees with s5_death.euler's convention R = Rz Ry Rx."""
    ry = -np.arcsin(np.clip(R[2, 0], -1, 1))
    rx = np.arctan2(R[2, 1], R[2, 2])
    rz = np.arctan2(R[1, 0], R[0, 0])
    return [float(v) for v in np.degrees([rx, ry, rz])]


def align(a, b):
    """Rotation turning unit vector a onto b."""
    v, c = np.cross(a, b), float(a @ b)
    if np.linalg.norm(v) < 1e-9:
        return np.eye(3) if c > 0 else -np.eye(3)
    K = np.array([[0, -v[2], v[1]], [v[2], 0, -v[0]], [-v[1], v[0], 0]])
    return np.eye(3) + K + K @ K * ((1 - c) / (np.linalg.norm(v) ** 2))


class HDFit(cf.Fit):
    def __init__(self, stage, frames, caprim):
        super().__init__(Path(stage) / "skinned_lod3.npz", frames, caprim)
        model = Path(stage) / "overlay" / pb.FOLDER / "torso_lod0.model"
        self.sk = sd.Skeleton(model)
        skin = np.load(Path(stage) / "skinned_lod3.npz")
        names = [str(x) for x in skin["bones"]]
        self.vb = np.array([[self.sk.idx[names[j]] for j in row] for row in skin["bone_idx"]])
        self.capv = self.vb[:, 0] == self.sk.idx["jaw"]
        self.bodysel = np.nonzero(~self.capv)[0][::2]
        self.capb = skin["pos"][self.capv]
        self.cb = self.capb.mean(0)
        X = self.capb - self.cb
        w, V = np.linalg.eigh(X.T @ X)
        up = V[:, 0] * (1 if V[1, 0] > 0 else -1)
        self.R0 = align(up / np.linalg.norm(up), np.array([0.0, 1.0, 0.0]))
        flat = (self.R0 @ X.T).T
        self.cap_r = float(np.percentile(np.hypot(flat[:, 0], flat[:, 2]), 98))
        self.head = self.sk.idx["head"]
        self.kind = skin["kind"][self.bodysel]

    def to_pose(self, x):
        v = dict(zip(NAMES, x))
        c, b = v["curl"], v["bend"]
        bones = {"spine_01": [c, 0, b], "chest": [0.7 * c, 0, 0.7 * b], "neck": [0.4 * c, 0, 0.4 * b],
                 "head": [v["head_rx"], 0, v["head_rz"]],
                 "L_UpperArm": [v["Lua_x"], 0, v["Lua_z"]], "R_UpperArm": [v["Rua_x"], 0, v["Rua_z"]],
                 "L_ForeArm": [v["Lfa_x"], 0, 0], "R_ForeArm": [v["Rfa_x"], 0, 0],
                 "L_Thigh": [v["Lth_x"], 0, v["Lth_z"]], "R_Thigh": [v["Rth_x"], 0, v["Rth_z"]],
                 "L_Calf": [v["Lca_x"], 0, 0], "R_Calf": [v["Rca_x"], 0, 0]}
        Rc = sd.euler(v["cap_tx"], v["cap_ry"], v["cap_tz"]) @ self.R0
        if self.attached:
            bones["jaw"] = [v["jaw_x"], 0, v["jaw_z"]]
        return {"cog": [v["cog_rx"], v["cog_ry"], v["cog_rz"]], "pivot": [0.0, 0.0, 0.0],
                "shift": [v["sh_x"], 0.0, v["sh_z"]], "bones": bones,
                "cap": {"rot": mat_euler(Rc), "centre": [v["cap_x"], v["cap_z"]], "sink": 0.05, "scale": 1.0,
                        "attached": bool(self.attached)},
                "params": {k: round(float(val), 3) for k, val in v.items()}}

    out_w = 0.6
    attached = False

    def corpse(self, pose):
        """(body points, cap points); with the cap attached it rides the head (the jaw, with its small flex), and the
        whole heap, cap included, is set on the floor."""
        if not self.attached:
            return super().corpse(pose)
        sd.set_pose(pose)
        sk = self.sk
        _l, W = sk.pose(sd.body_motion(sk, sd.LENGTH))
        M = np.stack([W[j] @ sk.Binv[j] for j in range(len(W))])
        sel = self.bodysel
        P = np.zeros((len(sel), 3))
        for c in range(4):
            P += self.w[sel, c, None] * np.einsum("nij,nj->ni", M[self.vb[sel, c]], self.V[sel])[:, :3]
        jw = sk.idx["jaw"]
        Q = (M[jw] @ np.hstack([self.capb, np.ones((len(self.capb), 1))]).T).T[:, :3]
        m = min(P[:, 1].min(), Q[:, 1].min())
        P[:, 1] -= m
        Q[:, 1] -= m
        return P, Q
    ground_w = 0.08
    height_w, height_max = 0.3, 2.0
    cap_flat = False

    def total(self, x, detail=False):
        if self.cap_flat:
            x = x.copy()
            x[NAMES.index("cap_tx")] = np.clip(x[NAMES.index("cap_tx")], -8, 8)
            x[NAMES.index("cap_tz")] = np.clip(x[NAMES.index("cap_tz")], -8, 8)
        pose = self.to_pose(x)
        r = self.score(pose, True)
        s = r[0]
        # our pixels outside classic's heap (a limb thrown out costs little IoU, but reads at once)
        outs = []
        for d in cf.DIRS:
            ours = r[1][d]["masks"][0]
            outs.append((ours & ~self.dd[d][0]).sum() / max(ours.sum(), 1))
            r[1][d]["outside"] = round(float(outs[-1]), 3)
        s -= self.out_w * float(np.mean(outs))
        # lying on the floor: the trunk's lowest point near the ground, the heap low (classic's camera hardly sees height)
        P, Q = self.corpse(pose)
        tor = P[self.kind == "torso", 1]
        if self.attached:
            # the cap stands on its rim: its lowest point on the floor
            s -= 0.3 * max(0.0, float(Q[:, 1].min()) - 0.1)
        s -= self.ground_w * (max(0.0, float(tor.min()) - 0.15) + 0.25 * float(P[:, 1].mean()))
        # nothing propped up: the heap is about one body thick (feet and hands not raised)
        s -= self.height_w * max(0.0, float(np.percentile(P[:, 1], 97)) - self.height_max)
        # the cap beside the head
        sd.set_pose(pose)
        _l, W = self.sk.pose(sd.body_motion(self.sk, sd.LENGTH))
        hx = np.array([W[self.head][0, 3], W[self.head][2, 3]]) + np.array(pose["shift"])[[0, 2]] * 0
        d = float(np.hypot(*(np.array(pose["cap"]["centre"]) - hx)))
        pen = 0.0 if self.attached else 0.05 * max(0.0, d - (self.cap_r + 0.6))
        return (s - pen, r[1], d) if detail else s - pen


def fit(a):
    stage, frames, caprim, out = a[:4]
    f = HDFit(stage, frames, caprim)
    f.cap_flat = "--cap-flat" in a
    f.attached = "--cap-attached" in a
    f.out_w = float(opt(a, "--outside", "0.6"))
    f.ground_w = float(opt(a, "--ground", "0.08"))
    f.height_w = float(opt(a, "--height-w", "0.3"))
    f.height_max = float(opt(a, "--height", "2.0"))
    cal = f.calibrate(float(opt(a, "--el", "35")))
    print("calibration", cal, "cap radius", round(f.cap_r, 2), flush=True)
    iters = int(opt(a, "--iters", "2500"))
    side = opt(a, "--side", "both")
    best_all = None
    for sname, sg in (("L", 1), ("R", -1)):
        if side not in ("both", sname):
            continue
        lo, hi = LO.copy(), HI.copy()
        if sg < 0:
            lo[2], hi[2] = -HI[2], -LO[2]
        rng = np.random.default_rng(int(opt(a, "--seed", "1")))
        # starts: the cog's heading in 8 steps, limbs folded forward
        cands = []
        for ry in range(-180, 180, 45):
            x = np.zeros(len(NAMES))
            x[NAMES.index("cog_rz")] = 90 * sg
            x[NAMES.index("cog_ry")] = ry
            for n, val in (("Lua_x", -40), ("Rua_x", -40), ("Lfa_x", -40), ("Rfa_x", -40), ("Lth_x", -45),
                           ("Rth_x", -45), ("Lca_x", 60), ("Rca_x", 60), ("dd_dy", 12)):
                x[NAMES.index(n)] = val
            x = np.clip(x, lo, hi)
            cands.append((f.total(x), x))
        if "--init" in a:
            ip = json.loads(Path(opt(a, "--init", "")).read_text())["params"]
            x = np.clip(np.array([ip.get(n, 0.0) for n in NAMES], float), lo, hi)
            cands.append((f.total(x), x))
        cands.sort(key=lambda c: -c[0])
        # short search from the 3 best starts, then a long one from the winner
        runs = []
        for s0, x0 in cands[:3]:
            runs.append(search(f, x0, lo, hi, iters // 5, rng))
        s1, x1 = max(runs, key=lambda r: r[0])
        s1, x1 = search(f, x1, lo, hi, iters, rng)
        print("side", sname, "score", round(s1, 4), flush=True)
        if best_all is None or s1 > best_all[0]:
            best_all = (s1, x1, sname)
    s, x, sname = best_all
    tot, rows, capd = f.total(x, detail=True)
    pose = f.to_pose(x)
    pose["fit"] = {"score": round(tot, 4), "side": sname, "calibration": cal, "cap_head_dist": round(capd, 2),
                   "per_facing": {d: {k: v for k, v in r.items() if k != "masks"} for d, r in rows.items()},
                   "median_iou": round(float(np.median([r["iou"] for r in rows.values()])), 3),
                   "median_cap_iou": round(float(np.median([r["cap_iou"] for r in rows.values()])), 3)}
    Path(out).write_text(json.dumps(pose, indent=1))
    print(json.dumps({k: v for k, v in pose["fit"].items() if k != "per_facing"}))
    if "--sheet" in a:
        sheet(f, rows, opt(a, "--sheet", ""))


def search(f, x, lo, hi, iters, rng):
    best = f.total(x)
    for it in range(iters):
        scale = 0.6 * (1 - it / iters) + 0.05
        y = x.copy()
        pick = rng.random(len(x)) < 0.2
        pick[rng.integers(len(x))] = True
        y[pick] += rng.normal(0, 1, pick.sum()) * STEP[pick] * scale
        y = np.clip(y, lo, hi)
        s = f.total(y)
        if s > best:
            best, x = s, y
    return best, x


def sheet(f, rows, path):
    tiles = []
    for d in cf.DIRS:
        sil, im = f.dd[d]
        ours, ours_cap = rows[d]["masks"]
        t = np.zeros(sil.shape + (3,), np.uint8) + 40
        t[sil] = [110, 110, 120]
        t[f.ddcap[d]] = [60, 90, 200]
        t[ours & ~nd.binary_erosion(ours)] = [255, 210, 60]
        t[ours_cap & ~nd.binary_erosion(ours_cap)] = [255, 80, 80]
        big = Image.fromarray(t).resize((sil.shape[1] * 3, sil.shape[0] * 3), Image.NEAREST)
        orig = Image.fromarray(im).resize(big.size, Image.NEAREST)
        pair = Image.new("RGB", (big.width * 2, big.height), (40, 40, 48))
        pair.paste(orig, (0, 0), orig)
        pair.paste(big, (big.width, 0))
        ImageDraw.Draw(pair).text((4, 4), "d%d iou %.2f cap %.2f out %.2f" % (d, rows[d]["iou"], rows[d]["cap_iou"],
                                                                         rows[d].get("outside", 0)),
                                  fill=(240, 240, 240))
        tiles.append(np.asarray(pair))
    Image.fromarray(np.vstack([np.hstack(tiles[i:i + 2]) for i in range(0, 8, 2)])).save(path)


# ------------------------------------------------------------------------------------------------ settle (limp corpse)
# (name, bone, axis index, lo, hi, relaxed): world-axis turns in the body frame (s5_death: x side, y up, z forward);
# calves and forearms bend with + (s5_death's DEATH keys), thighs swing forward with -.
SETTLE = [("cog_rx", "cog", 0, -40, 40, 0), ("cog_ry", "cog", 1, -180, 180, 0), ("cog_rz", "cog", 2, -120, 120, 0),
          ("sp_x", "spine_01", 0, -25, 45, 10), ("sp_z", "spine_01", 2, -25, 25, 0), ("sp_y", "spine_01", 1, -20, 20, 0),
          ("ch_x", "chest", 0, -20, 40, 8), ("ch_z", "chest", 2, -20, 20, 0),
          ("nk_x", "neck", 0, -40, 50, 10), ("nk_z", "neck", 2, -35, 35, 0),
          ("hd_x", "head", 0, -40, 50, 0), ("hd_z", "head", 2, -35, 35, 0),
          ("jaw_x", "jaw", 0, -12, 12, 0), ("jaw_z", "jaw", 2, -12, 12, 0)]
for _sd, _sg in (("L", -1), ("R", 1)):
    SETTLE += [("%sua_x" % _sd, "%s_UpperArm" % _sd, 0, -130, 70, -15), ("%sua_y" % _sd, "%s_UpperArm" % _sd, 1, -60, 60, 0),
               ("%sua_z" % _sd, "%s_UpperArm" % _sd, 2, -100, 100, 0),
               ("%sfa_x" % _sd, "%s_ForeArm" % _sd, 0, -5, 140, 35),
               ("%sth_x" % _sd, "%s_Thigh" % _sd, 0, -120, 30, -25), ("%sth_y" % _sd, "%s_Thigh" % _sd, 1, -40, 40, 0),
               ("%sth_z" % _sd, "%s_Thigh" % _sd, 2, -45, 45, 0),
               ("%sca_x" % _sd, "%s_Calf" % _sd, 0, -5, 140, 40), ("%sft_x" % _sd, "%s_Foot" % _sd, 0, -40, 40, 0)]
S_LO = np.array([r[3] for r in SETTLE], float)
S_HI = np.array([r[4] for r in SETTLE], float)
S_REL = np.array([r[5] for r in SETTLE], float)


class Settle(HDFit):
    attached = True

    def __init__(self, stage, frames, caprim):
        super().__init__(stage, frames, caprim)
        skin = np.load(Path(stage) / "skinned_lod3.npz")
        self.kind_all = skin["kind"]
        self.body = np.nonzero(~self.capv)[0]
        k = self.kind_all[self.body]
        self.limb = np.isin(k, ["arm", "leg", "foot"])
        self.capall = self.capb
        # the trunk's radius about the pelvis-neck line in the bind pose
        B = self.sk.B
        self.trunk_bones = (self.sk.idx["pelvis"], self.sk.idx["neck"])
        a, b = B[self.trunk_bones[0]][:3, 3], B[self.trunk_bones[1]][:3, 3]
        T = skin["pos"][skin["kind"] == "torso"]
        self.r_trunk = float(np.percentile(seg_dist(T, a, b), 60))

    def pose_of(self, x):
        bones = {}
        for (n, b, ax, _l, _h, _r), v in zip(SETTLE, x):
            if b == "cog":
                continue
            bones.setdefault(b, [0.0, 0.0, 0.0])[ax] = float(v)
        cog = [float(x[0]), float(x[1]), float(x[2])]
        return {"cog": cog, "pivot": [0.0, 0.0, 0.0], "shift": [0.0, 0.0, 0.0], "bones": bones,
                "cap": {"rot": [0, 0, 0], "centre": [0, 0], "sink": 0.0, "scale": 1.0, "attached": True},
                "params": {r[0]: round(float(v), 3) for r, v in zip(SETTLE, x)}}

    def posed(self, x):
        sd.set_pose(self.pose_of(x))
        sk = self.sk
        _l, W = sk.pose(sd.body_motion(sk, sd.LENGTH))
        M = np.stack([W[j] @ sk.Binv[j] for j in range(len(W))])
        P = np.zeros((len(self.V), 3))
        for c in range(4):
            P += self.w[:, c, None] * np.einsum("nij,nj->ni", M[self.vb[:, c]], self.V)[:, :3]
        P[:, 1] -= P[:, 1].min()
        return P, W

    def energy(self, x, detail=False):
        P, W = self.posed(x)
        Pb, Pc = P[self.body], P[self.capv]
        e_grav = float(Pb[:, 1].mean())                               # gravity on the body (the cap is held on its edge)
        a, b = W[self.trunk_bones[0]][:3, 3], W[self.trunk_bones[1]][:3, 3]
        dist = seg_dist(Pb[self.limb], a, b)
        e_pen = float((np.maximum(0, 0.8 * self.r_trunk - dist) ** 2).mean()) * 40     # limbs not through the trunk
        e_cap = 2.0 * float(Pc[:, 1].min())                           # the cap's rim on the floor
        up = W[self.sk.idx["jaw"]][:3, :3] @ (np.linalg.inv(self.R0) @ [0, 1, 0])
        e_edge = 1.5 * float(up[1]) ** 2                              # the cap on its edge (its axis level)
        e_rel = 1e-4 * float(((x - S_REL)[3:] ** 2).mean())           # a limp joint rests near its relaxed bend
        e = e_grav + e_pen + e_cap + e_edge + e_rel
        if detail:
            return e, {"grav": round(e_grav, 3), "pen": round(e_pen, 3), "cap": round(e_cap, 3), "edge": round(e_edge, 3),
                       "relax": round(e_rel, 4), "max_h_body": round(float(np.percentile(Pb[:, 1], 98)), 2)}
        return e


def seg_dist(P, a, b):
    d = b - a
    t = np.clip(((P - a) @ d) / max(float(d @ d), 1e-9), 0, 1)
    return np.linalg.norm(P - (a + t[:, None] * d), axis=1)


def settle(a):
    """settle <stage> <classic frames dir> <caprim.json> <start pose.json> <out pose.json> [--iters 20000] [--seed 1]

    Owner, round 18: "just make it look like its laying on the ground dead and limp, i dont care how". A quasi-static
    ragdoll: from a start pose on its side (s4_hdcorpse fit --cap-attached), the joints are let go and the pose that
    minimises the body's potential energy is searched (random search with shrinking steps), so the limbs fall onto the
    floor under their own weight. Constraints, all soft: the floor (the heap is set on it, nothing sinks), joint ranges
    (SETTLE, hinge knees and elbows), limbs kept out of the trunk (distance to the pelvis-neck line), and a weak pull to
    a relaxed bend (no straight, stiff limbs). The cap rides the head and is held on its edge with its rim on the floor
    (classic and the owner: standing, attached, slightly bent at the jaw). Writes a pose for s4_hdcap.py corpse --target."""
    stage, frames, caprim, start, out = a[:5]
    f = Settle(stage, frames, caprim)
    f.calibrate(35.0)
    sp = json.loads(Path(start).read_text())
    x = np.zeros(len(SETTLE))
    x[0:3] = sp["cog"]
    for i, (n, b, ax, lo, hi, rel) in enumerate(SETTLE):
        if b != "cog":
            x[i] = sp["bones"].get(b, [0, 0, 0])[ax]
    x = np.clip(x, S_LO, S_HI)
    rng = np.random.default_rng(int(opt(a, "--seed", "1")))
    iters = int(opt(a, "--iters", "20000"))
    e0 = best = f.energy(x)
    step = (S_HI - S_LO) / 8
    for it in range(iters):
        sc = 0.5 * (1 - it / iters) ** 2 + 0.02
        y = x.copy()
        pick = rng.random(len(x)) < 0.15
        pick[rng.integers(len(x))] = True
        y[pick] += rng.normal(0, 1, pick.sum()) * step[pick] * sc
        y = np.clip(y, S_LO, S_HI)
        e = f.energy(y)
        if e < best:
            best, x = e, y
        if it % 2000 == 0:
            print(it, round(best, 4), flush=True)
    e, det = f.energy(x, detail=True)
    pose = f.pose_of(x)
    pose["settle"] = {"energy_start": round(e0, 4), "energy": round(e, 4), **det}
    Path(out).write_text(json.dumps(pose, indent=1))
    print(json.dumps(pose["settle"]))


# ------------------------------------------------------------------------------------------------ corpse texture (tex)
STRIP = (1792, 0, 256)       # x0, y0, size of the corpse's own texels in the 2048 atlas (s5_build's strip, F = 0.125)


def shell_tris(path):
    """(uv per vertex, triangles) of the corpse shell in a LOD model: the vertices whose main bone is loin_cloth."""
    g, tree = pb.d2r_mesh.load_model(path)
    m = tree["Meshes"][0]
    vs = m["PrimaryVertexData"]["Vertices"].obj
    names = [b["BoneName"] for b in m["BoneBindings"]]
    bi = np.array([v["BoneIndices"] for v in vs])
    bw = np.array([v["BoneWeights"] for v in vs])
    shell = np.array(names)[bi[np.arange(len(bi)), bw.argmax(1)]] == "loin_cloth"
    uv = np.array([v["TextureCoordinates0"] for v in vs], np.uint16).view(np.float16).astype(float)   # half-float bits
    t = np.array([x["Int16"] for x in m["PrimaryTopology"]["Indices16"]], int).reshape(-1, 3) % 65536
    return g, tree, m, vs, shell, uv, t[shell[t].all(1)]


def pack(boxes, size, pad):
    """Shelf packing of (w, h) boxes (strip pixels, pad added) into size x size; positions or None."""
    order = sorted(range(len(boxes)), key=lambda i: -boxes[i][1])
    pos = [None] * len(boxes)
    x = y = sh = 0
    for i in order:
        w, h = boxes[i][0] + 2 * pad, boxes[i][1] + 2 * pad
        if x + w > size:
            x, y, sh = 0, y + sh, 0
        if y + h > size or w > size:
            return None
        pos[i] = (x + pad, y + pad)
        x += w
        sh = max(sh, h)
    return pos


def classic_cap_ramp(frames, bins=32):
    """classic's corpse cap colours by brightness: the opaque pixels in each DD frame's fallen-cap box."""
    cols = []
    for d in cf.DIRS:
        im = np.asarray(Image.open(Path(frames) / "dd" / ("d%d_f00.png" % d)).convert("RGBA")).astype(float)
        x0, x1, y0, y1 = cf.DD_CAP_BOX[d]
        sub = im[y0:y1, x0:x1]
        cols.append(sub[sub[..., 3] > 0][:, :3])
    c = np.vstack(cols)
    L = c @ [0.299, 0.587, 0.114]
    q = np.quantile(L, np.linspace(0, 1, bins + 1))
    return np.array([c[(L >= q[i]) & (L <= q[i + 1])].mean(0) for i in range(bins)])


def classic_ramp(frames, bins=32):
    """classic's corpse colours by brightness: per luminance quantile bin, the mean RGB of the DD frames' body pixels
    (opaque, outside the fallen cap's box, not the cap's saturated blue)."""
    cols = []
    for d in cf.DIRS:
        im = np.asarray(Image.open(Path(frames) / "dd" / ("d%d_f00.png" % d)).convert("RGBA")).astype(float)
        m = im[..., 3] > 0
        x0, x1, y0, y1 = cf.DD_CAP_BOX[d]
        m[y0:y1, x0:x1] = False
        R, G, B = im[..., 0], im[..., 1], im[..., 2]
        m &= ~((B >= 120) & (B - np.maximum(R, G) > 50))
        cols.append(im[m][:, :3])
    c = np.vstack(cols)
    L = c @ [0.299, 0.587, 0.114]
    q = np.quantile(L, np.linspace(0, 1, bins + 1))
    ramp = np.array([c[(L >= q[i]) & (L <= q[i + 1])].mean(0) for i in range(bins)])
    return ramp


def tex(a):
    """tex <stage> <classic frames dir> [--gain 0.9] [--pad 3] [--lo 0.0] [--cap-own [--cap-gain 1.0] [--cap-sat 1.0] [--cap-max 255]]: the corpse shell's own texels in the strip.

    The corpse shell (s4_hdcap.py shell) used the live atlas, so the corpse was the live body's near-black; classic's
    corpse is pale blue (owner, round 18). The model has no vertex colour, and the corpse shares the live material, so
    the corpse gets its own texels: the atlas regions its triangles use (LOD 3's shell and LOD 4's, grown 3 px,
    connected pieces) of the body are packed at one scale into the 256 px strip at the atlas' top right (unused since round 18);
    albedo, normal and ORM are resampled there (box filter; a uniform scale and a shift keep the tangent frames), the
    albedo of the body's texels mapped by brightness rank onto classic's DD corpse colours (classic_ramp) times --gain,
    the cap's kept. The shell's UVs in every LOD move to the strip. Only the strip's blocks are written (s4_hdcap's
    block-safe splice with the rest of the atlas kept); the glow masks are not touched (a corpse has no glow)."""
    from PIL import ImageDraw
    import s4_hdbody as hb
    stage, frames = Path(a[0]), a[1]
    gain, pad = float(opt(a, "--gain", "0.9")), int(opt(a, "--pad", "3"))
    od = stage / "overlay" / pb.FOLDER
    N = 2048
    lods = [shell_tris(od / ("torso_lod%d.model" % k)) for k in range(5)]
    # atlas regions used by the shells (LODs 0-3 share LOD 3's shell)
    used = Image.new("L", (N, N), 0)
    dr = ImageDraw.Draw(used)
    for k in (3, 4):
        uv, t = lods[k][5], lods[k][6]
        for tri in t:
            dr.polygon([tuple(p) for p in uv[tri] * N], fill=255)
    used = np.asarray(used) > 0
    capm = np.load(stage / "cap_texels.npy")
    lab, n = nd.label(used)
    sl = nd.find_objects(lab)
    # the cap keeps its live texels (classic's corpse cap is the live cap's blue): only the body's regions are packed
    is_cap = np.array([capm[s_][lab[s_] == i + 1].mean() > 0.5 for i, s_ in enumerate(sl)])
    cap_own = "--cap-own" in a
    body_ids = [i for i in range(n) if cap_own or not is_cap[i]]
    boxes0 = [(sl[i][1].stop - sl[i][1].start, sl[i][0].stop - sl[i][0].start) for i in body_ids]
    lo_, hi_ = 0.01, 1.0
    for _ in range(30):
        sc = (lo_ + hi_) / 2
        ok = pack([(int(np.ceil(w * sc)) + 1, int(np.ceil(h * sc)) + 1) for w, h in boxes0], STRIP[2], pad)
        lo_, hi_ = (sc, hi_) if ok else (lo_, sc)
    sc = lo_
    pos_b = pack([(int(np.ceil(w * sc)) + 1, int(np.ceil(h * sc)) + 1) for w, h in boxes0], STRIP[2], pad)
    pos = [None] * n
    for j, i in enumerate(body_ids):
        pos[i] = pos_b[j]
    print("regions", n, "scale %.4f" % sc, "texels per atlas texel", round(sc, 3), flush=True)
    # textures
    alb_p, nrm_p, orm_p = (pb.bm.tex_path(stage, k) for k in ("alb", "nrm", "orm"))
    dec = {}
    for kind, pth in (("alb", alb_p), ("nrm", nrm_p), ("orm", orm_p)):
        fmt, w, h, mips = pb.d2r_texture.read_texture(pth)
        assert w == h and N % w == 0, (kind, w, h)
        D = pb.d2r_texture.decode(fmt, w, h, mips[0])
        if w != N:      # work at the atlas size, written back at the file's
            D = np.asarray(Image.fromarray(D).resize((N, N), Image.NEAREST))
        dec[kind] = (fmt, mips, D, w)
    # brightness ranks of the body texels the shell uses -> classic's colours
    A = dec["alb"][2][..., :3].astype(float)
    L = A @ [0.299, 0.587, 0.114]
    ramp = classic_ramp(frames)
    sel = used & ~capm
    qs = np.quantile(L[sel], np.linspace(0, 1, len(ramp) + 1))
    idx = np.clip(np.searchsorted(qs, L, side="right") - 1, 0, len(ramp) - 1)
    lo = float(opt(a, "--lo", "0.0"))       # --lo Q: ranks map onto classic's colours from quantile Q up (paler)
    idx = np.clip(np.round(lo * (len(ramp) - 1) + (1 - lo) * idx), 0, len(ramp) - 1).astype(int)
    pale = np.clip(ramp[idx] * gain, 0, 255)
    alb_new = A.copy()
    alb_new[sel] = pale[sel]
    if cap_own:
        # the corpse cap: classic's corpse cap tones by brightness rank (a dark crown, a muted blue rim; no bright blotches)
        cr = classic_cap_ramp(frames)
        selc = used & capm
        qc = np.quantile(L[selc], np.linspace(0, 1, len(cr) + 1))
        ic = np.clip(np.searchsorted(qc, L, side="right") - 1, 0, len(cr) - 1)
        cc = cr[ic] * float(opt(a, "--cap-gain", "1.0"))
        # dead: --cap-sat scales the chroma (a muted rim), --cap-max caps the luminance (no bright spot reads as a glow)
        lum = cc @ [0.299, 0.587, 0.114]
        cc = lum[..., None] + float(opt(a, "--cap-sat", "1.0")) * (cc - lum[..., None])
        cmax = float(opt(a, "--cap-max", "255"))
        cc *= np.minimum(1.0, cmax / np.maximum(lum, 1e-6))[..., None]
        alb_new[selc] = np.clip(cc, 0, 255)[selc]
        rep_cap = cr.round(1).tolist()
    srcs = {"alb": np.dstack([alb_new, dec["alb"][2][..., 3:4].astype(float)]) if dec["alb"][2].shape[-1] == 4 else alb_new,
            "nrm": dec["nrm"][2].astype(float), "orm": dec["orm"][2].astype(float)}
    X0, Y0, S = STRIP
    filled = np.zeros((S, S), bool)
    strip_img = {k: np.zeros((S, S, srcs[k].shape[-1]), float) for k in srcs}
    maps = []
    for i, s_ in enumerate(sl):
        y0, y1, x0, x1 = s_[0].start, s_[0].stop, s_[1].start, s_[1].stop
        if pos[i] is None:
            maps.append(None)
            continue
        px, py = pos[i]
        w2, h2 = max(1, int(round((x1 - x0) * sc))), max(1, int(round((y1 - y0) * sc)))
        reg = nd.binary_dilation(lab[y0:y1, x0:x1] == i + 1, iterations=2)
        msk = np.asarray(Image.fromarray((reg * 255).astype(np.uint8)).resize((w2, h2), Image.BOX)) > 0
        for k, src in srcs.items():
            crop = src[y0:y1, x0:x1]
            chans = [np.asarray(Image.fromarray(crop[..., c].astype(np.float32), "F").resize((w2, h2), Image.BOX))
                     for c in range(crop.shape[-1])]
            r = np.dstack(chans)
            dst = strip_img[k][py:py + h2, px:px + w2]
            dst[msk] = r[msk]
        filled[py:py + h2, px:px + w2] |= msk
        maps.append((x0, y0, px, py, w2 / (x1 - x0), h2 / (y1 - y0)))
    # gutters: nearest filled texel everywhere in the strip
    _d, (iy, ix) = nd.distance_transform_edt(~filled, return_indices=True)
    rep = {"cap_own": cap_own, "regions": n, "scale": round(sc, 4), "strip_fill": round(float(filled.mean()), 3), "ramp": ramp.round(1).tolist()}
    stripmask = np.zeros((N, N), bool)
    stripmask[Y0:Y0 + S, X0:X0 + S] = True
    for k in srcs:
        fmt, mips, _D, w = dec[k]
        pth = {"alb": alb_p, "nrm": nrm_p, "orm": orm_p}[k]
        f_ = N // w
        old = pb.d2r_texture.decode(fmt, w, w, mips[0])
        full = old.copy()
        si = np.clip(strip_img[k][iy, ix], 0, 255).astype(np.uint8)
        if f_ > 1:
            si = np.dstack([np.asarray(Image.fromarray(si[..., c]).resize((S // f_, S // f_), Image.BOX))
                            for c in range(si.shape[-1])])
        full[Y0 // f_:(Y0 + S) // f_, X0 // f_:(X0 + S) // f_, :si.shape[-1]] = si
        keep = np.ones((w, w), bool)
        keep[Y0 // f_:(Y0 + S) // f_, X0 // f_:(X0 + S) // f_] = False
        ch = (full != old).reshape(w, w, -1).any(-1)
        rep[k] = hb.write_spliced_capsafe(pth, fmt, w, w, pb.bm.levels_keeping_part(full, fmt, mips, keep), mips, ch, 16,
                                          keep)
    # the shells' UVs
    _d, (ly, lx) = nd.distance_transform_edt(lab == 0, return_indices=True)
    labn = lab[ly, lx]                       # nearest region everywhere (sliver triangles the raster missed)
    # the corpse's texels never glow: both glow masks are zero over the strip (round 18: the cap mask still held
    # round 13's miniature glow there, up to 142)
    for gk in ("glow_cap_mask", "glow_body_mask"):
        gp = sorted(Path(stage, "overlay").rglob("*_%s.texture" % gk))[0]
        fmt, w, h, mips = pb.d2r_texture.read_texture(gp)
        G = pb.d2r_texture.decode(fmt, w, h, mips[0])
        G = G[..., 0] if G.ndim == 3 else G
        f_ = N // w
        G2 = G.copy()
        G2[Y0 // f_:(Y0 + S) // f_, X0 // f_:(X0 + S) // f_] = 0
        keep = np.ones((h, w), bool)
        keep[Y0 // f_:(Y0 + S) // f_, X0 // f_:(X0 + S) // f_] = False
        rep[gk] = hb.write_spliced_capsafe(gp, fmt, w, h, pb.bm.levels_keeping_part(G2, fmt, mips, keep, kind="BC4"),
                                           mips, G2 != G, 8, keep)
    for k, (g, tree, m, vs, shell, uv, t) in enumerate(lods):
        lab_v = np.zeros(len(vs), int)
        for tri in t:
            c = uv[tri].mean(0) * N
            li = labn[int(np.clip(c[1], 0, N - 1)), int(np.clip(c[0], 0, N - 1))]
            lab_v[tri] = li
        sv = np.nonzero(shell)[0]
        assert (lab_v[sv] > 0).all(), (k, int((lab_v[sv] == 0).sum()))
        for v in sv:
            if maps[lab_v[v] - 1] is None:
                continue                      # a cap region: its live texels
            x0, y0, px, py, fx, fy = maps[lab_v[v] - 1]
            u2 = (X0 + px + (uv[v, 0] * N - x0) * fx) / N
            v2 = (Y0 + py + (uv[v, 1] * N - y0) * fy) / N
            vs[v]["TextureCoordinates0"] = [int(x) for x in np.array([u2, v2], np.float16).view(np.uint16)]
        rep["lod%d_bytes" % k] = pb.d2r_mesh.write_model(g, tree, od / ("torso_lod%d.model" % k))
    (stage / "hdcorpse_tex.json").write_text(json.dumps(rep, indent=1))
    print(json.dumps({k: v for k, v in rep.items() if k != "ramp"}))


if __name__ == "__main__":
    {"fit": fit, "tex": tex, "settle": settle}[sys.argv[1]](sys.argv[2:])
