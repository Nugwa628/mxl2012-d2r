"""Stage 3c: more surface detail than the classic sprite gives, by estimation. Writes one folder per option and a close-up sheet.

  venv python s3_detail.py make <albedo.png> <part.png> <out dir> [--esrgan <realesrgan-ncnn-vulkan program>] [--seed 7]
  venv python s3_detail.py sheet <out.png> <bake dir> <cams.json> "<label>=<albedo.png>[|<normal.png>]" [...] [--views 4,0] [--zoom 4]
        [--ref "<label>=<bake dir>|<albedo.png>"]

`make` takes the relit albedo of s3_relight.py (2048^2, the UV atlas of project_texture.py) and writes, each with albedo.png,
normal.png (tangent space, RGB, +x = +u, +y = +v, v down like the atlas rows) and lit.png (the albedo shaded by its normal map
under a light from the upper left in tangent space, for the sheet only):
- a_sfs: shape from shading. Height = the band-pass of the albedo's luminance (bright = raised, dark = sunk: the sprite's
  painter shaded pits dark), normal from its gradient. The albedo stays as it is.
- b_proc: colour-following procedural detail at 4096^2. Body: pores (small dark pits from a thresholded fine noise) and a
  two-octave grain, amplitude scaled by the local luminance; cap: small specks of the local colour lifted toward pale blue
  where the cap is blue (the rim), a fine grain on the dark centre. The same fields give the height, plus a_sfs's band.
- c_esrgan: Real-ESRGAN x4plus (ncnn Vulkan build, local) on the atlas, 8192^2 brought down to 4096^2 (Lanczos); normal by
  a_sfs's method from the result.
(The fourth option, a bake at 4096^2 from the 8 x4 sprite views, is project_texture.py --size 4096 and s3_relight.py.)

`sheet` renders each albedo (lit by its normal map in the preview sense above, otherwise unlit) through the fitted sprite
cameras `--views`, `--zoom` times the x4 view size, and crops the cap rim and the body; the classic frame (nearest) and the
x4 upscaled view are the first columns.
"""
import json
import subprocess
import sys
from pathlib import Path

import numpy as np
from PIL import Image, ImageDraw
from scipy import ndimage as ndi

import common

sys.path.insert(0, str(common.WT / "tools" / "sprite3d"))
import render_soft  # noqa: E402
import cam_fit  # noqa: E402

LIGHT = np.array([-0.45, -0.45, 0.77])          # tangent space: from the upper left (v runs down the atlas)
LIGHT = LIGHT / np.linalg.norm(LIGHT)


def lum(c):
    return 0.2126 * c[..., 0] + 0.7152 * c[..., 1] + 0.0722 * c[..., 2]


def smoothstep(a, b, x):
    t = np.clip((x - a) / (b - a), 0, 1)
    return t * t * (3 - 2 * t)


def band(L, lo, hi):
    return ndi.gaussian_filter(L, lo) - ndi.gaussian_filter(L, hi)


def normal_from_height(h, strength):
    gy, gx = np.gradient(h)
    n = np.dstack([-strength * gx, -strength * gy, np.ones_like(h)])
    return n / np.linalg.norm(n, axis=2, keepdims=True)


def encode_normal(n):
    return np.round((n * 0.5 + 0.5) * 255).astype(np.uint8)


def lit(alb, n):
    """Preview only: albedo x (0.55 + 0.45 n.l) / (0.55 + 0.45 l_z), so a flat normal leaves the albedo as it is."""
    s = (0.55 + 0.45 * np.clip(n @ LIGHT, 0, 1)) / (0.55 + 0.45 * LIGHT[2])
    return np.clip(alb * s[..., None], 0, 255).astype(np.uint8)


def value_noise(shape, cell, rng):
    gh, gw = shape[0] // cell + 2, shape[1] // cell + 2
    g = rng.random((gh, gw)).astype(np.float32)
    return ndi.zoom(g, cell, order=3)[:shape[0], :shape[1]]


def sfs_height(alb):
    L = lum(alb.astype(np.float32)) / 255
    return band(L, 0.7, 6.0)


def make(a):
    alb = np.asarray(Image.open(a[1]).convert("RGB")).astype(np.float32)
    part = np.asarray(Image.open(a[2]).convert("L").resize(alb.shape[1::-1], Image.BILINEAR)) > 127
    out = Path(a[3])
    seed = int(a[a.index("--seed") + 1]) if "--seed" in a else 7
    report = {}

    def save(name, albedo, n, extra):
        d = out / name
        d.mkdir(parents=True, exist_ok=True)
        Image.fromarray(albedo.astype(np.uint8)).save(d / "albedo.png")
        Image.fromarray(encode_normal(n)).save(d / "normal.png")
        Image.fromarray(lit(albedo.astype(np.float32), n)).save(d / "lit.png")
        tilt = np.degrees(np.arccos(np.clip(n[..., 2], -1, 1)))
        report[name] = {"albedo_px": list(albedo.shape[:2]), "normal_px": list(n.shape[:2]),
                        "tilt_deg_p50_p90_p99": [round(float(np.percentile(tilt, p)), 1) for p in (50, 90, 99)], **extra}
        print(name, json.dumps(report[name]), flush=True)

    # a: shape from shading on the atlas as it is
    h = sfs_height(alb)
    save("a_sfs", alb, normal_from_height(h, 9.0), {"height": "band-pass 0.7..6 texels of the luminance", "strength": 9.0})

    # b: colour-following procedural detail at 4096
    big = np.asarray(Image.fromarray(alb.astype(np.uint8)).resize((4096, 4096), Image.LANCZOS)).astype(np.float32)
    pb = np.asarray(Image.fromarray(part.astype(np.uint8) * 255).resize((4096, 4096), Image.BILINEAR)) > 127
    rng = np.random.default_rng(seed)
    L = lum(big) / 255
    fine, mid, coarse = value_noise(pb.shape, 3, rng), value_noise(pb.shape, 7, rng), value_noise(pb.shape, 19, rng)
    grain = (fine - 0.5) * 0.6 + (mid - 0.5) * 0.4
    pores = smoothstep(0.80, 0.93, value_noise(pb.shape, 4, rng)) * smoothstep(0.35, 0.65, coarse)
    blue = smoothstep(90, 200, big[..., 2]) * smoothstep(25, 80, big[..., 2] - big[..., 0])
    specks = smoothstep(0.84, 0.95, value_noise(pb.shape, 3, rng)) * blue
    amp = 0.35 + 0.65 * L                                       # detail is weaker in the dark parts, as on the sprite
    body_mul = 1 + 0.10 * grain * amp - 0.08 * pores * amp    # 0.22 read as dirt on the sheet
    cap_mul = 1 + 0.06 * grain
    mul = np.where(pb, cap_mul, body_mul)
    pale = np.array([175, 215, 255], np.float32)
    outb = big * mul[..., None]
    outb = outb + (pale - outb) * (0.55 * specks)[..., None] * pb[..., None]
    outb = np.clip(outb, 0, 255)
    hb = np.where(pb, 0.6 * specks + 0.08 * grain, 0.12 * grain - 0.35 * pores) * 0.05
    hb = hb + ndi.zoom(h, 2, order=1)
    save("b_proc", outb, normal_from_height(hb, 9.0),
         {"seed": seed, "pore_cover": round(float((pores[~pb] > 0.5).mean()), 4),
          "speck_cover_on_cap": round(float((specks[pb] > 0.5).mean()), 4)})

    # c: Real-ESRGAN x4plus on the atlas
    if "--esrgan" in a:
        exe = Path(a[a.index("--esrgan") + 1])
        src, dst = (out / "c_in.png").resolve(), (out / "c_x4.png").resolve()
        Image.fromarray(alb.astype(np.uint8)).save(src)
        r = subprocess.run([str(exe), "-i", str(src), "-o", str(dst), "-n", "realesrgan-x4plus", "-s", "4", "-t", "256"],
                           cwd=exe.parent, capture_output=True, text=True)
        if r.returncode != 0 or not dst.is_file():
            raise SystemExit("esrgan failed: %s %s" % (r.returncode, r.stderr[-400:]))
        x4 = np.asarray(Image.open(dst).convert("RGB").resize((4096, 4096), Image.LANCZOS)).astype(np.float32)
        hc = band(lum(x4) / 255, 1.4, 12.0)
        save("c_esrgan", x4, normal_from_height(hc, 9.0), {"model": "realesrgan-x4plus (ncnn)", "x4_px": 8192})
        dst.unlink()
        src.unlink()
    (out / "detail.json").write_text(json.dumps(report, indent=1), encoding="utf-8")


def through(cam, d, tex, zoom):
    c2 = dict(cam, s=cam["s"] * zoom, w=cam["w"] * zoom, h=cam["h"] * zoom, tx=cam["tx"] * zoom, ty=cam["ty"] * zoom)
    S = max(c2["w"], c2["h"]) + 64
    r, u, _ = cam_fit.basis(c2["az"], c2["el"])
    ctr = (np.array([0, c2["yoff"], 0]) + (S / 2 - c2["tx"] - 32) / c2["s"] * r
           + (c2["ty"] + 32 - S / 2) / (c2["s"] * c2["ky"]) * u)
    img = render_soft.render(d["pos"], d["tris"], c2["az"], c2["el"], S, c2["s"], ctr, uv=d["uv"], tex=tex, ky=c2["ky"],
                             lit=True, ss=1)
    return img[32:32 + c2["h"], 32:32 + c2["w"]]


def sheet(a):
    out, bake, cams = Path(a[1]), Path(a[2]), json.load(open(a[3]))["cams"]
    zoom = int(a[a.index("--zoom") + 1]) if "--zoom" in a else 4
    views = [int(x) for x in (a[a.index("--views") + 1] if "--views" in a else "4,0").split(",")]
    specs = [x for x in a[4:] if "=" in x and not x.startswith("--")]
    refs = [a[i + 1] for i, x in enumerate(a) if x == "--ref"]
    specs = [s for s in specs if s not in refs]
    d0 = np.load(bake / "mesh_uv.npz")
    BG = np.array([40, 40, 48], np.float32)
    cols = []        # (label, [tile per view])

    def over(t):
        al = t[..., 3:].astype(np.float32) / 255
        return (t[..., :3] * al + BG * (1 - al)).astype(np.uint8)

    xv = common.STAGES / "1-frames" / "x4" / "nu00"
    cl = [np.asarray(Image.open(common.STAGES / "1-frames" / "classic" / "nu" / ("d%d_f00.png" % v)).convert("RGBA")) for v in views]
    up = [np.asarray(Image.open(xv / ("nu_d%d.png" % v)).convert("RGBA")) for v in views]
    sz = [(u.shape[1] * zoom, u.shape[0] * zoom) for u in up]
    cols.append(("classic (nearest)", [over(np.asarray(Image.fromarray(c).resize(s, Image.NEAREST))) for c, s in zip(cl, sz)]))
    cols.append(("sprite x4 (card)", [over(np.asarray(Image.fromarray(u).resize(s, Image.LANCZOS))) for u, s in zip(up, sz)]))
    for spec in refs + specs:
        label, rest = spec.split("=", 1)
        parts = rest.split("|")
        if spec in refs:
            d, tex_path = np.load(Path(parts[0]) / "mesh_uv.npz"), parts[1]
        else:
            d, tex_path = d0, parts[0]
        tex = np.asarray(Image.open(tex_path).convert("RGB")).astype(np.float32)
        tiles = [over(through(cams[str(v)], d, tex, zoom)) for v in views]
        cols.append((label, tiles))
        print("rendered", label, flush=True)
    # crops: cap rim (upper third) and body (middle) of each view, same box for every column
    rows = []
    for k, v in enumerate(views):
        H, W = cols[0][1][k].shape[:2]
        boxes = [("cap rim d%d" % v, (int(W * 0.08), int(H * 0.10), int(W * 0.92), int(H * 0.42))),
                 ("body d%d" % v, (int(W * 0.25), int(H * 0.42), int(W * 0.75), int(H * 0.80)))]
        for name, box in boxes:
            rows.append((name, [Image.fromarray(c[1][k]).crop(box) for c in cols]))
    cw = 420
    pad, top = 6, 26
    tiles = []
    for name, row in rows:
        tiles.append((name, [t.resize((cw, int(t.height * cw / t.width)), Image.LANCZOS) for t in row]))
    total_h = top + sum(max(t.height for t in r) + pad + 18 for _, r in tiles)
    S = Image.new("RGB", (len(cols) * (cw + pad) + pad, total_h), (24, 24, 28))
    dr = ImageDraw.Draw(S)
    for i, (label, _) in enumerate(cols):
        dr.text((pad + i * (cw + pad), 6), label, fill=(235, 235, 235))
    y = top
    for name, r in tiles:
        dr.text((pad, y), name, fill=(200, 200, 160))
        y += 16
        for i, t in enumerate(r):
            S.paste(t, (pad + i * (cw + pad), y))
        y += max(t.height for t in r) + pad + 2
    out.parent.mkdir(parents=True, exist_ok=True)
    S.save(out)
    print(out, S.size)


if __name__ == "__main__":
    args = sys.argv[1:]
    {"make": make, "sheet": sheet}[args[0]](args)
