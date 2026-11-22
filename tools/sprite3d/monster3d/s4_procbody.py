"""Stage 4 (round 14, Glowing Fungus): replace the reconstructed body with a clean procedural body; the cap untouched.

  python s4_procbody.py build <src stage> <dst stage> [--params <json>] [--report <json>]

Why (owner on round 13: "yea its terrible"): the body mesh from the reconstruction is crumpled, its arms are short lumps
at the shoulders and the legs read as one column. Its skin is also broken at the source: the mesh's arms were made
hanging but are bound to the donor's T-pose skeleton (vertices down to y 2.6 weighted to the wrist bone, whose bind joint
is at y 6.16), and the thighs carry almost no weight (98 and 171 vertices), so every clip smears the limbs. A
reshape of that mesh cannot fix it. Classic's body is simple: a dark narrow torso under the cap, long thin pale arms
hanging to about the knees with dark hands, two thin dark legs with pale-blue patches, dark feet.

build: copies <src stage> to <dst stage> and, there:
1. Skeleton (every LOD model's skeleton and the rest pose): the forearm and wrist bones' local offsets are scaled
   (--params upper, fore; clav: the upper arm's offset from the clavicle, broader shoulders; leg: thigh and
   calf length, so that with the body height held the knees bend into classic's crouch) so the arms are long; the thighs' offsets from the pelvis are scaled sideways (hip) so the
   legs stand apart. Inverse world transforms follow. The cap's chain (cog, spine, chest, neck, head, jaw) is not
   touched, so the cap's world transform in every clip stays exact.
2. Clips: in every clip of combined.animations, the same bones' position tracks get the same scale (a retarget), so
   donor and own clips (death, knockback, skill1) keep their motion on the longer bones.
3. Body mesh per LOD: generalised tubes along the bind joints (arm: shoulder, elbow, wrist, hand end; leg: hip, knee,
   ankle; foot: heel to toe) and a lofted torso of elliptic sections along the spine, closed with domes; radii, sections
   and resolutions come from the params. Weights are explicit: along each tube a bone owns its segment, blended
   linearly across a band at each joint (the torso by height between its spine bones). Normals are the welded,
   area-weighted face normals of the smooth surface. The cap vertices (fully on --bone jaw) and the corpse shell
   (loin_cloth) are kept as the file's own vertex records, byte for byte; only the old body is replaced.
4. Texture: each part gets a column of one rectangle of the atlas that holds no cap texel and no cap glow
   (params rect, in 2048 texels): u around the part, v along it. The rectangle is painted (albedo: matte classic
   colours with periodic soft mottling; normal: flat; ORM: occlusion 255, roughness, metal 0, specular level; body glow
   mask 0) with s3_bodymat's splice writer, so every compressed block outside it is the old file's bytes.
5. skinned_lod<N>.npz (cap + new body, the bones list without loin_cloth) for s5_clipfit/s5_limbfit and labels.
Writes <dst>/procbody.json (params and counts).
"""
import json
import shutil
import sys
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage as nd

import common
import s3_bodymat as bm

sys.path.insert(0, str(common.WT / "tools"))
import d2r_mesh  # noqa: E402
import d2r_model as dm  # noqa: E402
import d2r_texture  # noqa: E402
import hd_gltf  # noqa: E402
from hdkit.view import gr2  # noqa: E402

FOLDER = "hd/character/enemy/mxl/m3d/fungus"

DEFAULT = {
    "upper": 1.3, "fore": 1.3, "hip": 1.35, "clav": 1.0,
    # arm radii (shoulder, elbow, wrist, hand) and the hand's length past the wrist joint
    "arm_r": [0.30, 0.23, 0.19, 0.24], "hand_len": 0.55, "arm_in": 0.25,
    # leg radii (hip, knee, ankle), how far the leg tube starts above the hip joint
    "leg_r": [0.40, 0.29, 0.21], "leg_up": 0.35,
    # foot: half width, half height, heel back, toe forward of the ball, lift
    "foot": [0.21, 0.14, 0.2, 0.25, 0.13],
    # torso sections: [y, rx, rz, z offset]
    "torso": [[3.60, 0.10, 0.10, 0.0], [3.75, 0.70, 0.52, 0.0], [4.10, 0.92, 0.64, 0.0], [4.60, 0.85, 0.62, 0.02],
              [5.20, 0.88, 0.64, 0.0], [5.80, 1.00, 0.68, -0.02], [6.25, 0.95, 0.64, -0.02], [6.60, 0.60, 0.48, 0.05],
              [7.00, 0.10, 0.10, 0.10]],
    "torso_bones": [["pelvis", 3.9], ["spine_01", 4.4], ["spine_02", 4.9], ["chest", 5.5], ["neck", 6.35], ["head", 6.8]],
    "bands": {"shoulder": 0.15, "elbow": 0.14, "wrist": 0.08, "hip": 0.18, "knee": 0.14, "ankle": 0.08},
    # per LOD: ring segments, step along the tube
    "res": [[18, 0.05], [14, 0.08], [11, 0.12], [9, 0.18], [7, 0.27]],
    "rect": [224, 1216, 416, 1440],
    "cols": {"torso": [0, 64], "arm": [64, 112], "leg": [112, 160], "foot": [160, 192]},
    # mottling scale per part in texels (across, along): the parts' texel densities differ by direction
    "sigma": {"torso": [4, 22], "arm": [7, 18], "leg": [6, 16], "foot": [4, 8]},
    "inset": 5,
    # albedo colours (sRGB 0..255)
    "torso_rgb": [26, 26, 28], "torso_var": 0.35,
    "arm_rgb": [104, 116, 168], "arm_hi": [150, 166, 226], "arm_dark": [64, 72, 108], "hand_rgb": [36, 38, 46], "hand_v": 0.86,
    "leg_rgb": [32, 33, 38], "leg_pale": [104, 118, 168], "leg_pale_share": [0.45, 0.2],
    "foot_rgb": [50, 50, 54],
    "rough": 240, "spec": 6,
    "seed": 14,
}


def opt(a, name, default):
    return a[a.index(name) + 1] if name in a else default


# ---------------------------------------------------------------------------------------------------------- skeleton
def edit_skeleton(bones, P):
    """New rest Transforms and inverse world transforms of a model's skeleton (list of bone Objs), in place.
    Returns the new bind world matrices (column convention) by name."""
    names = [b["Name"] for b in bones]
    idx = {n: i for i, n in enumerate(names)}
    scale = scale_map(P)
    for n, s in scale.items():
        b = bones[idx[n]]
        tr = b["Transform"]
        b["Transform"] = dm.Transform(tr.flags, tuple(float(x) for x in np.array(tr.position) * s), tr.orientation,
                                      tr.scale_shear)
    loc = [gr2.compose(np.array(b["Transform"].position, float), np.array(b["Transform"].orientation, float),
                       np.array(b["Transform"].scale_shear, float)) for b in bones]
    W = []
    for i, b in enumerate(bones):
        p = int(b["ParentIndex"])
        W.append(loc[i] if p < 0 else W[p] @ loc[i])
    for i, b in enumerate(bones):
        old = np.array(b["InverseWorldTransform"], float).reshape(4, 4).T
        new = np.linalg.inv(W[i])
        if not any(n in scale for n in chain(bones, i)):
            assert np.abs(old - new).max() < 1e-4, (names[i], np.abs(old - new).max())
            continue
        b["InverseWorldTransform"] = [float(x) for x in new.T.ravel()]
    return {n: W[i] for i, n in enumerate(names)}


def chain(bones, i):
    out = []
    while i >= 0:
        out.append(bones[i]["Name"])
        i = int(bones[i]["ParentIndex"])
    return out


def scale_map(P):
    """bone -> per-axis scale of its local offset (the donor's arm bones run along local x; the thighs sit at local z)."""
    u, f, h, c = float(P["upper"]), float(P["fore"]), float(P["hip"]), float(P.get("clav", 1.0))
    g = float(P.get("leg", 1.0))
    return {"L_UpperArm": np.array([c, 1, 1]), "R_UpperArm": np.array([c, 1, 1]),
            "L_Calf": np.array([g, 1, 1]), "R_Calf": np.array([g, 1, 1]), "L_Foot": np.array([g, 1, 1]), "R_Foot": np.array([g, 1, 1]),"L_ForeArm": np.array([u, 1, 1]), "R_ForeArm": np.array([u, 1, 1]),
            "L_Wrist": np.array([f, 1, 1]), "R_Wrist": np.array([f, 1, 1]),
            "L_Thigh": np.array([1, 1, h]), "R_Thigh": np.array([1, 1, h])}


def retarget_clips(path, P):
    """Scale the position tracks of the scale_map bones in every clip (any curve kind; keyed ones resampled at 60/s)."""
    g = dm.Gr2File.read(path.read_bytes())
    tree = dm.parse_tree(g)
    kinds = {}
    for an in tree["Animations"]:
        for tg in an["TrackGroups"]:
            for tr in tg["TransformTracks"]:
                for k in ("OrientationCurve", "PositionCurve"):
                    v = tr[k]["CurveData"]
                    kinds.setdefault(list(v.obj.f)[0], v)
    tmpl_k, tmpl_p = kinds["CurveDataHeader_DaK32fC32f"], kinds["CurveDataHeader_D3Constant32f"]
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

    def curve_c(values):
        hk, h = header(tmpl_p, 0)
        return dm.Variant(tmpl_p.td, dm.Obj(tmpl_p.obj.td, {hk: h, "Padding": 0, "Controls": [float(x) for x in values]}))

    sm = scale_map(P)
    rep = {}
    for an in tree["Animations"]:
        dur = float(an["Duration"])
        for tg in an["TrackGroups"]:
            for tr in tg["TransformTracks"]:
                s = sm.get(tr["Name"])
                if s is None:
                    continue
                cv = tr["PositionCurve"]
                kind = gr2.curve_kind(cv)
                if kind == "D3Constant32f":
                    v = np.array(cv["CurveData"].obj["Controls"], float) * s
                    tr["PositionCurve"]["CurveData"] = curve_c(v)
                elif kind == "DaK32fC32f":
                    o = cv["CurveData"].obj
                    c = np.array([x["Real32"] for x in o["Controls"]], float).reshape(-1, 3) * s
                    tr["PositionCurve"]["CurveData"] = curve_k([x["Real32"] for x in o["Knots"]], c.ravel())
                else:
                    ts = np.round(np.arange(0, dur + 1e-6, 1 / 60.0), 6)
                    v = np.array([gr2.sample_curve(cv, float(t), 3) for t in ts]) * s
                    tr["PositionCurve"]["CurveData"] = curve_c(v[0]) if np.abs(v - v[0]).max() < 1e-6 else curve_k(ts, v.ravel())
                rep.setdefault(an["Name"], []).append("%s:%s" % (tr["Name"], kind))
    d2r_mesh.write_model(g, tree, path)
    return rep


# ---------------------------------------------------------------------------------------------------------- geometry
def frames_along(C):
    """Parallel-transport frames (T, N, B) along polyline samples C (n, 3)."""
    T = np.gradient(C, axis=0)
    T /= np.maximum(np.linalg.norm(T, axis=1, keepdims=True), 1e-12)
    ref = np.array([0.0, 0.0, 1.0]) if abs(T[0, 2]) < 0.9 else np.array([1.0, 0.0, 0.0])
    N = [np.cross(np.cross(T[0], ref), T[0])]
    N[0] /= np.linalg.norm(N[0])
    for i in range(1, len(C)):
        n = N[-1] - T[i] * (N[-1] @ T[i])
        N.append(n / max(np.linalg.norm(n), 1e-12))
    N = np.array(N)
    return T, N, np.cross(T, N)


def resample(points, step):
    """Dense samples along a polyline: (samples (m, 3), arc length (m,), arc length of each given point)."""
    P = np.asarray(points, float)
    seg = np.linalg.norm(np.diff(P, axis=0), axis=1)
    sk = np.r_[0, np.cumsum(seg)]
    n = max(int(np.ceil(sk[-1] / step)), 2)
    s = np.linspace(0, sk[-1], n + 1)
    C = np.stack([np.interp(s, sk, P[:, k]) for k in range(3)], 1)
    # smooth corners a little (Chaikin-like): keeps the tube from kinking at a bent joint
    for _ in range(2):
        C[1:-1] = 0.25 * C[:-2] + 0.5 * C[1:-1] + 0.25 * C[2:]
    return C, s, sk


def gnarl_field(G, seed):
    """Round 16: a knobbly, fibrous radius modulation disp(v, theta) (v in model units along the part, theta around it):
    a few random waves (whole numbers around, so the seam closes) plus twisted ridges (fibres). Resolution-free, so every
    LOD gets the same shape. G = {"amp", "ridges", "ridge_amp", "twist"} or None."""
    if not G:
        return lambda v, th: np.zeros(np.broadcast(v, th).shape)
    rng = np.random.default_rng(seed)
    n = 7
    k = rng.integers(1, 6, n)
    w = rng.uniform(2.0, 9.0, n) * rng.choice([-1, 1], n)
    ph = rng.uniform(0, 2 * np.pi, n)
    a = rng.uniform(0.5, 1.0, n)
    a /= np.sqrt((a ** 2).sum() / 2)
    amp, nr, ra, tw = float(G.get("amp", 0.1)), int(G.get("ridges", 0)), float(G.get("ridge_amp", 0)), float(G.get("twist", 0))

    def f(v, th):
        v, th = np.broadcast_arrays(np.asarray(v, float), np.asarray(th, float))
        out = sum(a[j] * np.cos(k[j] * th + w[j] * v + ph[j]) for j in range(n)) * amp
        if nr:
            out = out + ra * np.cos(nr * th + tw * v)
        return out
    return f


def tube(C, s, radius, seg, dome0=True, dome1=True, ell=None, nref=None, gnarl=None):
    """Rings around centerline C at arc lengths s with radius(s) (and ellipse ratio ell(s) on B); domes close the ends.
    Returns pos (rings, seg+1, 3), ring param v (rings,), circumferential u (seg+1,)."""
    T, N, B = frames_along(C)
    if nref is not None:     # turn the frames so N is as close as possible to nref (for flattened sections)
        n2 = nref - T * (T @ nref)[:, None]
        n2 /= np.maximum(np.linalg.norm(n2, axis=1, keepdims=True), 1e-12)
        N, B = n2, np.cross(T, n2)
    r = np.array([radius(x) for x in s])
    e = np.array([ell(x) for x in s]) if ell else np.ones(len(s))
    rings_c, rings_r, rings_e, rings_T, rings_N, rings_B, vv = [], [], [], [], [], [], []
    L = s[-1]
    if dome0:
        for k in range(5, 0, -1):
            a = k / 5 * np.pi / 2
            rings_c.append(C[0] - T[0] * r[0] * np.sin(a) * 0.8)
            rings_r.append(r[0] * max(np.cos(a), 0.02))
            rings_e.append(e[0]), rings_T.append(T[0]), rings_N.append(N[0]), rings_B.append(B[0])
            vv.append(-r[0] * np.sin(a) * 0.8)
    for i in range(len(C)):
        rings_c.append(C[i]), rings_r.append(r[i]), rings_e.append(e[i])
        rings_T.append(T[i]), rings_N.append(N[i]), rings_B.append(B[i]), vv.append(s[i])
    if dome1:
        for k in range(1, 6):
            a = k / 5 * np.pi / 2
            rings_c.append(C[-1] + T[-1] * r[-1] * np.sin(a) * 0.8)
            rings_r.append(r[-1] * max(np.cos(a), 0.02))
            rings_e.append(e[-1]), rings_T.append(T[-1]), rings_N.append(N[-1]), rings_B.append(B[-1])
            vv.append(L + r[-1] * np.sin(a) * 0.8)
    th = np.linspace(0, 2 * np.pi, seg + 1)
    ct, st = np.cos(th), np.sin(th)
    vv = np.array(vv)
    D = 1.0 + (gnarl(vv[:, None], th[None, :]) if gnarl is not None else 0.0) * np.ones((len(vv), len(th)))
    if gnarl is not None:      # no knobs on the end caps' tips
        D = 1.0 + (D - 1.0) * np.clip(np.minimum(vv - vv.min(), vv.max() - vv)[:, None] / 0.15, 0, 1)
    pos = np.array([c + rr * D[i][:, None] * (ct[:, None] * n + ee * st[:, None] * b) for i, (c, rr, ee, n, b)
                    in enumerate(zip(rings_c, rings_r, rings_e, rings_N, rings_B))])
    return pos, vv, th / (2 * np.pi)


def grid_tris(nr, nc):
    """Triangles of an (nr x nc) vertex grid (rows = rings, columns = around, last column = seam copy)."""
    t = []
    for i in range(nr - 1):
        for j in range(nc - 1):
            a, b, c, d = i * nc + j, i * nc + j + 1, (i + 1) * nc + j, (i + 1) * nc + j + 1
            t += [(a, c, b), (b, c, d)]
    return np.array(t, int)


def blend_weights(v, joints, bones, bands):
    """Two-bone weights along a tube: bone k owns [joint k, joint k+1); at each inner joint the weight moves linearly
    across +-band. joints: arc lengths of the inner joints (len(bones) - 1)."""
    w = np.zeros((len(v), len(bones)))
    k = np.searchsorted(joints, v)          # segment index
    w[np.arange(len(v)), k] = 1.0
    for j, (sj, b) in enumerate(zip(joints, bands)):
        m = np.abs(v - sj) < b
        t = (v[m] - (sj - b)) / (2 * b)
        w[m] = 0
        w[m, j] = 1 - t
        w[m, j + 1] = t
    return w


VMARK = {}       # joint positions along each limb (model units), for the paint


class Part:
    def __init__(self, name, kind, pos, v01, u, bones, w):
        self.name, self.kind = name, kind
        self.pos, self.v01, self.u, self.bones, self.w = pos, v01, u, bones, w


def build_body(Wb, P, seg, step):
    """The procedural body in the bind pose (Wb: new bind worlds by name). Returns a list of Part."""
    J = {n: M[:3, 3] for n, M in Wb.items()}
    parts = []
    bands = P["bands"]
    for side in "LR":
        # arm
        sh, el, wr = J[side + "_UpperArm"], J[side + "_ForeArm"], J[side + "_Wrist"]
        d0 = (sh - J[side + "_Clavicle"]) / np.linalg.norm(sh - J[side + "_Clavicle"])
        dh = (wr - el) / np.linalg.norm(wr - el)
        pts = [sh - d0 * P["arm_in"], sh, el, wr, wr + dh * P["hand_len"]]
        C, s, sk = resample(pts, step)
        r0, r1, r2, r3 = P["arm_r"]
        hand_mid = sk[3] + 0.45 * P["hand_len"]

        kb = float(P.get("knob", 0.0))

        def rad(x, sk=sk, r=(r0, r0, r1, r2, r3), hm=hand_mid):
            base = float(np.interp(x, [sk[0], sk[1], sk[2], sk[3] - 0.05, hm, sk[4]], [r[0] * 0.95, r[0], r[2], r[3], r[4], r[4] * 0.8]))
            return base * (1 + kb * np.exp(-((x - sk[2]) / 0.13) ** 2) + 0.6 * kb * np.exp(-((x - sk[3]) / 0.08) ** 2))
        # the hand is a flattened paddle: thinner across the palm
        ell = lambda x, sk=sk: float(np.interp(x, [sk[3] - 0.05, sk[3] + 0.15], [1.0, 0.62]))  # noqa: E731
        pos, v, u = tube(C, s, rad, seg, ell=ell, nref=np.array([0.0, 0.0, 1.0]),
                         gnarl=gnarl_field(P.get("gnarl", {}).get("arm"), 11 if side == "L" else 12))
        VMARK[side + "_arm"] = {"elbow": sk[2], "wrist": sk[3], "v0": float(v.min()), "v1": float(v.max())}
        nr = pos.shape[0]
        w = blend_weights(v, [sk[1] - 0.02, sk[2], sk[3]], [side + "_Clavicle", side + "_UpperArm", side + "_ForeArm", side + "_Wrist"],
                          [0.08, bands["elbow"], bands["wrist"]])
        # the clavicle is barely used: give the root to the upper arm and chest
        cl = w[:, 0].copy()
        w[:, 0] = 0
        w[:, 1] += cl
        parts.append(Part(side + "_arm", "arm", pos, (v - v.min()) / (v.max() - v.min()), u,
                          [side + "_Clavicle", side + "_UpperArm", side + "_ForeArm", side + "_Wrist"], np.repeat(w, pos.shape[1], 0)))
        # leg
        hp, kn, an = J[side + "_Thigh"], J[side + "_Calf"], J[side + "_Foot"]
        top = hp + np.array([0, P["leg_up"], 0])
        pts = [top, hp, kn, an]
        C, s, sk = resample(pts, step)
        a0, a1, a2 = P["leg_r"]

        def radl(x, sk=sk):
            base = float(np.interp(x, [sk[0], sk[1], 0.5 * (sk[1] + sk[2]), sk[2], 0.5 * (sk[2] + sk[3]), sk[3]],
                                   [a0 * 0.9, a0, 0.5 * (a0 + a1) * 1.02, a1, 0.5 * (a1 + a2) * 1.08, a2]))
            return base * (1 + float(P.get("knob", 0.0)) * np.exp(-((x - sk[2]) / 0.16) ** 2))
        pos, v, u = tube(C, s, radl, seg, gnarl=gnarl_field(P.get("gnarl", {}).get("leg"), 21 if side == "L" else 22))
        VMARK[side + "_leg"] = {"knee": sk[2], "ankle": sk[3], "v0": float(v.min()), "v1": float(v.max())}
        w = blend_weights(v, [sk[1], sk[2], sk[3]], ["pelvis", side + "_Thigh", side + "_Calf", side + "_Foot"],
                          [bands["hip"], bands["knee"], bands["ankle"]])
        parts.append(Part(side + "_leg", "leg", pos, (v - v.min()) / (v.max() - v.min()), u,
                          ["pelvis", side + "_Thigh", side + "_Calf", side + "_Foot"], np.repeat(w, pos.shape[1], 0)))
        # foot: heel -> ball -> toe, flattened (wide across, low)
        fw, fh, back, fwd, lift = P["foot"]
        ball, toe = J[side + "_Ball"], J[side + "_Toe_END"]
        fdir = toe - an
        fdir[1] = 0
        fdir /= np.linalg.norm(fdir)
        dy = an[1] - 0.43            # the foot sits under the ankle (the donor's ankle is 0.43 above the sole)
        heel = np.array([an[0], dy + lift + fh * 0.2, an[2]]) - fdir * back
        b2 = np.array([ball[0], dy + lift, ball[2]])
        t2 = np.array([toe[0], dy + lift * 0.8, toe[2]]) + fdir * (fwd - np.linalg.norm((toe - ball)[[0, 2]]))
        C, s, sk = resample([heel, b2, t2], step * 0.7)
        radf = lambda x, sk=sk: float(np.interp(x, [sk[0], 0.35 * sk[2], sk[1], sk[2]], [fw * 0.8, fw, fw * 0.95, fw * 0.6]))  # noqa: E731
        ellf = lambda x: fh / fw  # noqa: E731
        pos, v, u = tube(C, s, radf, max(seg - 2, 6), ell=ellf, nref=np.array([1.0, 0.0, 0.0]),
                         gnarl=gnarl_field(P.get("gnarl", {}).get("foot"), 31 if side == "L" else 32))
        w = blend_weights(v, [sk[1]], [side + "_Foot", side + "_Ball"], [0.1])
        parts.append(Part(side + "_foot", "foot", pos, (v - v.min()) / (v.max() - v.min()), u,
                          [side + "_Foot", side + "_Ball"], np.repeat(w, pos.shape[1], 0)))
    # torso: lofted ellipses along y
    sec = np.array(P["torso"], float)
    ys = np.arange(sec[0, 0], sec[-1, 0] + 1e-6, step * 0.8)
    rx, rz, zo = (np.interp(ys, sec[:, 0], sec[:, k]) for k in (1, 2, 3))
    # round the bottom and top (sections ramp to the end radii given)
    th = np.linspace(0, 2 * np.pi, seg + 1)
    gt = gnarl_field(P.get("gnarl", {}).get("torso"), 41)
    tw = np.radians(float(P.get("torso_twist", 0.0)))      # the stalk's twist, degrees over its height
    pos = []
    for y, r, q, z in zip(ys, rx, rz, zo):
        d = 1.0 + gt(y - ys[0], th)
        a = th + tw * (y - ys[0]) / max(ys[-1] - ys[0], 1e-6)
        pos.append(np.stack([r * d * np.sin(a), np.full(len(th), y), z + q * d * np.cos(a)], 1))
    pos = np.array(pos)
    tb = P["torso_bones"]
    names = [b for b, _ in tb]
    hs = np.array([h for _, h in tb])
    w = np.zeros((len(ys), len(names)))
    sig = float(P.get("torso_sigma", 0))
    for i, y in enumerate(ys):
        if sig > 0:
            # soft weights over the nearest spine bones (round 14: a sharp linear blend stretched under the donor's
            # big spine bends in skill1)
            g = np.exp(-((y - hs) / sig) ** 2)
            g[np.argsort(-g)[4:]] = 0
            w[i] = g / g.sum()
            continue
        if y <= hs[0]:
            w[i, 0] = 1
        elif y >= hs[-1]:
            w[i, -1] = 1
        else:
            k = np.searchsorted(hs, y) - 1
            t = (y - hs[k]) / (hs[k + 1] - hs[k])
            w[i, k], w[i, k + 1] = 1 - t, t
    parts.append(Part("torso", "torso", pos, (ys - ys[0]) / (ys[-1] - ys[0]), th / (2 * np.pi), names,
                      np.repeat(w, pos.shape[1], 0)))
    return parts


def assemble(parts, P):
    """Flat arrays: pos, uv (atlas, v down), tris, per-vertex 4 bone names + weights, part kind per vertex."""
    x0, y0, x1, y1 = P["rect"]
    ins = P["inset"]
    allp, alluv, allt, allb, allw, kinds = [], [], [], [], [], []
    off = 0
    for p in parts:
        nr, nc = p.pos.shape[:2]
        c0, c1 = P["cols"][p.kind]
        uu = (x0 + c0 + ins + p.u * (c1 - c0 - 2 * ins)) / 2048.0
        vv = (y0 + ins + p.v01 * (y1 - y0 - 2 * ins)) / 2048.0
        uv = np.stack(np.meshgrid(uu, vv), -1).reshape(-1, 2)
        allp.append(p.pos.reshape(-1, 3))
        alluv.append(uv)
        allt.append(grid_tris(nr, nc) + off)
        W = p.w
        order = np.argsort(-W, 1)[:, :4]
        idx = np.zeros((len(W), 4), object)
        ww = np.zeros((len(W), 4))
        for k in range(min(4, W.shape[1])):
            idx[:, k] = np.array(p.bones, object)[order[:, k]]
            ww[:, k] = W[np.arange(len(W)), order[:, k]]
        idx[ww == 0] = p.bones[0]
        allb.append(idx)
        allw.append(ww)
        kinds += [p.kind] * len(W)
        off += nr * nc
    return (np.vstack(allp), np.vstack(alluv), np.vstack(allt), np.vstack(allb), np.vstack(allw), np.array(kinds))


def smooth_normals(pos, tris):
    key = np.round(pos * 1e5).astype(np.int64)
    _u, inv = np.unique(key, axis=0, return_inverse=True)
    inv = inv.ravel()
    fn = np.cross(pos[tris[:, 1]] - pos[tris[:, 0]], pos[tris[:, 2]] - pos[tris[:, 0]])
    N = np.zeros((inv.max() + 1, 3))
    for c in range(3):
        np.add.at(N, inv[tris[:, c]], fn)
    N = N[inv]
    return N / np.maximum(np.linalg.norm(N, axis=1, keepdims=True), 1e-12)


# ---------------------------------------------------------------------------------------------------------- texture
def periodic_noise(h, w, sigma, rng):
    """Smooth noise, periodic across (u wraps around the part); sigma = (along v, across u) in texels."""
    return nd.gaussian_filter(rng.normal(0, 1, (h, w)), sigma, mode="wrap")


def paint(P):
    """(albedo rgb (h, w, 3) uint8 of the rect)."""
    x0, y0, x1, y1 = P["rect"]
    h, w = y1 - y0, x1 - x0
    rng = np.random.default_rng(int(P["seed"]))
    out = np.zeros((h, w, 3), np.float32)
    ins = P["inset"]
    for kind, (c0, c1) in P["cols"].items():
        cw = c1 - c0
        su, sv = P["sigma"][kind]
        n1 = periodic_noise(h, cw, (sv, su), rng)
        n1 /= n1.std()
        n2 = periodic_noise(h, cw, (sv * 0.35, su * 0.35), rng)
        n2 /= n2.std()
        v = np.clip((np.arange(h)[:, None] - ins) / (h - 2 * ins), 0, 1) * np.ones((1, cw))
        if kind == "torso":
            k = 1 + P["torso_var"] * (0.7 * n1 + 0.3 * n2)
            col = np.array(P["torso_rgb"], np.float32)[None, None] * k[..., None]
        elif kind == "arm":
            base, hi, dk = (np.array(P[k], np.float32) for k in ("arm_rgb", "arm_hi", "arm_dark"))
            t = np.clip(0.5 + 0.35 * n1 + 0.15 * n2, 0, 1)[..., None]
            col = np.where(t < 0.5, dk + (base - dk) * (t / 0.5), base + (hi - base) * ((t - 0.5) / 0.5))
            hv = float(P["hand_v"])
            hand = np.clip((v - hv) / 0.04, 0, 1)[..., None]
            hcol = np.array(P["hand_rgb"], np.float32) * (1 + 0.2 * n2[..., None])
            col = col * (1 - hand) + hcol * hand
        elif kind == "leg":
            dark, pale = np.array(P["leg_rgb"], np.float32), np.array(P["leg_pale"], np.float32)
            s0, s1 = P["leg_pale_share"]
            share = s0 + (s1 - s0) * v            # paler at the thigh, darker down the shin
            from scipy.stats import norm
            thr = norm.ppf(1 - np.clip(share, 1e-3, 1 - 1e-3))
            m = np.clip((n1 - thr) / 0.5 + 0.5, 0, 1)[..., None]
            col = dark * (1 + 0.15 * n2[..., None]) * (1 - m) + pale * (1 + 0.1 * n2[..., None]) * m
        else:
            col = np.array(P["foot_rgb"], np.float32)[None, None] * (1 + 0.18 * n1[..., None])
        out[:, c0:c1] = col
    return np.clip(np.round(out), 0, 255).astype(np.uint8)


def vfrac(name, key):
    m = VMARK.get(name)
    if not m:
        return None
    return (m[key] - m["v0"]) / max(m["v1"] - m["v0"], 1e-6)


def paint2(P):
    """Round 16 paint (P["paint"] == "v2"): classic's body is dark and stalk-like with SPARSE pale-blue patches (knees,
    forearms, feet), mid blue-grey arms with a few pale highlights and dark hands. Patches are placed along each part from
    the joint marks of the built geometry (VMARK), their shape from smooth periodic noise."""
    x0, y0, x1, y1 = P["rect"]
    h, w = y1 - y0, x1 - x0
    ins = P["inset"]
    rng = np.random.default_rng(int(P["seed"]) + 100)
    out = np.zeros((h, w, 3), np.float32)
    v = np.clip((np.arange(h)[:, None] - ins) / (h - 2 * ins), 0, 1)
    C = {k: np.array(P[k], np.float32) for k in ("torso_rgb", "arm_rgb", "arm_hi", "arm_dark", "hand_rgb", "leg_rgb",
                                                  "leg_pale", "foot_rgb")}

    def noise(cw, sv, su):
        n = periodic_noise(h, cw, (sv, su), rng)
        return n / n.std()

    def patch(cw, centre, width, share, sv, su):
        """mask (h, cw) of pale patches: noise above a threshold, inside a soft window around v = centre"""
        n = noise(cw, sv, su)
        win = np.exp(-((v - centre) / width) ** 2) * np.ones((1, cw))
        # one-sided: a splash on part of the circumference, not a ring around the limb
        u = (np.arange(cw)[None, :] + 0.5) / cw
        side = 0.5 * (np.cos(2 * np.pi * (u - rng.uniform())) + 1) * np.ones((h, 1))
        from scipy.stats import norm
        t = norm.ppf(1 - share)
        return np.clip((n + 1.2 * (win - 1) + 1.5 * (side - 1) - t) / 0.35, 0, 1)
    for kind, (c0, c1) in P["cols"].items():
        cw = c1 - c0
        su, sv = P["sigma"][kind]
        fib = noise(cw, sv * 2.5, max(su * 0.35, 1.0))          # fibres: long along the part, thin across
        mot = noise(cw, sv, su)
        if kind == "torso":
            col = C["torso_rgb"][None, None] * (1 + P["torso_var"] * (0.6 * fib + 0.4 * mot))[..., None]
        elif kind == "arm":
            ve, vw = vfrac("L_arm", "elbow") or 0.45, vfrac("L_arm", "wrist") or 0.8
            t = np.clip(0.5 + 0.3 * mot + 0.15 * fib, 0, 1)[..., None]
            col = C["arm_dark"] + (C["arm_rgb"] - C["arm_dark"]) * t
            pale = np.maximum(patch(cw, (ve + vw) / 2, 0.18, P.get("arm_pale_share", 0.12), sv, su),
                              patch(cw, ve, 0.06, P.get("arm_pale_share", 0.12), sv * 0.6, su))[..., None]
            col = col * (1 - pale) + C["arm_hi"] * pale
            hand = np.clip((v - vw) / 0.03, 0, 1)[..., None] * np.ones((1, cw, 1))
            col = col * (1 - hand) + C["hand_rgb"] * (1 + 0.25 * mot[..., None]) * hand
        elif kind == "leg":
            vk = vfrac("L_leg", "knee") or 0.5
            pale = np.maximum(patch(cw, vk, 0.09, P.get("leg_pale_knee", 0.35), sv * 0.7, su),
                              patch(cw, 0.93, 0.06, P.get("leg_pale_ankle", 0.2), sv * 0.6, su))[..., None]
            dark = C["leg_rgb"][None, None] * (1 + 0.35 * fib + 0.2 * mot)[..., None]
            col = dark * (1 - pale) + C["leg_pale"] * (1 + 0.1 * mot[..., None]) * pale
        else:
            pale = patch(cw, 0.5, 0.5, P.get("foot_pale", 0.08), sv, su)[..., None]
            col = C["foot_rgb"][None, None] * (1 + 0.2 * mot[..., None]) * (1 - pale) + C["leg_pale"] * pale
        out[:, c0:c1] = col
    return np.clip(np.round(out), 0, 255).astype(np.uint8)


def height_rect(P):
    """Fibre and knob height (rect size, 0 mean) for the normal map (round 16)."""
    x0, y0, x1, y1 = P["rect"]
    h, w = y1 - y0, x1 - x0
    rng = np.random.default_rng(int(P["seed"]) + 200)
    H = np.zeros((h, w), np.float32)
    for kind, (c0, c1) in P["cols"].items():
        cw = c1 - c0
        su, sv = P["sigma"][kind]
        fib = periodic_noise(h, cw, (sv * 1.5, 0.8), rng)
        knob = periodic_noise(h, cw, (sv * 0.25, su * 0.5), rng)
        H[:, c0:c1] = 0.6 * fib / fib.std() + 0.4 * knob / knob.std()
    return H


def write_textures(dst, P, cap_mask):
    x0, y0, x1, y1 = P["rect"]
    rep = {}
    rect = np.zeros((2048, 2048), bool)
    rect[y0:y1, x0:x1] = True
    assert not (rect & cap_mask).any()
    # albedo
    src = bm.tex_path(dst, "alb")
    fmt, w, h, mips = d2r_texture.read_texture(src)
    A = d2r_texture.decode(fmt, w, h, mips[0])
    A2 = A.copy()
    A2[y0:y1, x0:x1, :3] = paint2(P) if P.get("paint") == "v2" else paint(P)
    A2[y0:y1, x0:x1, 3] = 255
    ch = (A2 != A).any(-1)
    rep["alb"] = bm.write_spliced(src, fmt, w, h, bm.levels_keeping_part(A2, fmt, mips, cap_mask), mips, ch, 16)
    Image.fromarray(A2[..., :3]).save(dst / "albedo_procbody.png")
    Image.fromarray(A2[y0:y1, x0:x1, :3]).resize(((x1 - x0) * 3, (y1 - y0) * 3), Image.NEAREST).save(dst / "procbody_rect.png")
    # normal: flat (the file's flat value is 255, 128, 0, 128)
    src = bm.tex_path(dst, "nrm")
    fmt, w, h, mips = d2r_texture.read_texture(src)
    A = d2r_texture.decode(fmt, w, h, mips[0])
    A2 = A.copy()
    A2[y0:y1, x0:x1] = [255, 128, 0, 128]
    ns = float(P.get("nrm_strength", 0))
    if ns:
        # tangent-space detail from the height field: x (along u, around the part) in A, y (along v) in G (the file's
        # flat value is 255,128,0,128)
        Hh = height_rect(P)
        gy, gx = np.gradient(Hh)
        nx, ny = -ns * gx, -ns * gy
        nz = np.ones_like(nx)
        l = np.sqrt(nx ** 2 + ny ** 2 + nz ** 2)
        A2[y0:y1, x0:x1, 3] = np.clip(np.round(128 + 127 * nx / l), 0, 255).astype(np.uint8)
        A2[y0:y1, x0:x1, 1] = np.clip(np.round(128 + 127 * ny / l), 0, 255).astype(np.uint8)
    rep["nrm"] = bm.write_spliced(src, fmt, w, h, bm.levels_keeping_part(A2, fmt, mips, cap_mask), mips, (A2 != A).any(-1), 16)
    # ORM at its own size
    src = bm.tex_path(dst, "orm")
    fmt, w, h, mips = d2r_texture.read_texture(src)
    A = d2r_texture.decode(fmt, w, h, mips[0])
    k = w / 2048.0
    A2 = A.copy()
    A2[int(y0 * k):int(y1 * k), int(x0 * k):int(x1 * k)] = [255, int(P["rough"]), 0, int(P["spec"])]
    capo = np.asarray(Image.fromarray(cap_mask.astype(np.uint8)).resize((w, h), Image.NEAREST)) > 0
    rep["orm"] = bm.write_spliced(src, fmt, w, h, bm.levels_keeping_part(A2, fmt, mips, capo), mips, (A2 != A).any(-1), 16)
    # body glow mask: 0 in the rect
    msk = next(Path(dst, "overlay").rglob("*_glow_body_mask.texture"))
    fm, wm, hm, lm = d2r_texture.read_texture(msk)
    M = d2r_texture.decode(fm, wm, hm, lm[0])
    M = (M[..., 0] if M.ndim == 3 else M).copy()
    M0 = M.copy()
    M[y0:y1, x0:x1] = 0
    if (M != M0).any():
        lv = [d2r_texture.bc4_encode(x).ljust(8, b"\0") for x in d2r_texture.mip_chain(M, len(lm))]
        rep["glow"] = bm.write_spliced(msk, fm, wm, hm, lv, lm, M != M0, 8)
    return rep


# ---------------------------------------------------------------------------------------------------------- models
def write_lod(path, P, lod, cap_bone="jaw", shell_bone="loin_cloth"):
    g, tree = d2r_mesh.load_model(path)
    Wb = edit_skeleton(tree["Skeletons"][0]["Bones"], P)
    m = tree["Meshes"][0]
    vs = m["PrimaryVertexData"]["Vertices"].obj
    names = [b["BoneName"] for b in m["BoneBindings"]]
    bi = np.array([v["BoneIndices"] for v in vs])
    bw = np.array([v["BoneWeights"] for v in vs])
    main = np.array(names)[bi[np.arange(len(bi)), bw.argmax(1)]]
    cap = (main == cap_bone) & (bw.max(1) >= 254)
    shell = main == shell_bone
    keep = shell if P.get("hd_cap") else (cap | shell)
    tris = np.array([x["Int16"] for x in m["PrimaryTopology"]["Indices16"]], int).reshape(-1, 3) % 65536
    kt = keep[tris].all(1)
    remap = -np.ones(len(vs), int)
    remap[keep] = np.arange(keep.sum())
    old_t = remap[tris[kt]]
    if P.get("hd_dir"):
        # round 17: the body modelled in Blender (s4_hdbody.py), its LOD with weights
        z = np.load(Path(P["hd_dir"]) / ("body_lod%d.npz" % lod))
        pos, uv, t, bn, ww, kinds = z["pos"], z["uv"], z["tris"], z["bn"], z["ww"], z["kind"]
        nrm = z["nrm"] / np.maximum(np.linalg.norm(z["nrm"], axis=1, keepdims=True), 1e-9)
        if P.get("hd_cap"):
            # round 18: the cap modelled from scratch (s4_hdcap.py), rigid on the cap bone
            zc = np.load(Path(P["hd_dir"]) / ("cap_lod%d.npz" % lod))
            nc = len(zc["pos"])
            cn = zc["nrm"] / np.maximum(np.linalg.norm(zc["nrm"], axis=1, keepdims=True), 1e-9)
            bnc = np.full((nc, bn.shape[1]), cap_bone, dtype=bn.dtype if bn.dtype.kind == "U" and
                          bn.dtype.itemsize >= np.dtype("U%d" % len(cap_bone)).itemsize else "U32")
            wwc = np.zeros((nc, ww.shape[1]))
            wwc[:, 0] = 1
            t = np.vstack([t, zc["tris"] + len(pos)])
            pos, nrm, uv = np.vstack([pos, zc["pos"]]), np.vstack([nrm, cn]), np.vstack([uv, zc["uv"]])
            bn = np.vstack([bn.astype(bnc.dtype), bnc])
            ww = np.vstack([ww, wwc])
            kinds = np.r_[kinds.astype("U16"), np.array(["cap"] * nc)]
    else:
        seg, step = P["res"][lod]
        parts = build_body(Wb, P, int(seg), float(step))
        pos, uv, t, bn, ww, kinds = assemble(parts, P)
        nrm = smooth_normals(pos, t)
    # bones the body uses that the donor mesh does not bind (round 17: the claws on the finger bones): new bindings
    for b in sorted(set(bn.astype(str).ravel()) - set(names)):
        nbnd = dm.Obj(m["BoneBindings"][0].td, dict(m["BoneBindings"][0].f if hasattr(m["BoneBindings"][0], "f") else m["BoneBindings"][0]))
        nbnd["BoneName"] = b
        m["BoneBindings"].append(nbnd)
        names.append(b)
    bidx = np.vectorize(names.index)(bn.astype(str))
    scale = float(m["ExtendedData"].obj["VertexScale"])
    assert np.abs(pos).max() < scale, (np.abs(pos).max(), scale)
    new = d2r_mesh.encode_vertices(vs[0].td, pos, nrm, uv, t, bidx, ww, scale)
    assert new[0]["Position"][3] == vs[np.nonzero(keep)[0][0]]["Position"][3]
    kept = [v for v, k in zip(vs, keep) if k]
    m["PrimaryVertexData"]["Vertices"].obj = kept + new
    allt = np.vstack([old_t, t + len(kept)])
    nv = len(kept) + len(new)
    assert nv <= 65535
    topo = m["PrimaryTopology"]
    idx_td = topo["Indices16"][0].td
    topo["Indices16"] = [dm.Obj(idx_td, {"Int16": int(i) - 65536 if i > 32767 else int(i)}) for i in allt.reshape(-1)]
    topo["Groups"][0]["TriCount"] = len(allt)
    topo["Groups"] = topo["Groups"][:1]
    # bone boxes of the body bones (in each bone's bind space); the cap's and the shell's stay
    inv = {b["Name"]: np.array(b["InverseWorldTransform"], float).reshape(4, 4) for b in tree["Skeletons"][0]["Bones"]}
    for k, b in enumerate(m["BoneBindings"]):
        if b["BoneName"] in ((shell_bone,) if P.get("hd_cap") else (cap_bone, shell_bone)):
            continue
        sel = ((bidx == k) & (ww > 0)).any(1)
        if not sel.any():
            continue
        pts = pos[sel] @ inv[b["BoneName"]][:3, :3] + inv[b["BoneName"]][3, :3]
        b["OBBMin"] = [float(x) for x in pts.min(0)]
        b["OBBMax"] = [float(x) for x in pts.max(0)]
    # the whole mesh's box
    ed = m["ExtendedData"].obj
    ed["bbMin"] = [float(min(a, b)) for a, b in zip(ed["bbMin"], pos.min(0))]
    ed["bbMax"] = [float(max(a, b)) for a, b in zip(ed["bbMax"], pos.max(0))]
    size = d2r_mesh.write_model(g, tree, path)
    capt = int((np.asarray(kinds)[t] == "cap").all(1).sum())
    return {"vertices": nv, "kept": int(keep.sum()), "cap": int(cap.sum()), "shell": int(shell.sum()),
            "body_vertices": len(new), "body_tris": len(t) - capt, "new_cap_tris": capt, "kept_tris": len(old_t),
            "total_tris": len(allt), "bytes": size}, (pos, nrm, uv, t, bn, ww, kinds), Wb


def cmd_build(a):
    src, dst = Path(a[0]), Path(a[1])
    P = dict(DEFAULT)
    if "--params" in a:
        P.update(json.loads(Path(opt(a, "--params", "")).read_text()))
    if dst.exists():
        raise SystemExit("%s exists" % dst)
    shutil.copytree(src, dst)
    rep = {"src": str(src), "params": P, "lods": {}}
    cap_lab = bm.labels(src, "jaw", bm.ARMS.split(","), bm.LEGS.split(","), 2048, 6) == 1
    od = dst / "overlay" / FOLDER
    for lod in range(5):
        r, body, Wb = write_lod(od / ("torso_lod%d.model" % lod), P, lod)
        rep["lods"][lod] = r
        # npz: the cap from the source npz + the new body
        z = dict(np.load(src / ("skinned_lod%d.npz" % lod)))
        bones = [str(x) for x in z["bones"]]
        jb = bones.index("jaw")
        capv = (z["bone_idx"][:, 0] == jb) & (z["weights"][:, 0] > 0.99)
        if P.get("hd_cap"):
            capv[:] = False         # round 18: the new cap comes with the body arrays
        ct = z["tris"][capv[z["tris"]].all(1)]
        rm = -np.ones(len(capv), int)
        rm[capv] = np.arange(capv.sum())
        pos, nrm, uv, t, bn, ww, kinds = body
        for b in sorted(set(bn.astype(str).ravel()) - set(bones)):
            bones.append(b)
        nb = np.vectorize(bones.index)(bn.astype(str))
        out = {"pos": np.vstack([z["pos"][capv], pos]), "nrm": np.vstack([z["nrm"][capv], nrm]),
               "uv": np.vstack([z["uv"][capv], uv]), "tris": np.vstack([rm[ct], t + capv.sum()]),
               "bone_idx": np.vstack([z["bone_idx"][capv], nb]), "weights": np.vstack([z["weights"][capv], ww]),
               "bones": np.array(bones), "kind": np.r_[np.array(["cap"] * int(capv.sum())), kinds]}
        np.savez(dst / ("skinned_lod%d.npz" % lod), **out)
        print("lod", lod, json.dumps(r), flush=True)
    rep["clips"] = retarget_clips(od / "animation" / "combined.animations", P)
    # the unit's own .skeleton with the same edit (as rig_embed.py build: the unit JSON otherwise loads the donor's,
    # whose bone lengths are the donor's; which one D2R takes the inverse binds from is not checked in game)
    donor = __import__("s5_build").MONSTERS[common.TOKEN]["donor"]
    dsk = common.EV / "d2r" / "data" / "hd/character/enemy" / donor / "skeleton" / (donor + ".skeleton")
    if dsk.is_file() and "--no-unit-skeleton" not in a:
        gs, ts = d2r_mesh.load_model(dsk)
        # by name from the edited model skeleton (the .skeleton has its bones in another order)
        _gm, tm = d2r_mesh.load_model(od / "torso_lod0.model")
        mb = {b["Name"]: b for b in tm["Skeletons"][0]["Bones"]}
        for b in ts["Skeletons"][0]["Bones"]:
            if b["Name"] in mb:
                b["Transform"] = mb[b["Name"]]["Transform"]
                b["InverseWorldTransform"] = list(mb[b["Name"]]["InverseWorldTransform"])
        dest = od / (common.NAME + ".skeleton")
        d2r_mesh.write_model(gs, ts, dest)
        unit_path = dst / "overlay/hd/character/enemy" / ("mxl_m3d_%s.json" % common.NAME)
        unit = json.loads(unit_path.read_text(encoding="utf-8"))
        logical = "data/" + dest.relative_to(dst / "overlay").as_posix()
        for e in unit["entities"]:
            for c in e["components"]:
                if c["type"] == "SkeletonDefinitionComponent":
                    c["filename"] = logical
        unit["dependencies"]["skeletons"] = [{"path": logical}]
        unit_path.write_text(json.dumps(unit, separators=(",", ":")), encoding="utf-8")
        rep["unit_skeleton"] = logical
    else:
        rep["unit_skeleton"] = "donor (not found: %s)" % dsk
    if P.get("hd_cap"):
        import s4_hdcap
        rep["textures"] = s4_hdcap.write_textures(dst, P)
    elif P.get("hd_dir"):
        import s4_hdbody
        rep["textures"] = s4_hdbody.write_textures_hd(dst, P, cap_lab)
    else:
        rep["textures"] = write_textures(dst, P, cap_lab)
    rep["bind_joints"] = {n: [round(float(x), 3) for x in Wb[n][:3, 3]] for n in
                          ("L_UpperArm", "L_ForeArm", "L_Wrist", "L_Thigh", "L_Calf", "L_Foot", "R_Thigh")}
    (dst / "procbody.json").write_text(json.dumps(rep, indent=1, default=str))
    if "--report" in a:
        Path(opt(a, "--report", "")).write_text(json.dumps(rep, indent=1, default=str))
    print(json.dumps({k: v for k, v in rep.items() if k != "params"}, default=str)[:2000])


def bind_worlds(bones):
    loc = [gr2.compose(np.array(b["Transform"].position, float), np.array(b["Transform"].orientation, float),
                       np.array(b["Transform"].scale_shear, float)) for b in bones]
    W = []
    for i, b in enumerate(bones):
        p = int(b["ParentIndex"])
        W.append(loc[i] if p < 0 else W[p] @ loc[i])
    return {b["Name"]: W[i] for i, b in enumerate(bones)}


def cmd_shell(a):
    """shell <stage> [--t -1] [--drop 12] [--eps 0.1] [--up 1.0] [--shell-lod 3]: rebuild the corpse shell's body from the new body.

    The shell (s5_death.py --shell --shell-cap) is a rigid copy of the corpse on the shell bone (loin_cloth), shown in
    `dead` and at the end of `death`; its UVs point into the miniature at the top of the atlas strip. Its cap part is
    kept (the shell vertices whose texel in the old layout is a cap texel); its body part is replaced by the procedural
    body (LOD max(k, --shell-lod) resolution) skinned in the death clip's last pose (--t -1: its end with the hide-body
    drop undone; or the pose at --t seconds), pushed out along its normals by --eps, normals bent to world up by --up (as
    round 9's shell), UVs in the miniature. The miniature's copy of the body rectangle is painted with the body paint
    (torso lifted to the corpse's pale grey-blue, classic's corpse body is paler than the live one)."""
    stage = Path(a[0])
    P = dict(DEFAULT)
    P.update(json.loads((stage / "procbody.json").read_text())["params"])
    t_pose, eps, up = float(opt(a, "--t", "-1")), float(opt(a, "--eps", "0.1")), float(opt(a, "--up", "1.0"))
    slod = int(opt(a, "--shell-lod", "3"))
    F = float(json.loads((stage / "build.json").read_text()).get("strip", 0.125))
    od = stage / "overlay" / FOLDER
    cap_lab = bm.labels(stage, "jaw", bm.ARMS.split(","), bm.LEGS.split(","), 2048, 6) == 1
    _ms, gsk = gr2.load_meshes((od / "torso_lod0.model").read_bytes())
    death = gr2.load_clips((od / "animation" / "combined.animations").read_bytes(), gsk)["death"]
    # the body's last death pose: the end of `death` with the hide-body drop (s5_death --hide-body: cog --drop units
    # down) undone; the shell's model positions are that pose seen through the shell bone's own skin matrix in `dead`
    drop = float(opt(a, "--drop", "12"))
    pose = gr2.pose_at(gsk, death, death.duration if t_pose < 0 else t_pose).worlds.copy()
    if t_pose < 0:
        pose[:, 1, 3] += drop
    Mskin = {n: pose[i] @ gsk.iwt[i] for i, n in enumerate(gsk.names)}
    dead = gr2.load_clips((od / "animation" / "combined.animations").read_bytes(), gsk)["dead"]
    sbi = gsk.names.index("loin_cloth")
    S_inv = np.linalg.inv(gr2.pose_at(gsk, dead, 0.0).worlds[sbi] @ gsk.iwt[sbi])

    def to_mini(uv):
        return np.stack([(1 - F) + F * uv[:, 0] / (1 - F), F * uv[:, 1]], 1)

    rep = {"t": t_pose, "eps": eps, "up": up, "lods": {}}
    for lod in range(5):
        path = od / ("torso_lod%d.model" % lod)
        g, tree = d2r_mesh.load_model(path)
        bones = tree["Skeletons"][0]["Bones"]
        Wb = bind_worlds(bones)
        m = tree["Meshes"][0]
        vs = m["PrimaryVertexData"]["Vertices"].obj
        names = [b["BoneName"] for b in m["BoneBindings"]]
        bi = np.array([v["BoneIndices"] for v in vs])
        bw = np.array([v["BoneWeights"] for v in vs])
        main = np.array(names)[bi[np.arange(len(bi)), bw.argmax(1)]]
        shell = main == "loin_cloth"
        d = hd_gltf.decode_mesh(m)
        uvm = d["uv"]
        # old layout texel of each shell vertex (miniature -> layout -> label)
        up_ = (uvm[:, 0] - (1 - F)) / F * (1 - F)
        vp_ = uvm[:, 1] / F
        lab = cap_lab[np.clip((vp_ * 2048).astype(int), 0, 2047), np.clip((up_ * 2048).astype(int), 0, 2047)]
        tris = np.array([x["Int16"] for x in m["PrimaryTopology"]["Indices16"]], int).reshape(-1, 3) % 65536
        shell_t = shell[tris].all(1)
        capshell_t = shell_t & lab[tris].all(1)
        keepv = ~shell
        keepv[np.unique(tris[capshell_t])] = True
        remap = -np.ones(len(vs), int)
        remap[keepv] = np.arange(keepv.sum())
        kept_t = remap[tris[(~shell[tris]).all(1) | capshell_t]]
        # the new shell body
        seg, step = P["res"][max(lod, slod)]
        pos, uv, t, bn, ww, _k = assemble(build_body(Wb, P, int(seg), float(step)), P)
        Pw = np.zeros_like(pos)
        for c in range(4):
            M = np.stack([Mskin[n] for n in bn[:, c]])
            Pw += ww[:, c, None] * (np.einsum("nij,nj->ni", M[:, :3, :3], pos) + M[:, :3, 3])
        nrm = smooth_normals(Pw, t)
        Pw = Pw + eps * nrm
        Pw[:, 1] += max(0.0, float(P.get("corpse_floor", 0.02)) - Pw[:, 1].min())   # nothing under the floor
        # round 16: classic's corpse is a compact pile; pull the body in across the floor (corpse_tighten, about its own
        # centre) and stack it up (corpse_heap, height scale from the floor)
        kt, kh = float(P.get("corpse_tighten", 1.0)), float(P.get("corpse_heap", 1.0))
        if kt != 1.0 or kh != 1.0:
            cxz = Pw[:, [0, 2]].mean(0)
            Pw[:, [0, 2]] = cxz + kt * (Pw[:, [0, 2]] - cxz)
            fl = Pw[:, 1].min()
            Pw[:, 1] = fl + kh * (Pw[:, 1] - fl)
        Pw = Pw @ S_inv[:3, :3].T + S_inv[:3, 3]
        nrm = (1 - up) * nrm + up * np.array([0.0, 1.0, 0.0])
        sb = names.index("loin_cloth")
        bidx = np.zeros((len(Pw), 4), int) + sb
        wts = np.zeros((len(Pw), 4))
        wts[:, 0] = 1
        scale = float(m["ExtendedData"].obj["VertexScale"])
        assert np.abs(Pw).max() < scale
        new = d2r_mesh.encode_vertices(vs[0].td, Pw, nrm, to_mini(uv), t, bidx, wts, scale)
        kept = [v for v, k in zip(vs, keepv) if k]
        m["PrimaryVertexData"]["Vertices"].obj = kept + new
        allt = np.vstack([kept_t, t + len(kept)])
        assert len(kept) + len(new) <= 65535
        topo = m["PrimaryTopology"]
        idx_td = topo["Indices16"][0].td
        topo["Indices16"] = [dm.Obj(idx_td, {"Int16": int(i) - 65536 if i > 32767 else int(i)}) for i in allt.reshape(-1)]
        topo["Groups"][0]["TriCount"] = len(allt)
        rep["lods"][lod] = {"shell_cap_vertices": int(keepv.sum() - (~shell).sum()), "shell_body_vertices": len(new),
                            "vertices": len(kept) + len(new), "bytes": d2r_mesh.write_model(g, tree, path)}
        print(lod, rep["lods"][lod], flush=True)
    # the miniature's body rectangle
    x0, y0, x1, y1 = P["rect"]
    Pc = dict(P)
    # classic's corpse body is pale periwinkle with dark feet and hands (round 12 corpse hue: mean 134,148,193)
    Pc.update({"torso_rgb": [104, 114, 158], "torso_var": 0.3, "leg_rgb": [52, 56, 74], "leg_pale": [122, 136, 184],
               "leg_pale_share": [0.55, 0.35]})
    Pc.update(P.get("corpse", {}))
    rect = paint(Pc)
    mx0, my0 = (1 - F) * 2048 + F * x0 / (1 - F), F * y0
    mx1, my1 = (1 - F) * 2048 + F * x1 / (1 - F), F * y1
    ix0, iy0, ix1, iy1 = int(np.floor(mx0)), int(np.floor(my0)), int(np.ceil(mx1)), int(np.ceil(my1))
    src = bm.tex_path(stage, "alb")
    fmt, w, h, mips = d2r_texture.read_texture(src)
    A = d2r_texture.decode(fmt, w, h, mips[0])
    A2 = A.copy()
    A2[iy0:iy1, ix0:ix1, :3] = np.asarray(Image.fromarray(rect).resize((ix1 - ix0, iy1 - iy0), Image.BOX))
    rep["alb"] = bm.write_spliced(src, fmt, w, h, bm.levels_keeping_part(A2, fmt, mips, cap_lab), mips, (A2 != A).any(-1), 16)
    rep["mini_rect"] = [ix0, iy0, ix1, iy1]
    (stage / "procbody_shell.json").write_text(json.dumps(rep, indent=1))


def cmd_heaptint(a):
    """heaptint <stage> [--gamma 1.6] [--ramp json]: recolour the corpse heap of the donor's own shell (s5_death --shell,
    kept by `build`) toward classic's corpse: the miniature's non-cap texels (the strip at the top of the atlas) are
    mapped by luminance, (L / L99) ** gamma, onto a ramp of classic's corpse colours (dark grey, slate, steel blue, pale
    teal; round 16 measured classic's DD pixels at 27 % near-black, 10 % pale teal 128,172,179). Cap texels are kept
    byte for byte (levels_keeping_part)."""
    stage = Path(a[0])
    g = float(opt(a, "--gamma", "1.6"))
    ramp = json.loads(opt(a, "--ramp", "[[0,[10,10,12]],[0.3,[40,44,60]],[0.6,[72,98,118]],[1.0,[150,200,205]]]"))
    F = float(json.loads((stage / "build.json").read_text()).get("strip", 0.125))
    cap_lab = bm.labels(Path(opt(a, "--labels-from", str(stage))), "jaw", bm.ARMS.split(","), bm.LEGS.split(","), 2048, 6) == 1
    src = bm.tex_path(stage, "alb")
    fmt, w, h, mips = d2r_texture.read_texture(src)
    A = d2r_texture.decode(fmt, w, h, mips[0])
    x0, y1 = int(round((1 - F) * w)), int(round(F * h))
    reg = np.zeros((h, w), bool)
    reg[:y1, x0:] = True
    # a miniature texel is cap when its texel in the full layout is
    yy, xx = np.nonzero(reg)
    lx = np.clip(((xx + 0.5) / w - (1 - F)) / F * (1 - F) * w, 0, w - 1).astype(int)
    ly = np.clip((yy + 0.5) / h / F * h, 0, h - 1).astype(int)
    body = ~cap_lab[ly, lx]
    sel = (yy[body], xx[body])
    rgb = A[sel][:, :3].astype(np.float32)
    L = rgb @ np.array([0.2126, 0.7152, 0.0722], np.float32)
    t = np.clip(L / max(np.percentile(L, 99), 1.0), 0, 1) ** g
    ts = np.array([r[0] for r in ramp], np.float32)
    cs = np.array([r[1] for r in ramp], np.float32)
    new = np.stack([np.interp(t, ts, cs[:, c]) for c in range(3)], 1)
    A2 = A.copy()
    A2[sel[0], sel[1], :3] = np.clip(np.round(new), 0, 255).astype(np.uint8)
    keep = cap_lab.copy()
    keep[yy[~body], xx[~body]] = True          # the miniature's own cap texels too
    rep = {"gamma": g, "ramp": ramp, "texels": int(body.sum()),
           "alb": __import__("s4_hdbody").write_spliced_capsafe(src, fmt, w, h, bm.levels_keeping_part(A2, fmt, mips, keep),
                                                                mips, (A2 != A).any(-1), 16, keep)}
    (stage / "procbody_heaptint.json").write_text(json.dumps(rep, indent=1))
    print(json.dumps({k: rep[k] for k in ("gamma", "texels")}))


if __name__ == "__main__":
    {"build": cmd_build, "shell": cmd_shell, "heaptint": cmd_heaptint}[sys.argv[1]](sys.argv[2:])
