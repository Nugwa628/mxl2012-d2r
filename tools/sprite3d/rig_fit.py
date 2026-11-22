#!/usr/bin/env python
"""Rig a generated, posed character mesh to a D2R skeleton: proximity skin weights + "unposing" into the skeleton's bind pose.

  rig_fit.py <mesh_lods.npz> <profile: wolf|goatman1|bear|hellbovine|mummy1> <out.npz> [--skeleton file.skeleton] [--png prefix]

<mesh_lods.npz> is the Wereowl set (pos/nrm/uv/tris and the _1.._4 level-of-detail suffixes; y up, faces +z, a standing figure
with its arms spread). The mesh is not in the skeleton's bind pose (the arms are horizontal at shoulder height of a chunky body, the
legs are short), so the method is:

1. POSED joints: a table of where the joints of a generic biped sit in this mesh (`POSED`, hand-placed from front/side views).
2. Every vertex gets weights over the bone segments of that posed skeleton by distance (capsule radii per role, top 4,
   smoothed over the mesh edges).
3. Per role the vertex is carried from the posed joint to the matching bone of the target skeleton:
   v' = B_j + R_j (v - P_j) / u   with the bone's bind position B_j, a minimal rotation R_j that turns the posed segment
   direction into the bind direction (arms down, digitigrade legs), and u, the unit scale the unit JSON applies, so that the
   mesh keeps its size in game (u < 1 shrinks the unit and enlarges the mesh in bind space).
4. The result (positions/normals in the skeleton's bind space, `bone_idx` (N,4), `weights`, `bones` names) is what
   `d2r_mesh.replace_with_mesh` writes.

Profiles map the generic roles to the skeleton's bone names. Only the roles with weights end up in `bones`. Optional profile
fields: `k` (the mesh is scaled by k first), `dz` (and moved by it along z), `posed` (joint roles of the mesh that replace the
POSED table), `skip` (roles the skeleton has no bone for: the weight chains bridge them), `leg_snap` (False: the leg joints stay
where `posed` puts them instead of at the scaled bind skeleton), `keep` ({axis: roles} carried without travel along that axis),
`stretch` (True: each segment is also scaled along its length by bind length / posed length, clipped to `smin` .. `smax`, with
`girth` the exponent that shares that scale across the other two axes), `rscale` ({role: factor} extra uniform scale per role).
A `posed` key with a side (`R_thigh`) places that side on its own instead of mirroring: a mesh generated from one sprite
view stands in the sprite's stance, not in a symmetric one.
The capsule weights are the fallback; the Druid form uses Blender bone heat weights made from this fit (owl_refit.py, owl_weights.py).

Lane rigaudit (docs/rigging.md): this carry squeezes a mesh into the donor's proportions and its capsule weights cross gaps
(a hand next to a thigh); monster3d/rig_embed.py embeds the skeleton in the mesh instead (medial joints, geodesic voxel
weights, bind in place, retargeted clips). carry_maps / uncarry expose the carry so that rig_audit.py can recover the
generated mesh from a stage built here.
"""
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))
import skel_info  # noqa: E402

# posed joints of the Wereowl mesh (game units of the mesh, x = character left/right, +z front). `L_`/`R_` are mirrored: R is -x
POSED = {
    "pelvis": (0, 2.35, -0.45), "spine_a": (0, 2.7, -0.45), "spine_b": (0, 3.15, -0.45), "chest": (0, 3.6, -0.4),
    "neck": (0, 4.0, -0.35), "head": (0, 4.35, -0.3), "head_end": (0, 6.0, -0.3),
    "clav": (0.25, 3.75, -0.4), "upperarm": (1.1, 3.55, -0.35), "forearm": (2.7, 3.2, -0.3), "hand": (4.0, 3.0, -0.3),
    "hand_end": (4.6, 2.9, -0.3),
    "thigh": (1.05, 2.3, -0.3), "calf": (1.1, 1.4, -0.05), "ankle": (1.1, 0.85, -0.1), "foot": (1.1, 0.4, -0.1),
    "toe": (1.2, 0.15, 0.4), "toe_end": (1.25, 0.05, 0.9),
}
SIDED = {"clav", "upperarm", "forearm", "hand", "hand_end", "thigh", "calf", "ankle", "foot", "toe", "toe_end"}
# weight chains per limb (a skipped role is bridged) and the capsule radius of a segment by its start role
LIMBS = [("pelvis", "spine_a", "spine_b", "chest", "neck", "head", "head_end"),
         ("clav", "upperarm", "forearm", "hand", "hand_end"),
         ("thigh", "calf", "ankle", "foot", "toe", "toe_end")]
RADIUS = {"pelvis": 1.3, "spine_a": 1.3, "spine_b": 1.3, "chest": 1.2, "neck": 1.2, "head": 1.9, "clav": 0.6, "upperarm": 0.6,
          "forearm": 0.55, "hand": 0.5, "thigh": 0.6, "calf": 0.5, "ankle": 0.5, "foot": 0.5, "toe": 0.4}
LEG_ROLES = {"thigh", "calf", "ankle", "foot", "toe"}
ENDS = {"head_end", "hand_end", "toe_end"}
NO_ROT = {"pelvis", "neck", "head", "hand", "foot", "toe", "ankle"}  # rigid: carried by the parent's turn, no own unposing

PROFILES = {
    "wolf": dict(u=0.55, bones={
        "pelvis": "pelvis", "spine_a": "C_spine1", "spine_b": "C_spine2", "chest": "C_chest", "neck": "C_NeckHead_neck1",
        "head": "C_NeckHead_head", "clav": "{S}_Clavicle", "upperarm": "{S}_UpperArm", "forearm": "{S}_ForeArm",
        "hand": "{S}_Wrist", "thigh": "{S}_Thigh", "calf": "{S}_Calf", "ankle": "{S}_Ankle", "foot": "{S}_Foot",
        "toe": "{S}_Ball"}),
    "goatman1": dict(u=0.75, bones={
        "pelvis": "pelvis_bind_jnt", "spine_a": "spine_01_bind_jnt", "spine_b": "spine_02_bind_jnt",
        "chest": "spine_04_bind_jnt", "neck": "neck_bind_jnt", "head": "head_bind_jnt", "clav": "{S}_shoulder_bind_jnt",
        "upperarm": "{S}_upr_arm_bind_jnt", "forearm": "{S}_lwr_arm_bind_jnt", "hand": "{S}_hand_bind_jnt",
        "thigh": "{S}_leg_01_bind_jnt", "calf": "{S}_leg_02_bind_jnt", "ankle": "{S}_leg_03_bind_jnt",
        "foot": "{S}_leg_04_bind_jnt", "toe": "{S}_leg_05_bind_jnt"}),
    # D2R's werebear (enemy/bear, 93 bones): a T-pose, upright biped (hip 4.2, shoulders 7.2, head top 8.5, arm span 13.6). The bear
    # has no ankle: the owl's ankle takes the bear's foot bone, its toe the ball (`skip` bridges the foot role).
    # k scales the mesh to about the bear's height, `posed` moves joint roles of the mesh to where the owl's own parts are (the head
    # joint to the middle of the big head), `keep_x` carries those roles without sideways travel (the owl stands wider than the bear).
    "bear": dict(u=1.0, k=1.25, dz=0.6, skip={"foot"}, leg_snap=False,
                 keep={"x": {"thigh", "calf", "ankle", "toe"}, "z": {"pelvis", "spine_a", "spine_b", "chest", "neck", "head", "clav",
                                                                     "upperarm", "forearm", "hand", "thigh", "calf", "ankle", "toe"}},
                 posed={"pelvis": (0, 2.9, -0.45), "spine_a": (0, 3.3, -0.45), "spine_b": (0, 3.8, -0.45), "chest": (0, 4.4, -0.4),
                        "neck": (0, 4.9, -0.35), "head": (0, 5.7, -0.3), "head_end": (0, 6.7, -0.3), "thigh": (1.05, 2.3, -0.3),
                        "calf": (1.1, 1.4, -0.05), "ankle": (1.1, 0.5, -0.45), "toe": (1.2, 0.15, 0.4)},
                 bones={"pelvis": "pelvis", "spine_a": "C_Spine_spine1", "spine_b": "C_Spine_spine2", "chest": "chest",
                        "neck": "C_Neck_neck1", "head": "head", "clav": "{S}_Clavicle_Clavicle", "upperarm": "{S}_Arm_UpperArm",
                        "forearm": "{S}_Arm_ForeArm", "hand": "{S}_Arm_Wrist", "thigh": "{S}_Leg_Thigh", "calf": "{S}_Leg_Calf",
                        "ankle": "{S}_Leg_Foot", "toe": "{S}_Leg_Ball"}),
    # D2R's Hell Bovine (enemy/hellbovine, 97 bones): an A-pose, upright biped with two-handed polearm clips (hip 4.4, shoulders
    # 8.1, head joint 9.5, hands at 5.4); no toe bone. The posed joints are the Hardliner mesh of lane hdtools-monster3d (TripoSG,
    # seed 1, scaled to 9 units): it stands in the sprite's stance, right arm stretched out, right leg bent back, left thigh
    # forward, the trunk 0.45 to its left of the box centre. The segments are stretched to the Bovine's lengths (its trunk and
    # upper arms are longer), u is the unit scale that brings the result back to the Hardliner's height.
    "hellbovine": dict(u=0.8, k=1.0, leg_snap=False, skip={"toe"}, stretch=True, girth=0.35, smin=0.7, smax=1.6,
                       posed={"pelvis": (0.45, 4.1, 0.0), "spine_a": (0.45, 4.4, 0.0), "spine_b": (0.45, 5.0, 0.0),
                              "chest": (0.45, 5.7, 0.0), "neck": (0.4, 6.6, 0.0), "head": (0.4, 7.2, 0.1),
                              "head_end": (0.4, 8.2, 0.1),
                              "R_clav": (0.0, 6.4, 0.0), "R_upperarm": (-0.7, 6.3, 0.0), "R_forearm": (-1.7, 6.0, 0.2),
                              "R_hand": (-2.5, 5.9, 0.3), "R_hand_end": (-3.0, 5.9, 0.4),
                              "L_clav": (0.9, 6.4, 0.0), "L_upperarm": (1.6, 6.3, 0.0), "L_forearm": (2.05, 5.2, 0.1),
                              "L_hand": (2.35, 3.9, 0.0), "L_hand_end": (2.4, 3.3, 0.0),
                              "L_thigh": (0.9, 3.7, 0.2), "L_calf": (0.9, 2.8, 1.6), "L_ankle": (0.9, 0.8, 1.15),
                              "L_foot": (0.9, 0.35, 1.2), "L_toe_end": (0.9, 0.1, 1.9),
                              "R_thigh": (-0.5, 3.7, 0.0), "R_calf": (-1.0, 2.8, -0.8), "R_ankle": (-0.9, 2.1, -1.5),
                              "R_foot": (-0.9, 2.0, -1.7), "R_toe_end": (-0.9, 1.9, -1.9)},
                       bones={"pelvis": "pelvis_bind_jnt", "spine_a": "spine_01_bind_jnt", "spine_b": "spine_02_bind_jnt",
                              "chest": "spine_04_bind_jnt", "neck": "neck_bind_jnt", "head": "head_bind_jnt",
                              "clav": "{S}_shoulder_bind_jnt", "upperarm": "{S}_upr_arm_bind_jnt",
                              "forearm": "{S}_lwr_arm_bind_jnt", "hand": "{S}_hand_bind_jnt", "thigh": "{S}_leg_01_bind_jnt",
                              "calf": "{S}_leg_02_bind_jnt", "ankle": "{S}_leg_03_bind_jnt", "foot": "{S}_leg_04_bind_jnt"}),
    # D2R's Dried Corpse (enemy/mummy1, 82 bones): a T-pose, upright human biped without weapon (hip 4.2, shoulders 6.2, head
    # joint 6.8, arm span 6); no ankle bone: the ankle role takes its Foot bone, the toe its Ball (`skip` bridges the foot role).
    # The posed joints are the Glowing Fungus mesh of lane hdtools-monster3d (TripoSG, front view, seed 42, scaled to 9.2
    # units): it squats with both knees forward, the right foot ahead, the trunk leaning forward from a pelvis 0.8 behind the
    # box centre, the arms hanging with the elbows back. The cap is not posed: monster3d/s5_build.py binds it to the head alone.
    "mummy1": dict(u=0.9, k=1.0, leg_snap=False, skip={"foot"}, stretch=True, girth=0.35, smin=0.7, smax=1.6,
                   posed={"pelvis": (0, 3.86, -0.83), "spine_a": (0, 4.32, -1.0), "spine_b": (0, 4.88, -0.92),
                          "chest": (0, 5.52, -0.55), "neck": (0, 6.26, 0.18), "head": (0, 6.72, 0.83), "head_end": (0, 7.54, 1.47),
                          "L_clav": (0.74, 5.89, -0.46), "L_upperarm": (1.75, 5.89, -0.74), "L_forearm": (2.02, 4.42, -1.01),
                          "L_hand": (1.84, 2.76, 0.0), "L_hand_end": (1.81, 1.93, -0.37),
                          "R_clav": (-0.74, 5.89, -0.46), "R_upperarm": (-1.66, 5.89, -0.83), "R_forearm": (-1.84, 4.51, -1.29),
                          "R_hand": (-1.98, 3.04, 0.32), "R_hand_end": (-1.97, 2.39, 0.0),
                          "L_thigh": (0.92, 3.86, -0.83), "L_calf": (1.47, 2.21, 0.37), "L_ankle": (1.29, 0.55, -0.55),
                          "L_toe": (1.47, 0.14, 0.28), "L_toe_end": (1.47, 0.09, 0.64),
                          "R_thigh": (-0.92, 3.86, -0.74), "R_calf": (-1.10, 2.39, 0.92), "R_ankle": (-1.10, 0.64, 0.28),
                          "R_toe": (-1.20, 0.18, 1.29), "R_toe_end": (-1.20, 0.14, 1.66)},
                   bones={"pelvis": "pelvis", "spine_a": "spine_01", "spine_b": "spine_02", "chest": "chest", "neck": "neck",
                          "head": "head", "clav": "{S}_Clavicle", "upperarm": "{S}_UpperArm", "forearm": "{S}_ForeArm",
                          "hand": "{S}_Wrist", "thigh": "{S}_Thigh", "calf": "{S}_Calf", "ankle": "{S}_Foot", "toe": "{S}_Ball"}),
}


def rot_between(a, b):
    """Minimal rotation matrix (column vectors) taking direction a to direction b."""
    a, b = a / np.linalg.norm(a), b / np.linalg.norm(b)
    v = np.cross(a, b)
    c = float(a @ b)
    if c < -0.9999:
        return -np.eye(3)
    k = np.array([[0, -v[2], v[1]], [v[2], 0, -v[0]], [-v[1], v[0], 0]])
    return np.eye(3) + k + k @ k / (1 + c)


def instances(profile, bones):
    """(posed role key, side) -> (posed point, bind point, bone name, carry point). Role keys are 'pelvis' or 'L_thigh'.
    The carry point is where the role's vertices are measured from (the posed point, but for `keep_x` roles with the bind x)."""
    byname = {b["name"]: b for b in bones}
    posed = dict(POSED, **profile.get("posed", {}))
    k, skip, keep = profile.get("k", 1.0), profile.get("skip", ()), profile.get("keep", {})
    out = {}
    for role, p in posed.items():
        if role in skip or role[:2] in ("R_", "L_"):
            continue
        for side in ("R", "L") if role in SIDED else (None,):
            key = role if side is None else "%s_%s" % (side, role)
            own = side is not None and key in posed
            p3 = np.array(posed[key] if own else p, float) * k
            p3[2] += profile.get("dz", 0.0)
            if side == "R" and not own:
                p3[0] = -p3[0]
            if role in ENDS:  # a posed end point only shapes the capsule; no bone
                out[key] = (p3, None, None, p3)
                continue
            name = profile["bones"][role].replace("{S}", side or "")
            if name not in byname:
                raise KeyError("%s: no bone %s" % (role, name))
            b3 = np.array(byname[name]["pos"], float)
            if role in LEG_ROLES and profile.get("leg_snap", True):  # the posed leg joints sit where the scaled bind skeleton has them (feet on the ground)
                p3[1:] = b3[1:] * profile["u"]
            c3 = p3.copy()
            for ax, roles in keep.items():  # carried without travel along that axis
                if role in roles:
                    c3["xyz".index(ax)] = b3["xyz".index(ax)] * profile["u"]
            out[key] = (p3, b3, name, c3)
    return out


def segments(inst, profile=None):
    skip = (profile or {}).get("skip", ())
    segs = []
    for limb in LIMBS:
        roles = [r for r in limb if r not in skip]
        for a, b in zip(roles, roles[1:]):
            for side in ("R", "L") if a in SIDED else (None,):
                ka = a if side is None else "%s_%s" % (side, a)
                kb = b if side is None else "%s_%s" % (side, b)
                if ka in inst and kb in inst:
                    segs.append((ka, kb, RADIUS[a]))
    return segs


def seg_dist(P, a, b):
    ab = b - a
    t = np.clip(((P - a) @ ab) / (ab @ ab), 0, 1)
    return np.linalg.norm(P - (a + t[:, None] * ab), axis=1)


def smooth(w, tris, it=4):
    """Average every vertex's weights with its edge neighbours `it` times."""
    n = len(w)
    e = np.concatenate([tris[:, [0, 1]], tris[:, [1, 2]], tris[:, [2, 0]]])
    e = np.unique(np.concatenate([e, e[:, ::-1]]), axis=0)
    deg = np.bincount(e[:, 0], minlength=n) + 1.0
    for _ in range(it):
        acc = w.copy()
        np.add.at(acc, e[:, 0], w[e[:, 1]])
        w = acc / deg[:, None]
    return w


def carry_maps(profile, bones):
    """{joint key: (bind point b, matrix M, carry point c, bone name)} of every joint with a bone: rig_fit carries a vertex
    of that joint to b + M (v - c) / u. M = R S: R the minimal turn of the posed segment onto the bind segment (none for the
    NO_ROT roles: the hand, foot, toe, ankle take their parent's), S the stretch along the segment when the profile has
    `stretch`, times `rscale`."""
    inst = instances(profile, bones)
    segs = segments(inst, profile)
    rot = {k: np.eye(3) for k in inst}
    for ka, kb, r in segs:
        role = ka.split("_", 1)[1] if ka[:2] in ("R_", "L_") else ka
        if role in NO_ROT:
            continue
        dp = inst[kb][0] - inst[ka][0]
        db = inst[kb][1] - inst[ka][1]
        if np.linalg.norm(db) > 1e-3:
            rot[ka] = rot_between(dp, db)
    # roles without a segment of their own inherit the parent's turn
    for k in ("head", "neck", "pelvis"):
        rot[k] = np.eye(3)
    rot = {k: v for k, v in rot.items() if inst[k][1] is not None}
    for side in ("R", "L"):
        for role, parent in (("hand", "forearm"), ("foot", "calf"), ("ankle", "calf"), ("toe", "calf")):
            if side + "_" + role in inst:
                rot[side + "_" + role] = rot[side + "_" + parent]
    stretch, girth, rscale = profile.get("stretch", False), profile.get("girth", 0.0), profile.get("rscale", {})
    out = {}
    for k in rot:
        b, c = inst[k][1], inst[k][3]
        M = rot[k].copy()
        role = k.split("_", 1)[1] if k[:2] in ("R_", "L_") else k
        if stretch and role not in NO_ROT:
            seg = next(((ka, kb) for ka, kb, r in segs if ka == k and inst[kb][1] is not None), None)
            if seg:
                dp, db = inst[seg[1]][0] - inst[seg[0]][0], inst[seg[1]][1] - inst[seg[0]][1]
                s = float(np.clip(np.linalg.norm(db) / np.linalg.norm(dp), profile.get("smin", 0.6), profile.get("smax", 1.9)))
                g = s ** girth
                d = dp / np.linalg.norm(dp)
                M = M @ (g * np.eye(3) + (s - g) * np.outer(d, d))
        if role in rscale:
            M = M * rscale[role]
        out[k] = (b, M, c, inst[k][2])
    return out


def uncarry(profile, bones, pos, bidx, wts, names, extra=None):
    """The inverse of the carry: posed positions (this module's frame, after k and dz) of bind-space vertices that fit()
    skinned (pos, bone_idx, weights, bone names as s5_build saves them). The weights blend one affine map per joint, so a
    vertex's map is affine too and is inverted exactly. extra: {bone name: joint key} for bones bound after the fit (a cap
    bone carried with the head)."""
    maps = carry_maps(profile, bones)
    by_name = {v[3]: v for v in maps.values()}
    for n, key in (extra or {}).items():
        by_name[n] = maps[key]
    u = profile["u"]
    A = np.zeros((len(pos), 3, 3))
    t = np.zeros((len(pos), 3))
    for j, n in enumerate(names):
        b, M, c, _ = by_name[n]
        w = (wts * (bidx == j)).sum(1)
        A += w[:, None, None] * (M / u)
        t += w[:, None] * (b - (M @ c) / u)
    return np.linalg.solve(A, (pos - t)[..., None])[..., 0]


def fit(profile, bones, pos, nrm, tris, soft=2.0, rigid=None):
    """rigid: {joint key ('head', 'L_hand', ...): bool mask of vertices} that follow that one joint alone (a hat, a shell)."""
    inst = instances(profile, bones)
    segs = segments(inst, profile)
    u = profile["u"]
    pos = pos * profile.get("k", 1.0) + np.array([0, 0, profile.get("dz", 0.0)])  # the mesh scaled into the unit's size
    maps = carry_maps(profile, bones)
    # weights: one column per joint instance that starts a segment; a segment gives its start joint the weight at the start
    # and its end joint the weight at the end by interpolation along the segment
    cols = []
    for ka, kb, r in segs:
        for k in (ka, kb):
            if inst[k][1] is not None and k not in cols:
                cols.append(k)
    W = np.zeros((len(pos), len(cols)))
    for ka, kb, r in segs:
        a, b = inst[ka][0], inst[kb][0]
        ab = b - a
        t = np.clip(((pos - a) @ ab) / (ab @ ab), 0, 1)
        d = np.maximum(np.linalg.norm(pos - (a + t[:, None] * ab), axis=1) - r, 0) + 0.12
        ww = 1.0 / d ** (3 * soft / 2)
        if inst[kb][1] is None:
            W[:, cols.index(ka)] += ww
        else:
            W[:, cols.index(ka)] += ww * (1 - t)
            W[:, cols.index(kb)] += ww * t
    # keep the top 4, smooth, keep the top 4 again
    for _ in range(2):
        idx = np.argsort(-W, axis=1)[:, 4:]
        np.put_along_axis(W, idx, 0, axis=1)
        W /= W.sum(1, keepdims=True)
        W = smooth(W, tris, 3)
    idx = np.argsort(-W, axis=1)[:, 4:]
    np.put_along_axis(W, idx, 0, axis=1)
    W /= W.sum(1, keepdims=True)
    for key, mask in (rigid or {}).items():
        W[mask] = 0
        W[mask, cols.index(key)] = 1
    return carry(maps, cols, W, pos, nrm, u) + (inst, cols)


def carry(maps, cols, W, pos, nrm, u):
    """Bind-space positions and normals of posed vertices with weights W over the joint keys `cols` (carry_maps), and the
    top-4 bone indices, weights and bone names that d2r_mesh writes."""
    out = np.zeros_like(pos)
    on = np.zeros_like(nrm)
    for j, k in enumerate(cols):
        b, M, c, _ = maps[k]
        moved = b + ((pos - c) / u) @ M.T
        out += W[:, [j]] * moved
        on += W[:, [j]] * (nrm @ np.linalg.inv(M))
    on /= np.linalg.norm(on, axis=1, keepdims=True) + 1e-9
    top = np.argsort(-W, axis=1)[:, :4]
    wts = np.take_along_axis(W, top, 1)
    used = sorted({int(c) for c in np.unique(top[wts > 0])})
    names = [maps[cols[c]][3] for c in used]
    remap = {c: i for i, c in enumerate(used)}
    bidx = np.vectorize(remap.get, otypes=[int])(np.where(wts > 0, top, used[0]))
    return out, on, bidx, wts, names


def main():
    a = sys.argv[1:]
    if len(a) < 3:
        print(__doc__)
        return 1
    src, prof, dst = a[:3]
    skel = a[a.index("--skeleton") + 1] if "--skeleton" in a else None
    bones = skel_info.bones(skel)
    d = np.load(src, allow_pickle=True)
    res = {}
    for lod in range(5):
        sfx = "" if lod == 0 else "_%d" % lod
        if "pos" + sfx not in d:
            continue
        out, on, bidx, wts, names, inst, cols = fit(PROFILES[prof], bones, d["pos" + sfx], d["nrm" + sfx], d["tris" + sfx])
        res["pos" + sfx], res["nrm" + sfx], res["uv" + sfx], res["tris" + sfx] = out, on, d["uv" + sfx], d["tris" + sfx]
        res["bone_idx" + sfx], res["weights" + sfx] = bidx, wts
        res["bones" + sfx] = np.array(names)
        print("lod %d: %d verts, %d bones; bind-space box %s .. %s" % (lod, len(out), len(names), out.min(0).round(2), out.max(0).round(2)))
    np.savez(dst, **res)
    if "--png" in a:
        png(a[a.index("--png") + 1], res, bones, inst)
    return 0


def png(prefix, res, bones, inst):
    from PIL import Image, ImageDraw
    P = res["pos"]
    for ax, name, xr in ((0, "front", (-9, 9)), (2, "side", (-6, 6))):
        s = 70
        yr = (0, 12)
        W, H = int((xr[1] - xr[0]) * s), int((yr[1] - yr[0]) * s)
        im = Image.new("RGB", (W, H), (25, 25, 25))
        dr = ImageDraw.Draw(im)
        X = lambda x: (x - xr[0]) * s
        Y = lambda y: H - (y - yr[0]) * s
        for p in P[::2]:
            dr.rectangle([X(p[ax]), Y(p[1]), X(p[ax]) + 1, Y(p[1]) + 1], fill=(120, 180, 255))
        for b in bones:
            if b["parent"] >= 0:
                q = bones[b["parent"]]["pos"]
                dr.line([X(q[ax]), Y(q[1]), X(b["pos"][ax]), Y(b["pos"][1])], fill=(255, 60, 60))
        im.save("%s_%s.png" % (prefix, name))


if __name__ == "__main__":
    sys.exit(main())
