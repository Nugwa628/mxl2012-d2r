"""Stage 3 finish: fill the atlas gutter (texels no triangle covers) from the nearest covered texel, in every map of an overlay.

  venv python s3_gutter.py <overlay dir> <skinned_lod0.npz> [--strip 0.125] [--name fungus] [--report <json>]

Why (round 9, Glowing Fungus): a monster about 80 px tall on screen samples its atlas at mip 3 to 4 (13x minification,
METHOD rule 4). Every mip averages a chart's border texels with the gutter next to it. The projection bake leaves the gutter
with other colours (Fungus cap: 812,860 gutter texels at albedo L 82 and cap glow 10, against L 6 and glow 0 in the dark
centre), so at game size bright blobs creep into the chart borders inside the dark cap. Filling the gutter with each chart's
own edge colours keeps the mips true. Maps: the albedo, the ORM and the glow masks (vfx/textures/.../*_glow_*_mask). The
corpse strip (the right --strip of the atlas, top --strip rows) is left as it is; only the live area is filled.
Coverage: the LOD0 triangles rasterised in the (squashed) live UV layout, row = v * height, plus one texel of margin.
"""
import json
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage as nd

sys.path.insert(0, str(Path(__file__).resolve().parents[2]))
import d2r_texture as t  # noqa: E402


def coverage(npz, size):
    z = np.load(npz)
    U, T = z["uv"], z["tris"]
    im = Image.new("L", (size, size))
    dr = ImageDraw.Draw(im)
    for tri in T:
        dr.polygon([(U[i, 0] * size, U[i, 1] * size) for i in tri], fill=1)
    return nd.binary_dilation(np.asarray(im).astype(bool), iterations=1)


def fill(path, cov_full, strip, report):
    fmt, w, h, lv = t.read_texture(path)[:4]
    a = t.decode(fmt, w, h, lv[0])
    cov = np.asarray(Image.fromarray(cov_full.astype(np.uint8) * 255).resize((w, h), Image.NEAREST)) > 127
    x0 = int(round(w * (1 - strip)))
    live = np.zeros((h, w), bool)
    live[:, :x0] = True
    hole = live & ~cov
    src = cov & live
    _, (iy, ix) = nd.distance_transform_edt(~src, return_indices=True)
    out = a.copy()
    out[hole] = a[iy[hole], ix[hole]]
    ch = out.shape[-1] if out.ndim == 3 else 1
    before = float(a[hole].astype(float).mean()) if hole.any() else 0.0
    after = float(out[hole].astype(float).mean()) if hole.any() else 0.0
    if fmt == 63:
        t.write_bc4(path, out[..., 0] if out.ndim == 3 else out, len(lv))
    else:
        t.write_bc3(path, out, mips=len(lv), linear=path.name.endswith("_orm.texture"))
    report[path.name] = {"format": fmt, "size": [w, h], "gutter_texels": int(hole.sum()), "channels": ch,
                         "gutter_mean_before": round(before, 2), "gutter_mean_after": round(after, 2)}


def main():
    a = sys.argv[1:]
    opt = lambda n, d: a[a.index(n) + 1] if n in a else d  # noqa: E731
    ov, npz = Path(a[0]) / "hd", a[1]
    strip, name = float(opt("--strip", "0.125")), opt("--name", "fungus")
    cov = coverage(npz, 2048)
    rep = {"coverage_share_2048": round(float(cov.mean()), 4)}
    maps = [ov / "character/enemy/mxl/m3d" / name / ("%s_%s.texture" % (name, k)) for k in ("alb", "orm")]
    maps += sorted((ov / "vfx/textures/mxl/m3d" / name).glob("%s_glow_*_mask.texture" % name))
    for p in maps:
        if p.is_file():
            fill(p, cov, strip, rep)
    print(json.dumps(rep))
    if "--report" in a:
        Path(opt("--report", "")).write_text(json.dumps(rep, indent=1), encoding="utf-8")


if __name__ == "__main__":
    main()
