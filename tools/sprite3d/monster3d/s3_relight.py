"""Stage 3b: take the classic sprite's baked shading out of a projected albedo, so the engine's own light does not darken it twice.

  venv python s3_relight.py <albedo.png> <part.png> <coverage.png> <lit frames dir> <out.png> [--mix 0.5] [--cap-gamma 0.7]
                            [--cap-dark 18,48] [--body-gamma 1.0] [--report <json>]

Why: the classic frames are pictures of a lit model. On the standing frames most of a body faces sideways, away from the light
from above, so the projected albedo holds that shadow (the Glowing Fungus: 63 % of the body pixels below 40 of 255 luminance) and
D2R's light then darkens it a second time. The frames where the body lies on the ground (the corpse frame DD, the end of the death
DT) show the same skin facing the light: there it is pale.

What it does:
- body (outside part.png): each texel's luminance is moved to the same rank in the luminance spread of the lit reference pixels
  (the `<lit frames dir>` PNGs: every opaque pixel that is not the part by colour, i.e. blue minus red under 100 and luminance
  over 20), so the order of light and dark texels (the detail) stays and the level becomes that of the lit skin. The colour is
  the texel's own chroma mixed with the reference's mean chroma by --mix. --body-gamma under 1 then lifts that level
  (luminance out = 255 (L/255)^g): the reference is a lit sprite, so its level is what a lit surface showed, and D2R's light
  falls off on the sides of the mesh as well (Glowing Fungus: 0.4, reference median 76 -> 157; blue-grey in game at night).
- part (the cap): mid tones are lifted by --cap-gamma (luminance out = 255 (L/255)^g) with a smooth ramp between the two
  --cap-dark levels, so the darkest centre stays dark and the blue band around it opens up.
Texels no view saw (coverage 0) are treated like the others: they were filled from seen neighbours.
"""
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image


def lum(c):
    return 0.2126 * c[..., 0] + 0.7152 * c[..., 1] + 0.0722 * c[..., 2]


def smoothstep(a, b, x):
    t = np.clip((x - a) / (b - a), 0, 1)
    return t * t * (3 - 2 * t)


def reference(folder: Path) -> np.ndarray:
    px = []
    for p in sorted(folder.glob("*.png")):
        a = np.asarray(Image.open(p).convert("RGBA")).astype(np.float32)
        q = a[a[..., 3] > 200][:, :3]
        px.append(q[((q[:, 2] - q[:, 0]) < 100) & (lum(q) > 20)])
    return np.vstack(px)


def main():
    a = sys.argv[1:]
    opt = lambda n, d: a[a.index(n) + 1] if n in a else d  # noqa: E731
    alb = np.asarray(Image.open(a[0]).convert("RGB")).astype(np.float32)
    size = alb.shape[1::-1]
    part = np.asarray(Image.open(a[1]).convert("L").resize(size, Image.BILINEAR)) > 127
    ref = reference(Path(a[3]))
    mix, cap_g = float(opt("--mix", "0.5")), float(opt("--cap-gamma", "0.7"))
    d0, d1 = (float(v) for v in opt("--cap-dark", "18,48").split(","))
    body_g = float(opt("--body-gamma", "1.0"))
    out = alb.copy()
    L = lum(alb)

    # body: rank of each texel's luminance -> the same quantile of the lit reference
    body = ~part
    lb = L[body]
    rank = np.argsort(np.argsort(lb, kind="stable"), kind="stable") / max(len(lb) - 1, 1)
    lr = np.sort(lum(ref))
    lt = np.interp(rank, np.linspace(0, 1, len(lr)), lr)
    lt = 255.0 * (np.clip(lt, 0, 255) / 255.0) ** body_g
    own = alb[body] / np.maximum(lb, 1.0)[:, None]                   # chroma: colour per unit of luminance
    refc = ref.mean(0) / max(lum(ref.mean(0)), 1.0)
    chroma = (1 - mix) * own + mix * refc
    chroma /= np.maximum(lum(chroma), 1e-6)[:, None]
    out[body] = chroma * lt[:, None]

    # cap: open the mid tones, keep the dark centre
    lc = L[part]
    lift = 255.0 * (np.clip(lc, 0, 255) / 255.0) ** cap_g
    w = smoothstep(d0, d1, lc)
    lnew = (1 - w) * lc + w * lift
    out[part] = alb[part] * (lnew / np.maximum(lc, 1.0))[:, None]

    out = np.clip(out, 0, 255)
    Image.fromarray(out.round().astype(np.uint8)).save(a[4])

    def st(x):
        y = lum(x)
        return {"mean_rgb": [round(float(v), 1) for v in x.mean(0)], "L_p25_p50_p75_p90": [round(float(v), 1) for v in np.percentile(y, [25, 50, 75, 90])],
                "frac_L_below_40": round(float((y < 40).mean()), 3)}
    rep = {"reference_pixels": int(len(ref)), "reference": st(ref), "body_before": st(alb[body]), "body_after": st(out[body]),
           "cap_before": st(alb[part]), "cap_after": st(out[part]), "mix": mix, "body_gamma": body_g, "cap_gamma": cap_g, "cap_dark": [d0, d1]}
    print(json.dumps(rep, indent=1))
    if "--report" in a:
        Path(opt("--report", "")).write_text(json.dumps(rep, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
