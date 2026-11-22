"""Skinning check of a stage (round 13, Glowing Fungus): how far the posed mesh's edges stretch from the bind pose.

  python s5_stretch.py <stage overlay dir> [--clips neutral,walk,...] [--step 0.05] [--json <out>] [--part-bone jaw]

Every clip of the stage's combined.animations is sampled every --step seconds with hdkit.view's own pose and skin code
(what the viewer and the web bundle draw), on LOD0. Per sample: each triangle edge's posed length over its bind length.
A limb smear (round 12's NU: one leg pulled into a long pale streak) shows as edges stretched far beyond 1. Reported
per clip, for the sample with the most excess length (sum over body edges of max(0, posed - 1.5 x bind), model units:
many tiny edges stretched a little count little, a long smear counts a lot): that excess, the p99.9 and max ratio, and
the share of body edges above 1.5 and 2.0 (the part bone's
vertices, the cap, are left out: they are rigid).
"""
import json
import sys
from pathlib import Path

import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
from hdkit.view import gr2  # noqa: E402


def load(overlay):
    d = next(Path(overlay).glob("hd/character/enemy/mxl/m3d/*"))
    meshes, sk = gr2.load_meshes((d / "torso_lod0.model").read_bytes())
    clips = gr2.load_clips((d / "animation" / "combined.animations").read_bytes(), sk)
    return meshes, sk, clips


def edges(tris):
    e = np.vstack([tris[:, [0, 1]], tris[:, [1, 2]], tris[:, [2, 0]]])
    e.sort(1)
    return np.unique(e, axis=0)


def check(overlay, names=None, step=0.05, part_bone="jaw"):
    meshes, sk, clips = load(overlay)
    out = {}
    for name, clip in clips.items():
        if names and name not in names:
            continue
        worst = None
        for t in np.arange(0, clip.duration + 1e-6, step):
            pose = gr2.pose_at(sk, clip, float(t))
            ratios, excess = [], []
            for m in meshes:
                if m.joints is None:
                    continue
                pb = m.bones.index(part_bone) if part_bone in m.bones else -1
                body = ~((m.joints[:, 0] == pb) & (m.weights[:, 0] > 0.99)) if pb >= 0 else np.ones(len(m.pos), bool)
                E = edges(m.tris)
                E = E[body[E[:, 0]] & body[E[:, 1]]]
                P, _n, _t = gr2.skin(m, sk, pose)
                lb = np.linalg.norm(m.pos[E[:, 0]] - m.pos[E[:, 1]], axis=1)
                lp = np.linalg.norm(P[E[:, 0]] - P[E[:, 1]], axis=1)
                ok = lb > 1e-5
                ratios.append(lp[ok] / lb[ok])
                excess.append(np.maximum(lp - 1.5 * lb, 0))
            r = np.concatenate(ratios)
            ex = float(np.concatenate(excess).sum())
            row = {"excess": round(ex, 2), "t": round(float(t), 3), "p999": round(float(np.percentile(r, 99.9)), 3), "max": round(float(r.max()), 2),
                   "over1_5": round(float((r > 1.5).mean()), 5), "over2": round(float((r > 2.0).mean()), 5)}
            if worst is None or row["excess"] > worst["excess"]:
                worst = row
        out[name] = {"duration": round(clip.duration, 3), "worst": worst}
    return out


def main():
    a = sys.argv[1:]
    opt = lambda n, d: a[a.index(n) + 1] if n in a else d  # noqa: E731
    names = opt("--clips", None)
    res = check(a[0], names.split(",") if names else None, float(opt("--step", "0.05")), opt("--part-bone", "jaw"))
    print(json.dumps(res, indent=1))
    if "--json" in a:
        Path(opt("--json", "")).write_text(json.dumps(res, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
