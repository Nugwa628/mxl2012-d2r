"""Round 17: the Glowing Fungus body designed and modelled from scratch (the cap stays the donor's, untouched).

Pipeline (every step writes into one work folder W):
  design <src stage> W [--params body.json] [--design design.json]  the design graph (nodes: centre, radius, bone
        weights, chain, kind; edges) on the skeleton edited to the body's proportions, and the free-atlas mask
  blender: hdbody_bl.py model W                                       skin modifier + subdivision -> low/high meshes
  shape W                                                             displacement (knobs, twisted ridges, fibres, cracks)
                                                                      and paint (albedo, glow, roughness) as vertex data
  blender: hdbody_bl.py bake W                                        UVs packed into the free texels, Cycles bakes
                                                                      (normal, AO, albedo, glow, roughness), LOD meshes
  weights W                                                           bone weights per LOD from the design graph
  build <src stage> <dst stage> W [--params body.json]                the stage: models (cap and corpse shell kept),
                                                                      textures spliced outside the cap, clips, skeleton
"""
import json
import shutil
import sys
from pathlib import Path

import numpy as np
from PIL import Image
from scipy import ndimage as nd
from scipy.spatial import cKDTree

import common
import s3_bodymat as bm
import s4_procbody as pb

d2r_mesh, dm, d2r_texture, gr2 = pb.d2r_mesh, pb.dm, pb.d2r_texture, pb.gr2
opt = pb.opt
FOLDER = pb.FOLDER

# ------------------------------------------------------------------------------------------------------------- design
DESIGN = {
    "step": 0.16,
    # torso stalk: [y, radius, z offset, bone weights]
    "torso": [[3.62, 0.30, 0.00, {"pelvis": 1}], [3.95, 0.50, 0.00, {"pelvis": 1}],
              [4.35, 0.50, 0.02, {"pelvis": 0.5, "spine_01": 0.5}], [4.80, 0.44, 0.04, {"spine_01": 0.5, "spine_02": 0.5}],
              [5.30, 0.52, 0.06, {"spine_02": 0.5, "chest": 0.5}], [5.80, 0.60, 0.07, {"chest": 1}],
              [6.15, 0.56, 0.05, {"chest": 1}], [6.50, 0.44, 0.03, {"chest": 0.4, "neck": 0.6}],
              [6.85, 0.40, 0.02, {"neck": 0.4, "head": 0.6}], [7.30, 0.38, 0.00, {"head": 1}]],
    # arm from the stalk: [x, y, z, radius, weights]; x > 0 is the left side (mirrored for the right)
    "arm": [[0.50, 6.10, -0.05, 0.36, {"chest": 0.6, "UpperArm": 0.4}], [1.00, 6.14, -0.10, 0.27, {"UpperArm": 1}],
            [1.55, 6.15, -0.12, 0.22, {"UpperArm": 1}], [2.00, 6.16, -0.13, 0.20, {"UpperArm": 1}],
            [2.36, 6.16, -0.15, 0.22, {"UpperArm": 0.5, "ForeArm": 0.5}], [2.80, 6.16, -0.14, 0.18, {"ForeArm": 1}],
            [3.35, 6.16, -0.12, 0.16, {"ForeArm": 1}], [3.83, 6.16, -0.10, 0.13, {"ForeArm": 0.5, "Wrist": 0.5}],
            [4.08, 6.12, -0.10, 0.19, {"Wrist": 1}], [4.28, 6.06, -0.10, 0.17, {"Wrist": 1}]],
    # claws: finger bone chains (A, B, D and the thumb) lengthened by this factor; radius root -> tip
    "fingers": ["A", "B", "D", "thumb"], "finger_len": 2.4, "finger_r": [0.075, 0.025],
    # leg: [x, y, z, radius, weights]
    "leg": [[0.40, 3.95, 0.00, 0.34, {"pelvis": 0.5, "Thigh": 0.5}], [0.48, 3.55, 0.02, 0.31, {"Thigh": 1}],
            [0.50, 3.05, 0.04, 0.27, {"Thigh": 1}], [0.50, 2.55, 0.06, 0.24, {"Thigh": 1}],
            [0.50, 2.16, 0.08, 0.26, {"Thigh": 0.5, "Calf": 0.5}], [0.50, 1.75, 0.06, 0.20, {"Calf": 1}],
            [0.50, 1.20, 0.03, 0.17, {"Calf": 1}], [0.50, 0.75, 0.02, 0.15, {"Calf": 1}],
            [0.50, 0.45, 0.01, 0.15, {"Calf": 0.5, "Foot": 0.5}]],
    # foot: heel and ball [x, y, z, radius], toes fanned from the ball (degrees about y), toe length, radius root -> tip
    "heel": [0.50, 0.20, -0.18, 0.16], "ball": [0.52, 0.14, 0.45, 0.17], "toes": [-28, 0, 26], "toe_len": 0.34,
    "toe_r": [0.08, 0.035],
    # vertical squash of the feet and palms (their skin is round)
    "foot_squash": 0.55, "palm_squash": 0.55,
}


def bones_P(src, P):
    g, tree = d2r_mesh.load_model(Path(src) / "overlay" / FOLDER / "torso_lod0.model")
    bones = tree["Skeletons"][0]["Bones"]
    Wb = pb.edit_skeleton(bones, P)
    return {n: M[:3, 3].copy() for n, M in Wb.items()}


def graph(J, D):
    """nodes: list of dict(p, r, w, chain, kind); edges: list of (i, j). Long edges are split to D['step']."""
    nodes, edges = [], []

    def add(p, r, w, chainn, kind):
        nodes.append({"p": np.asarray(p, float), "r": float(r), "w": dict(w), "chain": chainn, "kind": kind})
        return len(nodes) - 1

    def link(a, b):
        edges.append((a, b))

    torso = [add([0, y, z], r, w, "torso", "torso") for y, r, z, w in D["torso"]]
    for a, b in zip(torso, torso[1:]):
        link(a, b)
    ty = np.array([n[0] for n in D["torso"]])

    def torso_at(y):
        return torso[int(np.argmin(np.abs(ty - y)))]

    for side, sx in (("L", 1.0), ("R", -1.0)):
        def wn(w):
            return {(k if k in ("chest", "pelvis", "spine_01", "spine_02", "neck", "head") else side + "_" + k): v
                    for k, v in w.items()}
        # arm
        prev = torso_at(6.15)
        arm = []
        for x, y, z, r, w in D["arm"]:
            i = add([sx * x, y, z], r, wn(w), side + "_arm", "arm")
            link(prev, i)
            prev = i
            arm.append(i)
        palm = arm[-1]
        # claws along the finger bones, lengthened
        fl = float(D["finger_len"])
        r0, r1 = D["finger_r"]
        for f in D["fingers"]:
            names = ["%s_thumb_A_%s" % (side, k) for k in "ABC"] if f == "thumb" else \
                ["%s_finger_%s_%s" % (side, f, k) for k in "ABC"]
            pts = [J[n] for n in names]
            base = pts[0]
            # lengthen from the first joint
            P_ = [base] + [base + (q - base) * fl for q in pts[1:]]
            tip = P_[-1] + (P_[-1] - P_[-2]) * 0.9
            P_.append(tip)
            prev = palm
            for k, q in enumerate(P_):
                rr = r0 + (r1 - r0) * k / (len(P_) - 1)
                bn = names[min(k, 2)]
                i = add(q, rr * (1.1 if f == "thumb" else 1.0), {bn: 1.0}, side + "_claw_" + f, "hand")
                link(prev, i)
                prev = i
        # leg
        prev = torso_at(3.95)
        leg = []
        for x, y, z, r, w in D["leg"]:
            i = add([sx * x, y, z], r, wn(w), side + "_leg", "leg")
            link(prev, i)
            prev = i
            leg.append(i)
        ankle = leg[-1]
        hx, hy, hz, hr = D["heel"]
        heel = add([sx * hx, hy, hz], hr, {side + "_Foot": 1}, side + "_foot", "foot")
        link(ankle, heel)
        bx, by, bz, br = D["ball"]
        ball = add([sx * bx, by, bz], br, {side + "_Foot": 0.5, side + "_Ball": 0.5}, side + "_foot", "foot")
        link(ankle, ball)
        t0, t1 = D["toe_r"]
        for k, ang in enumerate(D["toes"]):
            a = np.radians(ang * sx)
            d = np.array([np.sin(a), -0.15, np.cos(a)])
            d /= np.linalg.norm(d)
            prev = ball
            for j in (1, 2):
                q = np.array([sx * bx, by, bz]) + d * float(D["toe_len"]) * j / 2
                i = add(q, t0 + (t1 - t0) * (j - 1), {side + "_Ball": 1}, "%s_toe%d" % (side, k), "foot")
                link(prev, i)
                prev = i
    # split long edges
    step = float(D["step"])
    out = []
    for a, b in edges:
        pa, pb_ = nodes[a]["p"], nodes[b]["p"]
        n = int(np.ceil(np.linalg.norm(pb_ - pa) / step))
        prev = a
        for k in range(1, n):
            t = k / n
            w = {}
            for kk, v in nodes[a]["w"].items():
                w[kk] = w.get(kk, 0) + (1 - t) * v
            for kk, v in nodes[b]["w"].items():
                w[kk] = w.get(kk, 0) + t * v
            nb_ = nodes[b] if nodes[b]["chain"] == nodes[a]["chain"] else nodes[b]
            i = add(pa + (pb_ - pa) * t, nodes[a]["r"] + (nodes[b]["r"] - nodes[a]["r"]) * t, w, nb_["chain"], nb_["kind"])
            out.append((prev, i))
            prev = i
        out.append((prev, b))
    return nodes, out


def cmd_design(a):
    src, W = Path(a[0]), Path(a[1])
    W.mkdir(parents=True, exist_ok=True)
    P = dict(pb.DEFAULT)
    if "--params" in a:
        P.update(json.loads(Path(opt(a, "--params", "")).read_text()))
    D = dict(DESIGN)
    if "--design" in a:
        D.update(json.loads(Path(opt(a, "--design", "")).read_text()))
    J = bones_P(src, P)
    nodes, edges = graph(J, D)
    out = {"design": D, "joints": {k: v.tolist() for k, v in J.items()},
           "nodes": [{"p": n["p"].tolist(), "r": n["r"], "w": n["w"], "chain": n["chain"], "kind": n["kind"]} for n in nodes],
           "edges": [list(e) for e in edges], "root": 1}
    (W / "graph.json").write_text(json.dumps(out, indent=0))
    # the atlas texels the cap uses (and the corpse miniature's strip): the body never writes there
    cap = bm.labels(src, "jaw", bm.ARMS.split(","), bm.LEGS.split(","), 2048, 6) == 1
    F = float(json.loads((src / "build.json").read_text()).get("strip", 0.125)) if (src / "build.json").is_file() else 0.125
    occ = cap.copy()
    occ[:int(np.ceil(F * 2048)) + 8, int((1 - F) * 2048) - 8:] = True
    occ = nd.binary_dilation(occ, iterations=6)
    np.save(W / "occupied.npy", occ)
    print(json.dumps({"nodes": len(nodes), "edges": len(edges), "free_texels": int((~occ).sum())}))


# -------------------------------------------------------------------------------------------------------------- fields
def _perm(seed):
    rng = np.random.default_rng(seed)
    p = rng.permutation(256)
    return np.r_[p, p]


GRAD = np.array([[1, 1, 0], [-1, 1, 0], [1, -1, 0], [-1, -1, 0], [1, 0, 1], [-1, 0, 1], [1, 0, -1], [-1, 0, -1],
                 [0, 1, 1], [0, -1, 1], [0, 1, -1], [0, -1, -1], [1, 1, 0], [-1, 1, 0], [0, -1, 1], [0, -1, -1]], float)


def perlin(P, seed=0):
    """3D gradient noise, vectorised, about -1..1."""
    perm = _perm(seed)
    P = np.asarray(P, float)
    Pi = np.floor(P).astype(int)
    f = P - Pi
    Pi &= 255
    u = f * f * f * (f * (f * 6 - 15) + 10)
    out = 0.0

    def g(ix, iy, iz, fx, fy, fz):
        h = perm[perm[perm[ix] + iy] + iz] & 15
        gr = GRAD[h]
        return gr[:, 0] * fx + gr[:, 1] * fy + gr[:, 2] * fz
    x, y, z = Pi[:, 0], Pi[:, 1], Pi[:, 2]
    fx, fy, fz = f[:, 0], f[:, 1], f[:, 2]
    n = {}
    for dx in (0, 1):
        for dy in (0, 1):
            for dz in (0, 1):
                n[dx, dy, dz] = g((x + dx) & 255, (y + dy) & 255, (z + dz) & 255, fx - dx, fy - dy, fz - dz)
    ux, uy, uz = u[:, 0], u[:, 1], u[:, 2]
    x00 = n[0, 0, 0] + ux * (n[1, 0, 0] - n[0, 0, 0])
    x10 = n[0, 1, 0] + ux * (n[1, 1, 0] - n[0, 1, 0])
    x01 = n[0, 0, 1] + ux * (n[1, 0, 1] - n[0, 0, 1])
    x11 = n[0, 1, 1] + ux * (n[1, 1, 1] - n[0, 1, 1])
    y0 = x00 + uy * (x10 - x00)
    y1 = x01 + uy * (x11 - x01)
    out = y0 + uz * (y1 - y0)
    return out


def fbm(P, oct_=4, seed=0, lac=2.0, gain=0.5):
    s, a, f = 0.0, 1.0, 1.0
    for k in range(oct_):
        s = s + a * perlin(P * f, seed + k)
        a *= gain
        f *= lac
    return s


def nearest_edges(X, G):
    """per point: edge index, t along it, distance, and the edge's chain arc length at t."""
    nodes = G["nodes"]
    Pn = np.array([n["p"] for n in nodes])
    E = np.array(G["edges"])
    A, B = Pn[E[:, 0]], Pn[E[:, 1]]
    AB = B - A
    L2 = np.maximum((AB ** 2).sum(1), 1e-12)
    best = np.full(len(X), np.inf)
    bi = np.zeros(len(X), int)
    bt = np.zeros(len(X))
    for s in range(0, len(X), 20000):
        x = X[s:s + 20000]
        t = np.clip(((x[:, None, :] - A[None]) * AB[None]).sum(-1) / L2[None], 0, 1)
        d = np.linalg.norm(x[:, None, :] - (A[None] + t[..., None] * AB[None]), axis=-1)
        k = d.argmin(1)
        bi[s:s + 20000] = k
        bt[s:s + 20000] = t[np.arange(len(x)), k]
        best[s:s + 20000] = d[np.arange(len(x)), k]
    return bi, bt, best


def edge_frames(G):
    """per edge: axis, u, w (perpendicular frame), chain arc length at its start and its length; per node: arc length."""
    nodes = G["nodes"]
    Pn = np.array([n["p"] for n in nodes])
    E = np.array(G["edges"])
    # arc length per node: walk edges in order (each edge's b comes after a)
    s = np.zeros(len(nodes))
    for a, b in E:
        if nodes[a]["chain"] == nodes[b]["chain"]:
            s[b] = s[a] + np.linalg.norm(Pn[b] - Pn[a])
        else:
            s[b] = 0.0
    ax = Pn[E[:, 1]] - Pn[E[:, 0]]
    ln = np.linalg.norm(ax, axis=1)
    ax = ax / np.maximum(ln, 1e-9)[:, None]
    up = np.array([0.0, 1.0, 0.0])
    fw = np.array([0.0, 0.0, 1.0])
    ref = np.where((np.abs(ax @ up) > 0.8)[:, None], fw, up)
    u = np.cross(ax, ref)
    u /= np.linalg.norm(u, axis=1, keepdims=True)
    w = np.cross(ax, u)
    return ax, u, w, s[E[:, 0]], ln, s


def vnormals(V, F):
    N = np.zeros_like(V)
    fn = np.cross(V[F[:, 1]] - V[F[:, 0]], V[F[:, 2]] - V[F[:, 0]])
    for k in range(3):
        np.add.at(N, F[:, k], fn)
    return N / np.maximum(np.linalg.norm(N, axis=1, keepdims=True), 1e-12)


def lin(c):
    c = np.asarray(c, float) / 255.0
    return np.where(c <= 0.04045, c / 12.92, ((c + 0.055) / 1.055) ** 2.4)


SHAPE = {
    "ridge": {"torso": [7, 0.030, 2.2], "arm": [5, 0.016, 3.0], "leg": [6, 0.018, 2.5], "hand": [0, 0, 0], "foot": [4, 0.010, 0]},
    "lump_amp": 0.035, "lump_freq": 1.6,
    "knobs": 90, "knob_r": [0.06, 0.16], "knob_h": [0.02, 0.07],
    "fibre_amp": 0.010, "fibre_around": 9.0, "fibre_along": 1.3,
    "crack_amp": 0.012, "crack_freq": 3.0,
    "fine_amp": 0.004, "fine_freq": 14.0,
}

PAINT = {
    "flesh": [17, 17, 20], "flesh_var": 0.45, "fibre_light": [34, 37, 46],
    "knob_top": [44, 48, 60],
    "arm": [64, 73, 100], "arm_dark": [30, 33, 44],
    "hand": [13, 13, 16], "claw_tip": [52, 54, 62],
    "pale": [128, 150, 208], "pale_core": [182, 202, 240],
    # patches: chain, centre (fraction of the chain or a joint name), half width (units along), facing (bind direction),
    # coverage (0..1), glow
    "patches": [["L_leg", 2.16, 0.42, [0, 0, 1], 0.75, 0.8], ["R_leg", 2.16, 0.36, [0, 0, 1], 0.6, 0.8],
                ["L_leg", 1.25, 0.35, [0.3, 0, 1], 0.5, 0.6], ["R_leg", 1.05, 0.25, [-0.3, 0, 1], 0.4, 0.5],
                ["L_arm", 3.1, 0.45, [0, -0.3, 1], 0.6, 0.7], ["R_arm", 3.0, 0.4, [0, -0.3, 1], 0.5, 0.6],
                ["L_arm", 1.7, 0.2, [0, 1, 0], 0.3, 0.4],
                ["L_foot", -1, 9, [0, 1, 0.3], 0.55, 0.6], ["R_foot", -1, 9, [0, 1, 0.3], 0.5, 0.6],
                ["L_toe", -1, 9, [0, 1, 0], 0.6, 0.6], ["R_toe", -1, 9, [0, 1, 0], 0.5, 0.6],
                ["L_hand", -1, 9, [0, 1, 0], 0.45, 0.7]],
    "rough_flesh": 0.82, "rough_pale": 0.55, "rough_claw": 0.45,
}


def fields(X, Nrm, G, sh, seed, fine):
    """displacement along the normal for points X (bind space)."""
    nodes = G["nodes"]
    E = np.array(G["edges"])
    ei, t, dist = nearest_edges(X, G)
    ax, u, w, s0, ln, _s = edge_frames(G)
    kind = np.array([nodes[E[i, 1]]["kind"] for i in range(len(E))])[ei]
    Pn = np.array([n["p"] for n in nodes])
    c = Pn[E[ei, 0]] + t[:, None] * (Pn[E[ei, 1]] - Pn[E[ei, 0]])
    d = X - c
    th = np.arctan2((d * w[ei]).sum(1), (d * u[ei]).sum(1))
    s = s0[ei] + t * ln[ei]
    chains = sorted({n["chain"] for n in nodes})
    cid = np.array([chains.index(nodes[E[i, 1]]["chain"]) for i in range(len(E))])[ei]
    rng = np.random.default_rng(seed)
    ph = rng.uniform(0, 2 * np.pi, len(chains))
    disp = np.zeros(len(X))
    # twisted ridges along each part
    for k, (n_, amp, tw) in sh["ridge"].items():
        m = kind == k
        if amp:
            disp[m] += amp * np.cos(n_ * th[m] + tw * s[m] + ph[cid[m]]) * (0.6 + 0.4 * perlin(X[m] * 0.8, seed + 3))
    # lumps
    disp += sh["lump_amp"] * fbm(X * sh["lump_freq"], 3, seed + 10)
    # knobs: sparse bumps at random surface points (not on claws)
    cand = np.nonzero(kind != "hand")[0]
    pick = rng.choice(cand, int(sh["knobs"]), replace=False)
    kc = X[pick]
    kr = rng.uniform(*sh["knob_r"], len(pick))
    kh = rng.uniform(*sh["knob_h"], len(pick))
    tree = cKDTree(kc)
    dd, ii = tree.query(X, k=4)
    disp += (kh[ii] * np.exp(-(dd / kr[ii]) ** 2)).sum(1)
    if fine:
        # fibres: noise stretched along the part (around: many, along: few)
        q = np.stack([np.cos(th) * sh["fibre_around"], np.sin(th) * sh["fibre_around"], s * sh["fibre_along"] + cid * 17.0], 1)
        fb = fbm(q, 3, seed + 20)
        disp += sh["fibre_amp"] * (1 - 2 * np.abs(fb))
        # bark cracks: thin grooves where ridged noise peaks
        cr = 1 - np.abs(fbm(X * sh["crack_freq"], 3, seed + 30))
        disp -= sh["crack_amp"] * np.clip((cr - 0.8) / 0.2, 0, 1) ** 2
        disp += sh["fine_amp"] * fbm(X * sh["fine_freq"], 2, seed + 40)
    aux = {"kind": kind, "s": s, "th": th, "chain": np.array(chains)[cid], "fib": fb if fine else None,
           "knob": (kh[ii] * np.exp(-(dd / kr[ii]) ** 2)).sum(1), "ei": ei, "t": t}
    return disp, aux


def paint_vertices(X, N, aux, G, pt, seed):
    """linear albedo (n,3), glow (n,), roughness (n,) on the high mesh."""
    rng = np.random.default_rng(seed + 50)
    kind, s, chain = aux["kind"], aux["s"], aux["chain"]
    mot = fbm(X * 2.2, 3, seed + 60)
    col = np.array(pt["flesh"], float)[None] * (1 + pt["flesh_var"] * mot)[:, None]
    fib = aux["fib"] if aux["fib"] is not None else np.zeros(len(X))
    fl = np.clip((fib - float(pt.get("fibre_lo", 0.2))) / float(pt.get("fibre_span", 0.6)), 0, 1)[:, None]
    col = col * (1 - 0.6 * fl) + np.array(pt["fibre_light"], float) * 0.6 * fl
    kn = np.clip((aux["knob"] - float(pt.get("knob_lo", 0.0))) / float(pt.get("knob_span", 0.05)), 0, 1)[:, None]
    col = col * (1 - 0.5 * kn) + np.array(pt["knob_top"], float) * 0.5 * kn
    arm = (kind == "arm")
    t = np.clip(0.5 + 0.45 * fbm(X * 3.0, 3, seed + 70), 0, 1)[:, None]
    acol = np.array(pt["arm_dark"], float) + (np.array(pt["arm"], float) - np.array(pt["arm_dark"], float)) * t
    # the shoulder end of the arm fades into the dark stalk
    fade = np.clip((np.abs(X[:, 0]) - 0.6) / 0.5, 0, 1)[:, None]
    col[arm] = col[arm] * (1 - fade[arm]) + acol[arm] * fade[arm]
    hand = kind == "hand"
    col[hand] = np.array(pt["hand"], float) * (1 + 0.3 * mot[hand, None])
    # claw tips a little lighter
    glow = np.zeros(len(X))
    pale = np.zeros(len(X))
    joints = {k: np.array(v) for k, v in G["joints"].items()}
    for ch, centre, half, face, cov, gl in pt["patches"]:
        if ch.endswith("_hand"):
            m = (kind == "hand") & (np.sign(X[:, 0]) == (1 if ch[0] == "L" else -1))
            # the back of the hand: the palm part, not the claws
            m &= np.abs(X[:, 0]) < 4.35
        elif ch.endswith("_toe"):
            m = np.char.startswith(chain.astype(str), ch)
        else:
            m = chain == ch
        if not m.any():
            continue
        if centre >= 0:
            # centre given as a height (legs) or |x| (arms) in bind space
            coord = X[:, 1] if "leg" in ch else np.abs(X[:, 0])
            win = np.exp(-((coord - centre) / half) ** 2)
        else:
            win = np.ones(len(X))
        f = np.array(face, float)
        f /= np.linalg.norm(f)
        side = np.clip((N @ f + 0.2) / 0.8, 0, 1)
        nz = fbm(X * float(pt.get("patch_freq", 3.5)), 3, seed + 80 + len(ch))
        thr = 1.0 - 2.0 * cov
        p = np.clip((nz * 1.4 + win - 1 + side - 1 - thr) / 0.25, 0, 1) * m
        pale = np.maximum(pale, p)
        glow = np.maximum(glow, p * gl)
    core = np.clip((pale - 0.6) / 0.4, 0, 1)[:, None]
    pc = np.array(pt["pale"], float) * (1 - core) + np.array(pt["pale_core"], float) * core
    pc = pc * (1 + 0.12 * mot[:, None])
    col = col * (1 - pale[:, None]) + pc * pale[:, None]
    rough = np.full(len(X), pt["rough_flesh"]) * (1 - pale) + pt["rough_pale"] * pale
    rough[hand] = pt["rough_claw"]
    col = np.clip(col, 0, 255)
    return lin(col), np.clip(glow, 0, 1), np.clip(rough, 0, 1)


def cmd_shape(a):
    W = Path(a[0])
    G = json.loads((W / "graph.json").read_text())
    sh = dict(SHAPE)
    pt = dict(PAINT)
    if "--shape" in a:
        sh.update(json.loads(Path(opt(a, "--shape", "")).read_text()))
    if "--paint" in a:
        pt.update(json.loads(Path(opt(a, "--paint", "")).read_text()))
    seed = int(opt(a, "--seed", "17"))
    D = G["design"]
    out = {}
    for which in ("low", "high"):
        z = np.load(W / ("%s_base.npz" % which))
        V, F = z["V"].astype(float), z["T"]
        # flatten the feet and palms (the skin modifier makes them round)
        ei, t, _d = nearest_edges(V, G)
        E = np.array(G["edges"])
        nodes = G["nodes"]
        Pn = np.array([n["p"] for n in nodes])
        kinds = np.array([nodes[E[i, 1]]["kind"] for i in range(len(E))])[ei]
        c = Pn[E[ei, 0]] + t[:, None] * (Pn[E[ei, 1]] - Pn[E[ei, 0]])
        foot = kinds == "foot"
        V[foot, 1] = c[foot, 1] + (V[foot, 1] - c[foot, 1]) * float(D["foot_squash"])
        V[foot, 1] = np.maximum(V[foot, 1], 0.0)
        palm = (kinds == "arm") & (np.abs(V[:, 0]) > 3.95)
        V[palm, 1] = c[palm, 1] + (V[palm, 1] - c[palm, 1]) * float(D["palm_squash"])
        N = vnormals(V, F)
        disp, aux = fields(V, N, G, sh, seed, fine=(which == "high"))
        V2 = V + N * disp[:, None]
        V2[:, 1] = np.maximum(V2[:, 1], 0.0)
        out[which] = {"V": V2.astype(np.float32)}
        if which == "high":
            N2 = vnormals(V2, F)
            col, glow, rough = paint_vertices(V2, N2, aux, G, pt, seed)
            out[which].update({"col": col.astype(np.float32), "glow": glow.astype(np.float32),
                               "rough": rough.astype(np.float32)})
        np.savez(W / ("%s_shaped.npz" % which), **out[which])
        print(which, len(V), "disp range %.3f..%.3f" % (disp.min(), disp.max()), flush=True)


# ------------------------------------------------------------------------------------------------------------ weights
def cmd_weights(a):
    """bone weights of each LOD mesh (W/lod{k}.npz -> W/body_lod{k}.npz): along the nearest design edge, the two nodes'
    weights mixed by the position along it, smoothed over the welded mesh, the 4 largest kept."""
    W = Path(a[0])
    G = json.loads((W / "graph.json").read_text())
    nodes = G["nodes"]
    E = np.array(G["edges"])
    bones = sorted({b for n in nodes for b in n["w"]})
    Wn = np.zeros((len(nodes), len(bones)))
    for i, n in enumerate(nodes):
        for b, v in n["w"].items():
            Wn[i, bones.index(b)] = v
    Wn /= Wn.sum(1, keepdims=True)
    it = int(opt(a, "--smooth", "3"))
    for k in range(5):
        f = W / ("lod%d.npz" % k)
        if not f.is_file():
            break
        z = np.load(f)
        pos, tris = z["pos"], z["tris"]
        ei, t, _d = nearest_edges(pos, G)
        w = (1 - t)[:, None] * Wn[E[ei, 0]] + t[:, None] * Wn[E[ei, 1]]
        kind = np.array([nodes[E[i, 1]]["kind"] for i in range(len(E))])[ei]
        kind = np.where(kind == "hand", "arm", kind)
        # weld (UV seams split vertices) and smooth over edges
        _u, weld = np.unique(np.round(pos, 5), axis=0, return_inverse=True)
        weld = weld.ravel()
        nw = weld.max() + 1
        ww = np.zeros((nw, len(bones)))
        np.add.at(ww, weld, w)
        cnt = np.bincount(weld, minlength=nw)[:, None]
        ww /= cnt
        tw = weld[tris]
        ed = np.vstack([tw[:, [0, 1]], tw[:, [1, 2]], tw[:, [2, 0]]])
        for _ in range(it):
            acc = np.zeros_like(ww)
            deg = np.zeros(nw)
            np.add.at(acc, ed[:, 0], ww[ed[:, 1]])
            np.add.at(acc, ed[:, 1], ww[ed[:, 0]])
            np.add.at(deg, ed[:, 0], 1)
            np.add.at(deg, ed[:, 1], 1)
            ww = 0.5 * ww + 0.5 * acc / np.maximum(deg, 1)[:, None]
        w = ww[weld]
        top = np.argsort(-w, 1)[:, :4]
        tw4 = np.take_along_axis(w, top, 1)
        tw4[tw4 < float(opt(a, "--min-w", "0.02"))] = 0
        tw4 /= tw4.sum(1, keepdims=True)
        bn = np.array(bones)[top]
        np.savez(W / ("body_lod%d.npz" % k), pos=pos, nrm=z["nrm"], uv=z["uv"], tris=tris, bn=bn, ww=tw4, kind=kind)
        print("weights lod", k, len(pos), flush=True)


# ----------------------------------------------------------------------------------------------------------- textures
def write_spliced_capsafe(path, fmt, w, h, new_levels, old_levels, changed, bpb, cap):
    """bm.write_spliced, but a compressed block whose footprint touches a cap texel keeps the old file's bytes at
    every mip (round 17: the body's islands sit between the cap's, so coarse blocks mix both; re-encoding them moved
    cap texels). The body's texels in such blocks keep the old content at that mip."""
    out, kept, new = [], 0, 0
    for m, (nl, ol) in enumerate(zip(new_levels, old_levels)):
        wm, hm = max(1, w >> m), max(1, h >> m)
        bw, bh = max(1, (wm + 3) // 4), max(1, (hm + 3) // 4)
        if len(nl) != len(ol) or len(nl) < bw * bh * bpb or h % bh or w % bw:
            out.append(ol)
            kept += bw * bh
            continue
        ch = bm.block_any(changed, bh, bw).ravel() & ~bm.block_any(cap, bh, bw).ravel()
        A = np.frombuffer(nl, np.uint8)[:bw * bh * bpb].reshape(-1, bpb).copy()
        B = np.frombuffer(ol, np.uint8)[:bw * bh * bpb].reshape(-1, bpb)
        A[~ch] = B[~ch]
        kept += int((~ch).sum())
        new += int(ch.sum())
        out.append(A.tobytes() + ol[bw * bh * bpb:])
    d2r_texture.write_texture(path, fmt, w, h, out)
    return {"blocks_kept": kept, "blocks_new": new}


def write_textures_hd(dst, P, cap_mask):
    """splice the bakes into the stage's textures on the body's texels only (never on the cap's)."""
    W = Path(P["hd_dir"])
    body = np.load(W / "body_texels.npy")
    body = nd.binary_dilation(body, iterations=2) & ~cap_mask
    assert not (body & cap_mask).any()
    rep = {"body_texels": int(body.sum())}

    def png(name):
        return np.asarray(Image.open(W / ("bake_%s.png" % name)).convert("RGB"))

    def splice(kind, fn, mask):
        src = bm.tex_path(dst, kind) if kind in ("alb", "nrm", "orm") else \
            sorted(Path(dst, "overlay").rglob("*_%s.texture" % kind))[0]
        fmt, w, h, mips = d2r_texture.read_texture(src)
        A = d2r_texture.decode(fmt, w, h, mips[0])
        bc4 = fmt == d2r_texture.FMT_BC4
        if bc4 and A.ndim == 3:
            A = A[..., 0]
        A2 = A.copy()
        m = mask if mask.shape == (h, w) else np.asarray(Image.fromarray(mask.astype(np.uint8) * 255).resize((w, h), Image.BOX)) > 127
        fn(A2, m, (w, h))
        cm = cap_mask if cap_mask.shape == (h, w) else \
            np.asarray(Image.fromarray(cap_mask.astype(np.uint8) * 255).resize((w, h), Image.BOX)) > 0
        A2[cm] = A[cm]
        ch = (A2 != A).reshape(h, w, -1).any(-1)
        if bc4:
            rep[kind] = write_spliced_capsafe(src, fmt, w, h, bm.levels_keeping_part(A2, fmt, mips, cm, kind="BC4"), mips,
                                              ch, 8, cm)
        else:
            rep[kind] = write_spliced_capsafe(src, fmt, w, h, bm.levels_keeping_part(A2, fmt, mips, cm), mips, ch, 16, cm)
        return A2

    alb = png("alb")

    def f_alb(A2, m, wh):
        A2[m, :3] = alb[m]
        A2[m, 3] = 255
    splice("alb", f_alb, body)
    nb = png("nrm").astype(int)

    def f_nrm(A2, m, wh):
        # Blender bakes OpenGL tangent normals (y up the image); the game's y runs down the image (v down): flip G
        A2[m, 0] = 255
        A2[m, 1] = 255 - nb[m, 1]
        A2[m, 2] = 0
        A2[m, 3] = nb[m, 0]
    splice("nrm", f_nrm, body)
    ao = png("ao")[..., 0]
    aux = png("aux")

    def f_orm(A2, m, wh):
        def half(x):
            return np.asarray(Image.fromarray(x.astype(np.uint8)).resize(wh, Image.BOX))
        A2[m, 0] = half(ao)[m]
        A2[m, 1] = half(aux[..., 1])[m]
        A2[m, 2] = 0
        A2[m, 3] = int(P.get("hd_spec", 12))
    splice("orm", f_orm, body)
    glow = aux[..., 0].astype(float) * float(P.get("hd_glow", 1.0))

    def f_glow(A2, m, wh):
        if A2.ndim == 2:
            A2[m] = np.clip(glow[m], 0, 255).astype(A2.dtype)
        else:
            A2[m, :] = np.clip(glow[m], 0, 255).astype(A2.dtype)[:, None]
    try:
        splice("glow_body_mask", f_glow, body)
    except Exception as e:  # noqa: BLE001
        rep["glow_body_mask"] = "not written: %s" % e
    return rep


def cmd_build(a):
    """build <src stage> <dst stage> W [--params body.json]: s4_procbody's build with the hd body and bakes."""
    src, dst, W = a[0], a[1], Path(a[2])
    P = json.loads(Path(opt(a, "--params", "")).read_text()) if "--params" in a else {}
    P["hd_dir"] = str(W)
    pp = W / "build_params.json"
    pp.write_text(json.dumps(P))
    pb.cmd_build([src, dst, "--params", str(pp)])


if __name__ == "__main__":
    {"design": cmd_design, "shape": cmd_shape, "weights": cmd_weights, "build": cmd_build}[sys.argv[1]](sys.argv[2:])
