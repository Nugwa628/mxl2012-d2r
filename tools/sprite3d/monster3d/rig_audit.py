"""Rig audit (lane rigaudit): what the skin of a stage does, in pictures and numbers. Viewer-side only, no game run.

  venv python rig_audit.py posed   [--token T] <build stage dir> <out posed.npz>
  venv python rig_audit.py sheets  [--token T] <build stage dir> <posed.npz> <out dir> [--joints joints.json] [--label r13]
  venv python rig_audit.py iou     [--token T] <build stage dir> <classic frames dir> <out json> [--modes nu,wl,a1,a2,gh,dt]
  venv python rig_audit.py stretch [--token T] <build stage dir> <out json> [--step 0.05] [--png <out dir>]

posed: the stage's skinned_lod<k>.npz hold the mesh in the donor's bind space (s5_build.py). rig_fit.fit carries each vertex
with an affine map per joint, b_j + M_j (v - c_j) / u, blended by the vertex's weights, so the blend is one affine map per
vertex and can be inverted exactly: the result is the generated mesh in its own (posed) frame, height K (the unit's game
size), for every LOD, with the stage's own vertex order (cap split copies included). Writes pos, pos_1 .. pos_4 and tris*.
It only holds for stages made by rig_fit's carry (profile `MONSTERS[token]["profile"]`); a stage made by rig_embed.py has
its posed mesh beside it (posed.npz).

sheets: PNGs of the rig: posed mesh with the posed joint table (front, side), bind mesh with the donor's bind skeleton next
to the donor's own mesh (front, side), a weight paint (each bone its colour, blended by weight) and per-bone weight maps of
the arm, leg and spine bones (posed mesh, front and back), and the bone lengths posed vs bind.

iou: per mode, the median silhouette IoU and cap (part) IoU against classic's frames over every frame and the 8 facings,
from the clips as the stage has them (viewer skinning at frame / fps; s5_clipfit's camera, calibration and part masks).

stretch: per clip, the worst sample (s5_stretch's excess, LOD0) with the excess split by bone: each stretched edge's
excess goes to the bones of its two vertices by weight. With --png, the worst sample per clip rendered with each vertex
coloured by its most stretched edge (white 1.0, red 2.0+), front and side. --ref measures the edges against the generated
mesh (posed.npz / u) instead of the bind mesh: rig_fit's bind is itself stretched, so its clips measured against the bind
understate what the mesh goes through. Cap edges are left out either way (rigid).
"""
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw, ImageFont

import common

sys.path.insert(0, str(common.WT / "tools"))
sys.path.insert(0, str(common.WT / "tools" / "sprite3d"))
import render_soft  # noqa: E402
import rig_fit  # noqa: E402
import skel_info  # noqa: E402
from hdkit.view import gr2  # noqa: E402

import s5_build  # noqa: E402

D2R = common.EV / "d2r" / "data"
BG = (28, 28, 32)
PALETTE = {  # bone name pattern -> colour (L side; R side darker)
    "pelvis": (0.85, 0.85, 0.85), "spine_01": (0.95, 0.85, 0.2), "spine_02": (0.95, 0.6, 0.15), "chest": (0.9, 0.35, 0.2),
    "neck": (0.75, 0.2, 0.6), "head": (0.55, 0.25, 0.85), "jaw": (0.35, 0.35, 0.35), "Clavicle": (0.2, 0.75, 0.75),
    "UpperArm": (0.2, 0.5, 1.0), "ForeArm": (0.3, 0.95, 0.4), "Wrist": (0.95, 0.95, 0.4), "Thigh": (1.0, 0.25, 0.25),
    "Calf": (1.0, 0.6, 0.85), "Foot": (0.6, 0.35, 0.2), "Ball": (0.9, 0.75, 0.55),
}


def bone_colour(name):
    for k, c in PALETTE.items():
        if name == k or name.endswith("_" + k):
            c = np.array(c)
            return c * 0.6 if name.startswith("R_") else c
    return np.array([0.5, 0.5, 0.5])


def cfg_profile():
    cfg = s5_build.MONSTERS[common.TOKEN]
    return cfg, rig_fit.PROFILES[cfg["profile"]]


def donor_paths(cfg):
    d = D2R / "hd/character/enemy" / cfg["donor"]
    return d, d / "skeleton" / (cfg["donor"] + ".skeleton")


def stage_lods(stage):
    return [np.load(Path(stage) / ("skinned_lod%d.npz" % k)) for k in range(5) if (Path(stage) / ("skinned_lod%d.npz" % k)).is_file()]


def cmd_posed(a):
    stage, out = Path(a[0]), Path(a[1])
    cfg, profile = cfg_profile()
    bones = skel_info.bones(donor_paths(cfg)[1])
    res = {}
    for k, d in enumerate(stage_lods(stage)):
        names = [str(x) for x in d["bones"]]
        extra = {cfg["cap_bone"]: "head"} if cfg.get("cap_bone") else None
        V = rig_fit.uncarry(profile, bones, d["pos"], d["bone_idx"], d["weights"], names, extra)
        V = (V - np.array([0, 0, profile.get("dz", 0.0)])) / profile.get("k", 1.0)
        s = "" if k == 0 else "_%d" % k
        res["pos" + s], res["tris" + s], res["uv" + s] = V, d["tris"], d["uv"]
        print("lod %d: %d vertices, posed box %s .. %s" % (k, len(V), V.min(0).round(2), V.max(0).round(2)))
    np.savez(out, **res)


# ---- drawing --------------------------------------------------------------------------------------------------------------

def tile(pos, tris, az, el, size, scale, centre, vcol=None, colour=(0.62, 0.62, 0.66), alpha=1.0):
    img = render_soft.render(pos, tris, az, el, size, scale=scale, centre=centre, vcol=vcol, colour=colour, bg=BG, lit=True)
    im = Image.fromarray(img[..., :3])
    if alpha < 1:
        im = Image.blend(Image.new("RGB", im.size, BG), im, alpha)
    return im


def proj(p, az, el, size, scale, centre):
    r, u, _ = render_soft.cam_fit.basis(az, el)
    q = np.asarray(p, float) - centre
    return size / 2 + scale * (q @ r), size / 2 - scale * (q @ u)


def draw_skeleton(im, joints, edges, az, el, scale, centre, col=(255, 60, 60), r=3, labels=False):
    dr = ImageDraw.Draw(im)
    size = im.size[0]
    for a, b in edges:
        xa, ya = proj(joints[a], az, el, size, scale, centre)
        xb, yb = proj(joints[b], az, el, size, scale, centre)
        dr.line([xa, ya, xb, yb], fill=col, width=2)
    for k, p in joints.items():
        x, y = proj(p, az, el, size, scale, centre)
        dr.ellipse([x - r, y - r, x + r, y + r], fill=(255, 255, 255), outline=col)
        if labels:
            dr.text((x + 4, y - 6), k, fill=(255, 230, 160))
    return im


def label(im, text):
    dr = ImageDraw.Draw(im)
    dr.rectangle([0, 0, im.size[0], 16], fill=(0, 0, 0))
    dr.text((4, 2), text, fill=(255, 255, 255))
    return im


def row(ims):
    w = sum(i.size[0] for i in ims)
    h = max(i.size[1] for i in ims)
    out = Image.new("RGB", (w, h), BG)
    x = 0
    for i in ims:
        out.paste(i, (x, 0))
        x += i.size[0]
    return out


def column(ims):
    w = max(i.size[0] for i in ims)
    h = sum(i.size[1] for i in ims)
    out = Image.new("RGB", (w, h), BG)
    y = 0
    for i in ims:
        out.paste(i, (0, y))
        y += i.size[1]
    return out


def skel_edges(bones, keep):
    idx = {b["name"]: b for b in bones}
    out = []
    for b in bones:
        if b["name"] not in keep:
            continue
        p = b["parent"]
        while p >= 0 and bones[p]["name"] not in keep:
            p = bones[p]["parent"]
        if p >= 0:
            out.append((bones[p]["name"], b["name"]))
    return {n: np.array(idx[n]["pos"]) for n in keep if n in idx}, out


def weight_colours(d, names):
    cols = np.array([bone_colour(n) for n in names])
    return (d["weights"][..., None] * cols[d["bone_idx"]]).sum(1)


def bone_weight(d, names, bone):
    if bone not in names:
        return np.zeros(len(d["pos"]))
    j = names.index(bone)
    return (d["weights"] * (d["bone_idx"] == j)).sum(1)


def heat(w):
    """0 -> dark blue, 0.5 -> green/yellow, 1 -> red."""
    w = np.clip(w, 0, 1)[:, None]
    lo, mid, hi = np.array([0.1, 0.12, 0.35]), np.array([0.3, 0.9, 0.2]), np.array([1.0, 0.15, 0.1])
    return np.where(w < 0.5, lo + (mid - lo) * (w / 0.5), mid + (hi - mid) * ((w - 0.5) / 0.5))


def cmd_sheets(a):
    stage, posed_npz, outdir = Path(a[0]), Path(a[1]), Path(a[2])
    opt = lambda n, dft: a[a.index(n) + 1] if n in a else dft  # noqa: E731
    lab = opt("--label", stage.name)
    outdir.mkdir(parents=True, exist_ok=True)
    cfg, profile = cfg_profile()
    donor_dir, skel = donor_paths(cfg)
    bones = skel_info.bones(skel)
    d = stage_lods(stage)[0]
    names = [str(x) for x in d["bones"]]
    posed = np.load(posed_npz)
    P = posed["pos"] * (cfg["K"] if posed["pos"][:, 1].max() < 2 else 1.0)
    tris = d["tris"]
    size, el = 520, 0.0
    # joints: rig_fit's posed table (or the embedding's), in the posed frame of P
    if "--joints" in a:
        jt = json.loads(Path(opt("--joints", "")).read_text())
        pj = {k: np.array(v) for k, v in jt["posed"].items()}
        pe = [tuple(e) for e in jt["edges"]]
    else:
        inst = rig_fit.instances(profile, bones)
        pj = {k: v[0] for k, v in inst.items()}
        pe = [(ka, kb) for ka, kb, _ in rig_fit.segments(inst, profile)]
    scale, centre = render_soft.framing(P, size, el)
    ims = []
    for az, nm in ((0, "front"), (90, "side (from its left)")):
        im = tile(P, tris, az, el, size, scale, centre, alpha=0.55)
        ims.append(label(draw_skeleton(im, pj, pe, az, el, scale, centre, labels=(az == 0)), "%s posed mesh + posed joints, %s" % (lab, nm)))
    row(ims).save(outdir / "a_posed_joints.png")
    # bind: our bind mesh + donor skeleton | donor's own mesh + skeleton
    dm, _ = gr2.load_meshes((donor_dir / "torso_lod0.model").read_bytes())
    body = max(dm, key=lambda m: len(m.pos))
    keep = set(names) | {"cog"}
    bj, be = skel_edges(bones, keep)
    B = d["pos"]
    sc, ce = render_soft.framing(np.vstack([B, body.pos]), size, el)
    ims = []
    for az, nm in ((0, "front"), (90, "side")):
        ims.append(label(draw_skeleton(tile(B, tris, az, el, size, sc, ce, vcol=weight_colours(d, names), alpha=0.6), bj, be, az, el,
                                       sc, ce, col=(255, 255, 0)), "%s bind mesh + donor bind skeleton, %s" % (lab, nm)))
        ims.append(label(draw_skeleton(tile(body.pos, body.tris, az, el, size, sc, ce, colour=(0.7, 0.62, 0.5), alpha=0.6), bj, be, az,
                                       el, sc, ce, col=(255, 255, 0)), "donor %s own mesh, %s" % (cfg["donor"], nm)))
    row(ims).save(outdir / "b_bind_vs_donor.png")
    # weight paint
    wc = weight_colours(d, names)
    ims = [label(tile(P, tris, az, el, size, scale, centre, vcol=wc), "%s weights (bone colours), az %d" % (lab, az)) for az in (0, 90, 180, 270)]
    leg = Image.new("RGB", (190, size), BG)
    dr = ImageDraw.Draw(leg)
    for i, n in enumerate(names):
        c = tuple(int(255 * x) for x in bone_colour(n))
        dr.rectangle([6, 6 + i * 20, 22, 20 + i * 20], fill=c)
        dr.text((28, 7 + i * 20), n, fill=(230, 230, 230))
    row(ims + [leg]).save(outdir / "c_weight_paint.png")
    # per-bone heat maps
    groups = [("L_UpperArm", "L_ForeArm", "L_Wrist", "L_Clavicle"), ("R_UpperArm", "R_ForeArm", "R_Wrist", "R_Clavicle"),
              ("L_Thigh", "L_Calf", "R_Thigh", "R_Calf"), ("pelvis", "spine_01", "spine_02", "chest")]
    sm = 300
    s2, c2 = render_soft.framing(P, sm, el)
    rows = []
    for g in groups:
        cells = []
        for bn in g:
            w = bone_weight(d, names, bn)
            for az in (0, 180):
                cells.append(label(tile(P, tris, az, el, sm, s2, c2, vcol=heat(w)), "%s az%d (n>0.5: %d)" % (bn, az, int((w > 0.5).sum()))))
        rows.append(row(cells))
    column(rows).save(outdir / "d_bone_weights.png")
    # bone lengths posed vs bind
    rep = {}
    inst = rig_fit.instances(profile, bones)
    for ka, kb, _ in rig_fit.segments(inst, profile):
        if inst[kb][1] is None:
            continue
        rep[ka + "->" + kb] = {"posed": round(float(np.linalg.norm(inst[kb][0] - inst[ka][0])), 3),
                               "bind": round(float(np.linalg.norm(inst[kb][1] - inst[ka][1])), 3)}
    (outdir / "bone_lengths.json").write_text(json.dumps(rep, indent=1))
    print("sheets in", outdir)


# ---- stretch by bone --------------------------------------------------------------------------------------------------------

def stretch_by_bone(overlay, step=0.05, part_bone="jaw", png=None, label_="", shell_bone="loin_cloth", ref=None):
    """ref: (N_body, 3) reference positions of the first vertices (the original posed mesh / u) instead of the bind."""
    d = next(Path(overlay).glob("hd/character/enemy/mxl/m3d/*"))
    meshes, sk = gr2.load_meshes((d / "torso_lod0.model").read_bytes())
    clips = gr2.load_clips((d / "animation" / "combined.animations").read_bytes(), sk)
    m = max((x for x in meshes if x.joints is not None), key=lambda x: len(x.pos))
    pb = m.bones.index(part_bone) if part_bone in m.bones else -1
    body = ~((m.joints[:, 0] == pb) & (m.weights[:, 0] > 0.99)) if pb >= 0 else np.ones(len(m.pos), bool)
    E = np.vstack([m.tris[:, [0, 1]], m.tris[:, [1, 2]], m.tris[:, [2, 0]]])
    E.sort(1)
    E = np.unique(E, axis=0)
    E = E[body[E[:, 0]] & body[E[:, 1]]]
    R = m.pos
    if ref is not None:
        E = E[(E < len(ref)).all(1)]
        R = ref
    lb = np.linalg.norm(R[E[:, 0]] - R[E[:, 1]], axis=1)
    ok = lb > 1e-5
    E, lb = E[ok], lb[ok]
    nb = len(m.bones)
    Wfull = np.zeros((len(m.pos), nb))
    for k in range(4):
        np.add.at(Wfull, (np.arange(len(m.pos)), m.joints[:, k]), m.weights[:, k])
    out = {}
    for name, clip in clips.items():
        if name == "dead":
            continue
        worst = None
        for t in np.arange(0, clip.duration + 1e-6, step):
            pose = gr2.pose_at(sk, clip, float(t))
            Pp, _n, _t = gr2.skin(m, sk, pose)
            lp = np.linalg.norm(Pp[E[:, 0]] - Pp[E[:, 1]], axis=1)
            ex = np.maximum(lp - 1.5 * lb, 0)
            if worst is None or ex.sum() > worst[0]:
                worst = (float(ex.sum()), float(t), lp / lb, ex, Pp)
        tot, t, ratio, ex, Pp = worst
        per = 0.5 * (Wfull[E[:, 0]] + Wfull[E[:, 1]]) * ex[:, None]
        per = per.sum(0)
        top = np.argsort(-per)[:6]
        out[name] = {"excess": round(tot, 2), "t": round(t, 3), "p999": round(float(np.percentile(ratio, 99.9)), 3),
                     "over1_5": round(float((ratio > 1.5).mean()), 5),
                     "by_bone": {m.bones[i]: round(float(per[i]), 2) for i in top if per[i] > 0.05}}
        if png:
            vr = np.ones(len(m.pos))
            np.maximum.at(vr, E[:, 0], ratio)
            np.maximum.at(vr, E[:, 1], ratio)
            s = np.clip(vr - 1.0, 0, 1)[:, None]
            vc = np.array([0.85, 0.85, 0.85]) * (1 - s) + np.array([1.0, 0.1, 0.05]) * s
            vc[~body] = (0.3, 0.3, 0.45)
            sb = m.bones.index(shell_bone) if shell_bone in m.bones else -1
            live = ~((m.joints[:, 0] == sb) & (m.weights[:, 0] > 0.99)) if sb >= 0 else np.ones(len(m.pos), bool)
            tl = m.tris[live[m.tris].all(1)]
            sc, ce = render_soft.framing(Pp[live], 340, 0.0)
            ims = [label(tile(Pp, tl, az, 0.0, 340, sc, ce, vcol=vc), "%s %s t=%.2f ex %.1f az%d" % (label_, name, t, tot, az))
                   for az in (0, 90, 180)]
            Path(png).mkdir(parents=True, exist_ok=True)
            row(ims).save(Path(png) / ("stretch_%s.png" % name))
    return out


def cmd_stretch(a):
    opt = lambda n, dft: a[a.index(n) + 1] if n in a else dft  # noqa: E731
    stage = Path(a[0])
    ov = stage / "overlay" if (stage / "overlay").is_dir() else stage
    ref = None
    if "--ref" in a:          # the original posed mesh (rig_audit posed / rig_embed's input), / u: edges against the mesh as generated
        cfg, profile = cfg_profile()
        p = np.load(opt("--ref", ""))["pos"]
        ref = p * (cfg["K"] if p[:, 1].max() < 2 else 1.0) / profile["u"]
    res = stretch_by_bone(ov, float(opt("--step", "0.05")), png=opt("--png", None), label_=opt("--label", stage.name), ref=ref)
    print(json.dumps(res, indent=1))
    Path(a[1]).write_text(json.dumps(res, indent=1))


def stage_iou(stage, frames_dir, modes, part_bone="jaw", shell_bone="loin_cloth", every=1):
    """Per mode: median silhouette IoU and part IoU against classic over frames x 8 facings, from the clips written in the
    stage (sampled at frame / fps with the viewer's skinning, LOD0), camera and masks of s5_clipfit.Target."""
    import s5_clipfit as cf
    stage = Path(stage)
    d = next((stage / "overlay").glob("hd/character/enemy/mxl/m3d/*"))
    meshes, sk = gr2.load_meshes((d / "torso_lod0.model").read_bytes())
    clips = gr2.load_clips((d / "animation" / "combined.animations").read_bytes(), sk)
    m = max((x for x in meshes if x.joints is not None), key=lambda x: len(x.pos))
    pb, sb = m.bones.index(part_bone), (m.bones.index(shell_bone) if shell_bone in m.bones else -1)
    part = (m.joints[:, 0] == pb) & (m.weights[:, 0] > 0.99)
    shell = (m.joints[:, 0] == sb) & (m.weights[:, 0] > 0.99) if sb >= 0 else np.zeros(len(m.pos), bool)
    body_i, part_i = np.nonzero(~part & ~shell)[0][::4], np.nonzero(part)[0][::3]
    rig = cf.Rig(stage)
    out = {}
    for mode in modes:
        tg = cf.Target(rig, frames_dir, mode)
        clip = clips[dict(cf.CFG["clip_names"], dt="death")[mode]]
        ious, pious = [], []
        for i in range(0, tg.n, every):
            t = min(i / tg.fps, clip.duration)
            P, _n, _t = gr2.skin(m, sk, gr2.pose_at(sk, clip, t, loop=mode in cf.mcfg().get("loop", [])))
            for dd in cf.DIRS:
                sil, pm = tg.sil[dd, i], tg.part[dd, i]
                bx, by = tg.proj(P[body_i], dd)
                px, py = tg.proj(P[part_i], dd)
                ours_p = cf.splat(px, py, sil.shape)
                ours = cf.splat(bx, by, sil.shape) | ours_p
                ious.append(cf.iou(ours, sil))
                if tg.part_ok[dd, i]:
                    pious.append(cf.iou(ours_p, pm))
        out[mode] = {"iou": round(float(np.median(ious)), 3), "part_iou": round(float(np.median(pious)), 3) if pious else None,
                     "frames": tg.n, "samples": len(ious)}
    return out


def cmd_iou(a):
    opt = lambda n, dft: a[a.index(n) + 1] if n in a else dft  # noqa: E731
    res = stage_iou(a[0], a[1], opt("--modes", "nu,wl,a1,a2,gh,dt").split(","))
    print(json.dumps(res, indent=1))
    Path(a[2]).write_text(json.dumps(res, indent=1))


def main():
    a = sys.argv[1:]
    cmds = {"posed": cmd_posed, "sheets": cmd_sheets, "stretch": cmd_stretch, "iou": cmd_iou}
    if not a or a[0] not in cmds:
        print(__doc__)
        return 1
    cmds[a[0]](a[1:])
    return 0


if __name__ == "__main__":
    sys.exit(main())
