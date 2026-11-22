"""Rig a generated monster mesh by embedding the donor's skeleton in it (lane rigaudit, replaces rig_fit's carry).

  venv python rig_embed.py embed    [--token T] <posed.npz> <out joints.json> [--volume mesh_lods.npz] [--png <out dir>]
  venv python rig_embed.py build    [--token T] <from stage dir> <posed.npz> <joints.json> <out stage dir> [--power 4]
                                    [--smooth 2] [--body-scale 1.0] [--trunk delta|world]
                                    [--no-unit-skeleton]
  venv python rig_embed.py retarget [--token T] <stage dir>

Why (docs/rigging.md has the audit): rig_fit.py placed joints from a hand-typed table, weighted by distance to capsules of
fixed radii (a hand hanging next to a thigh took thigh weight, a segment's far half went to the child bone), and carried the
mesh into the donor's T-pose with the donor's bone lengths (the Fungus' arms, 1.9x the donor's, were squeezed to 0.7 and
the rest folded into the wrist). This tool keeps the mesh where it is and moves the skeleton instead:

embed: the joints from the mesh's shape. The posed mesh (`posed.npz`: pos, tris in the generated frame, height 1 or K) is
voxelised (h = height / 190, solid by hole filling; `--volume` takes a closed mesh for the volume when the stage's LOD0
is not closed, e.g. after the cap split), the rigid part (MONSTERS[token]["cap"]) cut off. The distance to the surface
(EDT) of every inside voxel weights a shortest-path graph so that paths run along the medial axis. From the thickest voxel
of the trunk (the seed) the geodesic extremities are found and named (biped: head = highest, feet = the lowest tip per side
(the most forward one: the toe), hands = the farthest remaining tip per side). Per chain, on the smoothed medial path:
  arms: clavicle at the point where the path leaves the spine path, shoulder at the sharpest bend in the first 10-40 % after
        it, elbow at the sharpest bend in 30-70 % of shoulder..tip, wrist at the donor's forearm : hand ratio;
  legs: hip where the path's radius falls under 0.75 x the seed's and it is 0.6 seed radii off the spine path, knee at the sharpest bend in 25-65 % of hip..tip,
        ankle at the sharpest bend in 60-92 %, ball at the donor's foot ratio;
  trunk: pelvis between the hips, chest where the arms leave the spine path, spine_a/b at its thirds, neck half way to
        the head; the head joint is the profile's when a rigid part rides on the head (rig_fit's carry frame: the cap keeps
        its attachment), else at 80 % of the spine path.
Writes joints.json (posed joints in game units, chains, the tips found) and with --png the joints over the mesh.

build: a copy of <from stage> (any s5_build stage of the same mesh: its overlay, textures, clips) rebound:
- weights: geodesic voxel binding. Each bone owns the medial path between its joint and its child's; a vertex's in-volume
  distance d_j to each bone (multi-source Dijkstra over the voxels, from the voxel just inside the vertex) gives
  w_j ~ 1 / (d_j + h)^power, top 4, `--smooth` passes over the mesh edges. Paths do not cross air, so a hand next to a
  thigh stays on the arm and the two legs stay apart wherever the mesh has a gap of a voxel.
- bind in place: no unposing. The bind (rest) pose of the skeleton is the donor's skeleton posed into the mesh: each mapped
  bone turned by the minimal rotation from its donor direction to the embedded one (parent's turn first), at the embedded
  joint, with the embedded length. The stored vertices are the posed mesh / u. The head keeps rig_fit's carry frame (the
  donor's head at the profile's head joint) and the rigid part's bone (jaw) and the corpse shell's (loin_cloth) keep the
  donor's bind: cap and shell vertices are copied byte for byte, and so are their positions in every clip.
- --body-scale s: the body (joints and vertices, not the rigid part) scaled uniformly by s about the head joint, for a
  generated body too big for its part against classic (no distortion: a proportion choice, made in the open).
- the models get the new skeleton (rest transforms and inverse world transforms) and vertices; the unit gets its own
  <name>.skeleton (the donor's file with that skeleton) unless --no-unit-skeleton. NOT CHECKED IN GAME: the viewer skins
  with the model's skeleton; whether D2R takes the model's or the unit's inverse world transforms is the first thing to look
  at in a game run (both are written the same).
- the donor-convention clips (the from stage's combined.animations) are kept as <stage>/clips_donor.animations, and
  retargeted into the overlay (below).

retarget: <stage>/clips_donor.animations -> overlay combined.animations. Per clip, at 60 samples a second:
  bones without weights (fingers, twist helpers, ends): unchanged;
  every mapped bone: its translation the embedded length (offset);
  pelvis, spine, chest, neck, clavicles: --trunk delta (default): the clip's rotation relative to the donor's rest,
  applied to our rest (the mesh's own lean and shoulder line are kept, the clip's motion is added); --trunk world: the
  clip's local rotations as they are (the trunk leans as the donor's: for clips fitted on rig_fit's upright trunk);
  upper arms: the donor clip's world orientation (arms hang and swing as the donor's, whatever the lean); forearms and
  hands: the clip's local rotations (forward kinematics);
  head (a rigid part rides on it): the donor clip's world orientation; the turn this needs on top of the trunk's is spread
  evenly over spine_a, spine_b, chest and neck first;
  cog: moved in every sample so that the head's world transform is the donor clip's (a rigid part rides on the head: the
  cap moves exactly as before), else raised by the hip height over the donor's;
  the rigid part's bone and the shell bone: their donor-clip world transforms;
  leg bones: two-bone IK. The ankle goes where the donor's ankle is in that sample, moved by the difference of the hips and
  by the difference of the ankle heights; the knee bends in the plane of the donor's knee; the foot keeps the donor's world
  rotation. Longer legs than the donor's bend more; feet stay on the ground.
s5_clipfit.py write on a stage with rig.json writes clips_donor.animations and calls this; s5_clipfit's Rig skins through
the retarget, so fits and measures see the new rig.
"""
import json
import shutil
import sys
from pathlib import Path

import numpy as np
from scipy import ndimage as nd
from scipy.sparse import coo_matrix
from scipy.sparse.csgraph import dijkstra
from scipy.spatial import cKDTree

import common

sys.path.insert(0, str(common.WT / "tools"))
sys.path.insert(0, str(common.WT / "tools" / "sprite3d"))
import d2r_mesh  # noqa: E402
import d2r_model as dm  # noqa: E402
import hd_gltf  # noqa: E402
import rig_fit  # noqa: E402
import skel_info  # noqa: E402
from hdkit.view import gr2  # noqa: E402

import s5_build  # noqa: E402

D2R = common.EV / "d2r" / "data"
ARM = ("clav", "upperarm", "forearm", "hand", "hand_end")
LEG = ("thigh", "calf", "ankle", "toe", "toe_end")
TRUNK = ("pelvis", "spine_a", "spine_b", "chest", "neck", "head")


# ---- helpers ------------------------------------------------------------------------------------------------------------------

def cfg_profile():
    cfg = s5_build.MONSTERS[common.TOKEN]
    return cfg, rig_fit.PROFILES[cfg["profile"]]


def donor_skeleton(cfg):
    return D2R / "hd/character/enemy" / cfg["donor"] / "skeleton" / (cfg["donor"] + ".skeleton")


def role_bone(profile, key):
    """Donor bone name of a joint key ('pelvis', 'L_thigh') or None (an end point, a skipped role)."""
    side, role = (key[0], key[2:]) if key[:2] in ("L_", "R_") else (None, key)
    if role not in profile["bones"]:
        return None
    return profile["bones"][role].replace("{S}", side or "")


def load_posed(path, K):
    d = np.load(path)
    lods = []
    for k in range(5):
        s = "" if k == 0 else "_%d" % k
        if "pos" + s not in d:
            break
        p = d["pos" + s].astype(float)
        if p[:, 1].max() < 2.0:     # height 1: to game units
            p = p * K
        lods.append((p, d["tris" + s]))
    return lods


def rigid_mask(cfg, P, K):
    if "cap" not in cfg:
        return np.zeros(len(P), bool)
    c, m = cfg["cap"]
    return P[:, 1] / K > c + m * P[:, 2] / K


# ---- volume and medial paths --------------------------------------------------------------------------------------------------

class Volume:
    def __init__(self, P, T, keep=None, res=190):
        """Solid voxels of the mesh (P game units). keep(points) -> bool: which voxel centres belong to the body."""
        H = P[:, 1].max() - P[:, 1].min()
        h = H / res
        lo = P.min(0) - 3 * h
        dims = np.ceil((P.max(0) - lo) / h).astype(int) + 3
        A, B, C = P[T[:, 0]], P[T[:, 1]], P[T[:, 2]]
        L = np.maximum(np.linalg.norm(B - A, axis=1), np.maximum(np.linalg.norm(C - A, axis=1), np.linalg.norm(C - B, axis=1)))
        n = np.ceil(L / (h * 0.5)).astype(int) + 1
        pts = []
        for k in np.unique(n):
            sel = n == k
            u, v = np.meshgrid(np.linspace(0, 1, k), np.linspace(0, 1, k))
            m = (u + v) <= 1
            u, v = u[m], v[m]
            pts.append((A[sel, None] * (1 - u - v)[None, :, None] + B[sel, None] * u[None, :, None]
                        + C[sel, None] * v[None, :, None]).reshape(-1, 3))
        pts = np.vstack(pts)
        ijk = np.floor((pts - lo) / h).astype(int)
        surf = np.zeros(dims, bool)
        surf[ijk[:, 0], ijk[:, 1], ijk[:, 2]] = True
        solid = nd.binary_fill_holes(surf)
        close = 0
        while (solid & ~surf).sum() < 0.5 * surf.sum() and close < 3:   # an open surface: close small holes first
            close += 1
            solid = nd.binary_fill_holes(nd.binary_closing(surf, iterations=close))
        self.closed_by = close
        centres = lo + (np.indices(dims).reshape(3, -1).T + 0.5) * h
        if keep is not None:
            solid &= keep(centres).reshape(dims)
        lab, nlab = nd.label(solid)
        if nlab > 1:
            sizes = nd.sum(solid, lab, range(1, nlab + 1))
            solid = lab == (np.argmax(sizes) + 1)
        self.h, self.lo, self.dims, self.solid = h, lo, dims, solid
        self.edt_grid = nd.distance_transform_edt(solid) * h
        ids = np.nonzero(solid.ravel())[0]
        self.ids = ids
        self.coords = np.array(np.unravel_index(ids, dims)).T
        self.P = lo + (self.coords + 0.5) * h
        self.r = self.edt_grid.ravel()[ids]
        index = -np.ones(dims, int)
        index.ravel()[ids] = np.arange(len(ids))
        rows, cols, ln = [], [], []
        for d in [(a, b, c) for a in (-1, 0, 1) for b in (-1, 0, 1) for c in (-1, 0, 1) if (a, b, c) > (0, 0, 0)]:
            q = self.coords + d
            ok = ((q >= 0) & (q < dims)).all(1)
            j = index[q[ok, 0], q[ok, 1], q[ok, 2]]
            m = j >= 0
            rows.append(np.nonzero(ok)[0][m])
            cols.append(j[m])
            ln.append(np.full(m.sum(), np.linalg.norm(d) * h))
        rows, cols, ln = np.concatenate(rows), np.concatenate(cols), np.concatenate(ln)
        N = len(ids)
        self.G = coo_matrix((ln, (rows, cols)), shape=(N, N)).tocsr()
        med = ln * 0.5 * (1 / self.r[rows] ** 2 + 1 / self.r[cols] ** 2) * h * h
        self.Gm = coo_matrix((med, (rows, cols)), shape=(N, N)).tocsr()
        self.tree = cKDTree(self.P)

    def nearest(self, X):
        return self.tree.query(np.asarray(X, float))[1]


def smooth_path(X, win):
    if len(X) < 3:
        return X
    k = max(1, int(win))
    pad = np.vstack([np.repeat(X[:1], k, 0), X, np.repeat(X[-1:], k, 0)])
    ker = np.ones(2 * k + 1) / (2 * k + 1)
    out = np.stack([np.convolve(pad[:, i], ker, mode="valid") for i in range(3)], 1)
    out[0], out[-1] = X[0], X[-1]
    return out


def arclen(X):
    return np.r_[0, np.cumsum(np.linalg.norm(np.diff(X, axis=0), axis=1))]


def at_arc(X, s, t):
    """Point and index of arc length t on the polyline X (arc lengths s)."""
    i = int(np.clip(np.searchsorted(s, t), 1, len(s) - 1))
    f = (t - s[i - 1]) / max(s[i] - s[i - 1], 1e-9)
    return X[i - 1] + f * (X[i] - X[i - 1]), i


def sharpest(X, s, lo, hi, span):
    """Index of the sharpest bend of X between arc lengths lo and hi (bend over +-span)."""
    best, bi = -1.0, None
    for i in range(len(X)):
        if not lo <= s[i] <= hi:
            continue
        a, _ = at_arc(X, s, max(s[i] - span, 0))
        b, _ = at_arc(X, s, min(s[i] + span, s[-1]))
        u, v = X[i] - a, b - X[i]
        if np.linalg.norm(u) < 1e-6 or np.linalg.norm(v) < 1e-6:
            continue
        ang = np.arccos(np.clip(u @ v / np.linalg.norm(u) / np.linalg.norm(v), -1, 1))
        if ang > best:
            best, bi = ang, i
    if bi is None:
        bi = int(np.argmin(np.abs(s - 0.5 * (lo + hi))))
    return bi, float(np.degrees(max(best, 0)))


def donor_lengths(profile, bones):
    """Bind distances between the donor joints of consecutive roles (L side), bind units."""
    by = {b["name"]: np.array(b["pos"]) for b in bones}

    def p(key):
        return by[role_bone(profile, key)]
    out = {}
    for a, b in zip(TRUNK, TRUNK[1:]):
        out[a] = float(np.linalg.norm(p(b) - p(a)))
    for a, b in (("L_upperarm", "L_forearm"), ("L_forearm", "L_hand")):
        out[a[2:]] = float(np.linalg.norm(p(b) - p(a)))
    # the hand and the foot: to the donor's end bones (Wrist_END / Toe_END) when the skeleton has them
    hand = role_bone(profile, "L_hand")
    ends = {b["name"]: np.array(b["pos"]) for b in bones}
    out["hand"] = float(np.linalg.norm(ends.get(hand + "_END", p("L_hand") + (p("L_hand") - p("L_forearm")) * 0.45) - p("L_hand")))
    ank, toe = role_bone(profile, "L_ankle"), role_bone(profile, "L_toe")
    toe_end = ends.get("L_Toe_END", by[toe] + (by[toe] - by[ank]) * 0.5)
    out["ankle"] = float(np.linalg.norm(by[toe] - by[ank]))
    out["toe"] = float(np.linalg.norm(toe_end - by[toe]))
    return out


# ---- embedding ----------------------------------------------------------------------------------------------------------------

def embed(P, T, cfg, profile, bones, volume_mesh=None, K=9.2):
    rig = rigid_mask(cfg, P, K)
    VP, VT = volume_mesh if volume_mesh is not None else (P, T)
    keep = None
    if "cap" in cfg:
        c, m = cfg["cap"]
        keep = lambda X: ~(X[:, 1] / K > c + m * X[:, 2] / K)  # noqa: E731
    vol = Volume(VP, VT, keep)
    h = vol.h
    H = P[:, 1].max() - P[:, 1].min()
    # seed: the thickest voxel of the trunk (below the shoulders' height share of the body)
    ybody = vol.P[:, 1]
    seed = int(np.argmax(vol.r * (ybody < np.percentile(ybody, 75))))
    D = dijkstra(vol.G, directed=False, indices=seed)
    Dm, pred = dijkstra(vol.Gm, directed=False, indices=seed, return_predecessors=True)
    # geodesic extremities
    order = np.argsort(-np.where(np.isfinite(D), D, -1))
    tips = []
    for c in order:
        if D[c] < 0.3 * D[np.isfinite(D)].max():
            break
        if all(np.linalg.norm(vol.P[c] - vol.P[t]) > 0.13 * H for t in tips):
            nb = vol.tree.query_ball_point(vol.P[c], 0.065 * H)
            if D[c] >= D[nb].max() - 1e-9:
                tips.append(int(c))
    tp = vol.P[tips]
    ylo = P[:, 1].min()
    names = {}
    low = [t for t in tips if vol.P[t, 1] - ylo < 0.15 * H]
    for side, sg in (("L", 1), ("R", -1)):
        cand = [t for t in low if np.sign(vol.P[t, 0] - vol.P[seed, 0]) == sg]
        if cand:
            names[side + "_toe_end"] = max(cand, key=lambda t: vol.P[t, 2])
    rest = [t for t in tips if t not in names.values()]
    head = max(rest, key=lambda t: vol.P[t, 1])
    names["head_end"] = head
    rest = [t for t in rest if t != head]
    for side, sg in (("L", 1), ("R", -1)):
        cand = [t for t in rest if np.sign(vol.P[t, 0] - vol.P[seed, 0]) == sg and vol.P[t, 1] - ylo >= 0.15 * H]
        if cand:
            names[side + "_hand_end"] = max(cand, key=lambda t: D[t])
    missing = [k for k in ("L_toe_end", "R_toe_end", "L_hand_end", "R_hand_end", "head_end") if k not in names]
    if missing:
        raise SystemExit("embed: no extremity found for %s (tips %s)" % (missing, tp.round(2).tolist()))

    def path(t):
        out = [t]
        while out[-1] != seed:
            out.append(pred[out[-1]])
        return vol.P[np.array(out[::-1])]

    win = max(1, int(round(0.2 / h)))
    paths = {k: smooth_path(path(t), win) for k, t in names.items()}
    dl = donor_lengths(profile, bones)
    u = profile["u"]
    J, info = {}, {"tips": {k: vol.P[t].round(3).tolist() for k, t in names.items()},
                   "all_tips": tp.round(3).tolist(), "seed": vol.P[seed].round(3).tolist(), "voxel": h,
                   "voxels": int(len(vol.P)), "closed_by": vol.closed_by}
    spine = paths["head_end"]
    ss = arclen(spine)
    sp_tree = cKDTree(spine)

    def radius_at(X):
        return vol.r[vol.nearest(X)]
    # legs: hip where the path's radius falls under 0.75 x the seed's and it is 0.6 seed radii off the spine path, knee and ankle at the sharpest bends
    rseed = vol.r[seed]
    ratio_ball = dl["ankle"] / (dl["ankle"] + dl["toe"])
    for side in ("L", "R"):
        X = paths[side + "_toe_end"]
        s = arclen(X)
        rr = radius_at(X)
        dsp = sp_tree.query(X)[0]
        hip = max(int(np.argmax(rr < 0.75 * rseed)), int(np.argmax(dsp > 0.6 * rseed)))
        J[side + "_thigh"] = X[hip].copy()
        L = s[-1] - s[hip]
        ki, ka = sharpest(X, s, s[hip] + 0.25 * L, s[hip] + 0.65 * L, 0.1 * L)
        ai, aa = sharpest(X, s, s[hip] + 0.6 * L, s[hip] + 0.92 * L, 0.06 * L)
        J[side + "_calf"], J[side + "_ankle"] = X[ki].copy(), X[ai].copy()
        J[side + "_toe"], _ = at_arc(X, s, s[ai] + ratio_ball * (s[-1] - s[ai]))
        J[side + "_toe_end"] = X[-1].copy()
        info[side + "_knee_bend_deg"], info[side + "_ankle_bend_deg"] = round(ka, 1), round(aa, 1)
        info[side + "_hip_radius"] = round(float(rr[hip]), 3)
    # arms: clavicle where the path leaves the spine path, shoulder at the sharpest bend in the first 10-40 % after it
    # (the arm turns from the shoulder line down the side), elbow at the sharpest bend of the rest, wrist by the donor's ratio
    ratio_hand = dl["hand"] / (dl["forearm"] + dl["hand"])
    branch = []
    for side in ("L", "R"):
        X = paths[side + "_hand_end"]
        s = arclen(X)
        dsp = sp_tree.query(X)[0]
        b = int(np.argmax(dsp > 2 * h))
        branch.append(int(sp_tree.query(X[b])[1]))
        Lb = s[-1] - s[b]
        sh, sa = sharpest(X, s, s[b] + 0.1 * Lb, s[b] + 0.4 * Lb, 0.08 * Lb)
        J[side + "_clav"] = X[b].copy()
        J[side + "_upperarm"] = X[sh].copy()
        L = s[-1] - s[sh]
        ei, ang = sharpest(X, s, s[sh] + 0.3 * L, s[sh] + 0.7 * L, 0.12 * L)
        J[side + "_forearm"] = X[ei].copy()
        J[side + "_hand"], _ = at_arc(X, s, s[ei] + (1 - ratio_hand) * (s[-1] - s[ei]))
        J[side + "_hand_end"] = X[-1].copy()
        info[side + "_shoulder_bend_deg"], info[side + "_elbow_bend_deg"] = round(sa, 1), round(ang, 1)
        info[side + "_arm_path"] = round(float(L), 3)
    # trunk: pelvis between the hips, chest where the arms branch off the spine path, spine_a/b at thirds between, the head
    # joint the profile's when a rigid part rides on the head (its carry frame: the cap keeps its attachment), else at 80 % of
    # the spine path; neck half way from chest to head (on the path)
    inst = rig_fit.instances(profile, bones)
    J["pelvis"] = 0.5 * (J["L_thigh"] + J["R_thigh"])
    ip_ = int(sp_tree.query(J["pelvis"])[1])
    ic = int(np.mean(branch))
    J["chest"] = spine[ic].copy()
    J["spine_a"], _ = at_arc(spine, ss, ss[ip_] + (ss[ic] - ss[ip_]) / 3)
    J["spine_b"], _ = at_arc(spine, ss, ss[ip_] + 2 * (ss[ic] - ss[ip_]) / 3)
    if "cap" in cfg:
        J["head"] = inst["head"][0].copy()
    else:
        J["head"], _ = at_arc(spine, ss, 0.8 * ss[-1])
    ih = int(sp_tree.query(J["head"])[1])
    J["neck"], _ = at_arc(spine, ss, 0.5 * (ss[ic] + ss[ih]))
    if not ss[ip_] < ss[ic] < ss[ih]:
        info.setdefault("warnings", []).append("spine order pelvis %.2f chest %.2f head %.2f" % (ss[ip_], ss[ic], ss[ih]))
    J["head_end"] = paths["head_end"][-1].copy()
    # the old table, for the record
    old = {k: v[0] for k, v in inst.items()}
    info["moved_from_table"] = {k: round(float(np.linalg.norm(J[k] - old[k])), 3) for k in J if k in old}
    edges = []
    for a, b in zip(TRUNK, TRUNK[1:] + ("head_end",)):
        edges.append((a, b))
    for side in ("L", "R"):
        edges.append(("chest", side + "_clav"))
        edges += [(side + "_" + a, side + "_" + b) for a, b in zip(ARM, ARM[1:])]
        edges.append(("pelvis", side + "_thigh"))
        edges += [(side + "_" + a, side + "_" + b) for a, b in zip(LEG, LEG[1:])]
    return {"posed": {k: [float(x) for x in v] for k, v in J.items()}, "edges": edges, "info": info,
            "paths": {k: v.round(4).tolist() for k, v in paths.items()}, "K": K, "rigid_vertices": int(rig.sum())}, vol


def cmd_embed(a, opt):
    cfg, profile = cfg_profile()
    bones = skel_info.bones(donor_skeleton(cfg))
    K = cfg["K"]
    P, T = load_posed(a[0], K)[0]
    vm = None
    if opt("--volume", None):
        v = np.load(opt("--volume", None))
        vp = v["pos"] * (K if v["pos"][:, 1].max() < 2 else 1.0)
        vm = (cap_scaled(cfg, vp, K, opt), v["tris"])
    res, _vol = embed(P, T, cfg, profile, bones, vm, K)
    res["volume"] = str(Path(opt("--volume", None)).resolve()) if opt("--volume", None) else None
    Path(a[1]).write_text(json.dumps(res, indent=1))
    print(json.dumps(res["info"], indent=1))
    if opt("--png", None):
        joints_png(P, T, res, Path(opt("--png", None)))


def cap_scaled(cfg, P, K, opt):
    """A volume mesh's rigid part scaled like s5_build's --cap-scale (the stage's build.json), so it sits like the stage's."""
    return P


def joints_png(P, T, res, outdir):
    from PIL import ImageDraw
    import render_soft
    import rig_audit
    outdir.mkdir(parents=True, exist_ok=True)
    J = {k: np.array(v) for k, v in res["posed"].items()}
    size = 520
    sc, ce = render_soft.framing(P, size, 0.0)
    ims = []
    for az in (0, 90):
        im = rig_audit.tile(P, T, az, 0.0, size, sc, ce, alpha=0.55)
        dr = ImageDraw.Draw(im)
        for k, X in res["paths"].items():
            X = np.array(X)
            x, y = rig_audit.proj(X, az, 0.0, size, sc, ce)
            dr.line(list(zip(x, y)), fill=(90, 200, 255), width=1)
        im = rig_audit.draw_skeleton(im, J, [tuple(e) for e in res["edges"]], az, 0.0, sc, ce, col=(255, 200, 0), labels=(az == 0))
        ims.append(rig_audit.label(im, "embedded joints (yellow) + medial paths (blue), az %d" % az))
    rig_audit.row(ims).save(outdir / "joints_embedded.png")


# ---- weights --------------------------------------------------------------------------------------------------------------------

def bone_curves(J, res, vol, profile):
    """{bone name: voxel indices of its medial curve}: the path between the bone's joint and its child's joint."""
    paths = {k: np.array(v) for k, v in res["paths"].items()}
    out = {}

    def seg(X, a, b):
        ia = int(cKDTree(X).query(a)[1])
        ib = int(cKDTree(X).query(b)[1])
        lo, hi = min(ia, ib), max(ia, ib)
        pts = X[lo:hi + 1] if hi > lo else np.array([a, b])
        # densify
        dense = [pts[0]]
        for p in pts[1:]:
            n = int(np.ceil(np.linalg.norm(p - dense[-1]) / (0.5 * vol.h)))
            dense += [dense[-1] + (p - dense[-1]) * (i + 1) / max(n, 1) for i in range(max(n, 1))]
        return np.unique(vol.nearest(np.array(dense)))

    spine = paths["head_end"]
    trunk = list(TRUNK) + ["head_end"]
    for a, b in zip(trunk, trunk[1:]):
        out[role_bone(profile, a)] = seg(spine, J[a], J[b])
    for side in ("L", "R"):
        X = paths[side + "_hand_end"]
        keys = [side + "_" + r for r in ARM]
        out[role_bone(profile, keys[0])] = np.unique(np.r_[seg(X, J[keys[0]], J[keys[1]]), seg(spine, J["chest"], J[keys[0]])])
        for a, b in zip(keys[1:], keys[2:]):
            out[role_bone(profile, a)] = seg(X, J[a], J[b])
        X = paths[side + "_toe_end"]
        keys = [side + "_" + r for r in LEG]
        for a, b in zip(keys, keys[1:]):
            out[role_bone(profile, a)] = seg(X, J[a], J[b])
    return {k: v for k, v in out.items() if k is not None}


def voxel_distances(vol, curves, limit):
    names = list(curves)
    Dist = np.full((len(names), len(vol.P)), np.inf, np.float32)
    for i, n in enumerate(names):
        Dist[i] = dijkstra(vol.G, directed=False, indices=curves[n], min_only=True, limit=limit)
    return names, Dist


def vertex_weights(P, N, tris, vol, names, Dist, power=4.0, smooth=2, rigid=None, rigid_bone=None):
    """Top-4 (bone_idx, weights, names) of the vertices from the voxel distances; `rigid` vertices take `rigid_bone` alone."""
    inside = P - N * 0.75 * vol.h
    vi = vol.nearest(inside)
    dvox = np.linalg.norm(vol.P[vi] - P, axis=1)
    d = Dist[:, vi].T.astype(float) + dvox[:, None]
    W = 1.0 / (d + vol.h) ** power
    W[~np.isfinite(W)] = 0
    W /= np.maximum(W.sum(1, keepdims=True), 1e-30)
    for _ in range(smooth):
        idx = np.argsort(-W, axis=1)[:, 4:]
        np.put_along_axis(W, idx, 0, axis=1)
        W /= np.maximum(W.sum(1, keepdims=True), 1e-30)
        W = rig_fit.smooth(W, tris, 1)
    idx = np.argsort(-W, axis=1)[:, 4:]
    np.put_along_axis(W, idx, 0, axis=1)
    names = list(names)
    if rigid is not None and rigid.any():
        if rigid_bone not in names:
            names.append(rigid_bone)
            W = np.hstack([W, np.zeros((len(W), 1))])
        W[rigid] = 0
        W[rigid, names.index(rigid_bone)] = 1
    W /= np.maximum(W.sum(1, keepdims=True), 1e-30)
    top = np.argsort(-W, axis=1)[:, :4]
    return top, np.take_along_axis(W, top, 1), names


# ---- skeleton in place ----------------------------------------------------------------------------------------------------------

def decompose(M):
    """(pos, quat xyzw, scale_shear 9) of a 4x4 with a rotation (and no scale)."""
    import s5_death as sd
    R = M[:3, :3]
    U, _s, Vt = np.linalg.svd(R)
    R = U @ Vt
    return M[:3, 3].copy(), sd.mat_q(R), np.eye(3).ravel()


class InPlace:
    """The donor skeleton posed into the mesh (bind units = game units / u). trunk: "delta" (clips add their motion to the
    mesh's own lean) or "world" (the trunk takes the clip's orientation: for clips fitted on an upright, unposed trunk)."""

    def __init__(self, cfg, profile, J, donor_model, trunk="delta"):
        self.cfg, self.profile, self.trunk = cfg, profile, trunk
        _g, tree = d2r_mesh.load_model(donor_model)
        self.sk = gr2.Skeleton(tree["Skeletons"][0])
        sk = self.sk
        u = profile["u"]
        B = np.linalg.inv(sk.iwt)                      # donor bind worlds (column vectors)
        self.B = B
        Jb = {k: np.array(v, float) / u for k, v in J.items() if not k.startswith("_")}
        self.Jb = Jb
        key_of = {}
        for k in Jb:
            n = role_bone(profile, k)
            if n is not None and n in sk.idx:
                key_of[n] = k
        self.key_of = key_of
        child = {}
        for a, b in [tuple(e) for e in J["_edges"]]:
            child.setdefault(a, b)                     # the chain's next joint (first edge from a)
        self.child = child
        keep = {cfg.get("cap_bone"), self.shell_bone()} - {None}
        self.keep = keep
        F = [None] * len(sk.names)
        R = [None] * len(sk.names)
        rest = sk.rest_locals()
        for i, n in enumerate(sk.names):
            p = sk.parent[i]
            Rp = R[p] if p >= 0 else np.eye(3)
            if n in key_of:
                k = key_of[n]
                ck = child.get(k)
                if k == "head" and "cap" in cfg:
                    Ri = np.eye(3)                     # rig_fit's carry frame: the donor's head, moved
                elif ck is not None:
                    c_name = role_bone(profile, ck)
                    if c_name in sk.idx:
                        db = B[sk.idx[c_name]][:3, 3] - B[i][:3, 3]
                    else:                              # an end point: along the donor's bone from its parent
                        db = B[i][:3, 3] - B[p][:3, 3]
                    dp = Jb[ck] - Jb[k]
                    Ri = rig_fit.rot_between(Rp @ db, dp) @ Rp
                else:
                    Ri = Rp
                M = np.eye(4)
                M[:3, :3] = Ri @ B[i][:3, :3]
                M[:3, 3] = Jb[k]
                F[i], R[i] = M, Ri
            elif n in keep:
                F[i], R[i] = B[i].copy(), np.eye(3)
            else:
                F[i] = (F[p] @ rest[i]) if p >= 0 else rest[i]
                R[i] = Rp
        self.F = np.stack(F)
        self.R = R
        self.locals = np.stack([np.linalg.inv(self.F[sk.parent[i]]) @ self.F[i] if sk.parent[i] >= 0 else self.F[i]
                                for i in range(len(sk.names))])

    def shell_bone(self):
        import s5_clipfit
        return s5_clipfit.CFG["monsters"].get(common.TOKEN, {}).get("shell_bone")

    def write_skeleton(self, tree):
        """Rest transforms and inverse world transforms of the tree's skeleton, by bone name (the unit's .skeleton file
        has the bones in another order than the model's copy)."""
        bones = tree["Skeletons"][0]["Bones"]
        names = [b["Name"] for b in bones]
        missing = set(names) ^ set(self.sk.names)
        if missing:
            raise SystemExit("skeleton bones differ from the model's: %s" % sorted(missing))
        for b in bones:
            i = self.sk.idx[b["Name"]]
            p = b["ParentIndex"]
            pn = names[p] if p >= 0 else None
            if (pn is None) != (self.sk.parent[i] < 0) or (pn is not None and self.sk.names[self.sk.parent[i]] != pn):
                raise SystemExit("bone %s: another parent than in the model" % b["Name"])
            pos, q, ss = decompose(self.locals[i])
            b["Transform"] = dm.Transform(b["Transform"].flags | 0x3, pos, q, ss)
            b["InverseWorldTransform"] = [float(x) for x in np.linalg.inv(self.F[i]).T.ravel()]


# ---- retarget -------------------------------------------------------------------------------------------------------------------

def two_bone(H, tgt, l1, l2, pole):
    """(knee, ankle) of a two-bone chain from H with lengths l1, l2 reaching for tgt (as far as it can), the knee bent
    toward `pole` (any vector; its part across the hip-target line is used)."""
    v = tgt - H
    d = float(np.clip(np.linalg.norm(v), abs(l1 - l2) + 1e-4, l1 + l2 - 1e-4))
    ax = v / max(np.linalg.norm(v), 1e-9)
    pole = pole - (pole @ ax) * ax
    if np.linalg.norm(pole) < 1e-9:
        pole = np.cross(ax, [1.0, 0, 0]) if abs(ax[0]) < 0.9 else np.cross(ax, [0, 1.0, 0])
    pole = pole / np.linalg.norm(pole)
    a = (l1 * l1 - l2 * l2 + d * d) / (2 * d)
    hk = np.sqrt(max(l1 * l1 - a * a, 0.0))
    return H + a * ax + hk * pole, H + d * ax


def rot_angle_axis(R):
    ang = float(np.arccos(np.clip((np.trace(R) - 1) / 2, -1, 1)))
    ax = np.array([R[2, 1] - R[1, 2], R[0, 2] - R[2, 0], R[1, 0] - R[0, 1]])
    n = np.linalg.norm(ax)
    if n < 1e-9:
        return 0.0, np.array([1.0, 0, 0])
    return ang, ax / n


def axis_angle(ax, ang):
    k = np.array([[0, -ax[2], ax[1]], [ax[2], 0, -ax[0]], [-ax[1], ax[0], 0]])
    return np.eye(3) + np.sin(ang) * k + (1 - np.cos(ang)) * k @ k


class Retarget:
    """Donor-convention clip locals -> this rig's locals (see the module doc)."""

    def __init__(self, ip: InPlace):
        self.ip = ip
        sk, pr = ip.sk, ip.profile
        own = []
        for k in ip.Jb:
            n = role_bone(pr, k)
            if n is not None and n in sk.idx:
                own.append(sk.idx[n])
        self.legs = []
        for side in ("L", "R"):
            th, ca, an = (sk.idx[role_bone(pr, side + "_" + r)] for r in ("thigh", "calf", "ankle"))
            self.legs.append((th, ca, an))
        # trunk and clavicles: the clip's motion from the donor's rest, on top of our rest (the mesh's own lean is kept);
        # the upper arms: the donor clip's world orientation (they hang as the donor's do, whatever the lean)
        self.delta = [sk.idx[role_bone(pr, r)] for r in ("pelvis", "spine_a", "spine_b", "chest", "neck")]
        self.delta += [sk.idx[role_bone(pr, s_ + "_clav")] for s_ in ("L", "R")]
        if ip.trunk == "world":
            self.delta = []
        self.world_rot = [sk.idx[role_bone(pr, s_ + "_upperarm")] for s_ in ("L", "R")]
        self.rest_d = sk.rest_locals()
        self.rest_o = ip.locals
        self.own_pos = {i: ip.locals[i][:3, 3].copy() for i in own}
        self.cog = sk.idx.get("cog")
        self.head = sk.idx[role_bone(pr, "head")]
        self.anchor_head = "cap" in ip.cfg          # the rigid part rides on the head: the head's world motion is kept
        self.keep = [sk.idx[n] for n in ip.keep if n in sk.idx]
        B = ip.B
        self.donor_ankle_h = {an: B[an][1, 3] for _t, _c, an in self.legs}
        self.own_ankle_h = {an: ip.F[an][1, 3] for _t, _c, an in self.legs}
        self.len = {}
        for th, ca, an in self.legs:
            self.len[th] = np.linalg.norm(ip.F[ca][:3, 3] - ip.F[th][:3, 3])
            self.len[ca] = np.linalg.norm(ip.F[an][:3, 3] - ip.F[ca][:3, 3])
        # without a head anchor the cog height scales with the legs (hip height over the donor's)
        hips = [ip.F[th][1, 3] for th, _c, _a in self.legs]
        dh = [B[th][1, 3] for th, _c, _a in self.legs]
        self.cog_scale = float(np.mean(hips) / np.mean(dh))

    def worlds(self, sk, L):
        W = np.zeros_like(L)
        for i, p in enumerate(sk.parent):
            W[i] = L[i] if p < 0 else W[p] @ L[i]
        return W

    def apply(self, Ld):
        """Our local matrices (B, 4, 4) from donor-convention locals Ld."""
        sk = self.ip.sk
        Wd = self.worlds(sk, Ld)
        L = Ld.copy()
        for i in self.delta:
            L[i] = self.rest_o[i] @ np.linalg.inv(self.rest_d[i]) @ Ld[i]
        for i, p in self.own_pos.items():
            L[i][:3, 3] = p
        W = self.worlds(sk, L)
        if self.anchor_head:
            # the head must turn as the donor clip's (the cap rides on it): the turn still missing is spread evenly over the
            # spine joints instead of all landing on the neck
            chain = [sk.idx[role_bone(self.ip.profile, r)] for r in ("spine_a", "spine_b", "chest", "neck")]
            for n_left, i in zip(range(len(chain), 0, -1), chain):
                Rm = Wd[self.head][:3, :3] @ W[self.head][:3, :3].T
                ang, ax = rot_angle_axis(Rm)
                Ri = axis_angle(ax, ang / n_left)
                Wi = W[i].copy()
                Wi[:3, :3] = Ri @ Wi[:3, :3]
                L[i] = np.linalg.inv(W[sk.parent[i]]) @ Wi
                L[i][:3, 3] = self.own_pos.get(i, L[i][:3, 3])
                W = self.worlds(sk, L)
        for i in self.world_rot + ([self.head] if self.anchor_head else []):
            Wi = W[i].copy()
            Wi[:3, :3] = Wd[i][:3, :3]
            L[i] = np.linalg.inv(W[sk.parent[i]]) @ Wi
            L[i][:3, 3] = self.own_pos.get(i, L[i][:3, 3])
            W = self.worlds(sk, L)
        if self.cog is not None:
            if self.anchor_head:
                delta = Wd[self.head][:3, 3] - W[self.head][:3, 3]
            else:
                delta = np.array([0.0, (self.cog_scale - 1.0) * Wd[self.cog][1, 3], 0.0])
            pc = sk.parent[self.cog]
            Rp = W[pc][:3, :3] if pc >= 0 else np.eye(3)
            L[self.cog][:3, 3] += np.linalg.solve(Rp, delta)
            W = self.worlds(sk, L)
        for th, ca, an in self.legs:
            Hd, Kd, Ad = Wd[th][:3, 3], Wd[ca][:3, 3], Wd[an][:3, 3]
            Ho = W[th][:3, 3]
            tgt = Ad + (Ho - Hd)
            tgt[1] = Ad[1] + (self.own_ankle_h[an] - self.donor_ankle_h[an])
            pole = Kd - Hd
            ad = (Ad - Hd) / max(np.linalg.norm(Ad - Hd), 1e-9)
            pole = pole - (pole @ ad) * ad
            if np.linalg.norm(pole) < 1e-3 * max(self.len[th], 1e-9):   # a straight donor leg: bend the way its knee faces
                pole = Wd[ca][:3, :3] @ self.knee_fwd(th, ca)
            Kn, An = two_bone(Ho, tgt, self.len[th], self.len[ca], pole)
            Rt = rig_fit.rot_between(Kd - Hd, Kn - Ho) @ Wd[th][:3, :3]
            Rc = rig_fit.rot_between(Ad - Kd, An - Kn) @ Wd[ca][:3, :3]
            for i, R in ((th, Rt), (ca, Rc), (an, Wd[an][:3, :3])):
                Wi = W[i].copy()
                Wi[:3, :3] = R
                L[i] = np.linalg.inv(W[sk.parent[i]]) @ Wi
                L[i][:3, 3] = self.own_pos.get(i, L[i][:3, 3])
                W = self.worlds(sk, L)
        for i in self.keep:            # the rigid part and the shell: their donor-convention world
            L[i] = np.linalg.inv(W[sk.parent[i]]) @ Wd[i]
        W = self.worlds(sk, L)
        for i in range(len(L)):
            U, sv, Vt = np.linalg.svd(L[i][:3, :3])
            if abs(sv - 1).max() < 1e-3:
                L[i][:3, :3] = U @ Vt
        return L

    def knee_fwd(self, th, ca):
        """The donor's knee forward direction in the calf's frame (its bind: +z of the world, the knee's front)."""
        Rc = self.ip.B[ca][:3, :3]
        return Rc.T @ np.array([0.0, 0.0, 1.0])

    def tracked(self):
        out = set(self.own_pos) | set(self.keep)
        if self.cog is not None:
            out.add(self.cog)
        return out


SAMPLE_FPS = 60


def retarget_file(stage):
    """<stage>/clips_donor.animations -> the overlay's combined.animations, per rig.json."""
    stage = Path(stage)
    rj = json.loads((stage / "rig.json").read_text())
    cfg, profile = cfg_profile()
    ip = InPlace(cfg, profile, dict(rj["joints"], _edges=rj["edges"]), Path(rj["donor_model"]), rj.get("trunk", "delta"))
    rt = Retarget(ip)
    sk = ip.sk
    src = stage / "clips_donor.animations"
    folder = next((stage / "overlay").glob("hd/character/enemy/mxl/m3d/*"))
    dst = folder / "animation" / "combined.animations"
    g = dm.Gr2File.read(src.read_bytes())
    tree = dm.parse_tree(g)
    clips = gr2.load_clips(src.read_bytes(), sk)
    kinds = {}
    for an in tree["Animations"]:
        for tg in an["TrackGroups"]:
            for tr in tg["TransformTracks"]:
                for k in ("OrientationCurve", "PositionCurve"):
                    v = tr[k]["CurveData"]
                    kinds.setdefault(list(v.obj.f)[0], v)
    import s5_death as sd
    tmpl_q, tmpl_p = kinds["CurveDataHeader_D4Constant32f"], kinds["CurveDataHeader_D3Constant32f"]
    tmpl_k = kinds.get("CurveDataHeader_DaK32fC32f")
    if tmpl_k is None:
        raise SystemExit("no DaK32fC32f curve in %s to copy the type from" % src)
    real = tmpl_k.obj["Knots"][0].td

    def header(tmpl, deg):
        hk = list(tmpl.obj.f)[0]
        hh = tmpl.obj[hk]
        return hk, dm.Obj(hh.td, {"Format": hh["Format"], "Degree": deg})

    def curve_k(knots, controls):
        hk, hh = header(tmpl_k, 1)
        return dm.Variant(tmpl_k.td, dm.Obj(tmpl_k.obj.td, {hk: hh, "Padding": 0,
                                                             "Knots": [dm.Obj(real, {"Real32": float(x)}) for x in knots],
                                                             "Controls": [dm.Obj(real, {"Real32": float(x)}) for x in controls]}))

    def curve_c(tmpl, values):
        hk, hh = header(tmpl, 0)
        return dm.Variant(tmpl.td, dm.Obj(tmpl.obj.td, {hk: hh, "Padding": 0, "Controls": [float(x) for x in values]}))

    report = {}
    tracked = rt.tracked()
    for an in tree["Animations"]:
        clip = clips[an["Name"]]
        dur = float(an["Duration"])
        times = np.round(np.arange(0, dur + 1e-6, 1.0 / SAMPLE_FPS), 6)
        if times[-1] < dur - 1e-6:
            times = np.append(times, dur)
        loop = False
        Ls = []
        for t in times:
            loc, *_ = gr2.locals_at(sk, clip, float(t), keep_root_translation=True)
            Ld = np.stack([gr2.compose(*x) for x in loc])
            Ls.append(rt.apply(Ld))
        root = max(an["TrackGroups"], key=lambda tg: len({tr["Name"] for tr in tg["TransformTracks"]} & set(sk.names)))
        have = {tr["Name"] for tr in root["TransformTracks"]}
        changed = []
        for tr in root["TransformTracks"]:
            i = sk.idx.get(tr["Name"])
            if i is None or i not in tracked:
                continue
            qs = np.array([sd.mat_q(L[i][:3, :3]) for L in Ls])
            for j in range(1, len(qs)):
                if qs[j] @ qs[j - 1] < 0:
                    qs[j] = -qs[j]
            ps = np.array([L[i][:3, 3] for L in Ls])
            tr["OrientationCurve"]["CurveData"] = (curve_c(tmpl_q, qs[0]) if np.abs(qs - qs[0]).max() < 1e-6
                                                   else curve_k(times, qs.ravel()))
            tr["PositionCurve"]["CurveData"] = (curve_c(tmpl_p, ps[0]) if np.abs(ps - ps[0]).max() < 1e-6
                                                else curve_k(times, ps.ravel()))
            changed.append(tr["Name"])
        missing = [sk.names[i] for i in tracked if sk.names[i] not in have]
        report[an["Name"]] = {"samples": len(times), "retargeted": len(changed), "untracked_bones": missing, "loop": loop}
    size = d2r_mesh.write_model(g, tree, dst)
    report["bytes"] = size
    (stage / "retarget.json").write_text(json.dumps(report, indent=1))
    return report


# ---- build ----------------------------------------------------------------------------------------------------------------------

def posed_normals(profile, bones, cfg, d, model_nrm):
    """Normals of the stage's body in the posed frame: the model's (smoothed) bind normals carried back through rig_fit's
    per-vertex map (the inverse transpose of the blend)."""
    maps = rig_fit.carry_maps(profile, bones)
    by_name = {v[3]: v for v in maps.values()}
    if cfg.get("cap_bone"):
        by_name[cfg["cap_bone"]] = maps["head"]
    names = [str(x) for x in d["bones"]]
    u = profile["u"]
    A = np.zeros((len(d["pos"]), 3, 3))
    for j, n in enumerate(names):
        w = (d["weights"] * (d["bone_idx"] == j)).sum(1)
        A += w[:, None, None] * np.linalg.inv(by_name[n][1]).T
    n = np.linalg.solve(A, model_nrm[..., None])[..., 0]
    return n / np.maximum(np.linalg.norm(n, axis=1, keepdims=True), 1e-12)


def cmd_build(a, opt):
    src, posed_npz, joints_json, out = Path(a[0]), Path(a[1]), Path(a[2]), Path(a[3])
    cfg, profile = cfg_profile()
    K, u = cfg["K"], profile["u"]
    res = json.loads(joints_json.read_text())
    J = {k: np.array(v) for k, v in res["posed"].items()}
    if out.exists():
        raise SystemExit("%s exists" % out)
    donor_dir = D2R / "hd/character/enemy" / cfg["donor"]
    InPlace(cfg, profile, dict(res["posed"], _edges=res["edges"]), donor_dir / "torso_lod0.model")   # fails early
    shutil.copytree(src, out)
    folder = next((out / "overlay").glob("hd/character/enemy/mxl/m3d/*"))
    bones = skel_info.bones(donor_skeleton(cfg))
    lods = load_posed(posed_npz, K)
    # the volume (the one embed used) and the bone distance fields
    vm = None
    if res.get("volume"):
        v = np.load(res["volume"])
        vm = (v["pos"] * (K if v["pos"][:, 1].max() < 2 else 1.0), v["tris"])
    keep = None
    if "cap" in cfg:
        c, m = cfg["cap"]
        keep = lambda X: ~(X[:, 1] / K > c + m * X[:, 2] / K)  # noqa: E731
    VP, VT = vm if vm is not None else lods[0]
    vol = Volume(VP, VT, keep)
    curves = bone_curves(J, res, vol, profile)
    names, Dist = voxel_distances(vol, curves, limit=0.6 * (VP[:, 1].max() - VP[:, 1].min()))
    # --body-scale s: the body (every joint and every vertex but the rigid part's) scaled by s about the head joint, a uniform
    # scale (no distortion) for a generated body that is too big under its part; weights are computed before it
    bs = float(opt("--body-scale", "1.0"))
    hj = np.array(res["posed"]["head"], float)
    scaled = {k: (hj + bs * (np.array(v, float) - hj)).tolist() for k, v in res["posed"].items()}
    trunk = opt("--trunk", "delta")
    ip = InPlace(cfg, profile, dict(scaled, _edges=res["edges"]), donor_dir / "torso_lod0.model", trunk)
    power, nsmooth = float(opt("--power", "4")), int(opt("--smooth", "2"))
    report = {"rig": "rig_embed", "body_scale": bs, "power": power, "smooth": nsmooth, "voxel": vol.h, "voxels": int(len(vol.P)), "lods": []}
    cap_bone = cfg.get("cap_bone")
    shell = ip.shell_bone()
    for k, (P, T) in enumerate(lods):
        d = np.load(src / ("skinned_lod%d.npz" % k))
        old_names = [str(x) for x in d["bones"]]
        nb = len(d["pos"])
        assert len(P) == nb, "posed lod %d: %d vertices, stage %d" % (k, len(P), nb)
        model_path = folder / ("torso_lod%d.model" % k)
        g, tree = d2r_mesh.load_model(model_path)
        me = max(tree["Meshes"], key=lambda m: len(m["PrimaryVertexData"]["Vertices"].obj or []))
        dec = hd_gltf.decode_mesh(me)
        vs = me["PrimaryVertexData"]["Vertices"].obj
        bind_names = [b["BoneName"] for b in me["BoneBindings"]]
        if np.abs(dec["pos"][:nb] - d["pos"]).max() > 2e-3 * np.abs(d["pos"]).max():
            raise SystemExit("lod %d: the model's first %d vertices are not skinned_lod%d.npz" % (k, nb, k))
        rig = np.zeros(nb, bool)
        if cap_bone:
            j = old_names.index(cap_bone)
            rig = (d["bone_idx"][:, 0] == j) & (d["weights"][:, 0] > 0.99)
        Npos = posed_normals(profile, bones, cfg, d, dec["nrm"][:nb])
        bidx, wts, wnames = vertex_weights(P, Npos, T, vol, names, Dist, power, nsmooth, rig, cap_bone)
        # binding list: the model's, then the new bones
        blist = list(bind_names)
        for n in wnames:
            if n not in blist:
                blist.append(n)
        remap = np.array([blist.index(n) for n in wnames])
        BI = remap[bidx]
        S = (hj + bs * (P - hj)) / u                    # stored = posed / u (bind in place), the body scaled
        S[rig] = d["pos"][rig]                          # the cap as it was (donor jaw bind)
        Nst = Npos.copy()
        Nst[rig] = dec["nrm"][:nb][rig]
        ip.write_skeleton(tree)
        # vertices: the body new, the cap and the shell (beyond nb) copied as they were
        scale = hd_gltf.vertex_scale_of(me)
        if np.abs(S).max() * 1.0001 > scale:
            raise SystemExit("lod %d: the new body does not fit the model's vertex scale" % k)
        tan, hand = d2r_mesh.tangents(S, Nst, dec["uv"][:nb].astype(float), T)
        vtd = vs[0].td
        w_old = vs[0]["Position"][3]
        body = hd_gltf.encode_vertices(vtd, S, Nst, np.hstack([tan, hand[:, None]]), dec["uv"][:nb], BI, hd_gltf.norm_weights(wts),
                                       scale, w=w_old, like=vs[:nb])
        for i in np.nonzero(rig)[0]:
            body[i] = vs[i]
        # cap/shell vertices keep their bytes: their bone indices point into the old binding list, which blist starts with
        me["PrimaryVertexData"]["Vertices"].obj = body + list(vs[nb:])
        # bone bindings: boxes in each bone's space
        tmpl = me["BoneBindings"][0]
        inv = {b["Name"]: np.array(b["InverseWorldTransform"], float).reshape(4, 4) for b in tree["Skeletons"][0]["Bones"]}
        allpos = np.vstack([S, dec["pos"][nb:]])
        allbi = np.vstack([BI, dec["joints"][nb:]])
        allw = np.vstack([wts, dec["weights"][nb:] / 255.0])
        bind = []
        for bi, n in enumerate(blist):
            sel = ((allbi == bi) & (allw > 0)).any(1)
            pts = allpos[sel] if sel.any() else allpos
            pts = pts @ inv[n][:3, :3] + inv[n][3, :3]
            b = dm.Obj(tmpl.td, dict(tmpl.f))
            b["BoneName"] = n
            b["OBBMin"] = [float(x) for x in pts.min(0)]
            b["OBBMax"] = [float(x) for x in pts.max(0)]
            b["TriangleIndices"] = []
            bind.append(b)
        me["BoneBindings"] = bind
        size = d2r_mesh.write_model(g, tree, model_path)
        np.savez(out / ("skinned_lod%d.npz" % k), pos=S, nrm=Nst, uv=d["uv"], tris=d["tris"],
                 bone_idx=bidx, weights=wts, bones=np.array(wnames))
        report["lods"].append({"lod": k, "vertices": int(nb), "cap_vertices": int(rig.sum()), "bones": len(wnames),
                               "bytes": size})
        print("lod %d: %d vertices (%d cap), %d bones, %d bytes" % (k, nb, rig.sum(), len(wnames), size), flush=True)
    # the unit's own skeleton file
    name = common.NAME
    if "--no-unit-skeleton" not in a:
        gs, ts = d2r_mesh.load_model(donor_skeleton(cfg))
        ip.write_skeleton(ts)
        dest = folder / (name + ".skeleton")
        d2r_mesh.write_model(gs, ts, dest)
        unit_path = out / "overlay/hd/character/enemy" / ("mxl_m3d_%s.json" % name)
        unit = json.loads(unit_path.read_text(encoding="utf-8"))
        logical = "data/" + dest.relative_to(out / "overlay").as_posix()
        for e in unit["entities"]:
            for c in e["components"]:
                if c["type"] == "SkeletonDefinitionComponent":
                    c["filename"] = logical
        unit["dependencies"]["skeletons"] = [{"path": logical}]
        unit_path.write_text(json.dumps(unit, separators=(",", ":")), encoding="utf-8")
        report["unit_skeleton"] = logical
    # clips: keep the donor-convention file, retarget into the overlay
    anim = folder / "animation" / "combined.animations"
    shutil.copy2(src / "clips_donor.animations" if (src / "clips_donor.animations").is_file() else anim, out / "clips_donor.animations")
    rj = {"joints": scaled, "body_scale": bs, "trunk": trunk, "edges": res["edges"], "donor_model": str(donor_dir / "torso_lod0.model"),
          "joints_json": str(joints_json), "posed": str(posed_npz), "from": str(src)}
    (out / "rig.json").write_text(json.dumps(rj, indent=1))
    report["retarget"] = retarget_file(out)
    report["lengths"] = {ip.sk.names[i]: {"own": round(float(np.linalg.norm(ip.locals[i][:3, 3])), 3),
                                          "donor": round(float(np.linalg.norm(ip.sk.rest[i][0])), 3)}
                         for i in sorted(Retarget(ip).own_pos)}
    (out / "rig_build.json").write_text(json.dumps(report, indent=1))
    print(json.dumps({k: v for k, v in report.items() if k not in ("lods",)}, indent=1))


def cmd_retarget(a, opt):
    print(json.dumps(retarget_file(Path(a[0])), indent=1))


def main():
    a = sys.argv[1:]
    opt = lambda n, dft: a[a.index(n) + 1] if n in a else dft  # noqa: E731
    vals = ("--volume", "--png", "--power", "--smooth", "--token", "--body-scale", "--trunk")
    pos = [x for i, x in enumerate(a[1:], 1) if not x.startswith("--") and a[i - 1] not in vals]
    cmds = {"embed": cmd_embed, "build": cmd_build, "retarget": cmd_retarget}
    if not a or a[0] not in cmds:
        print(__doc__)
        return 1
    cmds[a[0]](pos, opt)
    return 0


if __name__ == "__main__":
    sys.exit(main())
